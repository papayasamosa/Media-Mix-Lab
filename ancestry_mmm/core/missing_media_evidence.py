"""Missing-media gap diagnostics and estimation-evidence framework.

UK FH MMM implementation brief (2026-09-10), Workstream D. `REQ-COVERAGE-001`
already governs the canonical missingness-state vocabulary
(`core.coverage`) and explicitly leaves two things out of scope for a
future, separately-approved requirement to resolve (see that record's "Out
of scope" section): "any specific imputation formula... not named in
[the frequency-conversion requirement]" and "any specific validation
threshold, coverage-percentage cutoff, or approval rule." This module is
that dependent capability - it does not reopen or override
`REQ-COVERAGE-001`'s own text.

Three pieces, matching the brief's "Implement now" list:

1. ``diagnose_gaps`` - gap classification (consecutive-run length, edge vs.
   internal position, named-event overlap, cross-measure evidence) from an
   existing ``core.coverage.VariableCoverageRecord`` - it does not invent a
   new missingness vocabulary or coverage-matrix shape.
2. ``evaluate_candidate_reconstruction_method`` - a generic, method-agnostic
   holdout-evaluation harness: carve synthetic gaps out of already-observed
   weeks, ask a caller-supplied candidate method to reconstruct them, and
   score the reconstruction error. This module selects, endorses, and
   hard-codes no specific imputation formula - the candidate method is
   always supplied by the caller, per REQ-COVERAGE-001's explicit scope
   boundary above.
3. ``assess_estimation_readiness`` - a fail-closed readiness gate. When no
   ``EstimationReadinessPolicy`` is supplied, the result is always
   ``blocked_no_policy`` - this module never invents or defaults a missing-
   week/coverage-percentage threshold. A policy is deliberately a plain,
   versioned, attributable record (mirrors ``core.coverage.DefinitionBreak``'s
   approval-requires-attribution pattern) so a real approval leaves a
   traceable owner and date, and defaults to
   ``is_recommendation_only=True`` until Product/Finance formally adopts one
   (see ``docs/missing_media_threshold_recommendation.md``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional, Sequence

from .coverage import (
    STATE_MISSING_EXPECTED,
    STATE_UNKNOWN,
    CoverageSegment,
    VariableCoverageRecord,
)
from .named_events import NamedEventOccurrence

# Default candidate set for "is this segment a gap worth diagnosing" - reuses
# core.coverage.UNRESOLVED_BLOCKING_STATES's exact membership rather than
# defining a second, possibly-diverging list. Callers may still pass a
# different set explicitly (e.g. to also diagnose `unavailable_source`
# segments), since REQ-COVERAGE-001 does not mandate one universal gap
# vocabulary boundary for this purpose.
DEFAULT_GAP_STATES = frozenset({STATE_MISSING_EXPECTED, STATE_UNKNOWN})


def _week_count(period_start: str, period_end: str) -> int:
    start = date.fromisoformat(period_start)
    end = date.fromisoformat(period_end)
    return max(1, round((end - start).days / 7) + 1)


@dataclass(frozen=True)
class GapDiagnostics:
    """One classified gap (a single coverage-state run) for one variable.

    ``is_internal`` distinguishes a gap strictly inside the record's
    observed history from one touching (or beyond) its
    ``observed_start``/``observed_end`` edge - an edge gap is inherently
    riskier to estimate (no observed data on one side to anchor a fit) and
    is surfaced separately rather than folded into one boolean.
    """

    variable_id: str
    market: str
    gap_start: str
    gap_end: str
    state: str
    missing_week_count: int
    is_internal: bool
    is_at_start_of_history: bool
    is_at_end_of_history: bool
    overlapping_named_event_ids: tuple[str, ...] = ()
    spend_observed_during_gap: Optional[bool] = None
    delivery_observed_during_gap: Optional[bool] = None
    product: Optional[str] = None
    segment: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "variable_id": self.variable_id,
            "market": self.market,
            "gap_start": self.gap_start,
            "gap_end": self.gap_end,
            "state": self.state,
            "missing_week_count": self.missing_week_count,
            "is_internal": self.is_internal,
            "is_at_start_of_history": self.is_at_start_of_history,
            "is_at_end_of_history": self.is_at_end_of_history,
            "overlapping_named_event_ids": list(self.overlapping_named_event_ids),
            "spend_observed_during_gap": self.spend_observed_during_gap,
            "delivery_observed_during_gap": self.delivery_observed_during_gap,
            "product": self.product,
            "segment": self.segment,
        }


def _segment_overlaps(
    segment: CoverageSegment, other_period_start: str, other_period_end: str
) -> bool:
    return segment.period_start <= other_period_end and other_period_start <= segment.period_end


def _other_measure_covers_gap(
    companion: VariableCoverageRecord,
    gap: CoverageSegment,
    *,
    observed_like_states: frozenset[str],
) -> Optional[bool]:
    """`None` when the companion record has no segments at all overlapping
    this gap's window (no evidence either way) - never guessed as `False`."""
    overlapping = [
        seg
        for seg in companion.coverage_segments
        if _segment_overlaps(seg, gap.period_start, gap.period_end)
    ]
    if not overlapping:
        return None
    return any(seg.state in observed_like_states for seg in overlapping)


def diagnose_gaps(
    record: VariableCoverageRecord,
    *,
    gap_states: frozenset[str] = DEFAULT_GAP_STATES,
    named_event_occurrences: Sequence[NamedEventOccurrence] = (),
    spend_companion: Optional[VariableCoverageRecord] = None,
    delivery_companion: Optional[VariableCoverageRecord] = None,
    observed_like_states: frozenset[str] = frozenset({"observed_zero", "estimated", "modelled"}),
) -> tuple[GapDiagnostics, ...]:
    """Classify every gap-state run in ``record.coverage_segments``.

    ``spend_companion``/``delivery_companion`` let the caller cross-check
    "is spend observed when delivery is missing" (and vice versa) against
    another variable's own coverage record for the same market/product/
    segment - this function never assumes which variable is which; the
    caller decides. Passing neither leaves both fields ``None`` ("not
    assessed"), never guessed.

    A gap's overlap with a named event is scoped to
    ``occurrence.market_scope`` containing ``record.market`` (or the
    occurrence being scoped to every market via an empty/absent
    ``market_scope``, which ``NamedEventOccurrence`` does not permit - a
    truly universal event must be recorded once per relevant market, so no
    "all markets" wildcard needs to be special-cased here).
    """
    observed_start = record.observed_start
    observed_end = record.observed_end
    diagnostics: list[GapDiagnostics] = []
    for segment in record.coverage_segments:
        if segment.state not in gap_states:
            continue
        is_at_start = bool(observed_start) and segment.period_start <= (
            observed_start or ""
        )
        is_at_end = bool(observed_end) and segment.period_end >= (observed_end or "")
        overlapping_events = tuple(
            sorted(
                occurrence.event_id
                for occurrence in named_event_occurrences
                if record.market in occurrence.market_scope
                and segment.period_start <= occurrence.end_date
                and occurrence.start_date <= segment.period_end
            )
        )
        spend_observed = (
            _other_measure_covers_gap(
                spend_companion, segment, observed_like_states=observed_like_states
            )
            if spend_companion is not None
            else None
        )
        delivery_observed = (
            _other_measure_covers_gap(
                delivery_companion, segment, observed_like_states=observed_like_states
            )
            if delivery_companion is not None
            else None
        )
        diagnostics.append(
            GapDiagnostics(
                variable_id=record.variable_id,
                market=record.market,
                gap_start=segment.period_start,
                gap_end=segment.period_end,
                state=segment.state,
                missing_week_count=_week_count(segment.period_start, segment.period_end),
                is_internal=not (is_at_start or is_at_end),
                is_at_start_of_history=is_at_start,
                is_at_end_of_history=is_at_end,
                overlapping_named_event_ids=overlapping_events,
                spend_observed_during_gap=spend_observed,
                delivery_observed_during_gap=delivery_observed,
                product=record.product,
                segment=record.segment,
            )
        )
    return tuple(diagnostics)


# ---------------------------------------------------------------------------
# Estimation-evidence harness
# ---------------------------------------------------------------------------

ReconstructFn = Callable[[Sequence[str], Sequence[float], Sequence[str]], Sequence[float]]


@dataclass(frozen=True)
class HoldoutEvaluationResult:
    """One synthetic-holdout trial's reconstruction-error evidence for one
    candidate method. Never a verdict ("this method is valid") - only a
    measurement; `assess_estimation_readiness` is where a policy turns
    measurements into a readiness decision."""

    method_name: str
    method_description: str
    holdout_gap_length_weeks: int
    holdout_position: str
    holdout_start_week: str
    n_holdout_weeks: int
    reconstruction_error_mae: float
    reconstruction_error_mape: Optional[float]

    def to_dict(self) -> dict:
        return {
            "method_name": self.method_name,
            "method_description": self.method_description,
            "holdout_gap_length_weeks": self.holdout_gap_length_weeks,
            "holdout_position": self.holdout_position,
            "holdout_start_week": self.holdout_start_week,
            "n_holdout_weeks": self.n_holdout_weeks,
            "reconstruction_error_mae": self.reconstruction_error_mae,
            "reconstruction_error_mape": self.reconstruction_error_mape,
        }


def _mae(true: Sequence[float], predicted: Sequence[float]) -> float:
    return sum(abs(t - p) for t, p in zip(true, predicted)) / len(true)


def _mape(true: Sequence[float], predicted: Sequence[float]) -> Optional[float]:
    if any(t == 0 for t in true):
        return None
    return sum(abs((t - p) / t) for t, p in zip(true, predicted)) / len(true) * 100.0


def evaluate_candidate_reconstruction_method(
    observed_weeks: Sequence[str],
    observed_values: Sequence[float],
    *,
    method_name: str,
    method_description: str,
    reconstruct: ReconstructFn,
    holdout_gap_lengths: Sequence[int] = (1, 2, 4, 8),
    holdout_positions: Sequence[str] = ("start", "middle", "end"),
) -> tuple[HoldoutEvaluationResult, ...]:
    """Evaluate ``reconstruct`` against synthetic holdout gaps carved out of
    already-``observed_weeks``/``observed_values`` (both must already be
    real, fully-observed data - carving a synthetic gap out of a period
    that is itself uncertain would contaminate the evidence).

    For each requested ``(gap_length, position)`` combination that fits
    inside the observed series, this: (1) removes those weeks' values,
    (2) calls ``reconstruct(remaining_weeks, remaining_values,
    held_out_weeks)`` to get candidate reconstructions, (3) scores MAE (and
    MAPE, when no true value is exactly zero) against the real, known
    values. A combination that doesn't fit inside the series (gap longer
    than the whole history, or a position not reachable at that length) is
    silently skipped, never padded or approximated.

    ``reconstruct`` is entirely caller-supplied - this harness proposes,
    hard-codes, or approves no specific imputation formula.
    """
    n = len(observed_weeks)
    if n != len(observed_values):
        raise ValueError("observed_weeks and observed_values must be the same length.")
    if n == 0:
        return ()

    results: list[HoldoutEvaluationResult] = []
    for gap_length in holdout_gap_lengths:
        if gap_length <= 0 or gap_length >= n:
            continue
        for position in holdout_positions:
            if position == "start":
                start_index = 0
            elif position == "end":
                start_index = n - gap_length
            elif position == "middle":
                start_index = (n - gap_length) // 2
            else:
                raise ValueError(f"Unknown holdout_position {position!r}.")
            end_index = start_index + gap_length
            if start_index < 0 or end_index > n:
                continue

            held_out_weeks = list(observed_weeks[start_index:end_index])
            held_out_true = list(observed_values[start_index:end_index])
            remaining_weeks = list(observed_weeks[:start_index]) + list(
                observed_weeks[end_index:]
            )
            remaining_values = list(observed_values[:start_index]) + list(
                observed_values[end_index:]
            )
            if not remaining_weeks:
                continue

            predicted = list(
                reconstruct(remaining_weeks, remaining_values, held_out_weeks)
            )
            if len(predicted) != len(held_out_true):
                raise ValueError(
                    f"reconstruct() for method {method_name!r} returned "
                    f"{len(predicted)} value(s) for {len(held_out_true)} "
                    "held-out week(s)."
                )
            results.append(
                HoldoutEvaluationResult(
                    method_name=method_name,
                    method_description=method_description,
                    holdout_gap_length_weeks=gap_length,
                    holdout_position=position,
                    holdout_start_week=held_out_weeks[0],
                    n_holdout_weeks=gap_length,
                    reconstruction_error_mae=_mae(held_out_true, predicted),
                    reconstruction_error_mape=_mape(held_out_true, predicted),
                )
            )
    return tuple(results)


@dataclass(frozen=True)
class EstimationEvidenceSummary:
    """One activity/variable's collected holdout evidence across every
    candidate method evaluated for it - the artefact
    ``assess_estimation_readiness`` consumes, and what an analyst reviews
    before deciding whether to trust an estimate. ``recommendation`` is
    free text and never a verdict field - this module does not decide
    whether the evidence is "good enough"; that is exactly what a
    ``EstimationReadinessPolicy`` (analyst/Finance-owned) is for."""

    variable_id: str
    market: str
    evaluated_at: str
    n_observed_weeks_used: int
    results: tuple[HoldoutEvaluationResult, ...]
    recommendation: str = ""

    def worst_mae_for_gap_length(self, gap_length: int) -> Optional[float]:
        matching = [
            r.reconstruction_error_mae
            for r in self.results
            if r.holdout_gap_length_weeks == gap_length
        ]
        return max(matching) if matching else None

    def to_dict(self) -> dict:
        return {
            "variable_id": self.variable_id,
            "market": self.market,
            "evaluated_at": self.evaluated_at,
            "n_observed_weeks_used": self.n_observed_weeks_used,
            "results": [r.to_dict() for r in self.results],
            "recommendation": self.recommendation,
        }


# ---------------------------------------------------------------------------
# Fail-closed readiness gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EstimationReadinessPolicy:
    """An explicit, attributable readiness policy - never a hard-coded
    default (REQ-COVERAGE-001's "Out of scope" explicitly withholds
    approval of any specific validation threshold or coverage-percentage
    cutoff). ``is_recommendation_only=True`` (the default) means this
    policy has not been formally adopted by Product/Finance - it may still
    be *used* to get a deterministic readiness read during review, but a
    dependent gate should not silently treat an unadopted policy's
    ``blocked_*``/``estimable_with_evidence`` result as an official
    approval gate. Every ``max_*`` field left `None` means "no limit
    configured for this dimension" - it does not mean "no limit," it means
    that dimension is not checked, so leaving every field `None` produces
    a policy that allows everything (an explicit, visible choice, not a
    silent default)."""

    policy_id: str
    max_missing_week_count: Optional[int] = None
    max_consecutive_missing_run: Optional[int] = None
    allow_edge_gaps: bool = False
    max_reconstruction_error_mape: Optional[float] = None
    owner: str = ""
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    is_recommendation_only: bool = True

    def __post_init__(self) -> None:
        if not self.policy_id:
            raise ValueError("EstimationReadinessPolicy requires a policy_id.")
        for field_name in ("max_missing_week_count", "max_consecutive_missing_run"):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must be non-negative.")
        if self.max_reconstruction_error_mape is not None and (
            self.max_reconstruction_error_mape < 0
        ):
            raise ValueError("max_reconstruction_error_mape must be non-negative.")
        if not self.is_recommendation_only and not (self.approved_by and self.approved_at):
            raise ValueError(
                "A policy that is not recommendation-only requires "
                "approved_by and approved_at (mirrors "
                "core.coverage.DefinitionBreak's approval-requires-"
                "attribution pattern)."
            )

    def to_dict(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "max_missing_week_count": self.max_missing_week_count,
            "max_consecutive_missing_run": self.max_consecutive_missing_run,
            "allow_edge_gaps": self.allow_edge_gaps,
            "max_reconstruction_error_mape": self.max_reconstruction_error_mape,
            "owner": self.owner,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "is_recommendation_only": self.is_recommendation_only,
        }


READINESS_BLOCKED_NO_POLICY = "blocked_no_policy"
READINESS_BLOCKED_EDGE_GAP = "blocked_edge_gap"
READINESS_BLOCKED_EXCEEDS_MISSING_WEEK_COUNT = "blocked_exceeds_missing_week_count"
READINESS_BLOCKED_EXCEEDS_CONSECUTIVE_RUN = "blocked_exceeds_consecutive_run"
READINESS_BLOCKED_NO_EVIDENCE = "blocked_no_evidence"
READINESS_BLOCKED_EXCEEDS_RECONSTRUCTION_ERROR = "blocked_exceeds_reconstruction_error"
READINESS_ESTIMABLE_WITH_EVIDENCE = "estimable_with_evidence"

READINESS_STATUSES = (
    READINESS_BLOCKED_NO_POLICY,
    READINESS_BLOCKED_EDGE_GAP,
    READINESS_BLOCKED_EXCEEDS_MISSING_WEEK_COUNT,
    READINESS_BLOCKED_EXCEEDS_CONSECUTIVE_RUN,
    READINESS_BLOCKED_NO_EVIDENCE,
    READINESS_BLOCKED_EXCEEDS_RECONSTRUCTION_ERROR,
    READINESS_ESTIMABLE_WITH_EVIDENCE,
)


@dataclass(frozen=True)
class EstimationReadinessResult:
    status: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"status": self.status, "reasons": list(self.reasons)}


def assess_estimation_readiness(
    diagnostics: GapDiagnostics,
    *,
    policy: Optional[EstimationReadinessPolicy],
    evidence: Optional[EstimationEvidenceSummary] = None,
) -> EstimationReadinessResult:
    """Fail-closed gate: `policy=None` always blocks (never a silently
    permissive default). When a policy is supplied, checks - in order,
    stopping at the first failure - the gap's edge/internal position,
    missing-week count, longest consecutive run, then (only if evidence
    was supplied) the worst reconstruction error at this gap's length.
    Missing evidence for an otherwise-in-policy gap blocks rather than
    silently permitting estimation with no measured error at all.
    """
    if policy is None:
        return EstimationReadinessResult(
            status=READINESS_BLOCKED_NO_POLICY,
            reasons=(
                "No estimation readiness policy is configured - "
                "REQ-COVERAGE-001 does not approve a universal missing-"
                "week threshold, so this gate never assumes one.",
            ),
        )

    if not diagnostics.is_internal and not policy.allow_edge_gaps:
        return EstimationReadinessResult(
            status=READINESS_BLOCKED_EDGE_GAP,
            reasons=(
                f"Gap {diagnostics.gap_start}..{diagnostics.gap_end} touches "
                "the start or end of observed history and "
                f"policy {policy.policy_id!r} does not allow edge gaps.",
            ),
        )

    if (
        policy.max_missing_week_count is not None
        and diagnostics.missing_week_count > policy.max_missing_week_count
    ):
        return EstimationReadinessResult(
            status=READINESS_BLOCKED_EXCEEDS_MISSING_WEEK_COUNT,
            reasons=(
                f"{diagnostics.missing_week_count} missing week(s) exceeds "
                f"policy {policy.policy_id!r}'s max_missing_week_count="
                f"{policy.max_missing_week_count}.",
            ),
        )

    if (
        policy.max_consecutive_missing_run is not None
        and diagnostics.missing_week_count > policy.max_consecutive_missing_run
    ):
        return EstimationReadinessResult(
            status=READINESS_BLOCKED_EXCEEDS_CONSECUTIVE_RUN,
            reasons=(
                f"{diagnostics.missing_week_count}-week consecutive run "
                f"exceeds policy {policy.policy_id!r}'s "
                f"max_consecutive_missing_run={policy.max_consecutive_missing_run}.",
            ),
        )

    if policy.max_reconstruction_error_mape is not None:
        if evidence is None:
            return EstimationReadinessResult(
                status=READINESS_BLOCKED_NO_EVIDENCE,
                reasons=(
                    f"Policy {policy.policy_id!r} requires reconstruction-"
                    "error evidence, but none was supplied for this gap.",
                ),
            )
        worst_mape = max(
            (
                r.reconstruction_error_mape
                for r in evidence.results
                if r.reconstruction_error_mape is not None
            ),
            default=None,
        )
        if worst_mape is None:
            return EstimationReadinessResult(
                status=READINESS_BLOCKED_NO_EVIDENCE,
                reasons=(
                    f"Policy {policy.policy_id!r} requires reconstruction-"
                    "error evidence, but no candidate method's MAPE could "
                    "be computed (every holdout window included a true "
                    "zero value).",
                ),
            )
        if worst_mape > policy.max_reconstruction_error_mape:
            return EstimationReadinessResult(
                status=READINESS_BLOCKED_EXCEEDS_RECONSTRUCTION_ERROR,
                reasons=(
                    f"Worst observed holdout MAPE {worst_mape:.1f}% exceeds "
                    f"policy {policy.policy_id!r}'s "
                    f"max_reconstruction_error_mape="
                    f"{policy.max_reconstruction_error_mape:.1f}%.",
                ),
            )

    return EstimationReadinessResult(
        status=READINESS_ESTIMABLE_WITH_EVIDENCE,
        reasons=(),
    )
