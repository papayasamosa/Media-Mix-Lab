"""Blocker C (duplicate-definition governance follow-up): an intentionally
malformed named-event registry - one family with more than one current,
opted-in `EventResponseDefinition` (reachable via the pre-existing manual
"Register response definition" admin form on Data Upload, unrelated to
bulk adoption) - must fail closed at the core invariant boundary
(`core.named_event_fit_inputs.build_named_event_fit_inputs` raises
`NamedEventRegistryGovernanceError`) and must never crash any live page
that builds current named-event fit inputs or current named-event
identity from it. Covers all six page paths the review identified: Model
Training, Diagnostics, Curve Bank, Scenario Planner, Project Export,
Official Curve Generation."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

from ancestry_mmm.core.named_event_fit_inputs import (
    NamedEventRegistryGovernanceError,
    build_named_event_fit_inputs,
)
from ancestry_mmm.core.named_event_response import NAMED_EVENT_RESPONSE_STRUCTURE
from ancestry_mmm.core.named_events import (
    EventResponseDefinition,
    NamedEventFamily,
    NamedEventOccurrence,
)
from ancestry_mmm.tests.support.lifecycle_fixture import build_fitted_model

st.page_link = lambda *a, **k: None

ROOT = Path(__file__).parent.parent


def _malformed_registry():
    """One family, one occurrence, TWO current opted-in response
    definitions under distinct ids - the exact invalid state the manual
    admin form can already produce (unrelated to, and not fixed by, the
    bulk-adoption hardening in this same PR)."""
    family = NamedEventFamily(
        family_id="mothers_day",
        family_version=1,
        display_name="Mother's Day",
        classification="gifting",
    )
    occurrence = NamedEventOccurrence(
        event_id="md-2026",
        event_version=1,
        display_name="Mother's Day 2026",
        start_date="2026-03-22",
        end_date="2026-03-22",
        market_scope=("UK",),
        source_id="events",
        family_id="mothers_day",
    )
    definition_a = EventResponseDefinition(
        response_definition_id="mothers_day_a",
        response_definition_version=1,
        family_id="mothers_day",
        treatment="anticipatory",
        max_lead=6,
        max_lag=0,
        transformation_method_reference=NAMED_EVENT_RESPONSE_STRUCTURE,
    )
    definition_b = EventResponseDefinition(
        response_definition_id="mothers_day_b",
        response_definition_version=1,
        family_id="mothers_day",
        treatment="anticipatory",
        max_lead=6,
        max_lag=0,
        transformation_method_reference=NAMED_EVENT_RESPONSE_STRUCTURE,
    )
    return [family], [occurrence], [definition_a, definition_b]


def test_core_invariant_boundary_still_raises_closed():
    """The defensive check itself - never removed, never picks a
    definition - is the foundation every page-level fix below relies on."""
    fitted = build_fitted_model()
    families, occurrences, definitions = _malformed_registry()
    raised = False
    try:
        build_named_event_fit_inputs(
            fitted.frame,
            families=families,
            occurrences=occurrences,
            response_definitions=definitions,
        )
    except NamedEventRegistryGovernanceError:
        raised = True
    assert raised


def _seed_common_fitted_state(at: AppTest, fitted) -> None:
    at.session_state["frame"] = fitted.frame
    at.session_state["model_spec"] = fitted.model_spec_dict
    at.session_state["model_meta"] = fitted.meta
    at.session_state["trace"] = fitted.trace
    at.session_state["posterior_params"] = fitted.posterior_params
    at.session_state["model_type"] = "shared"
    at.session_state["model_run_id"] = fitted.model_run_id
    at.session_state["prior_config"] = fitted.prior_config
    at.session_state["dna_lag_weeks"] = fitted.dna_lag_weeks
    at.session_state["outcome_definitions"] = [fitted.outcome_definition.to_dict()]
    at.session_state["activity_definitions"] = [
        a.to_dict() for a in fitted.activity_definitions
    ]
    families, occurrences, definitions = _malformed_registry()
    at.session_state["named_event_families"] = [f.to_dict() for f in families]
    at.session_state["named_event_occurrences"] = [o.to_dict() for o in occurrences]
    at.session_state["named_event_response_definitions"] = [
        d.to_dict() for d in definitions
    ]


def _all_error_text(at: AppTest) -> str:
    return "\n".join((e.value or "") for e in at.error)


def test_model_training_does_not_crash_and_shows_governance_error():
    fitted = build_fitted_model()
    at = AppTest.from_file(
        str(ROOT / "pages" / "05_Model_Training.py"), default_timeout=90
    )
    _seed_common_fitted_state(at, fitted)
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    text = _all_error_text(at)
    assert "Named-event registry is invalid" in text
    assert "mothers_day" in text


def test_diagnostics_does_not_crash_and_shows_governance_error():
    fitted = build_fitted_model()
    at = AppTest.from_file(
        str(ROOT / "pages" / "06_Diagnostics.py"), default_timeout=90
    )
    _seed_common_fitted_state(at, fitted)
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    text = _all_error_text(at)
    assert "Named-event registry is invalid" in text


def test_curve_bank_does_not_crash_and_shows_governance_error():
    fitted = build_fitted_model()
    at = AppTest.from_file(
        str(ROOT / "pages" / "07_Results_Curve_Bank.py"), default_timeout=90
    )
    _seed_common_fitted_state(at, fitted)
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    text = _all_error_text(at)
    assert "Named-event registry is invalid" in text


def test_scenario_planner_does_not_crash_and_shows_governance_error():
    fitted = build_fitted_model()
    at = AppTest.from_file(
        str(ROOT / "pages" / "08_Scenario_Planner.py"), default_timeout=90
    )
    _seed_common_fitted_state(at, fitted)
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    text = _all_error_text(at)
    assert "Named-event registry is invalid" in text


def test_project_export_does_not_crash_and_shows_governance_error(
    monkeypatch, tmp_path
):
    # The named-event identity computation on this page lives inside
    # _resolve_official_curve_artifact_rows(), reached only once at least
    # one official curve artifact is loaded - sandbox CURVE_ARTIFACT_ROOT
    # and seed one minimal (otherwise unrelated) artifact so this path is
    # actually exercised, mirroring test_project_export_page_apptest.py's
    # own monkeypatch pattern.
    import ancestry_mmm.utils.session_state as ss
    from ancestry_mmm.tests.support.lifecycle_fixture import write_unrelated_artifact

    artifact_root = tmp_path / "artifact-root"
    monkeypatch.setattr(ss, "CURVE_ARTIFACT_ROOT", artifact_root)
    project_name = "test-project-export-governance"
    write_unrelated_artifact(artifact_root / project_name)

    fitted = build_fitted_model()
    at = AppTest.from_file(
        str(ROOT / "pages" / "09_Project_Export.py"), default_timeout=90
    )
    _seed_common_fitted_state(at, fitted)
    at.session_state["project_name"] = project_name
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    text = _all_error_text(at)
    assert "Named-event registry is invalid" in text


def test_official_curve_generation_does_not_crash_and_shows_governance_error():
    fitted = build_fitted_model()
    at = AppTest.from_file(
        str(ROOT / "pages" / "13_Official_Curve_Generation.py"), default_timeout=90
    )
    _seed_common_fitted_state(at, fitted)
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    text = _all_error_text(at)
    assert "Named-event registry is invalid" in text


def test_curve_bank_cannot_treat_invalid_registry_as_current_or_approved():
    """current_identity must stay None so approval-matching can never run
    against a fabricated/partial identity - never a real match, never a
    silently-approved state."""
    fitted = build_fitted_model()
    at = AppTest.from_file(
        str(ROOT / "pages" / "07_Results_Curve_Bank.py"), default_timeout=90
    )
    _seed_common_fitted_state(at, fitted)
    at.session_state["model_approval"] = {
        "model_run_id": fitted.model_run_id,
        "data_fingerprint": fitted.data_fingerprint,
        "model_spec_fingerprint": fitted.model_spec_fingerprint,
        "posterior_fingerprint": fitted.posterior_fingerprint,
    }
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    text = "\n".join(
        (w.value or "") for w in list(at.warning) + list(at.success) + list(at.info)
    )
    assert "approved and current" not in text.lower()
