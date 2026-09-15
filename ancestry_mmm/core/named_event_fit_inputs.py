"""Production-integration glue: wires the governed named-event registry
(`core.named_events`) and the approved S3 regularised-spline-basis
statistical method (`core.named_event_response`, Decision 12) into a real
model-fitting call (`core.hierarchical_model.build_fh_hierarchical_model`'s
optional `named_event_fit_inputs` parameter).

`core.named_event_response`'s own decision record
(`docs/named_event_response_method_decision_record.md`) explicitly scopes
itself to "the deterministic basis-construction and window-policy contract
only," naming the actual model-fitting wiring as "a separate, materially
statistical follow-up requiring its own synthetic-recovery validation on
the ACTUAL family windows chosen [t]here" as the next reasonable step, not
performed there. This module is that follow-up's *construction* half; the
*validation* half is `ancestry_mmm/tests/test_named_event_response_
recovery_posterior.py` (real `pm.sample` NUTS recovery against a planted
synthetic event effect, mirroring `core.search_candidate_a_recovery`'s own
precedent for exactly this kind of production-integration evidence).

Nothing here invents a new statistical mechanism: `build_named_event_fit_
inputs` only calls `core.named_event_response`'s own
`build_event_relative_design_matrix`/`build_spline_basis` functions, over
the registry's own factual occurrence dates
(`core.named_events.NamedEventOccurrence.start_date`/`end_date`, never
shifted) and each family's own approved
`EventResponseDefinition.max_lead`/`max_lag` window - never a new kernel,
a different window, or a business date invented here.

**Explicit per-family opt-in gate** (mirrors Decision 11's identical guard
on `core.experiment_lift_test_mapping` - "registering an event/experiment
must never silently calibrate a model"): a family is consumed at fit time
only when its current `EventResponseDefinition.transformation_method_
reference` exactly equals `NAMED_EVENT_RESPONSE_STRUCTURE`
(`"S3_regularised_spline_basis"`). A response definition with any other
(or blank) reference - which is every response definition registered
before this module existed, and remains the default for any new one -
stays registered metadata only, exactly as before: `build_named_event_
fit_inputs` returns `None` (not an empty-but-present object) whenever
nothing in the registry opts in, so a caller can treat "no named events
configured" and "no named events opted in yet" identically to "no fit
inputs supplied at all" - `core.hierarchical_model.build_fh_hierarchical_
model(..., named_event_fit_inputs=None)` (the default) reproduces exactly
today's behaviour, byte-for-byte, for every project that does not
explicitly opt a family in.

**Pooling default** (Decision 12, dimension 4 - "unpooled per market/
family by default; partial pooling ... permitted only when repeated-event
support and validation justify it", and `core.named_event_response.
assess_family_pooling_eligibility` fails closed with no approved
threshold): each `(market, family)` combination present in the data gets
its own independent spline-coefficient block (`NamedEventFamilyFitBlock`),
never a coefficient shared across markets. Coefficients within one family
DO share one family-level shrinkage scale (`tau`) across every market that
family occurs in - a disclosed, reasonable default this module makes
(no existing record specifies whether `tau` is per-family or global; the
per-family choice keeps one family's window/amplitude from being
regularised by an unrelated family's evidence, which a single global
`tau` would do).

**Outcome scope**: an empty `EventResponseDefinition.outcome_scope` is
treated as "applies to every fitted outcome" - a disclosed choice this
module makes (no existing consumer of any `*_scope` field in this
repository establishes an empty-means-what convention to follow instead),
chosen as the least-surprising default (an analyst who does not restrict
scope should not have their event silently excluded from every outcome).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .named_event_response import (
    EVENT_RESPONSE_SHRINKAGE_PRIOR_DEFAULT_SCALE,
    NAMED_EVENT_RESPONSE_STRUCTURE,
    build_event_relative_design_matrix,
    build_spline_basis,
)
from .named_events import (
    EventResponseDefinition,
    NamedEventFamily,
    NamedEventOccurrence,
    current_family_versions,
    current_occurrence_versions,
    current_response_definition_versions,
)

NAMED_EVENT_FIT_INPUTS_VERSION = "named-event-fit-inputs-v1"


@dataclass(frozen=True)
class NamedEventFamilyFitBlock:
    """One `(market, family)`'s spline-basis design matrix, already
    embedded into this fit's full `(n_obs, n_basis)` row range (zero
    outside that market's own rows - `core.hierarchical_model`'s
    `market_bounds` convention) - ready to `pm.math.dot` with a
    `pm.Normal` coefficient vector of width `design.shape[1]`. `n_basis`
    matches `core.named_event_response.build_spline_basis`'s own output
    width for this family's governed window."""

    family_id: str
    market: str
    design: np.ndarray
    response_definition_id: str
    response_definition_version: int
    outcome_scope: Tuple[str, ...]
    # The family's own governed classification at fit time (e.g. "gifting")
    # - diagnostic provenance only (implementation brief: "make named-event
    # diagnostics fit-time provenance aware"), never consumed by the PyMC
    # graph and deliberately excluded from `fingerprint()` below (a pure
    # reclassification with no design/definition change is a real, distinct
    # drift reason - not the same thing as a design-affecting change, so it
    # is compared directly by diagnostics rather than folded into one opaque
    # hash). Defaults to "" so this remains a purely additive field.
    classification: str = ""


@dataclass(frozen=True)
class NamedEventFitInputs:
    """Production-integration inputs for `core.hierarchical_model.
    build_fh_hierarchical_model`'s optional `named_event_fit_inputs`
    parameter - everything the additive event-response `eta` term needs
    beyond what the ordinary builder already computes from `frame`/
    `spec`, mirroring `core.search_capacity.CandidateASearchFitInputs`'s
    own "production-integration inputs" naming and role."""

    blocks: Tuple[NamedEventFamilyFitBlock, ...]
    shrinkage_prior_scale_by_family: Mapping[str, float]
    version: str = NAMED_EVENT_FIT_INPUTS_VERSION

    @property
    def family_ids(self) -> Tuple[str, ...]:
        seen: List[str] = []
        for block in self.blocks:
            if block.family_id not in seen:
                seen.append(block.family_id)
        return tuple(seen)

    def blocks_for_family(self, family_id: str) -> Tuple[NamedEventFamilyFitBlock, ...]:
        return tuple(b for b in self.blocks if b.family_id == family_id)

    def consumed_response_definitions(self) -> Tuple[Tuple[str, int], ...]:
        """`(response_definition_id, response_definition_version)` pairs
        actually consumed at fit time, in first-seen order - for
        `FHModelMeta`'s fit-time provenance record (mirrors
        `causal_graph_id`/`causal_graph_version`'s own "which governed
        identity was actually authoritative for this fit" pattern)."""
        seen: List[Tuple[str, int]] = []
        for block in self.blocks:
            pair = (block.response_definition_id, block.response_definition_version)
            if pair not in seen:
                seen.append(pair)
        return tuple(seen)

    def consumed_family_classifications(self) -> Tuple[Tuple[str, str], ...]:
        """`(family_id, classification)` pairs for every family actually
        consumed at fit time, deduplicated and sorted by `family_id` -
        the governance identity `fingerprint()` below deliberately
        excludes (see `NamedEventFamilyFitBlock.classification`'s own
        docstring). Feeds `named_event_classification_fingerprint`
        below, which `core.fingerprint.fingerprint_model_spec` combines
        alongside `fingerprint()`'s numerical design identity as a
        SEPARATE component, so a classification change (e.g. gifting ->
        promotion) participates in official model staleness
        (`REQ-EVENT-001` section 8) even when it changes nothing about
        the fitted design shape."""
        seen: Dict[str, str] = {}
        for block in self.blocks:
            seen.setdefault(block.family_id, block.classification)
        return tuple(sorted(seen.items()))

    def fingerprint(self) -> str:
        """Fingerprint the exact event design consumed by a model fit.

        Event occurrences and response-definition windows determine the
        design matrix, so both the matrix and its governed provenance are
        included.  This is intentionally separate from replay inputs: a
        future occurrence may change a replay basis without changing the
        historical fit identity.
        """
        payload = {
            "version": self.version,
            "shrinkage_prior_scale_by_family": dict(
                sorted(self.shrinkage_prior_scale_by_family.items())
            ),
            "blocks": [
                {
                    "family_id": block.family_id,
                    "market": block.market,
                    "design": block.design.tolist(),
                    "response_definition_id": block.response_definition_id,
                    "response_definition_version": block.response_definition_version,
                    "outcome_scope": list(block.outcome_scope),
                }
                for block in self.blocks
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def named_event_classification_fingerprint(
    fit_inputs: Optional[NamedEventFitInputs],
) -> str:
    """Deterministic fingerprint over the governed `classification` of
    every family actually consumed at fit time (`fit_inputs.consumed_
    family_classifications()`) - the SEPARATE governance component
    `core.fingerprint.fingerprint_model_spec`'s own `named_event_
    classification_fingerprint` parameter combines alongside `NamedEvent
    FitInputs.fingerprint()`'s numerical design identity, so `REQ-EVENT-
    001` section 8's "changing... family mapping [classification]...
    must stale the affected fit" is enforced through the model's own
    official fingerprint - never merely shown as an informational
    Diagnostics-only difference (see `core.named_event_diagnostics.
    assess_named_event_drift`, which reports the same kind of change for
    display purposes only and does not itself participate in official
    staleness). `fit_inputs=None` (no named event consumed) fingerprints
    identically to an empty tuple, matching every other named-event
    field's "no event" convention - callers pass the resulting value to
    `fingerprint_model_spec` exactly like `named_event_fit_fingerprint`
    (falsy is omitted from the payload, never invalidating an approval
    that consumed no named event)."""
    pairs = (
        fit_inputs.consumed_family_classifications() if fit_inputs is not None else ()
    )
    payload = {"family_classifications": [list(pair) for pair in pairs]}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def named_event_fingerprint_components(
    fit_inputs: Optional[NamedEventFitInputs],
) -> Tuple[Optional[str], Optional[str]]:
    """The exact `(named_event_fit_fingerprint, named_event_
    classification_fingerprint)` pair every `core.fingerprint.
    fingerprint_model_spec` call site must pass - built once, here, so
    the two can never be computed inconsistently (e.g. one page passing
    the design fingerprint but forgetting the classification one, or
    computing it a different way) across Model Training, Diagnostics,
    Curve Bank, Scenario Planner, Project Export and Official Curve
    Generation. Both are `None` (never an empty-but-present value) when
    `fit_inputs` is `None` - the same "opt-in, omitted entirely when no
    named event is consumed" contract `fingerprint_model_spec` already
    applies to both fields."""
    if fit_inputs is None:
        return None, None
    return fit_inputs.fingerprint(), (
        named_event_classification_fingerprint(fit_inputs) or None
    )


def current_named_event_identity_fingerprints(
    frame: Mapping[str, Any],
    *,
    families: Sequence[NamedEventFamily],
    occurrences: Sequence[NamedEventOccurrence],
    response_definitions: Sequence[EventResponseDefinition],
) -> Tuple[Optional[str], Optional[str]]:
    """Convenience one-shot for a caller that only needs the fingerprint
    pair (not the full `NamedEventFitInputs` object) for the CURRENT
    governed registry against `frame`: builds `NamedEventFitInputs` via
    `build_named_event_fit_inputs` (current registry, never a
    fit-time-pinned replay - this is "what would be consumed if
    prepared/fitted again right now", the same semantics `core.
    named_event_diagnostics.build_named_event_diagnostics`'s readiness
    view and `pages/06_Diagnostics.py`'s `current_model_identity` both
    already use), then returns `named_event_fingerprint_components`'s
    pair. A caller that already has a built `NamedEventFitInputs` for
    another reason (e.g. `pages/05_Model_Training.py`, which also passes
    it as a fit build kwarg) should call `named_event_fingerprint_
    components` directly on that object instead of rebuilding it here."""
    fit_inputs = build_named_event_fit_inputs(
        frame,
        families=families,
        occurrences=occurrences,
        response_definitions=response_definitions,
    )
    return named_event_fingerprint_components(fit_inputs)


def build_named_event_fit_inputs_for_replay(
    frame: Mapping[str, Any],
    *,
    families: Sequence[NamedEventFamily],
    occurrences: Sequence[NamedEventOccurrence],
    response_definitions: Sequence[EventResponseDefinition],
    fitted_response_definitions: Sequence[Tuple[str, int]],
) -> NamedEventFitInputs:
    """Replay-time counterpart of `build_named_event_fit_inputs` - closes
    the predict/scenario-replay gap `core.predict.predict_mu`/
    `core.market_specific_predict.predict_mu_market_specific`/
    `core.sequential_simulation.simulate_sequential_outcomes` raise
    `NamedEventReplayNotSupportedError` for (a fit that consumed a
    named-event response term).

    Two deliberate differences from `build_named_event_fit_inputs`, both
    required for a *replay* (as opposed to a *fit*) call:

    1. **`response_definitions` is pinned to the exact fit-time version**,
       via `fitted_response_definitions` (`meta.named_event_response_
       definitions_at_fit` - `(response_definition_id, response_definition_
       version)` pairs recorded at fit time). Replaying MUST use the exact
       window (`max_lead`/`max_lag`) and outcome scope that produced the
       already-fitted `event_coefs_<family>_<market>` posterior - using
       whatever the registry's *current* version happens to be today would
       silently mismatch the basis width (if the window changed since
       fitting) or the outcome scope, against coefficients that do not
       know about that change. `occurrences`/`families` are NOT pinned -
       using the CURRENT registry for occurrences is exactly what lets a
       replay frame that extends into future weeks pick up a future,
       not-yet-occurred occurrence of the same family/event automatically
       (see point 2) - this mirrors `core.planning.future_context`'s own
       "Promotions/events" contract (REQ-SCEN-002: "an explicit planned
       value or approved event schedule for every future period").
    2. **Never returns `None`.** `build_named_event_fit_inputs` returns
       `None` at FIT time to mean "nothing opted in - add nothing to the
       model graph at all," a meaning specific to the fit-time byte-for-
       byte-unchanged contract. At replay time the caller already knows
       (from `meta.named_event_response_definitions_at_fit` being
       non-empty) that named events were fit; this function's only job is
       to say what applies to THIS replay frame, and "nothing in this
       particular frame's date range" is a legitimate, non-exceptional
       empty result (e.g. a short backtest window with no event in it) -
       represented as a `NamedEventFitInputs` with an empty `blocks`
       tuple, never `None`. This is what lets `predict_mu`'s own
       `named_event_fit_inputs` parameter use `None` to mean specifically
       "the caller did not attempt replay support at all" (still raises)
       versus an actual (possibly block-empty) `NamedEventFitInputs`
       instance (replay support was attempted; compute whatever applies).

    A (family, market) block this function builds for the replay frame
    that was never actually fit (no corresponding `event_coefs_<family>_
    <market>` posterior exists - e.g. a market's first-ever occurrence of
    this family falls inside the replay window but not inside the
    historical fit window) is handled downstream by `predict_mu`/
    `predict_mu_market_specific` treating it as a zero contribution
    (mirroring every other "coefficient not found" default already in
    those modules, e.g. `outcome_control_coef.get(name, 0.0)`) - a direct,
    mechanical consequence of Decision 12's own already-approved
    "unpooled per market/family by default" choice (no pooling mechanism
    exists to borrow strength from another market's coefficients, so zero
    is the only defensible default without inventing a new, unapproved
    pooling mechanism), never a new business decision.
    """
    fitted_pairs = {tuple(pair) for pair in fitted_response_definitions}
    pinned_definitions = [
        d
        for d in response_definitions
        if (d.response_definition_id, d.response_definition_version) in fitted_pairs
    ]
    result = build_named_event_fit_inputs(
        frame,
        families=families,
        occurrences=occurrences,
        response_definitions=pinned_definitions,
    )
    if result is not None:
        return result
    return NamedEventFitInputs(blocks=(), shrinkage_prior_scale_by_family={})


def _weekly_period_bounds(
    period_starts: pd.DatetimeIndex,
) -> Tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Each period's own `[start, end]` calendar span, derived from the
    model's own weekly grid (implementation-brief section 7's preferred
    approach) rather than assuming a fixed Monday anchor: period `i`'s end
    is period `i+1`'s start minus one day; the final period uses the
    grid's own inferred spacing (falling back to seven days - the current
    weekly MMM's frequency - when only one period exists). `period_starts`
    must already be sorted ascending, matching `data.preprocessor.
    prepare_fh_modeling_frame`'s contiguous-per-market-block layout."""
    if len(period_starts) > 1:
        step = period_starts[1] - period_starts[0]
    else:
        step = pd.Timedelta(days=7)
    next_starts = period_starts[1:].append(pd.DatetimeIndex([period_starts[-1] + step]))
    period_ends = next_starts - pd.Timedelta(days=1)
    return period_starts, period_ends


def weekly_period_bounds_for_market(
    frame: Mapping[str, Any], market: str
) -> Tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Public wrapper over `_weekly_period_bounds` for one market's own
    slice of `frame` - the exact period boundaries `build_named_event_
    fit_inputs` itself uses for that market. Returns two empty
    `DatetimeIndex` values when `market` is not one of `frame["markets"]`
    (nothing to bound). Exists so a read-only reporting consumer (`core.
    named_event_diagnostics`) can reuse the model's own period-boundary
    construction verbatim rather than re-deriving an approximation of
    it."""
    markets: List[str] = list(frame["markets"])
    if market not in markets:
        empty = pd.DatetimeIndex([])
        return empty, empty
    market_i = markets.index(market)
    dates = np.asarray(frame["dates"])
    market_bounds: List[Tuple[int, int]] = list(frame["market_bounds"])
    start, end = market_bounds[market_i]
    market_dates = pd.to_datetime(dates[start:end])
    return _weekly_period_bounds(market_dates)


def weeks_overlapping_event_interval(
    period_starts: pd.DatetimeIndex,
    period_ends: pd.DatetimeIndex,
    occ_start: pd.Timestamp,
    occ_end: pd.Timestamp,
) -> Tuple[int, ...]:
    """The (0-indexed) positions of every period whose own
    `[period_starts[i], period_ends[i]]` calendar span overlaps the
    factual `[occ_start, occ_end]` event interval at all (implementation
    brief section 7's overlap rule: `period_start <= event_end and
    period_end >= event_start`) - never whether the period's own anchor
    date falls inside the event interval, which misses an event landing
    later in the same period (e.g. a Sunday event in a Monday-start
    week). The single tested core helper `build_named_event_fit_inputs`
    uses for this - not duplicated in the UI or anywhere else."""
    mask = (period_starts <= occ_end) & (period_ends >= occ_start)
    return tuple(int(i) for i in np.where(mask)[0])


def build_named_event_fit_inputs(
    frame: Mapping[str, Any],
    *,
    families: Sequence[NamedEventFamily],
    occurrences: Sequence[NamedEventOccurrence],
    response_definitions: Sequence[EventResponseDefinition],
) -> Optional[NamedEventFitInputs]:
    """Build `NamedEventFitInputs` for this fit's actual `(market, week)`
    grid (`frame["markets"]`/`frame["dates"]`/`frame["market_bounds"]` -
    `data.preprocessor.prepare_fh_modeling_frame`'s own contiguous-
    per-market-block layout) from the governed registry.

    Returns `None` (never an empty-but-present object) when nothing in
    the registry opts in to production fitting (see module docstring for
    the opt-in gate) - so a caller can treat "no named events configured"
    and "no named events opted in yet" identically to "no fit inputs
    supplied at all".
    """
    markets: List[str] = list(frame["markets"])
    dates = np.asarray(frame["dates"])
    market_bounds: List[Tuple[int, int]] = list(frame["market_bounds"])
    n_obs = len(dates)

    current_families = {f.family_id: f for f in current_family_versions(families)}
    opted_in_definitions = [
        d
        for d in current_response_definition_versions(response_definitions)
        if d.transformation_method_reference == NAMED_EVENT_RESPONSE_STRUCTURE
    ]
    if not opted_in_definitions:
        return None

    # Defensive registry-invariant check: `application.event_service.
    # bulk_adopt_preferred_event_rows` never creates a second current
    # opted-in definition for one family, but this function's registry
    # inputs are not exclusively reachable through that boundary (e.g. the
    # manual family/response-definition admin forms). Two opted-in
    # definitions for the same family would each produce their own block
    # below, and both model builders key their PyMC variable purely on
    # `family_id`/market (`event_coefs_<family_id>_<market>`) - so this
    # fails closed here, before any block is built, rather than letting a
    # duplicate-variable collision surface deep inside `pm.Model()`. This
    # does not pick a definition to prefer; that would be inventing a
    # selection rule this module has no approval to make.
    _duplicate_opted_in_family_ids = sorted(
        family_id
        for family_id, count in Counter(
            d.family_id for d in opted_in_definitions
        ).items()
        if count > 1
    )
    if _duplicate_opted_in_family_ids:
        raise ValueError(
            "Invalid named-event registry: famil"
            + ("y" if len(_duplicate_opted_in_family_ids) == 1 else "ies")
            + f" {tuple(_duplicate_opted_in_family_ids)!r} has more than one current "
            "opted-in EventResponseDefinition - this would create duplicate "
            "event_coefs_<family>_<market> variables at fit time. Reconcile the "
            "registry to exactly one current opted-in response definition per "
            "family before fitting."
        )

    current_occurrences = current_occurrence_versions(occurrences)

    blocks: List[NamedEventFamilyFitBlock] = []
    shrinkage_scale_by_family: Dict[str, float] = {}

    for definition in opted_in_definitions:
        family = current_families.get(definition.family_id)
        if family is None:
            # core.named_events.validate_registry_references already
            # reports an orphan family link as a registry problem
            # elsewhere - this function never fabricates a family here.
            continue
        family_occurrences = [
            occ for occ in current_occurrences if occ.family_id == family.family_id
        ]
        if not family_occurrences:
            continue
        max_lead = definition.max_lead
        max_lag = definition.max_lag
        if max_lead == 0 and max_lag == 0:
            # build_spline_basis requires a non-degenerate window; a
            # response definition recorded with no support at all simply
            # contributes nothing, never an error at fit time.
            continue

        for market_i, market in enumerate(markets):
            start, end = market_bounds[market_i]
            n_weeks = end - start
            market_dates = pd.to_datetime(dates[start:end])
            period_starts, period_ends = _weekly_period_bounds(market_dates)

            event_week_set: set[int] = set()
            for occ in family_occurrences:
                if market not in occ.market_scope:
                    continue
                occ_start = pd.Timestamp(occ.start_date)
                occ_end = pd.Timestamp(occ.end_date)
                # Interval overlap, not anchor-date containment (brief
                # section 7): a period is activated whenever its own span
                # overlaps the occurrence's factual span at all - e.g. a
                # Sunday event still activates the Monday-start week that
                # contains it, and a multi-week promotion activates every
                # week it crosses.
                event_week_set.update(
                    weeks_overlapping_event_interval(
                        period_starts, period_ends, occ_start, occ_end
                    )
                )
            if not event_week_set:
                continue

            design_matrix = build_event_relative_design_matrix(
                sorted(event_week_set),
                n_weeks,
                max_lead_weeks=max_lead,
                max_lag_weeks=max_lag,
            )
            basis = build_spline_basis(max_lead_weeks=max_lead, max_lag_weeks=max_lag)
            local_design = design_matrix @ basis  # (n_weeks, n_basis)

            full_design = np.zeros((n_obs, local_design.shape[1]))
            full_design[start:end, :] = local_design

            blocks.append(
                NamedEventFamilyFitBlock(
                    family_id=family.family_id,
                    market=market,
                    design=full_design,
                    response_definition_id=definition.response_definition_id,
                    response_definition_version=definition.response_definition_version,
                    outcome_scope=tuple(definition.outcome_scope),
                    classification=family.classification,
                )
            )
            shrinkage_scale_by_family.setdefault(
                family.family_id, EVENT_RESPONSE_SHRINKAGE_PRIOR_DEFAULT_SCALE
            )

    if not blocks:
        return None

    return NamedEventFitInputs(
        blocks=tuple(blocks),
        shrinkage_prior_scale_by_family=shrinkage_scale_by_family,
    )


def families_without_opted_in_response_definition(
    families: Sequence[NamedEventFamily],
    occurrences: Sequence[NamedEventOccurrence],
    response_definitions: Sequence[EventResponseDefinition],
) -> Tuple[str, ...]:
    """Registry-only visibility signal (no model frame required, usable
    immediately after adoption): the family ids that have at least one
    current, factual occurrence but no current response definition opted
    into fitting (`transformation_method_reference == NAMED_EVENT_
    RESPONSE_STRUCTURE`). These families are registered, governed data
    that currently contribute nothing to any fit - a caller must surface
    this explicitly rather than let the absence go unremarked (e.g. a
    `promotion`/`promotional` family, whose response mechanism is a
    disclosed, decision-required gap - see `docs/named_event_promotional_
    window_decision_package.md`).

    This is a coarser, registry-only cousin of `families_excluded_from_
    fitting`: it does not know about a specific fit frame, so it cannot
    detect a response definition that IS opted in but still contributes
    nothing for another reason (a degenerate window, or an occurrence
    outside this particular frame's market/date coverage) -
    `families_excluded_from_fitting` is authoritative for that."""
    current_occs = current_occurrence_versions(occurrences)
    family_ids_with_occurrences = {
        occ.family_id for occ in current_occs if occ.family_id
    }
    opted_in_family_ids = {
        d.family_id
        for d in current_response_definition_versions(response_definitions)
        if d.transformation_method_reference == NAMED_EVENT_RESPONSE_STRUCTURE
    }
    return tuple(sorted(family_ids_with_occurrences - opted_in_family_ids))


def families_excluded_from_fitting(
    frame: Mapping[str, Any],
    *,
    families: Sequence[NamedEventFamily],
    occurrences: Sequence[NamedEventOccurrence],
    response_definitions: Sequence[EventResponseDefinition],
) -> Tuple[str, ...]:
    """Frame-aware, authoritative visibility signal: the family ids with
    at least one current, factual occurrence that nonetheless do not
    appear in `build_named_event_fit_inputs`' actual result for THIS
    frame. Catches every reason a registered family contributes nothing
    to a specific fit - no opted-in response definition, a degenerate
    window, or no occurrence inside this frame's market/date coverage -
    not only the "never opted in" case `families_without_opted_in_
    response_definition` reports. A caller (the fit-proposal UI) must
    show this list explicitly: a registered family absent from the fit
    must never be presented as though it had been modelled and found to
    have zero effect."""
    current_occs = current_occurrence_versions(occurrences)
    family_ids_with_occurrences = {
        occ.family_id for occ in current_occs if occ.family_id
    }
    fit_inputs = build_named_event_fit_inputs(
        frame,
        families=families,
        occurrences=occurrences,
        response_definitions=response_definitions,
    )
    fitted_family_ids = set(fit_inputs.family_ids) if fit_inputs is not None else set()
    return tuple(sorted(family_ids_with_occurrences - fitted_family_ids))
