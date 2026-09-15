"""Named-event diagnostics: read-only reporting over the governed
named-event registry (`core.named_events`) and the actual prepared
modelling frame, at `event_family_id x market` grain.

Diagnostic only. This module never changes fit behaviour and is never
imported by `core.hierarchical_model`, `core.market_specific_model`,
`core.predict`, `core.market_specific_predict`, or `application.
model_fit_service` - it is a reporting consumer of the same governed
inputs those modules use, not a participant in fitting.

It reuses the model's own interval-overlap and event-relative
construction verbatim rather than re-deriving an approximation of it:

- `core.named_event_fit_inputs.weekly_period_bounds_for_market` and
  `weeks_overlapping_event_interval` for `model_periods_affected` (the
  raw factual-interval overlap, independent of fit status);
- `core.named_event_fit_inputs.build_named_event_fit_inputs` itself for
  `fit_status`/`fitted_support_weeks` (the actual design blocks a real
  fit would consume for this exact frame) - never a second, approximate
  reconstruction of "would this be fitted".

Per the event-upload-contract implementation brief's own section 12: no
numeric minimum-occurrence threshold is invented here, and no family is
ever labelled "adequately identified" - only counts and policy/fit
status are reported. `core.named_event_response.assess_family_pooling_
eligibility` (Decision 12, dimension 4) already owns that fail-closed
gate; this module does not duplicate or bypass it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .named_event_fit_inputs import (
    build_named_event_fit_inputs,
    weekly_period_bounds_for_market,
    weeks_overlapping_event_interval,
)
from .named_event_response import NAMED_EVENT_RESPONSE_STRUCTURE
from .named_event_type_policy import (
    CLASSIFICATION_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED,
    CLASSIFICATION_STATUS_RESPONSE_POLICY_REQUIRED,
)
from .named_events import (
    EventResponseDefinition,
    NamedEventFamily,
    NamedEventOccurrence,
    current_family_versions,
    current_occurrence_versions,
    current_response_definition_versions,
)

# --- fit_status: the model-consuming outcome for this (family, market) ----

FIT_STATUS_INCLUDED_IN_FIT = "included_in_fit"
FIT_STATUS_REGISTERED_NOT_FITTED = "registered_not_fitted"
FIT_STATUS_OUTSIDE_MODEL_WINDOW = "outside_model_window"
FIT_STATUS_RESPONSE_POLICY_REQUIRED = "response_policy_required"
FIT_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED = "promotional_window_unresolved"

FIT_STATUSES = (
    FIT_STATUS_INCLUDED_IN_FIT,
    FIT_STATUS_REGISTERED_NOT_FITTED,
    FIT_STATUS_OUTSIDE_MODEL_WINDOW,
    FIT_STATUS_RESPONSE_POLICY_REQUIRED,
    FIT_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED,
)

# --- response_policy: the registry-level policy state, independent of any
# particular fit frame -------------------------------------------------

RESPONSE_POLICY_OPTED_IN = "opted_in"
RESPONSE_POLICY_REGISTERED_NOT_OPTED_IN = "registered_not_opted_in"
RESPONSE_POLICY_RESPONSE_POLICY_REQUIRED = "response_policy_required"
RESPONSE_POLICY_PROMOTIONAL_WINDOW_UNRESOLVED = "promotional_window_unresolved"
RESPONSE_POLICY_NONE_REGISTERED = "none_registered"


@dataclass(frozen=True)
class NamedEventDiagnosticRow:
    """One `event_family_id x market` diagnostic row. Read-only - never
    consumed by any fit path, never persisted as a governed record."""

    event_family_id: str
    event_type: str
    market: str
    occurrence_count: int
    first_occurrence: str
    last_occurrence: str
    model_periods_affected: int
    response_policy: str
    temporal_treatment: Optional[str]
    max_lead_weeks: Optional[int]
    max_lag_weeks: Optional[int]
    fit_status: str
    exclusion_reason: str
    fitted_support_weeks: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "event_family_id": self.event_family_id,
            "event_type": self.event_type,
            "market": self.market,
            "occurrence_count": self.occurrence_count,
            "first_occurrence": self.first_occurrence,
            "last_occurrence": self.last_occurrence,
            "model_periods_affected": self.model_periods_affected,
            "response_policy": self.response_policy,
            "temporal_treatment": self.temporal_treatment,
            "max_lead_weeks": self.max_lead_weeks,
            "max_lag_weeks": self.max_lag_weeks,
            "fit_status": self.fit_status,
            "exclusion_reason": self.exclusion_reason,
            "fitted_support_weeks": self.fitted_support_weeks,
        }


def _pick_definition(
    definitions: Sequence[EventResponseDefinition],
) -> Optional[EventResponseDefinition]:
    """The definition diagnostics describes for a family: the opted-in
    one if any exists, else the first by id (deterministic). Most
    families have at most one current definition (the deterministic
    `{family_id}_default_response` id); a manually registered second one
    with a different id is possible but not treated specially here."""
    if not definitions:
        return None
    opted_in = [
        d
        for d in definitions
        if d.transformation_method_reference == NAMED_EVENT_RESPONSE_STRUCTURE
    ]
    pool = opted_in or list(definitions)
    return sorted(pool, key=lambda d: d.response_definition_id)[0]


def _response_policy_for(
    family: Optional[NamedEventFamily],
    definition: Optional[EventResponseDefinition],
) -> str:
    if definition is not None:
        if definition.transformation_method_reference == NAMED_EVENT_RESPONSE_STRUCTURE:
            return RESPONSE_POLICY_OPTED_IN
        return RESPONSE_POLICY_REGISTERED_NOT_OPTED_IN
    if family is not None:
        if (
            family.classification_status
            == CLASSIFICATION_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED
        ):
            return RESPONSE_POLICY_PROMOTIONAL_WINDOW_UNRESOLVED
        if (
            family.classification_status
            == CLASSIFICATION_STATUS_RESPONSE_POLICY_REQUIRED
        ):
            return RESPONSE_POLICY_RESPONSE_POLICY_REQUIRED
    return RESPONSE_POLICY_NONE_REGISTERED


def build_named_event_diagnostics(
    frame: Mapping[str, Any],
    *,
    families: Sequence[NamedEventFamily],
    occurrences: Sequence[NamedEventOccurrence],
    response_definitions: Sequence[EventResponseDefinition],
) -> Tuple[NamedEventDiagnosticRow, ...]:
    """One diagnostic row per `event_family_id x market` combination
    present in the current, factual occurrence registry - sorted by
    `(event_family_id, market)` for determinism. Repeated yearly
    occurrences of the same family/market collapse into a single row
    (`occurrence_count` reports how many); the same family in a
    different market gets its own separate row."""
    current_fams: Dict[str, NamedEventFamily] = {
        f.family_id: f for f in current_family_versions(families)
    }
    current_occs = current_occurrence_versions(occurrences)
    defs_by_family: Dict[str, List[EventResponseDefinition]] = {}
    for current_definition in current_response_definition_versions(
        response_definitions
    ):
        defs_by_family.setdefault(current_definition.family_id, []).append(
            current_definition
        )

    occs_by_key: Dict[Tuple[str, str], List[NamedEventOccurrence]] = {}
    for occ in current_occs:
        if not occ.family_id:
            continue  # unmapped occurrence - no family to group it under
        for market in occ.market_scope:
            occs_by_key.setdefault((occ.family_id, market), []).append(occ)

    fit_inputs = build_named_event_fit_inputs(
        frame,
        families=families,
        occurrences=occurrences,
        response_definitions=response_definitions,
    )
    blocks_by_key = {
        (block.family_id, block.market): block
        for block in (fit_inputs.blocks if fit_inputs is not None else ())
    }
    frame_markets = list(frame["markets"])

    rows: List[NamedEventDiagnosticRow] = []
    for family_id, market in sorted(occs_by_key):
        family = current_fams.get(family_id)
        family_occs = occs_by_key[(family_id, market)]
        starts = [pd.Timestamp(o.start_date) for o in family_occs]
        ends = [pd.Timestamp(o.end_date) for o in family_occs]

        period_starts, period_ends = weekly_period_bounds_for_market(frame, market)
        overlapping_weeks: set = set()
        if len(period_starts) > 0:
            for occ in family_occs:
                overlapping_weeks.update(
                    weeks_overlapping_event_interval(
                        period_starts,
                        period_ends,
                        pd.Timestamp(occ.start_date),
                        pd.Timestamp(occ.end_date),
                    )
                )
        model_periods_affected = len(overlapping_weeks)

        definition = _pick_definition(defs_by_family.get(family_id, ()))
        response_policy = _response_policy_for(family, definition)

        block = blocks_by_key.get((family_id, market))
        fitted_support_weeks: Optional[int] = None
        if block is not None:
            fit_status = FIT_STATUS_INCLUDED_IN_FIT
            exclusion_reason = ""
            fitted_support_weeks = int(np.any(block.design != 0.0, axis=1).sum())
        elif model_periods_affected == 0:
            fit_status = FIT_STATUS_OUTSIDE_MODEL_WINDOW
            if market not in frame_markets:
                exclusion_reason = (
                    f"market {market!r} is not part of this model's markets"
                )
            else:
                exclusion_reason = (
                    "none of this family's occurrences in this market overlap "
                    "any model period in this frame"
                )
        elif response_policy == RESPONSE_POLICY_PROMOTIONAL_WINDOW_UNRESOLVED:
            fit_status = FIT_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED
            exclusion_reason = (
                "promotional family - the bounded per-occurrence response "
                "mechanism is a disclosed, decision-required gap (see "
                "docs/named_event_promotional_window_decision_package.md)"
            )
        elif response_policy == RESPONSE_POLICY_RESPONSE_POLICY_REQUIRED:
            fit_status = FIT_STATUS_RESPONSE_POLICY_REQUIRED
            exclusion_reason = (
                "event_type has no automatic response policy and none is registered"
            )
        elif response_policy == RESPONSE_POLICY_NONE_REGISTERED:
            fit_status = FIT_STATUS_REGISTERED_NOT_FITTED
            exclusion_reason = "no response definition registered for this family"
        elif response_policy == RESPONSE_POLICY_REGISTERED_NOT_OPTED_IN:
            fit_status = FIT_STATUS_REGISTERED_NOT_FITTED
            exclusion_reason = (
                "a response definition is registered but not opted into the "
                "approved fitting reference"
            )
        else:
            # response_policy == opted_in but still absent from fit_inputs -
            # e.g. a degenerate (0, 0) window, which build_named_event_fit_
            # inputs silently skips rather than raising.
            fit_status = FIT_STATUS_REGISTERED_NOT_FITTED
            exclusion_reason = (
                "response definition is opted in but currently produces no "
                "fitted contribution (e.g. a degenerate lead/lag window)"
            )

        rows.append(
            NamedEventDiagnosticRow(
                event_family_id=family_id,
                event_type=(
                    family.classification
                    if family is not None
                    else "(unregistered family)"
                ),
                market=market,
                occurrence_count=len(family_occs),
                first_occurrence=min(starts).date().isoformat(),
                last_occurrence=max(ends).date().isoformat(),
                model_periods_affected=model_periods_affected,
                response_policy=response_policy,
                temporal_treatment=(
                    definition.treatment if definition is not None else None
                ),
                max_lead_weeks=(
                    definition.max_lead if definition is not None else None
                ),
                max_lag_weeks=(definition.max_lag if definition is not None else None),
                fit_status=fit_status,
                exclusion_reason=exclusion_reason,
                fitted_support_weeks=fitted_support_weeks,
            )
        )

    return tuple(rows)


# --- "This fitted model" view: built purely from persisted FHModelMeta ----
# provenance, never from the current registry or a frame. See module
# docstring's own "fit-time provenance" section.


@dataclass(frozen=True)
class FittedNamedEventDiagnosticRow:
    """One `event_family_id x market` row from the authoritative fit-time
    record (`FHModelMeta.named_event_fit_blocks`/`named_event_fit_block_
    provenance`) - never rebuilt from the current registry, so it cannot
    be rewritten by a later registry edit. `fit_status` is always
    `FIT_STATUS_INCLUDED_IN_FIT` (nothing else can appear here: a fit
    never persists which families it *excluded*, only which it
    included - see `build_fitted_named_event_diagnostics`'s own
    docstring). `provenance_complete=False` means this model was fitted
    before `named_event_fit_block_provenance` existed - `response_
    definition_id`/`_version`/`fitted_support_weeks` are genuinely
    unavailable, not fabricated as `None`/an approximation."""

    event_family_id: str
    market: str
    response_definition_id: Optional[str]
    response_definition_version: Optional[int]
    classification: Optional[str]
    response_policy: str
    fit_status: str
    fitted_support_weeks: Optional[int]
    provenance_complete: bool

    def to_dict(self) -> dict:
        return {
            "event_family_id": self.event_family_id,
            "market": self.market,
            "response_definition_id": self.response_definition_id,
            "response_definition_version": self.response_definition_version,
            "classification": self.classification,
            "response_policy": self.response_policy,
            "fit_status": self.fit_status,
            "fitted_support_weeks": self.fitted_support_weeks,
            "provenance_complete": self.provenance_complete,
        }


def build_fitted_named_event_diagnostics(
    meta: Any,
) -> Tuple[FittedNamedEventDiagnosticRow, ...]:
    """The "This fitted model" view: a pure function of `meta` alone.

    Never reads the current governed registry and never reads a frame -
    every value comes from `FHModelMeta.named_event_fit_blocks` (which
    `(family_id, market)` pairs actually got a real posterior coefficient
    at fit time - genuine fit-time fact, persisted since named-event
    production integration) and `FHModelMeta.named_event_fit_block_
    provenance` (the richer per-block `response_definition_id`/`_version`/
    `classification`/`fitted_support_weeks` detail, persisted from this
    implementation brief onward). Because this reads nothing but already-
    persisted `meta` fields, it is immune BY CONSTRUCTION to any registry
    edit made after fitting - adding, removing, or editing an occurrence,
    family, or response definition changes nothing this function returns
    for an already-fitted model.

    A row's absence here does NOT mean "excluded from the fit for a known
    reason" - only "not one of the (family_id, market) pairs recorded as
    included." `FHModelMeta` never persisted which families were
    *considered and excluded* at fit time (only the registry, at fit
    time, knew that - and only for as long as it stayed unfitted), so
    this function structurally cannot reconstruct a `registered_not_
    fitted`/`outside_model_window`/etc. row - use `build_named_event_
    diagnostics` against the CURRENT registry for that (current-registry
    readiness), never fabricated here as fit-time truth.

    A `meta` with no named-event consumption at all (`named_event_fit_
    blocks` empty, the default for every fit before this feature existed
    and every fit today with nothing opted in) returns an empty tuple -
    not an error, not a fabricated "no events" row.
    """
    blocks = list(getattr(meta, "named_event_fit_blocks", None) or ())
    if not blocks:
        return ()
    provenance_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {
        (str(item.get("family_id")), str(item.get("market"))): item
        for item in (getattr(meta, "named_event_fit_block_provenance", None) or ())
    }

    rows: List[FittedNamedEventDiagnosticRow] = []
    for family_id, market in blocks:
        key = (str(family_id), str(market))
        detail = provenance_by_key.get(key)
        if detail is not None:
            rows.append(
                FittedNamedEventDiagnosticRow(
                    event_family_id=key[0],
                    market=key[1],
                    response_definition_id=detail.get("response_definition_id"),
                    response_definition_version=detail.get(
                        "response_definition_version"
                    ),
                    classification=(detail.get("classification") or None),
                    response_policy=RESPONSE_POLICY_OPTED_IN,
                    fit_status=FIT_STATUS_INCLUDED_IN_FIT,
                    fitted_support_weeks=detail.get("fitted_support_weeks"),
                    provenance_complete=True,
                )
            )
        else:
            # A fit persisted before named_event_fit_block_provenance
            # existed: the (family_id, market) pair itself IS genuine
            # fit-time truth (named_event_fit_blocks always existed), but
            # the richer per-block detail was never recorded - report it
            # as unavailable, never approximated from the current
            # registry or from an aggregate cross-family list.
            rows.append(
                FittedNamedEventDiagnosticRow(
                    event_family_id=key[0],
                    market=key[1],
                    response_definition_id=None,
                    response_definition_version=None,
                    classification=None,
                    response_policy=RESPONSE_POLICY_OPTED_IN,
                    fit_status=FIT_STATUS_INCLUDED_IN_FIT,
                    fitted_support_weeks=None,
                    provenance_complete=False,
                )
            )

    return tuple(sorted(rows, key=lambda r: (r.event_family_id, r.market)))


# --- Drift: fitted provenance vs. the current registry ---------------------

NAMED_EVENT_CONFIG_CURRENT = "current"
NAMED_EVENT_CONFIG_CHANGED_SINCE_FIT = "changed_since_fit"
NAMED_EVENT_CONFIG_UNKNOWN_NO_FIT_TIME_FINGERPRINT = "unknown_no_fit_time_fingerprint"


@dataclass(frozen=True)
class NamedEventDriftResult:
    """Whether the current governed registry, replayed against the same
    frame this model was fitted on, would produce the same named-event
    fit inputs the model actually consumed - reusing `NamedEventFitInputs.
    fingerprint()` (the repository's existing fit-input fingerprint, also
    used by `pages/05_Model_Training.py`'s pre-fit preview and `pages/
    06_Diagnostics.py`'s `current_model_identity`) rather than a new,
    independent definition of staleness."""

    status: str
    reasons: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {"status": self.status, "reasons": list(self.reasons)}


def assess_named_event_drift(
    frame: Mapping[str, Any],
    meta: Any,
    *,
    families: Sequence[NamedEventFamily],
    occurrences: Sequence[NamedEventOccurrence],
    response_definitions: Sequence[EventResponseDefinition],
) -> NamedEventDriftResult:
    """Compare this model's persisted fit-time named-event provenance
    against what the CURRENT governed registry would produce for the
    SAME frame.

    `NAMED_EVENT_CONFIG_UNKNOWN_NO_FIT_TIME_FINGERPRINT` means this model
    was fitted before `named_event_fit_fingerprint` existed and DID
    consume at least one named event (`named_event_fit_blocks` is
    non-empty) - drift cannot be assessed for it without guessing; this
    is reported explicitly rather than defaulting to "current" (which
    would hide a real change) or "changed" (which would falsely flag an
    unchanged registry). A model that consumed no named event at all
    (both fields empty/blank) is unambiguously `current` when the
    registry still opts in nothing, and `changed_since_fit` the moment
    something newly opts in - no fingerprint is needed to know that.
    """
    fit_time_fingerprint = getattr(meta, "named_event_fit_fingerprint", "") or ""
    fit_time_blocks = {
        (str(f), str(m))
        for f, m in (getattr(meta, "named_event_fit_blocks", None) or ())
    }
    fit_time_definitions = {
        tuple(pair)
        for pair in (
            getattr(meta, "named_event_response_definitions_at_fit", None) or ()
        )
    }
    fit_time_classification_by_family: Dict[str, str] = {
        str(item.get("family_id")): str(item.get("classification") or "")
        for item in (getattr(meta, "named_event_fit_block_provenance", None) or ())
        if item.get("classification")
    }

    if not fit_time_blocks:
        current_fit_inputs = build_named_event_fit_inputs(
            frame,
            families=families,
            occurrences=occurrences,
            response_definitions=response_definitions,
        )
        if current_fit_inputs is None:
            return NamedEventDriftResult(status=NAMED_EVENT_CONFIG_CURRENT, reasons=())
        return NamedEventDriftResult(
            status=NAMED_EVENT_CONFIG_CHANGED_SINCE_FIT,
            reasons=(
                "a named event is now opted into fitting; none was consumed "
                "at fit time",
            ),
        )

    if not fit_time_fingerprint:
        return NamedEventDriftResult(
            status=NAMED_EVENT_CONFIG_UNKNOWN_NO_FIT_TIME_FINGERPRINT,
            reasons=(
                "this model was fitted before named-event fit-time "
                "fingerprinting existed - drift cannot be assessed without "
                "refitting",
            ),
        )

    current_fit_inputs = build_named_event_fit_inputs(
        frame,
        families=families,
        occurrences=occurrences,
        response_definitions=response_definitions,
    )
    current_fingerprint = (
        current_fit_inputs.fingerprint() if current_fit_inputs is not None else ""
    )
    fingerprint_differs = fit_time_fingerprint != current_fingerprint

    current_blocks = {
        (b.family_id, b.market)
        for b in (current_fit_inputs.blocks if current_fit_inputs is not None else ())
    }
    current_definitions = set(
        current_fit_inputs.consumed_response_definitions()
        if current_fit_inputs is not None
        else ()
    )
    current_classification_by_family = {
        f.family_id: f.classification for f in current_family_versions(families)
    }

    reasons: List[str] = []
    added_blocks = current_blocks - fit_time_blocks
    removed_blocks = fit_time_blocks - current_blocks
    if added_blocks:
        reasons.append(
            "newly included family/market: "
            + ", ".join(sorted(f"{f} ({m})" for f, m in added_blocks))
        )
    if removed_blocks:
        reasons.append(
            "no longer included family/market: "
            + ", ".join(sorted(f"{f} ({m})" for f, m in removed_blocks))
        )
    if current_definitions != fit_time_definitions:
        reasons.append(
            "response definition changed (a different definition id and/or "
            "version is now consumed for at least one family)"
        )
    changed_classifications = sorted(
        family_id
        for family_id, fit_classification in fit_time_classification_by_family.items()
        if family_id in current_classification_by_family
        and current_classification_by_family[family_id] != fit_classification
    )
    if changed_classifications:
        reasons.append(
            "classification/event type changed for: "
            + ", ".join(changed_classifications)
        )
    if not reasons and fingerprint_differs:
        # Same block set, same consumed-definition set, same classification
        # per family, yet the fingerprint differs - the only remaining
        # input NamedEventFitInputs.fingerprint() depends on is occurrence
        # CONTENT for an already-fitted family (window/treatment are
        # pinned by the unchanged response-definition version). This does
        # NOT prove a specific edit kind (a date change, an occurrence
        # added/removed while another keeps the block populated, etc.) -
        # narrowing further would require persisted fit-time occurrence
        # identity/dates, which does not exist; report the honest
        # boundary of what can be proven, never a more specific claim.
        reasons.append(
            "event occurrence set or timing changed for an already-fitted family"
        )
    if not reasons:
        # Neither the fingerprint (design/consumed-definitions) nor
        # classification changed for any consumed family - genuinely
        # unchanged, not merely "no reason found".
        return NamedEventDriftResult(status=NAMED_EVENT_CONFIG_CURRENT, reasons=())
    return NamedEventDriftResult(
        status=NAMED_EVENT_CONFIG_CHANGED_SINCE_FIT, reasons=tuple(reasons)
    )
