"""Tests for `core.named_event_diagnostics` - read-only per
`event_family_id x market` reporting over the governed named-event
registry and the actual prepared modelling frame. Diagnostic only: these
tests never assert anything about model-fitting behaviour changing, only
about the report being an accurate reflection of what `core.
named_event_fit_inputs` itself would (or would not) fit."""

from __future__ import annotations

import types

import numpy as np
import pandas as pd

from ancestry_mmm.core.named_event_diagnostics import (
    FIT_STATUS_INCLUDED_IN_FIT,
    FIT_STATUS_OUTSIDE_MODEL_WINDOW,
    FIT_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED,
    FIT_STATUS_RESPONSE_POLICY_REQUIRED,
    NAMED_EVENT_CONFIG_CHANGED_SINCE_FIT,
    NAMED_EVENT_CONFIG_CURRENT,
    NAMED_EVENT_CONFIG_UNKNOWN_NO_FIT_TIME_FINGERPRINT,
    RESPONSE_POLICY_NONE_REGISTERED,
    RESPONSE_POLICY_OPTED_IN,
    RESPONSE_POLICY_PROMOTIONAL_WINDOW_UNRESOLVED,
    RESPONSE_POLICY_RESPONSE_POLICY_REQUIRED,
    assess_named_event_drift,
    build_fitted_named_event_diagnostics,
    build_named_event_diagnostics,
)
from ancestry_mmm.core.named_event_fit_inputs import (
    build_named_event_fit_inputs,
    weeks_overlapping_event_interval,
    weekly_period_bounds_for_market,
)
from ancestry_mmm.core.named_event_response import NAMED_EVENT_RESPONSE_STRUCTURE
from ancestry_mmm.core.named_event_type_policy import (
    CLASSIFICATION_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED,
    CLASSIFICATION_STATUS_RESPONSE_POLICY_REQUIRED,
)
from ancestry_mmm.core.named_events import (
    DEFAULT_EVENT_EVIDENCE_STATUS,
    EventResponseDefinition,
    NamedEventFamily,
    NamedEventOccurrence,
)


def _family(**overrides):
    values = {
        "family_id": "mothers_day",
        "family_version": 1,
        "display_name": "Mother's Day",
        "classification": "gifting",
        "classification_status": DEFAULT_EVENT_EVIDENCE_STATUS,
    }
    values.update(overrides)
    return NamedEventFamily(**values)


def _occurrence(**overrides):
    values = {
        "event_id": "md-2026",
        "event_version": 1,
        "display_name": "Mother's Day 2026",
        "start_date": "2026-03-22",
        "end_date": "2026-03-22",
        "market_scope": ("UK",),
        "source_id": "events",
        "family_id": "mothers_day",
    }
    values.update(overrides)
    return NamedEventOccurrence(**values)


def _definition(**overrides):
    values = {
        "response_definition_id": "mothers_day_default_response",
        "response_definition_version": 1,
        "family_id": "mothers_day",
        "treatment": "anticipatory",
        "max_lead": 3,
        "max_lag": 0,
        "transformation_method_reference": NAMED_EVENT_RESPONSE_STRUCTURE,
    }
    values.update(overrides)
    return EventResponseDefinition(**values)


def _monday_frame(markets, n_weeks_per_market, *, start="2026-01-05"):
    """Explicit Monday-start weekly grid, one contiguous block per market
    (`data.preprocessor.prepare_fh_modeling_frame`'s own layout)."""
    dates = []
    market_bounds = []
    offset = 0
    for _m in markets:
        block_dates = pd.date_range(start, periods=n_weeks_per_market, freq="7D")
        dates.extend(block_dates)
        market_bounds.append((offset, offset + n_weeks_per_market))
        offset += n_weeks_per_market
    return {
        "markets": list(markets),
        "dates": np.array(dates, dtype="datetime64[ns]"),
        "market_bounds": market_bounds,
    }


class TestRepeatedYearlyOccurrencesCollapseIntoOneRow:
    def test_three_uk_occurrences_produce_one_row_with_correct_counts_and_dates(self):
        frame = _monday_frame(["UK"], 60, start="2024-01-01")
        occurrences = [
            _occurrence(
                event_id="md-2024", start_date="2024-03-10", end_date="2024-03-10"
            ),
            _occurrence(
                event_id="md-2025", start_date="2025-03-30", end_date="2025-03-30"
            ),
            _occurrence(
                event_id="md-2026", start_date="2026-03-15", end_date="2026-03-15"
            ),
        ]
        rows = build_named_event_diagnostics(
            frame,
            families=[_family()],
            occurrences=occurrences,
            response_definitions=[_definition()],
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.event_family_id == "mothers_day"
        assert row.market == "UK"
        assert row.occurrence_count == 3
        assert row.first_occurrence == "2024-03-10"
        assert row.last_occurrence == "2026-03-15"
        assert row.fit_status == FIT_STATUS_INCLUDED_IN_FIT
        assert row.response_policy == RESPONSE_POLICY_OPTED_IN


class TestUkAndDeAssessedSeparately:
    def test_two_markets_with_different_dates_produce_two_rows(self):
        frame = _monday_frame(["UK", "DE"], 80, start="2024-01-01")
        occurrences = [
            _occurrence(
                event_id="md-2025-uk",
                start_date="2025-03-30",
                end_date="2025-03-30",
                market_scope=("UK",),
            ),
            _occurrence(
                event_id="md-2025-de",
                start_date="2025-05-11",
                end_date="2025-05-11",
                market_scope=("DE",),
            ),
        ]
        rows = build_named_event_diagnostics(
            frame,
            families=[_family()],
            occurrences=occurrences,
            response_definitions=[_definition()],
        )
        assert len(rows) == 2
        by_market = {r.market: r for r in rows}
        assert set(by_market) == {"UK", "DE"}
        assert by_market["UK"].occurrence_count == 1
        assert by_market["DE"].occurrence_count == 1
        assert by_market["UK"].first_occurrence == "2025-03-30"
        assert by_market["DE"].first_occurrence == "2025-05-11"
        # Both markets fitted independently (Decision 12: unpooled default).
        assert by_market["UK"].fit_status == FIT_STATUS_INCLUDED_IN_FIT
        assert by_market["DE"].fit_status == FIT_STATUS_INCLUDED_IN_FIT


class TestEventOutsideModelWindow:
    def test_occurrence_outside_frame_contributes_no_fitted_support(self):
        frame = _monday_frame(["UK"], 10, start="2026-01-05")  # ~10 weeks, ends ~March
        occurrence = _occurrence(start_date="2027-06-01", end_date="2027-06-01")
        rows = build_named_event_diagnostics(
            frame,
            families=[_family()],
            occurrences=[occurrence],
            response_definitions=[_definition()],
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.model_periods_affected == 0
        assert row.fit_status == FIT_STATUS_OUTSIDE_MODEL_WINDOW
        assert row.fitted_support_weeks is None
        assert (
            "overlap" in row.exclusion_reason
            or "not part of this model" in row.exclusion_reason
        )

    def test_market_not_in_the_model_at_all_is_also_outside_model_window(self):
        frame = _monday_frame(["UK"], 20, start="2026-01-05")
        occurrence = _occurrence(
            start_date="2026-03-16", end_date="2026-03-16", market_scope=("FR",)
        )
        rows = build_named_event_diagnostics(
            frame,
            families=[_family()],
            occurrences=[occurrence],
            response_definitions=[_definition()],
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.market == "FR"
        assert row.fit_status == FIT_STATUS_OUTSIDE_MODEL_WINDOW
        assert "not part of this model" in row.exclusion_reason


class TestPromotionalFamily:
    def test_promotional_family_is_registered_but_not_fitted(self):
        frame = _monday_frame(["UK"], 20, start="2025-11-03")
        family = _family(
            family_id="black_friday",
            display_name="Black Friday",
            classification="promotional",
            classification_status=CLASSIFICATION_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED,
        )
        occurrence = _occurrence(
            event_id="black_friday_2025_uk",
            start_date="2025-11-28",
            end_date="2025-12-01",
            family_id="black_friday",
        )
        rows = build_named_event_diagnostics(
            frame, families=[family], occurrences=[occurrence], response_definitions=[]
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.event_family_id == "black_friday"
        assert row.event_type == "promotional"
        # The occurrence IS inside the model window (unlike the "outside
        # model window" case) - the exclusion is specifically the
        # unresolved response mechanism, not a data-coverage gap.
        assert row.model_periods_affected == 2  # crosses two Monday-start weeks
        assert row.fit_status == FIT_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED
        assert row.response_policy == RESPONSE_POLICY_PROMOTIONAL_WINDOW_UNRESOLVED
        assert row.fitted_support_weeks is None
        assert "decision-required" in row.exclusion_reason
        # Never presented as a fitted zero effect.
        assert row.fit_status != FIT_STATUS_INCLUDED_IN_FIT


class TestUnknownEventType:
    def test_unrecognised_event_type_is_response_policy_required(self):
        frame = _monday_frame(["UK"], 20, start="2026-01-05")
        family = _family(
            family_id="mystery_event",
            classification="seasonal_pop_up",
            classification_status=CLASSIFICATION_STATUS_RESPONSE_POLICY_REQUIRED,
        )
        occurrence = _occurrence(
            event_id="mystery-2026",
            start_date="2026-02-02",
            end_date="2026-02-02",
            family_id="mystery_event",
        )
        rows = build_named_event_diagnostics(
            frame, families=[family], occurrences=[occurrence], response_definitions=[]
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.fit_status == FIT_STATUS_RESPONSE_POLICY_REQUIRED
        assert row.response_policy == RESPONSE_POLICY_RESPONSE_POLICY_REQUIRED
        assert row.fitted_support_weeks is None
        assert row.model_periods_affected == 1


class TestNoRegistrationAtAll:
    def test_family_with_no_response_definition_is_none_registered(self):
        frame = _monday_frame(["UK"], 20, start="2026-01-05")
        rows = build_named_event_diagnostics(
            frame,
            families=[_family()],
            occurrences=[_occurrence(start_date="2026-01-19", end_date="2026-01-19")],
            response_definitions=[],
        )
        assert len(rows) == 1
        assert rows[0].response_policy == RESPONSE_POLICY_NONE_REGISTERED
        assert rows[0].temporal_treatment is None
        assert rows[0].max_lead_weeks is None
        assert rows[0].max_lag_weeks is None


class TestModelPeriodCountsMatchActualFitDesign:
    def test_fitted_support_weeks_matches_the_real_design_used_by_the_fit(self):
        frame = _monday_frame(["UK"], 20, start="2026-01-05")
        occurrence = _occurrence(start_date="2026-03-16", end_date="2026-03-16")
        definition = _definition(max_lead=3, max_lag=0)
        rows = build_named_event_diagnostics(
            frame,
            families=[_family()],
            occurrences=[occurrence],
            response_definitions=[definition],
        )
        assert len(rows) == 1
        row = rows[0]

        # Independently recompute what the real fit-input builder produces
        # for this exact frame/registry and cross-check.
        fit_inputs = build_named_event_fit_inputs(
            frame,
            families=[_family()],
            occurrences=[occurrence],
            response_definitions=[definition],
        )
        assert fit_inputs is not None
        block = fit_inputs.blocks_for_family("mothers_day")[0]
        expected_weeks = int(np.any(block.design != 0.0, axis=1).sum())

        assert row.fitted_support_weeks == expected_weeks
        assert row.fit_status == FIT_STATUS_INCLUDED_IN_FIT
        # The transformed (lead-extended) support must be at least as wide
        # as the raw factual-interval overlap it is built from.
        assert row.fitted_support_weeks >= row.model_periods_affected

    def test_model_periods_affected_matches_the_overlap_helper_directly(self):
        frame = _monday_frame(["UK"], 20, start="2025-11-03")
        occurrence = _occurrence(start_date="2025-11-28", end_date="2025-12-01")
        rows = build_named_event_diagnostics(
            frame,
            families=[_family()],
            occurrences=[occurrence],
            response_definitions=[_definition()],
        )
        row = rows[0]

        period_starts, period_ends = weekly_period_bounds_for_market(frame, "UK")
        expected = weeks_overlapping_event_interval(
            period_starts,
            period_ends,
            pd.Timestamp("2025-11-28"),
            pd.Timestamp("2025-12-01"),
        )
        assert row.model_periods_affected == len(expected) == 2


class TestSortedDeterministicOutput:
    def test_rows_are_sorted_by_family_then_market(self):
        frame = _monday_frame(["UK", "DE"], 30, start="2026-01-05")
        occurrences = [
            _occurrence(
                event_id="fd-2026-uk",
                family_id="fathers_day",
                start_date="2026-06-21",
                end_date="2026-06-21",
                market_scope=("UK",),
            ),
            _occurrence(start_date="2026-03-15", end_date="2026-03-15"),
        ]
        families = [
            _family(),
            _family(family_id="fathers_day", display_name="Father's Day"),
        ]
        rows = build_named_event_diagnostics(
            frame, families=families, occurrences=occurrences, response_definitions=[]
        )
        family_ids = [r.event_family_id for r in rows]
        assert family_ids == sorted(family_ids)


def _meta(**overrides):
    """A minimal fake `FHModelMeta` - `build_fitted_named_event_
    diagnostics`/`assess_named_event_drift` only ever read four attributes
    via `getattr`, so a `SimpleNamespace` exercises exactly that contract
    without needing a real PyMC-adjacent FHModelMeta construction. The
    hierarchical/market-specific model wiring tests separately prove the
    REAL `FHModelMeta` these functions consume in production is populated
    identically to what `_meta_from_fit` below reproduces here."""
    defaults = dict(
        named_event_fit_blocks=[],
        named_event_fit_block_provenance=[],
        named_event_fit_fingerprint="",
        named_event_response_definitions_at_fit=[],
    )
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _meta_from_fit(frame, *, families, occurrences, response_definitions):
    """Build the exact `meta` fields `core.hierarchical_model.
    build_fh_hierarchical_model` persists for a real fit - mirrors that
    function's own construction verbatim (see its "Diagnostics fit-time
    provenance" comment) without needing to build a real PyMC model."""
    fit_inputs = build_named_event_fit_inputs(
        frame,
        families=families,
        occurrences=occurrences,
        response_definitions=response_definitions,
    )
    if fit_inputs is None:
        return _meta()
    return _meta(
        named_event_fit_blocks=[(b.family_id, b.market) for b in fit_inputs.blocks],
        named_event_fit_block_provenance=[
            {
                "family_id": b.family_id,
                "market": b.market,
                "response_definition_id": b.response_definition_id,
                "response_definition_version": b.response_definition_version,
                "classification": b.classification,
                "fitted_support_weeks": int(np.any(b.design != 0.0, axis=1).sum()),
            }
            for b in fit_inputs.blocks
        ],
        named_event_fit_fingerprint=fit_inputs.fingerprint(),
        named_event_response_definitions_at_fit=list(
            fit_inputs.consumed_response_definitions()
        ),
    )


class TestBuildFittedNamedEventDiagnostics:
    """The "This fitted model" view - a pure function of `meta` alone."""

    def test_no_fitted_model_returns_empty(self):
        assert build_fitted_named_event_diagnostics(None) == ()
        assert build_fitted_named_event_diagnostics(_meta()) == ()

    def test_fitted_family_produces_a_row_with_full_provenance(self):
        frame = _monday_frame(["UK"], 20, start="2026-01-05")
        family = _family()
        occurrence = _occurrence(start_date="2026-03-16", end_date="2026-03-16")
        definition = _definition()
        meta = _meta_from_fit(
            frame,
            families=[family],
            occurrences=[occurrence],
            response_definitions=[definition],
        )
        rows = build_fitted_named_event_diagnostics(meta)
        assert len(rows) == 1
        row = rows[0]
        assert row.event_family_id == "mothers_day"
        assert row.market == "UK"
        assert row.response_definition_id == "mothers_day_default_response"
        assert row.response_definition_version == 1
        assert row.classification == "gifting"
        assert row.response_policy == RESPONSE_POLICY_OPTED_IN
        assert row.fit_status == FIT_STATUS_INCLUDED_IN_FIT
        assert row.fitted_support_weeks is not None and row.fitted_support_weeks > 0
        assert row.provenance_complete is True

    def test_pre_provenance_bundle_reports_unavailable_not_fabricated(self):
        # named_event_fit_blocks existed before named_event_fit_block_
        # provenance did - an old bundle has the former but not the latter.
        meta = _meta(named_event_fit_blocks=[("mothers_day", "UK")])
        rows = build_fitted_named_event_diagnostics(meta)
        assert len(rows) == 1
        row = rows[0]
        assert row.event_family_id == "mothers_day"
        assert row.market == "UK"
        assert row.fit_status == FIT_STATUS_INCLUDED_IN_FIT
        assert row.response_definition_id is None
        assert row.response_definition_version is None
        assert row.fitted_support_weeks is None
        assert row.provenance_complete is False

    def test_promotional_family_never_appears_here(self):
        # A promotional family never gets a response definition, so it
        # never gets a block, so it can never appear in the fitted view -
        # not even as an excluded row (this view has no such concept).
        assert build_fitted_named_event_diagnostics(_meta()) == ()


class TestAssessNamedEventDrift:
    def test_unchanged_registry_gives_no_drift(self):
        frame = _monday_frame(["UK"], 20, start="2026-01-05")
        family = _family()
        occurrence = _occurrence(start_date="2026-03-16", end_date="2026-03-16")
        definition = _definition()
        meta = _meta_from_fit(
            frame,
            families=[family],
            occurrences=[occurrence],
            response_definitions=[definition],
        )
        result = assess_named_event_drift(
            frame,
            meta,
            families=[family],
            occurrences=[occurrence],
            response_definitions=[definition],
        )
        assert result.status == NAMED_EVENT_CONFIG_CURRENT
        assert result.reasons == ()

    def test_adding_a_future_occurrence_does_not_rewrite_the_fitted_view(self):
        frame = _monday_frame(["UK"], 20, start="2026-01-05")  # ends well before 2027
        family = _family()
        occurrence = _occurrence(start_date="2026-03-16", end_date="2026-03-16")
        definition = _definition()
        meta = _meta_from_fit(
            frame,
            families=[family],
            occurrences=[occurrence],
            response_definitions=[definition],
        )
        fitted_before = build_fitted_named_event_diagnostics(meta)

        future_occurrence = _occurrence(
            event_id="md-2027", start_date="2027-03-15", end_date="2027-03-15"
        )
        # The fitted view reads only `meta` - it is identical regardless of
        # what the registry looks like now.
        fitted_after = build_fitted_named_event_diagnostics(meta)
        assert fitted_after == fitted_before

        # And since the future occurrence falls entirely outside this
        # fit's own historical frame, it changes nothing about what a
        # replay against that same frame would produce either.
        result = assess_named_event_drift(
            frame,
            meta,
            families=[family],
            occurrences=[occurrence, future_occurrence],
            response_definitions=[definition],
        )
        assert result.status == NAMED_EVENT_CONFIG_CURRENT

    def test_changing_an_occurrence_date_leaves_fitted_view_unchanged_but_shows_drift(
        self,
    ):
        frame = _monday_frame(["UK"], 20, start="2026-01-05")
        family = _family()
        occurrence = _occurrence(start_date="2026-03-16", end_date="2026-03-16")
        definition = _definition()
        meta = _meta_from_fit(
            frame,
            families=[family],
            occurrences=[occurrence],
            response_definitions=[definition],
        )
        fitted_before = build_fitted_named_event_diagnostics(meta)

        changed_occurrence = _occurrence(
            event_version=2, start_date="2026-03-23", end_date="2026-03-23"
        )
        fitted_after = build_fitted_named_event_diagnostics(meta)
        assert fitted_after == fitted_before  # meta itself never changes

        result = assess_named_event_drift(
            frame,
            meta,
            families=[family],
            occurrences=[changed_occurrence],
            response_definitions=[definition],
        )
        assert result.status == NAMED_EVENT_CONFIG_CHANGED_SINCE_FIT
        assert any(
            "event occurrence set or timing changed" in r for r in result.reasons
        )

    def test_classification_change_is_visible_as_drift(self):
        frame = _monday_frame(["UK"], 20, start="2026-01-05")
        family = _family()
        occurrence = _occurrence(start_date="2026-03-16", end_date="2026-03-16")
        definition = _definition()
        meta = _meta_from_fit(
            frame,
            families=[family],
            occurrences=[occurrence],
            response_definitions=[definition],
        )
        reclassified_family = _family(classification="commercial")
        result = assess_named_event_drift(
            frame,
            meta,
            families=[reclassified_family],
            occurrences=[occurrence],
            response_definitions=[definition],
        )
        assert result.status == NAMED_EVENT_CONFIG_CHANGED_SINCE_FIT
        assert any("classification" in r for r in result.reasons)

    def test_new_family_after_fit_is_not_shown_as_previously_fitted(self):
        frame = _monday_frame(["UK"], 30, start="2026-01-05")
        family = _family()
        occurrence = _occurrence(start_date="2026-03-16", end_date="2026-03-16")
        definition = _definition()
        meta = _meta_from_fit(
            frame,
            families=[family],
            occurrences=[occurrence],
            response_definitions=[definition],
        )

        fitted = build_fitted_named_event_diagnostics(meta)
        assert len(fitted) == 1
        assert fitted[0].event_family_id == "mothers_day"

        new_family = _family(family_id="fathers_day", display_name="Father's Day")
        new_occurrence = _occurrence(
            event_id="fd-2026",
            family_id="fathers_day",
            start_date="2026-06-21",
            end_date="2026-06-21",
        )
        new_definition = _definition(
            response_definition_id="fathers_day_default_response",
            family_id="fathers_day",
        )
        result = assess_named_event_drift(
            frame,
            meta,
            families=[family, new_family],
            occurrences=[occurrence, new_occurrence],
            response_definitions=[definition, new_definition],
        )
        assert result.status == NAMED_EVENT_CONFIG_CHANGED_SINCE_FIT
        assert any("newly included" in r and "fathers_day" in r for r in result.reasons)
        # The fitted view itself, rebuilt from the SAME meta, still only
        # ever shows the family actually consumed at fit time.
        assert build_fitted_named_event_diagnostics(meta) == fitted

    def test_promotional_family_remains_registered_not_fitted(self):
        frame = _monday_frame(["UK"], 20, start="2025-11-03")
        family = _family(
            family_id="black_friday",
            display_name="Black Friday",
            classification="promotional",
            classification_status=CLASSIFICATION_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED,
        )
        occurrence = _occurrence(
            event_id="black_friday_2025_uk",
            family_id="black_friday",
            start_date="2025-11-28",
            end_date="2025-12-01",
        )
        # Never fitted - no meta consumption at all.
        meta = _meta()
        assert build_fitted_named_event_diagnostics(meta) == ()

        current_rows = build_named_event_diagnostics(
            frame, families=[family], occurrences=[occurrence], response_definitions=[]
        )
        assert len(current_rows) == 1
        assert current_rows[0].fit_status == FIT_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED
        assert (
            current_rows[0].response_policy
            == RESPONSE_POLICY_PROMOTIONAL_WINDOW_UNRESOLVED
        )

    def test_no_fit_time_fingerprint_reports_unknown_not_current_or_changed(self):
        # A model fitted before named_event_fit_fingerprint existed, but
        # which DID consume a named event (named_event_fit_blocks
        # non-empty) - drift genuinely cannot be assessed.
        frame = _monday_frame(["UK"], 20, start="2026-01-05")
        family = _family()
        occurrence = _occurrence(start_date="2026-03-16", end_date="2026-03-16")
        definition = _definition()
        meta = _meta(named_event_fit_blocks=[("mothers_day", "UK")])
        result = assess_named_event_drift(
            frame,
            meta,
            families=[family],
            occurrences=[occurrence],
            response_definitions=[definition],
        )
        assert result.status == NAMED_EVENT_CONFIG_UNKNOWN_NO_FIT_TIME_FINGERPRINT

    def test_no_events_ever_consumed_and_none_opted_in_now_is_current(self):
        frame = _monday_frame(["UK"], 20, start="2026-01-05")
        result = assess_named_event_drift(
            frame, _meta(), families=[], occurrences=[], response_definitions=[]
        )
        assert result.status == NAMED_EVENT_CONFIG_CURRENT

    def test_newly_opted_in_event_when_fit_had_none_is_changed(self):
        frame = _monday_frame(["UK"], 20, start="2026-01-05")
        family = _family()
        occurrence = _occurrence(start_date="2026-03-16", end_date="2026-03-16")
        definition = _definition()
        result = assess_named_event_drift(
            frame,
            _meta(),
            families=[family],
            occurrences=[occurrence],
            response_definitions=[definition],
        )
        assert result.status == NAMED_EVENT_CONFIG_CHANGED_SINCE_FIT
