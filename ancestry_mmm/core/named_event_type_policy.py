"""Explicit source `event_type` -> governed classification/response-policy
resolver (`docs/approved_requirements/REQ-EVENT-001.md`'s 2026-08-30
addendum / Decision 12's family-to-treatment mapping; event-upload-contract
implementation brief, section 6).

This module maps only the analyst-supplied `event_type` source-row value
(and its approved compatibility aliases) to the family's governed
classification and its automatic `EventResponseDefinition` window - it
never infers anything from `event_name` or any other free text, and it
never classifies a concrete real-world event family on its own: the
mapping below is the TYPE-level mapping the addendum approved once
(gifting/remembrance/promotional -> temporal treatment); classifying a
specific family (e.g. "black_friday" -> `event_type="promotion"`) remains a
governed, explicit, analyst-supplied act happening at the adoption
boundary (`application.event_service`), never here.

Promotional events are a deliberate exception: the addendum's own
`PROMOTIONAL_WINDOW_POLICY.max_lag_weeks=None` records that the family's
support must be "bounded to the actual declared active period of the
specific promotion instance ... never a fixed generic number" - a
per-occurrence bound, not a family-wide lead/lag window. `core.
named_event_fit_inputs`' interval-overlap fix (implementation-brief
section 7) already activates every model period a multi-week promotion's
factual interval overlaps, so registering a literal `max_lag=0` response
definition would add no invented extension beyond that factual span - but
`core.named_event_response.build_spline_basis` cannot represent a
`(0, 0)` window at all (it requires a non-degenerate span for its
approved degree-3 B-spline construction, and deliberately raises rather
than guess - see its own `test_rejects_fully_degenerate_window`).
Fabricating a nonzero lead/lag purely to satisfy that helper is exactly
what the brief's section 9 forbids ("do not simply set an arbitrary
one-week lag ... to make a spline helper accept the data"), and
substituting a different, lower-order basis for this one case would be
choosing a new statistical representation unilaterally, which section 9
also forbids without approval. This module therefore resolves a
`promotion`/`promotional` `event_type` to its governed classification only
(so the family can still exist, reviewed, factually dated, governed) and
returns no automatic response policy - `resolve_event_type_policy` returns
`None` for it - `application.event_service` marks the family's
`classification_status` as `CLASSIFICATION_STATUS_PROMOTIONAL_WINDOW_
UNRESOLVED` rather than the generic `CLASSIFICATION_STATUS_RESPONSE_
POLICY_REQUIRED` used for a genuinely unrecognised type, so the UI can
state the specific, disclosed reason. See `docs/named_event_promotional_
window_decision_package.md` for the full decision-required record - this
module implements the fail-closed side of that gap, it does not resolve
it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from .named_event_response import (
    DEFAULT_FAMILY_WINDOW_POLICIES,
    NAMED_EVENT_RESPONSE_STRUCTURE,
    NamedEventFamilyWindowPolicy,
)

# Canonical event_type values the automatic resolver recognises.
EVENT_TYPE_GIFTING = "gifting"
EVENT_TYPE_REMEMBRANCE = "remembrance"
EVENT_TYPE_PROMOTION = "promotion"

SUPPORTED_EVENT_TYPES = (
    EVENT_TYPE_GIFTING,
    EVENT_TYPE_REMEMBRANCE,
    EVENT_TYPE_PROMOTION,
)

# Compatibility aliases where existing project state already uses a
# different label (implementation brief section 3).
EVENT_TYPE_ALIASES: Mapping[str, str] = {
    "commemorative": EVENT_TYPE_REMEMBRANCE,
    "promotional": EVENT_TYPE_PROMOTION,
}

# The event families a canonical event_type resolves to for family
# classification and `core.named_event_response.DEFAULT_FAMILY_WINDOW_
# POLICIES` lookup - that module's own key vocabulary predates, and
# slightly differs from ("promotional" vs "promotion"), this source
# vocabulary.
_EVENT_TYPE_TO_POLICY_KEY: Mapping[str, str] = {
    EVENT_TYPE_GIFTING: "gifting",
    EVENT_TYPE_REMEMBRANCE: "remembrance",
    EVENT_TYPE_PROMOTION: "promotional",
}

# Families with no automatic *response-definition* policy (they may still
# be adopted as governed families/occurrences - see module docstring).
_EVENT_TYPES_WITHOUT_AUTO_RESPONSE_DEFINITION = frozenset({EVENT_TYPE_PROMOTION})

CLASSIFICATION_STATUS_RESPONSE_POLICY_REQUIRED = "response_policy_required"

# A more specific status than CLASSIFICATION_STATUS_RESPONSE_POLICY_
# REQUIRED: the family IS a recognised, classified event type
# ("promotional") - the gap is not "this event_type is unknown", it is a
# disclosed, decision-required statistical-method gap (see `docs/
# named_event_promotional_window_decision_package.md`). Kept distinct so
# the UI can state the precise reason rather than a generic "unsupported
# type" message.
CLASSIFICATION_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED = "promotional_window_unresolved"


def normalise_event_type(event_type: Optional[str]) -> Optional[str]:
    """Resolve `event_type` (or one of its approved aliases) to its
    canonical value. Returns `None` for blank or unrecognised input -
    never guesses a canonical value from partial or free text."""
    if not event_type or not isinstance(event_type, str):
        return None
    value = event_type.strip().lower()
    if value in SUPPORTED_EVENT_TYPES:
        return value
    return EVENT_TYPE_ALIASES.get(value)


def resolve_family_classification(event_type: Optional[str]) -> Optional[str]:
    """The governed family `classification` a canonical `event_type`
    resolves to, or `None` if `event_type` is blank/unrecognised."""
    canonical = normalise_event_type(event_type)
    if canonical is None:
        return None
    return _EVENT_TYPE_TO_POLICY_KEY[canonical]


@dataclass(frozen=True)
class EventTypeResponsePolicy:
    """The automatic `EventResponseDefinition` inputs a supported
    `event_type` resolves to."""

    event_type: str
    classification: str
    treatment: str
    max_lead: int
    max_lag: int
    transformation_method_reference: str
    window_policy: NamedEventFamilyWindowPolicy


def resolve_event_type_policy(
    event_type: Optional[str],
) -> Optional[EventTypeResponsePolicy]:
    """The automatic response policy for a supported `event_type`, or
    `None` when `event_type` is blank, unrecognised, or (promotional)
    has no automatic response-definition policy yet - see module
    docstring. `None` must never silently opt a family into fitting
    (implementation brief section 6.2)."""
    canonical = normalise_event_type(event_type)
    if canonical is None or canonical in _EVENT_TYPES_WITHOUT_AUTO_RESPONSE_DEFINITION:
        return None
    policy_key = _EVENT_TYPE_TO_POLICY_KEY[canonical]
    window_policy = DEFAULT_FAMILY_WINDOW_POLICIES[policy_key]
    if window_policy.max_lag_weeks is None:
        # Defensive: every currently-supported auto-response type has a
        # concrete max_lag_weeks; a future family added to
        # DEFAULT_FAMILY_WINDOW_POLICIES with an open-ended window must be
        # added to _EVENT_TYPES_WITHOUT_AUTO_RESPONSE_DEFINITION too,
        # never silently coerced to a fabricated number here.
        return None
    return EventTypeResponsePolicy(
        event_type=canonical,
        classification=policy_key,
        treatment=window_policy.temporal_treatment,
        max_lead=window_policy.max_lead_weeks,
        max_lag=window_policy.max_lag_weeks,
        transformation_method_reference=NAMED_EVENT_RESPONSE_STRUCTURE,
        window_policy=window_policy,
    )


def default_response_definition_id(family_id: str) -> str:
    """Deterministic response-definition identity for `family_id`
    (implementation brief section 6.1) - stable across repeated yearly
    occurrences, never a fresh identity per upload."""
    return f"{family_id}_default_response"
