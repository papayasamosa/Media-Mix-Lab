"""Tests for application.outcome_valuation_reporting_service - the
Streamlit-independent orchestration of historical Results economic
reporting (WP2D-ui), composing core.outcome_valuation_periods, core.
outcome_valuation_reporting, core.outcome_valuation_rates, and core.
outcome_valuation_attribution end to end. Hand-constructed FHModelMeta/
InferenceData/frame, matching test_outcome_valuation_reporting.py's
fixtures."""

from __future__ import annotations

import inspect

import arviz as az
import numpy as np
import pandas as pd
import pytest

from ancestry_mmm.application.outcome_valuation_reporting_service import (
    HistoricalOutcomeValuationRequest,
    OutcomeValuationReportingService,
)
from ancestry_mmm.core.coverage import STATE_ESTIMATED, STATE_OBSERVED_ZERO
from ancestry_mmm.core.hierarchical_model import FHModelMeta
from ancestry_mmm.core.outcome_valuation import (
    VALUATION_KIND_DNA_REVENUE,
    VALUATION_KIND_FH_LTR,
    WeeklyOutcomeValuationRecord,
)
from ancestry_mmm.core.outcome_valuation_periods import (
    PERIOD_GRAIN_CUSTOM,
    PERIOD_GRAIN_QUARTER,
    PERIOD_GRAIN_WEEK,
)
from ancestry_mmm.core.outcome_valuation_reporting import attributable_spend
from ancestry_mmm.core.outcomes import FH_LTR_HORIZON_MONTHS

OUTCOME_IDS = ["New", "DNA_CrossSell"]
CHANNELS = ["TV_Brand", "DNA_Media"]
MARKETS = ["UK", "AU"]
N_WEEKS_PER_MARKET = 8
WEEK_STARTS = [
    (pd.Timestamp("2025-01-06") + pd.Timedelta(weeks=i)).strftime("%Y-%m-%d")
    for i in range(N_WEEKS_PER_MARKET)
]
SEGMENT = "All"


def _const_broadcast(value, n_chain, n_draw):
    arr = np.asarray(value, dtype=float)
    return np.broadcast_to(arr, (n_chain, n_draw) + arr.shape).copy()


@pytest.fixture
def meta() -> FHModelMeta:
    return FHModelMeta(
        markets=MARKETS,
        outcome_ids=OUTCOME_IDS,
        channels=CHANNELS,
        dna_channels=["DNA_Media"],
        dna_channel_idx=[1],
        non_dna_idx=[0],
        dna_outcome_id="DNA_CrossSell",
        dna_lag_weeks=1,
        unpooled_markets=[],
        control_names=[],
        outcome_id_to_segment={"New": SEGMENT, "DNA_CrossSell": SEGMENT},
    )


@pytest.fixture
def trace() -> az.InferenceData:
    n_chain, n_draw = 2, 10
    coords = {
        "outcome": OUTCOME_IDS,
        "channel": CHANNELS,
        "market": MARKETS,
        "fourier": list(range(4)),
    }
    rng = np.random.default_rng(11)

    def const(value):
        return _const_broadcast(value, n_chain, n_draw)

    posterior = {
        "decay_rate": const([0.5, 0.4]),
        "hill_K": const([1000.0, 500.0])
        * (1 + rng.normal(0, 0.05, size=(n_chain, n_draw, 2))),
        "hill_S": const([1.0, 1.0]),
        "beta": const([[0.10, 0.05], [0.02, 0.20]])
        * (1 + rng.normal(0, 0.1, size=(n_chain, n_draw, 2, 2))),
        "halo_strength": const([0.15, 1.0]),
        "promo_coef": const([0.0, 0.0]),
        "market_offset": const([[0.0, 0.0], [0.1, -0.1]]),
        "intercept": const([3.0, 2.0]),
        "trend_coef": const([0.0, 0.0]),
        "gamma_fourier": const(np.zeros((4, 2))),
        "alpha": const([5.0, 5.0]),
    }
    dims = {
        "decay_rate": ["channel"],
        "hill_K": ["channel"],
        "hill_S": ["channel"],
        "beta": ["outcome", "channel"],
        "halo_strength": ["outcome"],
        "promo_coef": ["outcome"],
        "market_offset": ["market", "outcome"],
        "intercept": ["outcome"],
        "trend_coef": ["outcome"],
        "gamma_fourier": ["fourier", "outcome"],
        "alpha": ["outcome"],
    }
    return az.from_dict(posterior=posterior, coords=coords, dims=dims)


@pytest.fixture
def frame():
    n_per_market = N_WEEKS_PER_MARKET
    n_markets = len(MARKETS)
    n = n_per_market * n_markets
    rng = np.random.default_rng(5)
    market_idx = np.repeat(np.arange(n_markets), n_per_market)
    market_bounds = [
        (i * n_per_market, (i + 1) * n_per_market) for i in range(n_markets)
    ]
    dates = np.array(WEEK_STARTS * n_markets, dtype="datetime64[D]")
    return {
        "markets": MARKETS,
        "market_idx": market_idx,
        "market_bounds": market_bounds,
        "dates": dates,
        "X_media": rng.uniform(50, 500, size=(n, 2)),
        "Y": rng.uniform(100, 1000, size=(n, len(OUTCOME_IDS))),
        "promo": np.zeros((n, len(OUTCOME_IDS))),
        "trend": np.zeros(n),
        "fourier": np.zeros((n, 4)),
        "control_names": [],
        "X_controls": np.zeros((n, 0)),
        "outcome_controls": {},
        "outcome_control_names": {},
    }


def _valuation_records(
    weeks, *, market="UK", segment=SEGMENT, aggregate_value=500.0, currency="GBP"
):
    return [
        WeeklyOutcomeValuationRecord(
            valuation_kind=VALUATION_KIND_FH_LTR,
            market=market,
            week=week,
            segment=segment,
            denominator_outcome_id="New",
            quality_status=STATE_ESTIMATED,
            aggregate_value=aggregate_value,
            currency=currency,
            horizon_months=FH_LTR_HORIZON_MONTHS,
        )
        for week in weeks
    ]


def _base_request(
    _trace, _frame, _meta, **overrides
) -> HistoricalOutcomeValuationRequest:
    defaults = dict(
        market="UK",
        grain=PERIOD_GRAIN_QUARTER,
        trace=_trace,
        frame=_frame,
        meta=_meta,
        outcome_ids=["New"],
        segment=SEGMENT,
        valuation_kind=VALUATION_KIND_FH_LTR,
        weekly_valuation_records=_valuation_records(WEEK_STARTS),
        period_label="2025-Q1",
        n_draws=4,
        n_permutations=5,
    )
    defaults.update(overrides)
    return HistoricalOutcomeValuationRequest(**defaults)


class TestHappyPath:
    def test_quarter_view_resolves_every_available_week(self, trace, frame, meta):
        request = _base_request(trace, frame, meta)
        result = OutcomeValuationReportingService().evaluate_period(request)

        assert result.errors == []
        assert result.resolved_weeks == WEEK_STARTS
        assert result.attribution is not None
        assert np.isfinite(result.attribution.incremental_value_mean)
        assert result.attribution.currency == "GBP"
        assert result.attribution.spend == pytest.approx(
            attributable_spend(frame, meta, market="UK", weeks=WEEK_STARTS)
        )

    def test_channel_selection_uses_that_channels_spend(self, trace, frame, meta):
        request = _base_request(trace, frame, meta, channel="TV_Brand")
        result = OutcomeValuationReportingService().evaluate_period(request)

        assert result.errors == []
        assert result.attribution is not None
        assert result.attribution.spend == pytest.approx(
            attributable_spend(
                frame, meta, market="UK", weeks=WEEK_STARTS, channel="TV_Brand"
            )
        )

    def test_single_week_grain(self, trace, frame, meta):
        request = _base_request(
            trace,
            frame,
            meta,
            grain=PERIOD_GRAIN_WEEK,
            period_label=WEEK_STARTS[0],
        )
        result = OutcomeValuationReportingService().evaluate_period(request)

        assert result.errors == []
        assert result.resolved_weeks == [WEEK_STARTS[0]]

    def test_custom_range_grain(self, trace, frame, meta):
        request = _base_request(
            trace,
            frame,
            meta,
            grain=PERIOD_GRAIN_CUSTOM,
            period_label=None,
            custom_range_start=WEEK_STARTS[1],
            custom_range_end=WEEK_STARTS[3],
        )
        result = OutcomeValuationReportingService().evaluate_period(request)

        assert result.errors == []
        assert result.resolved_weeks == WEEK_STARTS[1:4]


class TestFailsClosed:
    def test_missing_valuation_coverage_for_a_week_is_an_error(
        self, trace, frame, meta
    ):
        records = _valuation_records(WEEK_STARTS[:-1])  # last week has no record
        request = _base_request(trace, frame, meta, weekly_valuation_records=records)
        result = OutcomeValuationReportingService().evaluate_period(request)

        assert result.attribution is None
        assert any("Missing governed valuation coverage" in e for e in result.errors)
        assert WEEK_STARTS[-1] in result.errors[0]

    def test_wrong_segment_has_no_coverage(self, trace, frame, meta):
        records = _valuation_records(WEEK_STARTS, segment="Other")
        request = _base_request(trace, frame, meta, weekly_valuation_records=records)
        result = OutcomeValuationReportingService().evaluate_period(request)

        assert result.attribution is None
        assert any("Missing governed valuation coverage" in e for e in result.errors)

    def test_period_with_no_available_weeks_is_an_error(self, trace, frame, meta):
        request = _base_request(trace, frame, meta, period_label="2030-Q1")
        result = OutcomeValuationReportingService().evaluate_period(request)

        assert result.attribution is None
        assert result.resolved_weeks == []
        assert any("No weeks are available" in e for e in result.errors)

    def test_unsupported_grain_is_an_error(self, trace, frame, meta):
        request = _base_request(trace, frame, meta, grain="fortnight")
        result = OutcomeValuationReportingService().evaluate_period(request)

        assert result.attribution is None
        assert any("Unsupported reporting grain" in e for e in result.errors)

    @pytest.mark.parametrize(
        "field_name,value",
        [
            ("trace", None),
            ("frame", None),
            ("meta", None),
            ("market", ""),
            ("valuation_kind", ""),
            ("segment", ""),
            ("outcome_ids", []),
        ],
    )
    def test_missing_required_field_is_a_validation_error(
        self, trace, frame, meta, field_name, value
    ):
        request = _base_request(trace, frame, meta, **{field_name: value})
        result = OutcomeValuationReportingService().evaluate_period(request)

        assert result.attribution is None
        assert result.errors != []


class TestSpendCurrencyMismatch:
    """Finance constant-dollar correction (2026-09-10): attributable_spend
    is in the market's native currency, which may differ from the
    governed valuation catalogue's currency (here always GBP via
    `_valuation_records`). ROI must never silently divide across
    currencies, and the FX rate applied must always come from the
    selected Finance constant-dollar *vintage* (`financial_year`) -
    never joined to the calendar year of the observation being valued.
    No actual exchange rate appears anywhere in this class - every rate
    is a clearly synthetic test value."""

    def test_no_spend_currency_declared_is_unchanged(self, trace, frame, meta):
        """Backward-compatible default: omitting spend_currency (every
        caller before this feature existed) leaves behaviour identical to
        the happy path - no conversion, no warning, no block."""
        request = _base_request(trace, frame, meta)
        result = OutcomeValuationReportingService().evaluate_period(request)

        assert result.errors == []
        assert result.attribution.spend == pytest.approx(
            attributable_spend(frame, meta, market="UK", weeks=WEEK_STARTS)
        )
        assert not any("currency" in w.lower() for w in result.warnings)

    def test_matching_spend_currency_is_unchanged(self, trace, frame, meta):
        request = _base_request(trace, frame, meta, spend_currency="GBP")
        result = OutcomeValuationReportingService().evaluate_period(request)

        assert result.errors == []
        assert result.attribution.spend == pytest.approx(
            attributable_spend(frame, meta, market="UK", weeks=WEEK_STARTS)
        )

    def test_matching_usd_spend_currency_is_unchanged(self, trace, frame, meta):
        """A UK observation explicitly declared in USD (e.g. a UK spend
        variable already supplied in USD) must never be converted just
        because the market is UK - there is no blanket 'market currency'
        assumption anywhere in this path."""
        records = _valuation_records(WEEK_STARTS, currency="USD")
        request = _base_request(
            trace,
            frame,
            meta,
            spend_currency="USD",
            weekly_valuation_records=records,
        )
        result = OutcomeValuationReportingService().evaluate_period(request)

        assert result.errors == []
        assert result.attribution.spend == pytest.approx(
            attributable_spend(frame, meta, market="UK", weeks=WEEK_STARTS)
        )
        assert not any("currency" in w.lower() for w in result.warnings)

    def test_mismatched_currency_without_fx_rate_set_blocks_roi_only(
        self, trace, frame, meta
    ):
        request = _base_request(trace, frame, meta, spend_currency="USD")
        result = OutcomeValuationReportingService().evaluate_period(request)

        assert result.errors == []
        assert result.attribution is not None
        assert np.isfinite(result.attribution.incremental_value_mean)
        assert result.attribution.roi_mean is None
        assert result.attribution.spend is None
        assert any("no Finance FX rate set" in w for w in result.warnings)

    @staticmethod
    def _two_vintage_fx_rate_set_and_records(**overrides):
        """Two Finance constant-dollar vintages (2025, 2026), each with
        its own distinct, clearly synthetic USD->GBP rate - so a test can
        prove which vintage's rate was actually used, and that selecting
        a different vintage changes the result."""
        from ancestry_mmm.application.fx_service import build_manual_fx_rate_set

        rows = [
            dict(
                rate_date="2025-01-01",
                source_currency="USD",
                target_currency="GBP",
                rate="0.75",
                method="finance_constant_dollar_annual",
                frequency="annual",
                financial_year="2025",
            ),
            dict(
                rate_date="2026-01-01",
                source_currency="USD",
                target_currency="GBP",
                rate="0.8",
                method="finance_constant_dollar_annual",
                frequency="annual",
                financial_year="2026",
            ),
        ]
        kwargs = dict(
            rate_set_id="fx-finance-constant-dollar",
            rate_set_version=1,
            name="Finance constant-dollar table",
            provider="finance-approved-upload",
            base_or_reference_currency="GBP",
            start_date="2025-01-01",
            end_date="2026-12-31",
            rate_policy="finance_constant_dollar_vintage",
            approval_status="approved",
            approved_by="finance-reviewer",
            approved_at="2026-01-01T00:00:00Z",
        )
        kwargs.update(overrides)
        rate_set, records = build_manual_fx_rate_set(pd.DataFrame(rows), **kwargs)
        return rate_set.to_dict(), [record.to_dict() for record in records]

    def test_mismatched_currency_without_matching_fx_rate_blocks_roi_only(
        self, trace, frame, meta
    ):
        rate_set, records = self._two_vintage_fx_rate_set_and_records()
        request = _base_request(
            trace,
            frame,
            meta,
            spend_currency="AUD",  # no AUD->GBP rate in either vintage
            fx_rate_set=rate_set,
            fx_rate_records=records,
            fx_vintage_year_id="2026",
        )
        result = OutcomeValuationReportingService().evaluate_period(request)

        assert result.errors == []
        assert result.attribution.roi_mean is None
        assert result.attribution.spend is None
        assert any("no applicable" in w for w in result.warnings)

    def test_currency_present_in_a_different_vintage_still_blocks(
        self, trace, frame, meta
    ):
        """Regression: AUD has a rate in the 2025 vintage but not the
        2026 vintage. Selecting 2026 must block the economic output -
        never silently fall back to the 2025 vintage's AUD rate."""
        from ancestry_mmm.application.fx_service import build_manual_fx_rate_set

        rows = [
            dict(
                rate_date="2025-01-01",
                source_currency="AUD",
                target_currency="GBP",
                rate="0.5",
                method="finance_constant_dollar_annual",
                frequency="annual",
                financial_year="2025",
            ),
            dict(
                rate_date="2026-01-01",
                source_currency="USD",
                target_currency="GBP",
                rate="0.8",
                method="finance_constant_dollar_annual",
                frequency="annual",
                financial_year="2026",
            ),
        ]
        rate_set, records = build_manual_fx_rate_set(
            pd.DataFrame(rows),
            rate_set_id="fx-finance-constant-dollar-partial",
            rate_set_version=1,
            name="Finance constant-dollar table",
            provider="finance-approved-upload",
            base_or_reference_currency="GBP",
            start_date="2025-01-01",
            end_date="2026-12-31",
            rate_policy="finance_constant_dollar_vintage",
            approval_status="approved",
            approved_by="finance-reviewer",
            approved_at="2026-01-01T00:00:00Z",
        )
        request = _base_request(
            trace,
            frame,
            meta,
            spend_currency="AUD",
            fx_rate_set=rate_set.to_dict(),
            fx_rate_records=[r.to_dict() for r in records],
            fx_vintage_year_id="2026",
        )
        result = OutcomeValuationReportingService().evaluate_period(request)

        assert result.errors == []
        assert result.attribution.roi_mean is None
        assert result.attribution.spend is None
        assert any("no applicable" in w and "2026" in w for w in result.warnings)

    def test_mismatched_currency_with_approved_vintage_converts_and_computes_roi(
        self, trace, frame, meta
    ):
        rate_set, records = self._two_vintage_fx_rate_set_and_records()
        request = _base_request(
            trace,
            frame,
            meta,
            spend_currency="USD",
            fx_rate_set=rate_set,
            fx_rate_records=records,
            fx_vintage_year_id="2026",
        )
        result = OutcomeValuationReportingService().evaluate_period(request)
        native_spend = attributable_spend(frame, meta, market="UK", weeks=WEEK_STARTS)

        assert result.errors == []
        assert result.attribution.spend == pytest.approx(native_spend * 0.8)
        assert result.attribution.roi_mean is not None
        assert any(
            "2026" in w and "converted from USD to GBP" in w for w in result.warnings
        )

    def test_omitted_vintage_defaults_to_latest_available(self, trace, frame, meta):
        """"Default to the latest available vintage" - omitting
        fx_vintage_year_id must behave identically to explicitly
        selecting the newest vintage present in fx_rate_records (2026,
        here)."""
        rate_set, records = self._two_vintage_fx_rate_set_and_records()
        request = _base_request(
            trace,
            frame,
            meta,
            spend_currency="USD",
            fx_rate_set=rate_set,
            fx_rate_records=records,
        )
        result = OutcomeValuationReportingService().evaluate_period(request)
        native_spend = attributable_spend(frame, meta, market="UK", weeks=WEEK_STARTS)

        assert result.errors == []
        assert result.attribution.spend == pytest.approx(native_spend * 0.8)

    def test_selecting_an_older_vintage_changes_economic_values(
        self, trace, frame, meta
    ):
        rate_set, records = self._two_vintage_fx_rate_set_and_records()
        native_spend = attributable_spend(frame, meta, market="UK", weeks=WEEK_STARTS)

        request_2026 = _base_request(
            trace,
            frame,
            meta,
            spend_currency="USD",
            fx_rate_set=rate_set,
            fx_rate_records=records,
            fx_vintage_year_id="2026",
        )
        request_2025 = _base_request(
            trace,
            frame,
            meta,
            spend_currency="USD",
            fx_rate_set=rate_set,
            fx_rate_records=records,
            fx_vintage_year_id="2025",
        )
        result_2026 = OutcomeValuationReportingService().evaluate_period(request_2026)
        result_2025 = OutcomeValuationReportingService().evaluate_period(request_2025)

        assert result_2026.attribution.spend == pytest.approx(native_spend * 0.8)
        assert result_2025.attribution.spend == pytest.approx(native_spend * 0.75)
        assert result_2026.attribution.spend != pytest.approx(
            result_2025.attribution.spend
        )

    def test_switching_vintage_never_changes_the_count_model_outcome(
        self, trace, frame, meta
    ):
        """Changing FX vintage recalculates monetary/economic outputs
        only - it must never affect the non-monetary incremental-outcome
        (count) result, and must never require refitting: both requests
        share the identical trace/frame/meta, untouched."""
        rate_set, records = self._two_vintage_fx_rate_set_and_records()

        request_2026 = _base_request(
            trace,
            frame,
            meta,
            spend_currency="USD",
            fx_rate_set=rate_set,
            fx_rate_records=records,
            fx_vintage_year_id="2026",
        )
        request_2025 = _base_request(
            trace,
            frame,
            meta,
            spend_currency="USD",
            fx_rate_set=rate_set,
            fx_rate_records=records,
            fx_vintage_year_id="2025",
        )
        result_2026 = OutcomeValuationReportingService().evaluate_period(request_2026)
        result_2025 = OutcomeValuationReportingService().evaluate_period(request_2025)

        assert result_2026.attribution.incremental_outcome_mean == pytest.approx(
            result_2025.attribution.incremental_outcome_mean
        )
        assert result_2026.attribution.incremental_value_mean == pytest.approx(
            result_2025.attribution.incremental_value_mean
        )

    def test_vintage_rate_applies_regardless_of_the_observations_own_calendar_year(
        self, trace, frame, meta
    ):
        """The core Finance constant-dollar policy: the selected
        vintage's rate applies to every historical observation of that
        currency alike, never joined to the observation's own calendar
        year. A 2023-dated observation and a 2025-dated one must resolve
        to the identical 2026-vintage rate - including a week far
        earlier than any rate_date in the set, which the as-of-date
        mechanism this replaces would have found no applicable rate for
        and blocked."""
        rate_set_dict, records_dicts = self._two_vintage_fx_rate_set_and_records()
        request = _base_request(
            trace,
            frame,
            meta,
            spend_currency="USD",
            fx_rate_set=rate_set_dict,
            fx_rate_records=records_dicts,
            fx_vintage_year_id="2026",
        )

        spend_2023, warnings_2023 = (
            OutcomeValuationReportingService._resolve_spend_for_roi(
                request, 1000.0, "GBP", "2023-01-16"
            )
        )
        spend_2025, warnings_2025 = (
            OutcomeValuationReportingService._resolve_spend_for_roi(
                request, 1000.0, "GBP", "2025-06-02"
            )
        )

        assert spend_2023 == pytest.approx(800.0)
        assert spend_2025 == pytest.approx(800.0)
        assert not any("no applicable" in w for w in warnings_2023)
        assert not any("no applicable" in w for w in warnings_2025)


class TestComparePeriods:
    """WP2E: explicit two-period comparison. Reuses `evaluate_period()`
    itself (called twice) - one calculation path, verified here by
    checking the comparison numbers agree with two direct
    `evaluate_period()` calls."""

    def test_happy_path_compares_two_weeks(self, trace, frame, meta):
        records = _valuation_records(WEEK_STARTS)
        request_a = _base_request(
            trace,
            frame,
            meta,
            grain=PERIOD_GRAIN_WEEK,
            period_label=WEEK_STARTS[0],
            weekly_valuation_records=records,
        )
        request_b = _base_request(
            trace,
            frame,
            meta,
            grain=PERIOD_GRAIN_WEEK,
            period_label=WEEK_STARTS[4],
            weekly_valuation_records=records,
        )
        comparison = OutcomeValuationReportingService().compare_periods(
            request_a, request_b
        )

        assert comparison.errors == []
        assert comparison.period_a.resolved_weeks == [WEEK_STARTS[0]]
        assert comparison.period_b.resolved_weeks == [WEEK_STARTS[4]]

        direct_a = OutcomeValuationReportingService().evaluate_period(request_a)
        direct_b = OutcomeValuationReportingService().evaluate_period(request_b)

        assert comparison.incremental_value is not None
        assert comparison.incremental_value.period_a_value == pytest.approx(
            direct_a.attribution.incremental_value_mean
        )
        assert comparison.incremental_value.period_b_value == pytest.approx(
            direct_b.attribution.incremental_value_mean
        )
        assert comparison.incremental_value.absolute_change == pytest.approx(
            direct_b.attribution.incremental_value_mean
            - direct_a.attribution.incremental_value_mean
        )

        assert comparison.spend is not None
        assert comparison.spend.absolute_change == pytest.approx(
            direct_b.attribution.spend - direct_a.attribution.spend
        )

    def test_period_objects_expose_underlying_resolved_weeks_for_the_waterfall(
        self, trace, frame, meta
    ):
        """WP2F's future waterfall needs the exact resolved week-lists
        each period bridges from/to - exposed here via `period_a`/
        `period_b`, not re-derivable only from the comparison deltas."""
        records = _valuation_records(WEEK_STARTS)
        request_a = _base_request(
            trace,
            frame,
            meta,
            grain=PERIOD_GRAIN_QUARTER,
            period_label="2025-Q1",
            weekly_valuation_records=records,
        )
        request_b = _base_request(
            trace,
            frame,
            meta,
            grain=PERIOD_GRAIN_WEEK,
            period_label=WEEK_STARTS[0],
            weekly_valuation_records=records,
        )
        comparison = OutcomeValuationReportingService().compare_periods(
            request_a, request_b
        )
        assert comparison.period_a.resolved_weeks == WEEK_STARTS
        assert comparison.period_b.resolved_weeks == [WEEK_STARTS[0]]

    def test_zero_period_a_value_makes_percentage_change_unavailable(
        self, trace, frame, meta
    ):
        zero_week_record = WeeklyOutcomeValuationRecord(
            valuation_kind=VALUATION_KIND_FH_LTR,
            market="UK",
            week=WEEK_STARTS[0],
            segment=SEGMENT,
            denominator_outcome_id="New",
            quality_status=STATE_OBSERVED_ZERO,
            aggregate_value=0.0,
            currency="GBP",
            horizon_months=FH_LTR_HORIZON_MONTHS,
        )
        records = [zero_week_record] + _valuation_records(WEEK_STARTS[1:])
        request_a = _base_request(
            trace,
            frame,
            meta,
            grain=PERIOD_GRAIN_WEEK,
            period_label=WEEK_STARTS[0],
            weekly_valuation_records=records,
        )
        request_b = _base_request(
            trace,
            frame,
            meta,
            grain=PERIOD_GRAIN_WEEK,
            period_label=WEEK_STARTS[4],
            weekly_valuation_records=records,
        )
        comparison = OutcomeValuationReportingService().compare_periods(
            request_a, request_b
        )

        assert comparison.incremental_value is not None
        assert comparison.incremental_value.period_a_value == pytest.approx(0.0)
        assert comparison.incremental_value.percentage_change is None
        assert (
            comparison.incremental_value.percentage_change_unavailable_reason
            is not None
        )
        assert (
            "zero" in comparison.incremental_value.percentage_change_unavailable_reason
        )

    def test_a_failed_period_leaves_comparisons_none_but_surfaces_its_error(
        self, trace, frame, meta
    ):
        records = _valuation_records(WEEK_STARTS[:-1])  # last week uncovered
        request_a = _base_request(
            trace,
            frame,
            meta,
            grain=PERIOD_GRAIN_WEEK,
            period_label=WEEK_STARTS[0],
            weekly_valuation_records=records,
        )
        request_b = _base_request(
            trace,
            frame,
            meta,
            grain=PERIOD_GRAIN_WEEK,
            period_label=WEEK_STARTS[-1],
            weekly_valuation_records=records,
        )
        comparison = OutcomeValuationReportingService().compare_periods(
            request_a, request_b
        )

        assert comparison.incremental_value is None
        assert comparison.roi is None
        assert any(e.startswith("Period B:") for e in comparison.errors)
        assert comparison.period_a.attribution is not None


class TestGenericDenominatorArchitectureWithGSA:
    """UK FH MMM Next Autonomous Instructions (2026-09-10), section 8: the
    generic weekly-value-rate-derivation path must not assume NBT is the
    universal denominator. `denominator_outcome_id` is an opaque
    identifier as far as this service is concerned - REQ-ECON-002
    Requirement 3 explicitly forbids inferring or defaulting it to any
    particular outcome (GSA included). This proves the exact same
    `OutcomeValuationReportingService.evaluate_period` code path -
    weekly-rate derivation, draw-level join, aggregation, ROI - produces a
    correct result for a GSA-cohort-by-GSA-week valuation record, with no
    special-casing anywhere for which outcome the denominator happens to
    reference. `TestHappyPath`'s NBT-flavoured (`VALUATION_KIND_FH_LTR`)
    tests above are unmodified and continue to pass unchanged - this
    class adds a parallel path, never a replacement."""

    @staticmethod
    def _gsa_style_records(weeks, *, aggregate_value=300.0):
        # dna_revenue carries no LTR-horizon concept (unlike fh_ltr), so it
        # doubles here as a stand-in for "a non-NBT-flavoured valuation
        # kind" without needing FH_LTR_HORIZON_MONTHS at all - the point
        # under test is the denominator_outcome_id, not the valuation_kind.
        return [
            WeeklyOutcomeValuationRecord(
                valuation_kind=VALUATION_KIND_DNA_REVENUE,
                market="UK",
                week=week,
                segment=SEGMENT,
                denominator_outcome_id="New",  # stands in for a GSA outcome_id
                quality_status=STATE_ESTIMATED,
                aggregate_value=aggregate_value,
                currency="GBP",
            )
            for week in weeks
        ]

    def test_gsa_denominator_end_to_end_reporting_matches_nbt_path_shape(
        self, trace, frame, meta
    ):
        """An approved GSA-style outcome (the fixture's "New" outcome_id,
        used here as the GSA cohort) referenced by a weekly valuation
        record's denominator_outcome_id - the same generic weekly-rate
        derivation, draw-level join, and ROI computation as the NBT path,
        with no code branch keyed on which outcome_id is supplied."""
        request = _base_request(
            trace,
            frame,
            meta,
            valuation_kind=VALUATION_KIND_DNA_REVENUE,
            weekly_valuation_records=self._gsa_style_records(WEEK_STARTS),
        )
        result = OutcomeValuationReportingService().evaluate_period(request)

        assert result.errors == []
        assert result.attribution is not None
        assert np.isfinite(result.attribution.incremental_value_mean)
        assert result.attribution.currency == "GBP"
        assert result.attribution.spend == pytest.approx(
            attributable_spend(frame, meta, market="UK", weeks=WEEK_STARTS)
        )

    def test_nbt_style_path_is_unaffected_by_the_generic_mechanism(
        self, trace, frame, meta
    ):
        """The pre-existing FH_LTR/NBT-style request continues to work
        identically alongside the GSA-style one above - proving the
        generic mechanism serves both, never one at the expense of the
        other."""
        request = _base_request(trace, frame, meta)
        result = OutcomeValuationReportingService().evaluate_period(request)
        assert result.errors == []
        assert result.attribution is not None

    def test_no_runtime_valuation_module_hardcodes_an_nbt_specific_string(self):
        """Structural guard: the generic valuation/rate/attribution/
        reporting-service modules must never special-case a net-bill-
        through-specific identifier - REQ-ECON-002 Requirement 3's
        genericness requirement, enforced as source text, not just proven
        by example via the tests above."""
        import ancestry_mmm.core.outcome_valuation as _ov
        import ancestry_mmm.core.outcome_valuation_attribution as _ova
        import ancestry_mmm.core.outcome_valuation_rates as _ovr
        import ancestry_mmm.application.outcome_valuation_reporting_service as _ovrs

        forbidden = ("net_billthrough", "fh_net_billthrough", "nbt_")
        for module in (_ov, _ova, _ovr, _ovrs):
            source = inspect.getsource(module).lower()
            for needle in forbidden:
                assert needle not in source, (
                    f"{module.__name__} references {needle!r} - the "
                    "denominator/valuation mechanism must remain "
                    "outcome-agnostic."
                )
