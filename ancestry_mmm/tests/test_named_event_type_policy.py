"""Tests for `core.named_event_type_policy` - the explicit source
`event_type` -> governed classification/response-policy resolver
(implementation brief section 6; `docs/approved_requirements/
REQ-EVENT-001.md`'s 2026-08-30 addendum)."""

from __future__ import annotations

from ancestry_mmm.core.named_event_response import (
    GIFTING_WINDOW_POLICY,
    NAMED_EVENT_RESPONSE_STRUCTURE,
    REMEMBRANCE_WINDOW_POLICY,
    TEMPORAL_TREATMENT_ANTICIPATORY,
    TEMPORAL_TREATMENT_CONTEMPORANEOUS,
)
from ancestry_mmm.core.named_event_type_policy import (
    EVENT_TYPE_GIFTING,
    EVENT_TYPE_PROMOTION,
    EVENT_TYPE_REMEMBRANCE,
    default_response_definition_id,
    normalise_event_type,
    resolve_event_type_policy,
    resolve_family_classification,
)


class TestNormaliseEventType:
    def test_canonical_values_pass_through(self):
        assert normalise_event_type("gifting") == EVENT_TYPE_GIFTING
        assert normalise_event_type("remembrance") == EVENT_TYPE_REMEMBRANCE
        assert normalise_event_type("promotion") == EVENT_TYPE_PROMOTION

    def test_case_and_whitespace_insensitive(self):
        assert normalise_event_type("  Gifting  ") == EVENT_TYPE_GIFTING

    def test_approved_aliases(self):
        assert normalise_event_type("commemorative") == EVENT_TYPE_REMEMBRANCE
        assert normalise_event_type("promotional") == EVENT_TYPE_PROMOTION

    def test_unsupported_or_blank_returns_none(self):
        assert normalise_event_type("seasonal") is None
        assert normalise_event_type("") is None
        assert normalise_event_type(None) is None

    def test_never_derives_from_event_name_text(self):
        # A free-text label that merely *resembles* a supported type must
        # not resolve - only the exact event_type column value/alias does.
        assert normalise_event_type("Mother's Day") is None


class TestResolveFamilyClassification:
    def test_resolves_supported_types(self):
        assert resolve_family_classification("gifting") == "gifting"
        assert resolve_family_classification("remembrance") == "remembrance"
        assert resolve_family_classification("promotion") == "promotional"

    def test_unsupported_returns_none(self):
        assert resolve_family_classification("mystery") is None


class TestResolveEventTypePolicy:
    def test_gifting_matches_the_governed_window_policy(self):
        policy = resolve_event_type_policy("gifting")
        assert policy is not None
        assert policy.treatment == TEMPORAL_TREATMENT_ANTICIPATORY
        assert policy.max_lead == GIFTING_WINDOW_POLICY.max_lead_weeks == 6
        assert policy.max_lag == GIFTING_WINDOW_POLICY.max_lag_weeks == 0
        assert policy.transformation_method_reference == NAMED_EVENT_RESPONSE_STRUCTURE

    def test_remembrance_matches_the_governed_window_policy(self):
        policy = resolve_event_type_policy("commemorative")  # alias
        assert policy is not None
        assert policy.treatment == TEMPORAL_TREATMENT_CONTEMPORANEOUS
        assert policy.max_lead == REMEMBRANCE_WINDOW_POLICY.max_lead_weeks == 0
        assert policy.max_lag == REMEMBRANCE_WINDOW_POLICY.max_lag_weeks == 2

    def test_promotion_has_no_automatic_response_definition_policy(self):
        # Bounded to the actual per-occurrence promotion window (never a
        # fixed generic lead/lag) - no approved response policy exists
        # that the automatic resolver can register without inventing a
        # window; see module docstring / brief section 9.
        assert resolve_event_type_policy("promotion") is None
        assert resolve_event_type_policy("promotional") is None

    def test_unsupported_type_returns_none(self):
        assert resolve_event_type_policy("mystery") is None
        assert resolve_event_type_policy("") is None


class TestDefaultResponseDefinitionId:
    def test_deterministic_per_family(self):
        assert default_response_definition_id("mothers_day") == (
            "mothers_day_default_response"
        )
        # Same family -> same id every time, including across repeated
        # yearly uploads (brief section 6.1).
        assert default_response_definition_id("mothers_day") == (
            default_response_definition_id("mothers_day")
        )
