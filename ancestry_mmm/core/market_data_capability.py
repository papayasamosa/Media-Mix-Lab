"""
REQ-COVERAGE-001 S6: whether the current PyMC hierarchical/market-specific
engine's rectangular market x channel data requirement is validly satisfied
for a given `ModelSpec`'s markets/channels, using the governed variable
coverage matrix (`core.coverage`) as the sole source of truth for
per-(market, channel) support - never inferring support from the prepared
data's own zero/null values (REQ-COVERAGE-001 S1: "missing is not zero").

`core.hierarchical_model.build_fh_hierarchical_model` and
`core.market_specific_model.build_fh_market_specific_model` both consume a
single `X_media` matrix built from `data.preprocessor.prepare_fh_modeling_
frame`, where `spec.channels` supplies one shared column set applied to
every market's rows (`market_bounds` only slices which *rows* belong to
which market, never which *columns* apply). The engine therefore only
validly supports the rectangular case: every requested channel genuinely
observed, for every requested market. `FR-MOD-015` (market-specific/ragged
predictor sets - letting a market skip a channel it never had, without
fabricating a zero/observed value for it) is explicitly **not resolved**
here (REQ-COVERAGE-001 S6): no masking strategy, missing-data likelihood,
or per-market predictor-set restructuring is implemented or approved by
this module. It only reports whether the rectangular subset already
supported today is satisfied, and if not, exactly which (market, channel)
cells are missing governed support and what decision closing that gap
would require - mirroring `core.graph_model_compiler.check_engine_
capability`'s shape (REQ-GRAPH-001) for the same reason: never silently
drop, approximate, or mask what the engine cannot express; always name the
specific unsupported cells rather than a bare rejection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .coverage import (
    STATE_ESTIMATED,
    STATE_MODELLED,
    VariableCoverageMatrix,
    VariableCoverageRecord,
)
from .missing_media_evidence import (
    READINESS_ESTIMABLE_WITH_EVIDENCE,
    EstimationEvidenceSummary,
    EstimationReadinessPolicy,
    assess_estimation_readiness,
    diagnose_gaps,
)

_ESTIMATION_OVERRIDABLE_STATES = frozenset({STATE_ESTIMATED, STATE_MODELLED})

ENGINE_PYMC_RECTANGULAR = "pymc_hierarchical_rectangular"

# REQ-COVERAGE-001 S6 point 4: "surface, as a report rather than a silent
# choice, the exact modelling decision required to implement FR-MOD-015
# fully." Fixed text, not a template with any invented specifics filled
# in - the actual decision (which masking/likelihood/restructuring
# approach) is exactly what this record declines to invent.
FR_MOD_015_DECISION_REPORT = (
    "FR-MOD-015 (market-specific/ragged predictor sets) is not resolved by "
    "REQ-COVERAGE-001 S6 - no masking strategy, missing-data likelihood, "
    "zeroing convention, or per-market predictor-set restructuring is "
    "approved. Closing the gap listed above requires a separately-approved "
    "modelling decision for how the likelihood should treat an observation "
    "cell for a (market, channel) pair with no genuine coverage - for "
    "example (not a recommendation, just naming the shape of the decision "
    "needed): a masked/marginalised likelihood term for that cell, "
    "restructuring X_media/market_bounds construction so each market "
    "supplies only its own supported channel subset instead of one shared "
    "column set, or an explicit, governed zero-fill convention with its "
    "own recorded assumptions. See the brief's Work Package 5."
)


@dataclass(frozen=True)
class MarketChannelCapabilityIssue:
    """One (market, channel) cell the current engine cannot validly
    include in a rectangular fit, and why."""

    market: str
    channel: str
    reason: str

    def to_dict(self) -> dict:
        return {"market": self.market, "channel": self.channel, "reason": self.reason}


@dataclass(frozen=True)
class EngineCapabilityResult:
    """A deterministic report of whether `engine` can validly fit
    `markets` x `channels` today (REQ-COVERAGE-001 S6 point 3: "a
    deterministic engine-capability result - labelling the unsupported
    request exploratory/unsupported"). `supported=True` iff every
    requested (market, channel) cell has governed, officially-resolved
    coverage - never iff the prepared data merely contains no nulls,
    which would silently trust a zero-filled or otherwise fabricated
    value the same way REQ-COVERAGE-001 forbids elsewhere.

    `recommendation_only_notes` (UK FH MMM brief, 2026-09-10, review
    follow-up) holds the same shape of finding as `issues`, but produced
    by an `EstimationReadinessPolicy` with `is_recommendation_only=True`
    (Product/Finance has not adopted it) - it is diagnostic only and
    never affects `supported`. Only a policy with `is_recommendation_
    only=False` (which itself requires `approved_by`/`approved_at`) can
    ever contribute to `issues`."""

    engine: str
    markets: Tuple[str, ...]
    channels: Tuple[str, ...]
    issues: Tuple[MarketChannelCapabilityIssue, ...]
    recommendation_only_notes: Tuple[MarketChannelCapabilityIssue, ...] = ()

    @property
    def supported(self) -> bool:
        return not self.issues

    @property
    def decision_report(self) -> str:
        """REQ-COVERAGE-001 S6 point 4's report - only meaningful, and
        only ever non-empty, when `issues` is non-empty; a fully-supported
        request has no gap for FR-MOD-015 to close."""
        return FR_MOD_015_DECISION_REPORT if self.issues else ""

    def to_dict(self) -> dict:
        return {
            "engine": self.engine,
            "markets": list(self.markets),
            "channels": list(self.channels),
            "supported": self.supported,
            "issues": [issue.to_dict() for issue in self.issues],
            "recommendation_only_notes": [
                note.to_dict() for note in self.recommendation_only_notes
            ],
            "decision_report": self.decision_report,
        }


def check_market_channel_capability(
    markets: Sequence[str],
    channels: Sequence[str],
    coverage_matrix: Optional[VariableCoverageMatrix],
    *,
    engine: str = ENGINE_PYMC_RECTANGULAR,
    estimation_readiness_policy: Optional[EstimationReadinessPolicy] = None,
    estimation_evidence_by_variable: Optional[
        Mapping[Tuple[str, str], EstimationEvidenceSummary]
    ] = None,
) -> EngineCapabilityResult:
    """
    REQ-COVERAGE-001 S6 points 1-3: compile the rectangular (market,
    channel) subset `engine` already validly supports, using `coverage_matrix`
    (built on the Data Coverage page, `core.coverage.build_coverage_matrix_
    from_frame`) as the sole source of truth - never the prepared data's own
    values. A (market, channel) cell is unsupported when either:

    - no `VariableCoverageRecord` exists at all for that `(channel, market)`
      pair (REQ-COVERAGE-001 S3: "every candidate model must expose a
      variable coverage matrix before fitting" - a channel the coverage
      matrix was never built for cannot be certified as genuinely
      observed, whatever values happen to sit in the prepared frame); or
    - any matching record's `has_unapproved_non_observed_coverage` is true.
      Deliberately broader than `is_officially_unresolved` (REQ-COVERAGE-001
      S5's narrower "unknown/missing_expected must not become official fit
      input silently" check for the Data Coverage review UI): this capability
      report needs "is every segment a genuinely observed, directly usable
      number", so `not_applicable`/`unavailable_source`/`suppressed`/
      `estimated`/`modelled` all count as unsupported the same way `unknown`/
      `missing_expected` do (REQ-COVERAGE-001 S1: "missing is not zero",
      "unavailable source is not zero", "not applicable is not zero"; S2: "a
      latent/modelled value must never be stored or displayed as though it
      were an observed source fact") - unless the record has an explicit
      `approved_for_official_use` treatment.

    UK FH MMM brief (2026-09-10) Workstream D follow-up: `approved_for_
    official_use=True` alone still suffices exactly as before when
    `estimation_readiness_policy` is not supplied - this preserves every
    existing caller's behaviour byte-for-byte (REQ-COVERAGE-002 does not
    retroactively tighten an approval that already went through governance
    with no policy concept). When a policy *is* supplied, an `estimated`/
    `modelled` segment on an otherwise-approved record is additionally
    required to pass `missing_media_evidence.assess_estimation_readiness`
    (using `diagnose_gaps` on that same record, scoped to exactly those two
    states, plus whatever evidence `estimation_evidence_by_variable` supplies
    for this exact `(variable_id, market)` pair - evidence is never looked
    up by `variable_id` alone, so evidence measured in one market can never
    approve or block the same variable in another market) - "analyst-
    approved" and "policy-evidenced" are both
    required together once a policy exists, never either one alone
    overriding the other. `unknown`/`missing_expected`/`not_applicable`/
    `unavailable_source`/`suppressed` segments are never eligible for this
    override regardless of policy - a policy only re-examines a state an
    analyst has *already* explicitly marked `estimated`/`modelled`, never a
    genuinely unresolved or out-of-scope one.

    A policy with `is_recommendation_only=True` (the default - Product/
    Finance has not adopted it) is still evaluated for a deterministic
    read, but any resulting finding is routed to `EngineCapabilityResult.
    recommendation_only_notes`, never `issues` - it must never gate
    `supported`. Only a policy with `is_recommendation_only=False` (which
    itself requires `approved_by`/`approved_at`) can block.

    When a coverage matrix has product/segment-scoped records for the same
    (channel, market) key (the Data Coverage page's optional `product_col`/
    `segment_col` grouping), *every* matching record must be resolved for
    the cell to count as supported - channels are not product/segment-
    scoped in `ModelSpec`, so there is no approved rule here for picking
    only one of several scoped records to trust; requiring all of them
    resolved is the fail-closed reading, not an invented one.

    `coverage_matrix=None` (no matrix built yet at all) marks every
    requested cell unsupported - "no coverage matrix" is never treated as
    "no problem, assume support".
    """
    markets = tuple(markets)
    channels = tuple(channels)
    issues: List[MarketChannelCapabilityIssue] = []
    recommendation_only_notes: List[MarketChannelCapabilityIssue] = []

    if coverage_matrix is None:
        issues.extend(
            MarketChannelCapabilityIssue(
                market=market,
                channel=channel,
                reason=(
                    "No coverage matrix has been built yet (REQ-COVERAGE-001 "
                    "S3: every candidate model must expose a variable "
                    "coverage matrix before fitting) - build one on the Data "
                    "Coverage page first."
                ),
            )
            for market in markets
            for channel in channels
        )
        return EngineCapabilityResult(
            engine=engine, markets=markets, channels=channels, issues=tuple(issues)
        )

    records_by_channel_market: Dict[Tuple[str, str], List[VariableCoverageRecord]] = {}
    for record in coverage_matrix.records:
        records_by_channel_market.setdefault(
            (record.variable_id, record.market), []
        ).append(record)

    for market in markets:
        for channel in channels:
            matching = records_by_channel_market.get((channel, market), [])
            if not matching:
                issues.append(
                    MarketChannelCapabilityIssue(
                        market=market,
                        channel=channel,
                        reason=(
                            f"No coverage record for '{channel}' in market "
                            f"'{market}' - the engine's rectangular X_media "
                            "requires governed coverage for every requested "
                            "channel in every requested market."
                        ),
                    )
                )
                continue
            unresolved = [r for r in matching if r.has_unapproved_non_observed_coverage]
            if unresolved:
                issues.append(
                    MarketChannelCapabilityIssue(
                        market=market,
                        channel=channel,
                        reason=(
                            f"'{channel}' in market '{market}' has coverage that "
                            "is not a genuinely observed number (or approved "
                            "for official use) for every segment - unresolved "
                            "unknown/missing_expected coverage, or a "
                            "not_applicable/unavailable_source/suppressed/"
                            "estimated/modelled segment without an approved "
                            "treatment, must not become official fit input "
                            "silently (REQ-COVERAGE-001 S1, S2, S5)."
                        ),
                    )
                )
                continue
            if estimation_readiness_policy is not None:
                policy_reason = _estimation_policy_blocking_reason(
                    matching,
                    policy=estimation_readiness_policy,
                    evidence_by_variable=estimation_evidence_by_variable or {},
                )
                if policy_reason:
                    issue = MarketChannelCapabilityIssue(
                        market=market, channel=channel, reason=policy_reason
                    )
                    # An unadopted (`is_recommendation_only=True`) policy
                    # may be *used* to get a deterministic read during
                    # review, but it has not gone through Product/Finance
                    # approval - it must never gate the official
                    # capability result the same way an adopted policy
                    # does. Its finding is still surfaced, just as a
                    # diagnostic note rather than a blocking issue.
                    if estimation_readiness_policy.is_recommendation_only:
                        recommendation_only_notes.append(issue)
                    else:
                        issues.append(issue)

    return EngineCapabilityResult(
        engine=engine,
        markets=markets,
        channels=channels,
        issues=tuple(issues),
        recommendation_only_notes=tuple(recommendation_only_notes),
    )


def _estimation_policy_blocking_reason(
    records: Sequence[VariableCoverageRecord],
    *,
    policy: EstimationReadinessPolicy,
    evidence_by_variable: Mapping[Tuple[str, str], EstimationEvidenceSummary],
) -> str:
    """UK FH MMM brief (2026-09-10) Workstream D follow-up: for every
    approved record with an `estimated`/`modelled` segment, additionally
    require `assess_estimation_readiness` to agree once a policy is
    supplied. Returns `""` (no block) when every such segment passes, or a
    specific, attributable reason naming the first one that does not.
    `evidence_by_variable` is keyed by `(variable_id, market)`, never
    `variable_id` alone - a record's own `market` is always used for the
    lookup, so evidence collected for one market is never applied to the
    same `variable_id` in a different market."""
    for record in records:
        estimated_gaps = diagnose_gaps(
            record, gap_states=_ESTIMATION_OVERRIDABLE_STATES
        )
        if not estimated_gaps:
            continue
        evidence = evidence_by_variable.get((record.variable_id, record.market))
        for gap in estimated_gaps:
            result = assess_estimation_readiness(gap, policy=policy, evidence=evidence)
            if result.status != READINESS_ESTIMABLE_WITH_EVIDENCE:
                reason = "; ".join(result.reasons) or result.status
                return (
                    f"'{record.variable_id}' has an approved {gap.state} segment "
                    f"({gap.gap_start}..{gap.gap_end}) that does not meet policy "
                    f"{policy.policy_id!r}'s estimation-readiness requirement: "
                    f"{reason}"
                )
    return ""
