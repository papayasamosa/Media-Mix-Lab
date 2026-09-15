"""REQ-EVENT-001 (Work Package 1): tests for
`application.event_service` - the governed named-event adoption boundary
between uploaded Context `events` rows and the registry
(`core.named_events`). Adoption is explicit, the registry is immutable,
factual dates are preserved, and nothing derives classification or
treatment from an event name."""

from __future__ import annotations

import pytest

from ancestry_mmm.application.event_service import (
    BulkAdoptionOutcome,
    adopt_source_event_occurrence,
    bulk_adopt_preferred_event_rows,
    is_preferred_source_row,
    missing_occurrence_adoption_fields,
    missing_preferred_row_fields,
    new_family,
    new_registered_family_version,
    new_registered_occurrence_version,
    new_registered_response_definition_version,
    new_response_definition,
    register_family,
    register_occurrence,
    register_response_definition,
    registry_has_content,
    registry_problems,
    registry_to_dict,
)
from ancestry_mmm.core.named_event_type_policy import (
    CLASSIFICATION_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED,
    CLASSIFICATION_STATUS_RESPONSE_POLICY_REQUIRED,
)
from ancestry_mmm.core.named_events import (
    DEFAULT_EVENT_EVIDENCE_STATUS,
    EVENT_REGISTRY_SCHEMA_VERSION,
)


def _source_row(**overrides):
    row = {
        "event_id": "md-2026",
        "event_name": "Mother's Day 2026",
        "start_date": "2026-03-22",
        "end_date": "2026-03-22",
    }
    row.update(overrides)
    return row


def _analyst_input(**overrides):
    analyst = {
        "market": ["UK"],
        "source_id": "events",
        "source_version": 1,
    }
    analyst.update(overrides)
    return analyst


def _adopt(**overrides):
    return adopt_source_event_occurrence(_source_row(), _analyst_input(**overrides))


class TestAdoptionBoundary:
    def test_missing_fields_are_reported_and_nothing_is_adopted(self):
        assert missing_occurrence_adoption_fields(_source_row(), _analyst_input()) == ()
        missing = missing_occurrence_adoption_fields(
            _source_row(end_date=""), _analyst_input(market=[], source_id="")
        )
        assert "end_date" in missing
        assert "market" in missing
        assert "source_id" in missing
        with pytest.raises(ValueError, match="missing required field"):
            adopt_source_event_occurrence(
                _source_row(end_date=""), _analyst_input(market=[], source_id="")
            )

    def test_source_row_adopts_into_a_version_1_occurrence(self):
        occurrence = _adopt()
        assert occurrence.event_id == "md-2026"
        assert occurrence.event_version == 1
        assert occurrence.start_date == "2026-03-22"
        assert occurrence.end_date == "2026-03-22"
        assert occurrence.market_scope == ("UK",)
        assert occurrence.source_id == "events"
        assert occurrence.source_version == 1
        assert occurrence.family_id is None

    def test_factual_dates_are_preserved_verbatim(self):
        occurrence = _adopt()
        assert occurrence.start_date == _source_row()["start_date"]
        assert occurrence.end_date == _source_row()["end_date"]

    def test_family_link_is_only_what_the_analyst_supplied(self):
        occurrence = _adopt(family_id="mothers_day")
        assert occurrence.family_id == "mothers_day"
        assert _adopt().family_id is None

    def test_no_classification_or_treatment_is_derived(self):
        """Adopting a row named like a gifting occasion must produce no
        classification or treatment anywhere on the record."""
        occurrence = _adopt()
        assert not hasattr(occurrence, "classification")
        assert not hasattr(occurrence, "treatment")
        assert occurrence.display_name == "Mother's Day 2026"


class TestRegistryImmutability:
    def test_re_adopting_identical_content_is_idempotent(self):
        first = _adopt()
        registry = register_occurrence((), first)
        second = _adopt()
        assert register_occurrence(registry, second) == registry

    def test_re_adopting_different_content_raises_never_mutates(self):
        first = _adopt()
        registry = register_occurrence((), first)
        changed = adopt_source_event_occurrence(
            _source_row(end_date="2026-03-25"), _analyst_input()
        )
        with pytest.raises(ValueError, match="already registered"):
            register_occurrence(registry, changed)

    def test_new_occurrence_version_registers_without_mutation(self):
        registry = register_occurrence((), _adopt())
        versioned = new_registered_occurrence_version(
            registry, "md-2026", family_id="mothers_day"
        )
        assert len(versioned) == 2
        assert versioned[0].event_version == 1
        assert versioned[1].event_version == 2
        assert versioned[1].family_id == "mothers_day"

    def test_new_version_of_unregistered_occurrence_raises(self):
        with pytest.raises(ValueError, match="not registered"):
            new_registered_occurrence_version((), "md-2026", family_id="x")

    def test_family_registry_is_immutable(self):
        family = new_family(
            family_id="mothers_day",
            display_name="Mother's Day",
            classification="gifting",
        )
        registry = register_family((), family)
        assert register_family(registry, family) == registry
        changed = new_family(
            family_id="mothers_day",
            display_name="Mother's Day",
            classification="commercial",
        )
        with pytest.raises(ValueError, match="already registered"):
            register_family(registry, changed)
        versioned = new_registered_family_version(
            registry, "mothers_day", classification="commercial"
        )
        assert len(versioned) == 2
        assert versioned[1].classification == "commercial"

    def test_definition_registry_is_immutable(self):
        definition = new_response_definition(
            response_definition_id="md-def",
            family_id="mothers_day",
            treatment="anticipatory",
            max_lead=3,
            max_lag=0,
            transformation_method_reference="governed-ref",
        )
        registry = register_response_definition((), definition)
        assert register_response_definition(registry, definition) == registry
        changed = new_response_definition(
            response_definition_id="md-def",
            family_id="mothers_day",
            treatment="post_event",
            max_lead=0,
            max_lag=2,
            transformation_method_reference="governed-ref",
        )
        with pytest.raises(ValueError, match="already registered"):
            register_response_definition(registry, changed)
        versioned = new_registered_response_definition_version(
            registry, "md-def", max_lead=4
        )
        assert len(versioned) == 2
        assert versioned[1].max_lead == 4


class TestRegistrySerialisation:
    def test_registry_to_dict_has_schema_version_and_parts(self):
        family = new_family(
            family_id="mothers_day",
            display_name="Mother's Day",
            classification="gifting",
        )
        occurrence = _adopt(family_id="mothers_day")
        definition = new_response_definition(
            response_definition_id="md-def",
            family_id="mothers_day",
            treatment="anticipatory",
            max_lead=3,
            max_lag=0,
            transformation_method_reference="governed-ref",
        )
        payload = registry_to_dict([family], [occurrence], [definition])
        assert payload["schema_version"] == EVENT_REGISTRY_SCHEMA_VERSION
        assert payload["families"][0]["family_id"] == "mothers_day"
        assert payload["occurrences"][0]["start_date"] == "2026-03-22"
        assert payload["response_definitions"][0]["treatment"] == "anticipatory"

    def test_registry_has_content(self):
        family = new_family(
            family_id="mothers_day",
            display_name="Mother's Day",
            classification="gifting",
        )
        assert registry_has_content([family], [], [])
        assert not registry_has_content([], [], [])

    def test_registry_problems_surface_reference_errors(self):
        definition = new_response_definition(
            response_definition_id="md-def",
            family_id="missing",
            treatment="anticipatory",
            max_lead=3,
            max_lag=0,
            transformation_method_reference="governed-ref",
        )
        problems = registry_problems([], [_adopt()], [definition])
        assert any("references family 'missing'" in p for p in problems)

    def test_default_evidence_status_is_review_required(self):
        assert DEFAULT_EVENT_EVIDENCE_STATUS == "draft_review_required"
        definition = new_response_definition(
            response_definition_id="md-def",
            family_id="mothers_day",
            treatment="contemporaneous",
            max_lead=0,
            max_lag=0,
            transformation_method_reference="governed-ref",
        )
        assert definition.evidence_status == DEFAULT_EVENT_EVIDENCE_STATUS


def _preferred_row(**overrides):
    row = {
        "event_id": "mothers_day_2025_uk",
        "event_name": "Mother's Day",
        "event_family_id": "mothers_day",
        "event_type": "gifting",
        "market": "UK",
        "start_date": "2025-03-30",
        "end_date": "2025-03-30",
    }
    row.update(overrides)
    return row


class TestIsPreferredSourceRow:
    def test_full_seven_columns_is_preferred(self):
        assert is_preferred_source_row(_preferred_row()) is True
        assert missing_preferred_row_fields(_preferred_row()) == ()

    def test_legacy_four_column_row_is_not_preferred(self):
        legacy = {
            "event_id": "e1",
            "event_name": "Some event",
            "start_date": "2025-01-01",
            "end_date": "2025-01-01",
        }
        assert is_preferred_source_row(legacy) is False
        missing = missing_preferred_row_fields(legacy)
        assert "event_family_id" in missing
        assert "event_type" in missing
        assert "market" in missing


class TestBulkAdoptPreferredEventRows:
    def _adopt(self, rows, **registry):
        return bulk_adopt_preferred_event_rows(
            rows,
            source_id="events",
            source_version=1,
            families=registry.get("families", ()),
            occurrences=registry.get("occurrences", ()),
            response_definitions=registry.get("response_definitions", ()),
        )

    def test_gifting_row_creates_family_occurrence_and_response_definition(self):
        outcome = self._adopt([_preferred_row()])
        assert isinstance(outcome, BulkAdoptionOutcome)
        assert outcome.adopted_count == 1
        assert outcome.results[0].adopted is True
        assert outcome.results[0].created_family is True
        assert outcome.results[0].created_response_definition is True
        assert outcome.results[0].response_policy_required is False

        assert len(outcome.families) == 1
        family = outcome.families[0]
        assert family.family_id == "mothers_day"
        assert family.classification == "gifting"

        assert len(outcome.occurrences) == 1
        occurrence = outcome.occurrences[0]
        assert occurrence.event_id == "mothers_day_2025_uk"
        assert occurrence.market_scope == ("UK",)
        assert occurrence.family_id == "mothers_day"
        assert occurrence.start_date == "2025-03-30"
        assert occurrence.end_date == "2025-03-30"

        assert len(outcome.response_definitions) == 1
        definition = outcome.response_definitions[0]
        assert definition.response_definition_id == "mothers_day_default_response"
        assert definition.treatment == "anticipatory"
        assert definition.max_lead == 6
        assert definition.max_lag == 0

    def test_no_classification_or_treatment_derived_from_event_name(self):
        row = _preferred_row(event_name="Totally unrelated free text label")
        outcome = self._adopt([row])
        assert outcome.families[0].classification == "gifting"  # from event_type only

    def test_repeated_yearly_occurrences_share_one_family_and_definition(self):
        rows = [
            _preferred_row(
                event_id="mothers_day_2024_uk",
                start_date="2024-03-10",
                end_date="2024-03-10",
            ),
            _preferred_row(
                event_id="mothers_day_2025_uk",
                start_date="2025-03-30",
                end_date="2025-03-30",
            ),
        ]
        outcome = self._adopt(rows)
        assert outcome.adopted_count == 2
        assert len(outcome.families) == 1
        assert len(outcome.response_definitions) == 1
        assert len(outcome.occurrences) == 2
        assert outcome.results[1].created_family is False
        assert outcome.results[1].created_response_definition is False

    def test_uk_and_de_occurrences_share_family_with_distinct_occurrences(self):
        rows = [
            _preferred_row(event_id="mothers_day_2025_uk", market="UK"),
            _preferred_row(
                event_id="mothers_day_2025_de",
                market="DE",
                start_date="2025-05-11",
                end_date="2025-05-11",
            ),
        ]
        outcome = self._adopt(rows)
        assert outcome.adopted_count == 2
        assert len(outcome.families) == 1
        markets = {o.market_scope for o in outcome.occurrences}
        assert markets == {("UK",), ("DE",)}

    def test_conflicting_event_type_within_batch_blocks_those_rows(self):
        rows = [
            _preferred_row(event_id="a", event_type="gifting"),
            _preferred_row(event_id="b", event_type="remembrance"),
        ]
        outcome = self._adopt(rows)
        assert outcome.adopted_count == 0
        assert outcome.families == ()
        assert outcome.occurrences == ()
        for result in outcome.results:
            assert result.adopted is False
            assert "conflicting event_type" in result.problems[0]

    def test_conflicting_classification_against_existing_family_blocks(self):
        existing_family = new_family(
            family_id="mothers_day",
            display_name="Mother's Day (legacy)",
            classification="commercial",
        )
        outcome = self._adopt([_preferred_row()], families=[existing_family])
        assert outcome.adopted_count == 0
        assert outcome.results[0].adopted is False
        assert "conflicts with family" in outcome.results[0].problems[0]
        # The pre-existing family/registry must be untouched, not silently
        # reclassified.
        assert outcome.families == (existing_family,)

    def test_unsupported_event_type_is_response_policy_required_and_no_definition(self):
        row = _preferred_row(event_type="seasonal_pop_up")
        outcome = self._adopt([row])
        assert outcome.adopted_count == 1
        assert outcome.results[0].response_policy_required is True
        assert outcome.results[0].created_response_definition is False
        assert outcome.response_definitions == ()
        family = outcome.families[0]
        assert family.classification == "seasonal_pop_up"
        assert (
            family.classification_status
            == CLASSIFICATION_STATUS_RESPONSE_POLICY_REQUIRED
        )

    def test_promotion_event_type_creates_family_but_no_automatic_response_definition(
        self,
    ):
        row = _preferred_row(
            event_id="black_friday_2025_uk",
            event_name="Black Friday",
            event_family_id="black_friday",
            event_type="promotion",
            start_date="2025-11-28",
            end_date="2025-12-01",
        )
        outcome = self._adopt([row])
        assert outcome.adopted_count == 1
        family = outcome.families[0]
        assert family.family_id == "black_friday"
        assert (
            family.classification == "promotional"
        )  # real classification, not raw literal
        assert (
            outcome.response_definitions == ()
        )  # no auto policy - see brief section 9
        assert outcome.results[0].response_policy_required is True
        # Distinct, specific status - not the generic "unsupported type"
        # status - so the UI can state the disclosed, decision-required
        # reason (docs/named_event_promotional_window_decision_package.md).
        assert (
            family.classification_status
            == CLASSIFICATION_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED
        )
        assert (
            family.classification_status
            != CLASSIFICATION_STATUS_RESPONSE_POLICY_REQUIRED
        )

    def test_promotional_alias_also_gets_the_specific_status(self):
        row = _preferred_row(
            event_id="black_friday_2025_uk",
            event_family_id="black_friday",
            event_type="promotional",  # alias for "promotion"
        )
        outcome = self._adopt([row])
        assert outcome.families[0].classification_status == (
            CLASSIFICATION_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED
        )

    def test_missing_required_field_blocks_only_that_row(self):
        rows = [
            _preferred_row(event_id="good"),
            _preferred_row(event_id="bad", market=""),
        ]
        outcome = self._adopt(rows)
        assert outcome.adopted_count == 1
        bad_result = next(r for r in outcome.results if r.event_id == "bad")
        assert bad_result.adopted is False
        assert "market" in bad_result.problems[0]

    def test_end_date_before_start_date_blocks_the_row(self):
        row = _preferred_row(start_date="2025-03-31", end_date="2025-03-30")
        outcome = self._adopt([row])
        assert outcome.adopted_count == 0
        assert outcome.results[0].adopted is False

    def test_unknown_extra_columns_do_not_change_semantics(self):
        row = _preferred_row(some_unrelated_upstream_column="ignore me")
        outcome = self._adopt([row])
        assert outcome.adopted_count == 1
        assert outcome.families[0].classification == "gifting"
        assert "some_unrelated_upstream_column" not in outcome.families[0].to_dict()

    def test_factual_dates_and_market_survive_verbatim(self):
        row = _preferred_row(
            start_date="2025-11-28", end_date="2025-12-01", market="UK"
        )
        outcome = self._adopt([row])
        occurrence = outcome.occurrences[0]
        assert occurrence.start_date == "2025-11-28"
        assert occurrence.end_date == "2025-12-01"
        assert occurrence.market_scope == ("UK",)
