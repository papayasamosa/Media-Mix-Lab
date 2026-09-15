"""
Implementation-brief final audit: proves the single existing model-identity
invalidation chain - `core.fingerprint.fingerprint_model_spec` ->
`ModelIdentity`/`ModelApproval` matching -> `CurveService.authorize_use` ->
`core.optimization.validate_scenario_dependencies` -> export/import
reconstruction (`core.persistence.current_model_identity_fingerprints`) -
actually behaves correctly for a governed named-event change, exactly
mirroring `test_search_object_stale_state_integration.py`'s own structure
and precedent for Search objects. No second, named-event-specific staleness
mechanism is introduced anywhere: every check below reuses `core.
named_event_fit_inputs.current_named_event_identity_fingerprints` - the
same shared helper `pages/05_Model_Training.py`, `06_Diagnostics.py`,
`07_Results_Curve_Bank.py`, `08_Scenario_Planner.py`, `09_Project_Export.py`
and `13_Official_Curve_Generation.py` all call identically.

No live MCMC/NUTS sampling - reuses the shared deterministic
`ancestry_mmm.tests.support.lifecycle_fixture` builders.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from ancestry_mmm.application.curve_service import (
    CurveService,
    CurveUseNotAuthorizedError,
)
from ancestry_mmm.core.named_event_response import NAMED_EVENT_RESPONSE_STRUCTURE
from ancestry_mmm.core.named_events import (
    DEFAULT_EVENT_EVIDENCE_STATUS,
    EventResponseDefinition,
    NamedEventFamily,
    NamedEventOccurrence,
)
from ancestry_mmm.core.optimization import validate_scenario_dependencies
from ancestry_mmm.core.persistence import current_model_identity_fingerprints
from ancestry_mmm.tests.support.lifecycle_fixture import (
    MARKET,
    build_fitted_model,
    build_lifecycle_project,
    build_saved_scenario_dict,
    build_scenario_validation_context,
    create_official_artifacts,
    evaluate_official_manual_scenario,
    recompute_model_spec_fingerprint,
)

# build_transformed_data() (the fixture's fitted frame) spans
# pd.date_range("2024-01-01", periods=16, freq="W") - Sundays 2024-01-07
# through ~2024-04-14. 2024-02-11 is a Sunday well inside that window.
FITTED_OCCURRENCE_DATE = "2024-02-11"


def _family(classification: str = "gifting") -> NamedEventFamily:
    return NamedEventFamily(
        family_id="mothers_day",
        family_version=1,
        display_name="Mother's Day",
        classification=classification,
        classification_status=DEFAULT_EVENT_EVIDENCE_STATUS,
    )


def _occurrence(
    *,
    event_id: str = "md-2024",
    event_version: int = 1,
    start_date: str = FITTED_OCCURRENCE_DATE,
    end_date: str = FITTED_OCCURRENCE_DATE,
) -> NamedEventOccurrence:
    return NamedEventOccurrence(
        event_id=event_id,
        event_version=event_version,
        display_name="Mother's Day 2024",
        start_date=start_date,
        end_date=end_date,
        market_scope=(MARKET,),
        source_id="events",
        family_id="mothers_day",
    )


def _definition(version: int = 1) -> EventResponseDefinition:
    return EventResponseDefinition(
        response_definition_id="mothers_day_default_response",
        response_definition_version=version,
        family_id="mothers_day",
        treatment="anticipatory",
        max_lead=3,
        max_lag=0,
        transformation_method_reference=NAMED_EVENT_RESPONSE_STRUCTURE,
    )


def _fitted_registry():
    """The named-event registry the shared `project.fitted` below is
    actually built (and fingerprinted) against."""
    return [_family()], [_occurrence()], [_definition()]


class TestUnchangedRegistryDoesNotStale:
    def test_model_identity_fingerprint_unchanged(self):
        families, occurrences, definitions = _fitted_registry()
        project = build_lifecycle_project(
            named_event_families=families,
            named_event_occurrences=occurrences,
            named_event_response_definitions=definitions,
        )
        recomputed_fp = recompute_model_spec_fingerprint(
            project.fitted,
            named_event_families=families,
            named_event_occurrences=occurrences,
            named_event_response_definitions=definitions,
        )
        assert recomputed_fp == project.fitted.model_spec_fingerprint

    def test_official_curve_current_use_still_authorized(self, tmp_path):
        families, occurrences, definitions = _fitted_registry()
        project = build_lifecycle_project(
            named_event_families=families,
            named_event_occurrences=occurrences,
            named_event_response_definitions=definitions,
        )
        model_input_result, _ = create_official_artifacts(
            project, tmp_path / "curve-artifacts"
        )
        authorization = CurveService().authorize_use(
            model_input_result.artifact,
            "headline_reporting",
            current_governance=project.governance,
        )
        assert authorization.authorized is True


class TestOccurrenceDateChangeStales:
    """Changing an already-fitted family's occurrence date - a new
    occurrence version, same event_id/family/market - must stale the fit,
    even though the family/market block set and the response-definition
    id/version are unchanged (this is the "event occurrence set or timing
    changed" residual case `core.named_event_diagnostics.assess_named_
    event_drift` also reports, proved here through the official chain)."""

    def _edited_occurrence(self) -> NamedEventOccurrence:
        return _occurrence(event_version=2, start_date="2024-02-18", end_date="2024-02-18")

    def test_model_identity_fingerprint_changes(self):
        families, occurrences, definitions = _fitted_registry()
        project = build_lifecycle_project(
            named_event_families=families,
            named_event_occurrences=occurrences,
            named_event_response_definitions=definitions,
        )
        recomputed_fp = recompute_model_spec_fingerprint(
            project.fitted,
            named_event_families=families,
            named_event_occurrences=[self._edited_occurrence()],
            named_event_response_definitions=definitions,
        )
        assert recomputed_fp != project.fitted.model_spec_fingerprint

    def test_official_curve_current_use_rejected(self, tmp_path):
        families, occurrences, definitions = _fitted_registry()
        project = build_lifecycle_project(
            named_event_families=families,
            named_event_occurrences=occurrences,
            named_event_response_definitions=definitions,
        )
        recomputed_fp = recompute_model_spec_fingerprint(
            project.fitted,
            named_event_families=families,
            named_event_occurrences=[self._edited_occurrence()],
            named_event_response_definitions=definitions,
        )
        model_input_result, _ = create_official_artifacts(
            project, tmp_path / "curve-artifacts"
        )
        stale_governance = replace(
            project.governance,
            model_identity=replace(
                project.governance.model_identity,
                model_spec_fingerprint=recomputed_fp,
            ),
        )
        with pytest.raises(CurveUseNotAuthorizedError):
            CurveService().authorize_use(
                model_input_result.artifact,
                "headline_reporting",
                current_governance=stale_governance,
            )

    def test_saved_scenario_flagged_stale(self, tmp_path):
        families, occurrences, definitions = _fitted_registry()
        project = build_lifecycle_project(
            named_event_families=families,
            named_event_occurrences=occurrences,
            named_event_response_definitions=definitions,
        )
        recomputed_fp = recompute_model_spec_fingerprint(
            project.fitted,
            named_event_families=families,
            named_event_occurrences=[self._edited_occurrence()],
            named_event_response_definitions=definitions,
        )
        scenario_result = evaluate_official_manual_scenario(project)
        scenario_dict = build_saved_scenario_dict(project, scenario_result)
        context = replace(
            build_scenario_validation_context(project, scenario_dict),
            model_spec_fingerprint=recomputed_fp,
        )
        issues = validate_scenario_dependencies(scenario_dict, context=context)
        assert any(
            issue.issue_type == "stale" and "Model spec fingerprint" in issue.detail
            for issue in issues
        )


class TestOccurrenceAddedOrRemovedStales:
    def test_adding_a_second_occurrence_changes_the_fitted_design_and_stales(self):
        families, occurrences, definitions = _fitted_registry()
        project = build_lifecycle_project(
            named_event_families=families,
            named_event_occurrences=occurrences,
            named_event_response_definitions=definitions,
        )
        # Within the fitted frame's own 16-week window (2024-01-07 through
        # ~2024-04-14) but far enough from FITTED_OCCURRENCE_DATE that it
        # activates additional weeks the original single occurrence never
        # reached (max_lead=3 weeks around 2024-02-11 only reaches back to
        # ~2024-01-21).
        second_occurrence = _occurrence(
            event_id="md-2024-b", start_date="2024-04-07", end_date="2024-04-07"
        )
        recomputed_fp = recompute_model_spec_fingerprint(
            project.fitted,
            named_event_families=families,
            named_event_occurrences=[*occurrences, second_occurrence],
            named_event_response_definitions=definitions,
        )
        assert recomputed_fp != project.fitted.model_spec_fingerprint

    def test_removing_the_only_occurrence_stales(self):
        families, occurrences, definitions = _fitted_registry()
        project = build_lifecycle_project(
            named_event_families=families,
            named_event_occurrences=occurrences,
            named_event_response_definitions=definitions,
        )
        recomputed_fp = recompute_model_spec_fingerprint(
            project.fitted,
            named_event_families=families,
            named_event_occurrences=[],
            named_event_response_definitions=definitions,
        )
        assert recomputed_fp != project.fitted.model_spec_fingerprint


class TestClassificationChangeStales:
    """The specific regression this whole audit exists for: a family's
    classification changes (gifting -> promotion) while the fitted design
    itself is unaffected (NamedEventFitInputs.fingerprint() deliberately
    excludes classification) - must still stale through the SEPARATE
    named_event_classification_fingerprint component."""

    def test_model_identity_fingerprint_changes(self):
        families, occurrences, definitions = _fitted_registry()
        project = build_lifecycle_project(
            named_event_families=families,
            named_event_occurrences=occurrences,
            named_event_response_definitions=definitions,
        )
        recomputed_fp = recompute_model_spec_fingerprint(
            project.fitted,
            named_event_families=[_family(classification="promotion")],
            named_event_occurrences=occurrences,
            named_event_response_definitions=definitions,
        )
        assert recomputed_fp != project.fitted.model_spec_fingerprint

    def test_official_curve_current_use_rejected(self, tmp_path):
        families, occurrences, definitions = _fitted_registry()
        project = build_lifecycle_project(
            named_event_families=families,
            named_event_occurrences=occurrences,
            named_event_response_definitions=definitions,
        )
        recomputed_fp = recompute_model_spec_fingerprint(
            project.fitted,
            named_event_families=[_family(classification="promotion")],
            named_event_occurrences=occurrences,
            named_event_response_definitions=definitions,
        )
        model_input_result, _ = create_official_artifacts(
            project, tmp_path / "curve-artifacts"
        )
        stale_governance = replace(
            project.governance,
            model_identity=replace(
                project.governance.model_identity,
                model_spec_fingerprint=recomputed_fp,
            ),
        )
        with pytest.raises(CurveUseNotAuthorizedError):
            CurveService().authorize_use(
                model_input_result.artifact,
                "headline_reporting",
                current_governance=stale_governance,
            )


class TestResponseDefinitionVersionChangeStales:
    def test_model_identity_fingerprint_changes(self):
        families, occurrences, definitions = _fitted_registry()
        project = build_lifecycle_project(
            named_event_families=families,
            named_event_occurrences=occurrences,
            named_event_response_definitions=definitions,
        )
        widened_definition = replace(
            _definition(version=2), max_lead=6
        )
        recomputed_fp = recompute_model_spec_fingerprint(
            project.fitted,
            named_event_families=families,
            named_event_occurrences=occurrences,
            named_event_response_definitions=[widened_definition],
        )
        assert recomputed_fp != project.fitted.model_spec_fingerprint

    def test_saved_scenario_flagged_stale(self, tmp_path):
        families, occurrences, definitions = _fitted_registry()
        project = build_lifecycle_project(
            named_event_families=families,
            named_event_occurrences=occurrences,
            named_event_response_definitions=definitions,
        )
        widened_definition = replace(_definition(version=2), max_lead=6)
        recomputed_fp = recompute_model_spec_fingerprint(
            project.fitted,
            named_event_families=families,
            named_event_occurrences=occurrences,
            named_event_response_definitions=[widened_definition],
        )
        scenario_result = evaluate_official_manual_scenario(project)
        scenario_dict = build_saved_scenario_dict(project, scenario_result)
        context = replace(
            build_scenario_validation_context(project, scenario_dict),
            model_spec_fingerprint=recomputed_fp,
        )
        issues = validate_scenario_dependencies(scenario_dict, context=context)
        assert any(
            issue.issue_type == "stale" and "Model spec fingerprint" in issue.detail
            for issue in issues
        )


class TestNoNamedEventsBehavesExactlyAsBefore:
    """A project that never consumed a named event must fingerprint
    identically to `build_fitted_model()`'s pre-feature baseline - adding
    named-event fingerprinting must never inject a non-None value, or
    every pre-existing approval with no named events would be silently
    invalidated."""

    def test_fingerprint_matches_the_plain_baseline_build(self):
        baseline = build_fitted_model()
        with_no_named_events = build_fitted_model(
            named_event_families=[], named_event_occurrences=[], named_event_response_definitions=[]
        )
        assert (
            with_no_named_events.model_spec_fingerprint
            == baseline.model_spec_fingerprint
        )

    def test_recompute_with_no_registry_matches_no_named_events_baseline(self):
        baseline = build_fitted_model()
        recomputed_fp = recompute_model_spec_fingerprint(
            baseline,
            named_event_families=[],
            named_event_occurrences=[],
            named_event_response_definitions=[],
        )
        assert recomputed_fp == baseline.model_spec_fingerprint


def test_export_import_reconstruction_does_not_silently_present_stale_as_current(
    tmp_path,
):
    """Project Export's reconstruction path
    (`core.persistence.current_model_identity_fingerprints`, the function
    `application.project_service.verify_imported_readiness`/`09_Project_
    Export.py`'s own resumability check ultimately rely on) must recompute
    the SAME named-event-aware `model_spec_fingerprint` from a bundle's
    exported registry as the live app would - proving a bundle exported
    with a named-event registry that changed AFTER the fit (e.g. an
    occurrence date corrected post-fit) reconstructs as genuinely
    different from the original fit-time identity, never silently
    reported as still matching."""
    from ancestry_mmm.core.persistence import export_project, import_project

    families, occurrences, definitions = _fitted_registry()
    from ancestry_mmm.application.event_service import registry_to_dict

    project = build_lifecycle_project(
        named_event_families=families,
        named_event_occurrences=occurrences,
        named_event_response_definitions=definitions,
    )

    # The registry as it stands NOW (post-fit edit: the occurrence date was
    # corrected) - what actually gets exported in the bundle.
    edited_occurrence = _occurrence(
        event_version=2, start_date="2024-02-18", end_date="2024-02-18"
    )
    named_events_payload = registry_to_dict(families, [edited_occurrence], definitions)

    bundle_path = export_project(
        tmp_path / "bundle.zip",
        raw_sources={"joined": project.fitted.transformed_data.copy()},
        transformed_data=project.fitted.transformed_data,
        pipeline_steps=[],
        model_spec=project.fitted.model_spec_dict,
        prior_config=project.fitted.prior_config,
        dna_lag_weeks=project.fitted.dna_lag_weeks,
        trace=project.fitted.trace,
        scenarios=[],
        model_approval=project.approval.to_dict(),
        model_run_id=project.fitted.model_run_id,
        model_meta=project.fitted.meta,
        outcome_definitions=[project.fitted.outcome_definition.to_dict()],
        activity_definitions=[a.to_dict() for a in project.fitted.activity_definitions],
        outcome_approvals=[project.outcome_approval.to_dict()],
        validation_policy=project.policy.to_dict(),
        diagnostics_artefact=project.diagnostics.to_dict(),
        approval_readiness=project.readiness.to_dict(),
        media_cost_mappings=project.cost_mapping_registry.to_dict(),
        named_events=named_events_payload,
    )
    imported = import_project(bundle_path)

    from ancestry_mmm.core.persistence import reconstruct_model_state

    reconstructed = reconstruct_model_state(imported)
    assert reconstructed["frame"] is not None
    assert reconstructed["posterior_params"] is not None

    _, spec_fp, _ = current_model_identity_fingerprints(imported, reconstructed)
    # The reconstructed identity must NOT silently claim to match the
    # original fit-time identity - the occurrence date changed after
    # fitting, and the official chain must see that.
    assert spec_fp != project.fitted.model_spec_fingerprint


def test_export_import_reconstruction_matches_when_registry_is_unchanged(tmp_path):
    """The mirror-image of the test above: exporting the SAME registry the
    model was actually fitted against reconstructs the identical
    model_spec_fingerprint - proving the fix does not spuriously stale an
    unchanged project."""
    from ancestry_mmm.application.event_service import registry_to_dict
    from ancestry_mmm.core.persistence import export_project, import_project

    families, occurrences, definitions = _fitted_registry()
    project = build_lifecycle_project(
        named_event_families=families,
        named_event_occurrences=occurrences,
        named_event_response_definitions=definitions,
    )
    named_events_payload = registry_to_dict(families, occurrences, definitions)

    bundle_path = export_project(
        tmp_path / "bundle.zip",
        raw_sources={"joined": project.fitted.transformed_data.copy()},
        transformed_data=project.fitted.transformed_data,
        pipeline_steps=[],
        model_spec=project.fitted.model_spec_dict,
        prior_config=project.fitted.prior_config,
        dna_lag_weeks=project.fitted.dna_lag_weeks,
        trace=project.fitted.trace,
        scenarios=[],
        model_approval=project.approval.to_dict(),
        model_run_id=project.fitted.model_run_id,
        model_meta=project.fitted.meta,
        outcome_definitions=[project.fitted.outcome_definition.to_dict()],
        activity_definitions=[a.to_dict() for a in project.fitted.activity_definitions],
        outcome_approvals=[project.outcome_approval.to_dict()],
        validation_policy=project.policy.to_dict(),
        diagnostics_artefact=project.diagnostics.to_dict(),
        approval_readiness=project.readiness.to_dict(),
        media_cost_mappings=project.cost_mapping_registry.to_dict(),
        named_events=named_events_payload,
    )
    imported = import_project(bundle_path)

    from ancestry_mmm.core.persistence import reconstruct_model_state

    reconstructed = reconstruct_model_state(imported)
    assert reconstructed["frame"] is not None
    assert reconstructed["posterior_params"] is not None

    _, spec_fp, _ = current_model_identity_fingerprints(imported, reconstructed)
    assert spec_fp == project.fitted.model_spec_fingerprint
