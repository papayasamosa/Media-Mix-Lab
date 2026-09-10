"""Outcome valuation reporting service - orchestrates historical Results
economic reporting (WP2D-ui: REQ-ECON-002 through REQ-ECON-004) without
Streamlit dependencies.

Composes, in this exact order: `core.outcome_valuation_periods` (resolve
which already-fitted weeks a requested reporting period covers),
`core.outcome_valuation_reporting` (per-draw posterior incremental
outcome and attributable spend for those weeks), `core.
outcome_valuation_rates.derive_weekly_value_rates` (fixed weekly
value-per-outcome rates from the governed valuation catalogue), and
`core.outcome_valuation_attribution.summarize_posterior_economic_
attribution` (the draw-level value join, aggregation, and posterior
summary). This is the exact sequence REQ-ECON-003 requires - the join
happens at draw level, at the weekly grain, strictly before any
temporal aggregation, never a shortcut that multiplies a pre-summed
total by an average rate.

This service is deliberately agnostic to the Total/Product/Segment/
Funnel/Channel reporting-dimension vocabulary the Results page presents
- it only ever takes an explicit `outcome_ids`/`segment`/`channel`
selection and reports on exactly that slice. Resolving which dimension
choices are genuinely eligible (and disclosing the ones that are not) is
the page's job; this service does not know or care which UI dimension a
given `(outcome_ids, segment, channel)` combination came from.

Fails closed - returns `errors`, never a fabricated result - whenever
the requested period resolves to no weeks, or any resolved week has no
governed valuation-rate coverage. Never silently drops a week, never
substitutes a nearby rate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ancestry_mmm.application.fx_service import (
    FXUploadValidationError,
    resolve_approved_fx_rate,
)
from ancestry_mmm.core.fx_rates import FXRateRecord, FXRateSet
from ancestry_mmm.core.hierarchical_model import FHModelMeta
from ancestry_mmm.core.outcome_valuation import WeeklyOutcomeValuationRecord
from ancestry_mmm.core.outcome_valuation_attribution import (
    PosteriorEconomicAttribution,
    summarize_posterior_economic_attribution,
)
from ancestry_mmm.core.outcome_valuation_periods import resolve_weeks_for_grain
from ancestry_mmm.core.outcome_valuation_rates import derive_weekly_value_rates
from ancestry_mmm.core.outcome_valuation_reporting import (
    DEFAULT_REPORTING_N_PERMUTATIONS,
    attributable_spend,
    available_weeks_for_market,
    extract_incremental_outcome_draws,
    observed_denominator_counts_frame,
)
from ancestry_mmm.core.uncertainty import DEFAULT_CRED_MASS, DEFAULT_N_DRAWS


@dataclass
class HistoricalOutcomeValuationRequest:
    """Typed input for one historical outcome-valuation report. Identity
    fields (`market`, `valuation_kind`, `segment`, `outcome_ids`) are
    explicit - never inferred from `meta`."""

    market: str
    grain: str
    trace: Any
    frame: Dict
    meta: FHModelMeta
    outcome_ids: Sequence[str]
    segment: str
    valuation_kind: str
    weekly_valuation_records: Sequence[WeeklyOutcomeValuationRecord]
    channel: Optional[str] = None
    period_label: Optional[str] = None
    custom_range_start: Optional[str] = None
    custom_range_end: Optional[str] = None
    n_draws: int = DEFAULT_N_DRAWS
    n_permutations: int = DEFAULT_REPORTING_N_PERMUTATIONS
    seed: int = 42
    credible_mass: float = DEFAULT_CRED_MASS
    # UK FH MMM brief (2026-09-10), Workstream A/F: `attributable_spend` is
    # in the market's native media-input currency, which may differ from
    # the governed valuation catalogue's `currency`. `spend_currency` is
    # never inferred from `market` - the caller (the Results page, from
    # governed market/channel currency configuration) supplies it
    # explicitly, or leaves it `None` when unknown/not yet governed, in
    # which case no conversion is attempted (existing single-currency
    # behaviour is unchanged). When `spend_currency` differs from the
    # valuation catalogue's currency, resolving an approved rate reuses
    # `application.fx_service.resolve_approved_fx_rate` - the same
    # approval-status/fingerprint-checked, as-of-date lookup Official Curve
    # Generation already uses for monetary curves - never a second,
    # parallel FX-lookup mechanism. `fx_rate_set`/`fx_rate_records` are the
    # project's governed Finance FX upload; `fx_as_of_date` mirrors that
    # page's own "FX as-of date" input (defaults to the period's last
    # resolved week when not supplied).
    spend_currency: Optional[str] = None
    fx_rate_set: Optional[Mapping[str, Any]] = None
    fx_rate_records: Sequence[Any] = ()
    fx_as_of_date: Optional[str] = None


@dataclass
class HistoricalOutcomeValuationResult:
    """Structured historical outcome-valuation reporting output."""

    attribution: Optional[PosteriorEconomicAttribution] = None
    resolved_weeks: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class MetricComparison:
    """One metric's Period A vs Period B comparison (WP2E).

    `percentage_change` is `None` whenever Period A's value is zero or
    otherwise not a meaningful base to divide by - the brief's explicit
    "never compute a percentage change against a zero/misleading
    denominator" - `percentage_change_unavailable_reason` then explains
    why, so the UI shows an explicit unavailable state rather than
    omitting the field silently."""

    period_a_value: float
    period_b_value: float
    absolute_change: float
    percentage_change: Optional[float] = None
    percentage_change_unavailable_reason: Optional[str] = None


@dataclass
class PeriodComparisonResult:
    """Explicit two-period comparison (WP2E). `period_a`/`period_b` are
    the full underlying `HistoricalOutcomeValuationResult`s (including
    `resolved_weeks`) - deliberately exposed so a future contribution
    waterfall (WP2F) can consume the identical, already-resolved period
    week-lists rather than re-resolving them.

    Each metric comparison is populated only when *both* periods
    produced a value for it - `incremental_outcome`/`incremental_value`
    require both periods to have resolved successfully;
    `roi`/`spend` additionally require both periods to have a governed
    spend/ROI figure (REQ-ECON-001's CPA-vs-ROI split applies per
    period, so a period with zero spend simply has no ROI comparison,
    never a fabricated one)."""

    period_a: HistoricalOutcomeValuationResult
    period_b: HistoricalOutcomeValuationResult
    incremental_outcome: Optional[MetricComparison] = None
    incremental_value: Optional[MetricComparison] = None
    spend: Optional[MetricComparison] = None
    roi: Optional[MetricComparison] = None
    errors: List[str] = field(default_factory=list)


def _compare_metric(
    period_a_value: Optional[float], period_b_value: Optional[float]
) -> Optional[MetricComparison]:
    if period_a_value is None or period_b_value is None:
        return None
    absolute_change = period_b_value - period_a_value
    if period_a_value == 0:
        return MetricComparison(
            period_a_value=period_a_value,
            period_b_value=period_b_value,
            absolute_change=absolute_change,
            percentage_change=None,
            percentage_change_unavailable_reason=(
                "Period A's value is zero - a percentage change against a "
                "zero denominator would be misleading."
            ),
        )
    return MetricComparison(
        period_a_value=period_a_value,
        period_b_value=period_b_value,
        absolute_change=absolute_change,
        percentage_change=absolute_change / period_a_value,
    )


class OutcomeValuationReportingService:
    """Application service for historical Results economic reporting.

    Does not access Streamlit session state, mutate global state, or
    render any UI.
    """

    def evaluate_period(
        self, request: HistoricalOutcomeValuationRequest
    ) -> HistoricalOutcomeValuationResult:
        errors: List[str] = []

        if request.trace is None:
            errors.append("No fitted model trace provided.")
        if request.frame is None:
            errors.append("No model frame provided.")
        if request.meta is None:
            errors.append("No model metadata provided.")
        if not request.market:
            errors.append("No market provided.")
        if not request.valuation_kind:
            errors.append("No valuation_kind provided.")
        if not request.segment:
            errors.append("No segment provided.")
        if not request.outcome_ids:
            errors.append("No outcome_ids provided.")
        if errors:
            return HistoricalOutcomeValuationResult(errors=errors)

        try:
            available_weeks = available_weeks_for_market(
                request.frame, request.meta, request.market
            )
            resolved_weeks = self._resolve_weeks(request, available_weeks)
            if not resolved_weeks:
                return HistoricalOutcomeValuationResult(
                    errors=[
                        f"No weeks are available for the selected period in "
                        f"market '{request.market}' - this period is not "
                        "covered by the fitted model."
                    ]
                )

            resolved_week_set = set(resolved_weeks)
            filtered_records = [
                record
                for record in request.weekly_valuation_records
                if record.valuation_kind == request.valuation_kind
                and record.market == request.market
                and record.segment == request.segment
                and record.week in resolved_week_set
            ]
            observed_counts = observed_denominator_counts_frame(
                request.frame, request.meta, request.outcome_ids
            )
            rates, issues = derive_weekly_value_rates(filtered_records, observed_counts)
            rate_by_week = {rate.week: rate for rate in rates}
            missing_weeks = [w for w in resolved_weeks if w not in rate_by_week]
            if missing_weeks:
                return HistoricalOutcomeValuationResult(
                    resolved_weeks=resolved_weeks,
                    errors=[
                        "Missing governed valuation coverage for week(s) "
                        f"{', '.join(missing_weeks)} (market="
                        f"'{request.market}', segment='{request.segment}', "
                        f"valuation_kind='{request.valuation_kind}') - "
                        "cannot report this period without fabricating a "
                        "rate."
                    ]
                    + issues,
                )

            ordered_rates = [rate_by_week[week] for week in resolved_weeks]

            incremental_outcome_draws = extract_incremental_outcome_draws(
                request.trace,
                request.frame,
                request.meta,
                market=request.market,
                weeks=resolved_weeks,
                outcome_ids=request.outcome_ids,
                channel=request.channel,
                n_draws=request.n_draws,
                n_permutations=request.n_permutations,
                seed=request.seed,
            )
            spend = attributable_spend(
                request.frame,
                request.meta,
                market=request.market,
                weeks=resolved_weeks,
                channel=request.channel,
            )
            spend_for_roi, currency_warnings = self._resolve_spend_for_roi(
                request, spend, ordered_rates[0].currency, resolved_weeks[-1]
            )
            attribution = summarize_posterior_economic_attribution(
                incremental_outcome_draws,
                ordered_rates,
                spend=spend_for_roi,
                credible_mass=request.credible_mass,
            )
        except Exception as exc:
            errors.append(f"Historical outcome valuation reporting failed: {exc}")
            return HistoricalOutcomeValuationResult(errors=errors)

        return HistoricalOutcomeValuationResult(
            attribution=attribution,
            resolved_weeks=resolved_weeks,
            errors=[],
            warnings=list(issues) + currency_warnings,
        )

    @staticmethod
    def _resolve_spend_for_roi(
        request: "HistoricalOutcomeValuationRequest",
        spend: float,
        value_currency: str,
        last_resolved_week: str,
    ) -> "tuple[Optional[float], List[str]]":
        """UK FH MMM brief (2026-09-10) Workstream A/F: resolve the spend
        figure to pass into ROI, converting it into `value_currency` via
        `application.fx_service.resolve_approved_fx_rate` when
        `request.spend_currency` differs from it - the same
        approval-status/fingerprint-checked lookup Official Curve
        Generation already uses, never a second, parallel FX-lookup
        mechanism. Returns `(spend_for_roi, warnings)`. `spend_for_roi=None`
        means "ROI not shown" (the existing zero/absent-spend contract) - a
        currency block reuses that identical mechanism, never a new field.

        Zero/negative spend never needs conversion (no ROI is computed for
        it regardless), and `spend_currency=None` (not yet governed) leaves
        existing single-currency behaviour byte-for-byte unchanged - this
        function does exactly nothing unless a genuine, explicitly declared
        currency mismatch exists.
        """
        if (
            not request.spend_currency
            or not value_currency
            or request.spend_currency == value_currency
            or spend is None
            or spend <= 0
        ):
            return spend, []

        if request.fx_rate_set is None:
            return None, [
                f"Attributable spend is in {request.spend_currency} but the "
                f"governed valuation catalogue is in {value_currency}. ROI "
                "is not shown: no Finance FX rate set has been supplied yet."
            ]

        try:
            rate_set = FXRateSet.from_dict(dict(request.fx_rate_set))
            fx_records = [
                FXRateRecord.from_dict(item) if isinstance(item, Mapping) else item
                for item in (request.fx_rate_records or ())
            ]
            resolved_rate = resolve_approved_fx_rate(
                rate_set,
                fx_records,
                source_currency=request.spend_currency,
                target_currency=value_currency,
                as_of_date=request.fx_as_of_date or last_resolved_week,
            )
        except (ValueError, TypeError, FXUploadValidationError) as exc:
            return None, [f"ROI is not shown: {exc}"]

        if resolved_rate is None:
            return None, [
                "ROI is not shown: the approved Finance FX rate set has no "
                f"applicable {request.spend_currency}->{value_currency} rate "
                f"on or before {request.fx_as_of_date or last_resolved_week}."
            ]

        return float(spend) * float(resolved_rate), [
            f"Attributable spend converted from {request.spend_currency} to "
            f"{value_currency} at the approved Finance FX rate ({resolved_rate})."
        ]

    def compare_periods(
        self,
        request_a: HistoricalOutcomeValuationRequest,
        request_b: HistoricalOutcomeValuationRequest,
    ) -> PeriodComparisonResult:
        """Explicit period comparison (WP2E). Calls `evaluate_period()`
        twice - the identical single-period calculation path, never a
        second one - and compares the two results. The caller is
        responsible for keeping the "what" (market/valuation_kind/
        segment/channel/outcome_ids) fixed across `request_a`/
        `request_b` and varying only the "when" (grain/period_label/
        custom range); this method does not itself enforce that."""
        result_a = self.evaluate_period(request_a)
        result_b = self.evaluate_period(request_b)

        errors = [f"Period A: {e}" for e in result_a.errors] + [
            f"Period B: {e}" for e in result_b.errors
        ]

        incremental_outcome = None
        incremental_value = None
        spend = None
        roi = None
        if result_a.attribution is not None and result_b.attribution is not None:
            incremental_outcome = _compare_metric(
                result_a.attribution.incremental_outcome_mean,
                result_b.attribution.incremental_outcome_mean,
            )
            incremental_value = _compare_metric(
                result_a.attribution.incremental_value_mean,
                result_b.attribution.incremental_value_mean,
            )
            spend = _compare_metric(
                result_a.attribution.spend, result_b.attribution.spend
            )
            roi = _compare_metric(
                result_a.attribution.roi_mean, result_b.attribution.roi_mean
            )

        return PeriodComparisonResult(
            period_a=result_a,
            period_b=result_b,
            incremental_outcome=incremental_outcome,
            incremental_value=incremental_value,
            spend=spend,
            roi=roi,
            errors=errors,
        )

    @staticmethod
    def _resolve_weeks(
        request: HistoricalOutcomeValuationRequest, available_weeks: List[str]
    ) -> List[str]:
        return resolve_weeks_for_grain(
            available_weeks,
            request.grain,
            period_label=request.period_label,
            custom_range_start=request.custom_range_start,
            custom_range_end=request.custom_range_end,
        )
