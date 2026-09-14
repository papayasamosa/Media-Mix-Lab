"""Tests for `ancestry_mmm.core.population_preparation` (REQ-POPULATION-001,
2026-09-13 narrow follow-up). Every population value used is a clearly
synthetic test value."""

import inspect

import pytest

from ancestry_mmm.core import population_treatment
from ancestry_mmm.core.market_config import MarketDescriptors
from ancestry_mmm.core.population_preparation import (
    PopulationPreparationResult,
    PopulationTreatmentUnresolvedError,
    population_dependency_fingerprint,
    prepare_population_aware_observed_target,
)
from ancestry_mmm.core.population_reference import PopulationReferenceRecord
from ancestry_mmm.core.population_treatment import (
    OUTCOME_POPULATION_TREATMENT_EXPOSURE_OR_OFFSET,
    OUTCOME_POPULATION_TREATMENT_NONE,
    PREDICTOR_POPULATION_TREATMENT_SELECTED_ELIGIBLE_PREDICTORS,
    PopulationTreatmentSpecification,
)
from ancestry_mmm.core.schema import ModelSpec


def _spec(**overrides) -> PopulationTreatmentSpecification:
    defaults = dict(
        population_treatment_spec_id="spec-1",
        project_id="proj-1",
        market_scope=("UK",),
        owner="test_owner",
    )
    defaults.update(overrides)
    return PopulationTreatmentSpecification(**defaults)


def _active_outcome_spec() -> PopulationTreatmentSpecification:
    return _spec(
        outcome_population_treatment=OUTCOME_POPULATION_TREATMENT_EXPOSURE_OR_OFFSET
    )


def _active_predictor_spec() -> PopulationTreatmentSpecification:
    return _spec(
        predictor_population_treatment=(
            PREDICTOR_POPULATION_TREATMENT_SELECTED_ELIGIBLE_PREDICTORS
        ),
        eligible_measure_units=("impressions",),
    )


def _reference(**overrides) -> PopulationReferenceRecord:
    defaults = dict(
        population_reference_id="pop-1",
        market_id="UK",
        population=1_000_000.0,
        population_basis="total_resident_population",
        source_name="synthetic_source",
        owner="test_owner",
        reference_year=2024,
    )
    defaults.update(overrides)
    return PopulationReferenceRecord(**defaults)


class TestExistingUKModelsDefaultToInactive:
    def test_a_plain_modelspec_needs_no_population_configuration(self):
        # ModelSpec itself gained no population field - the "existing UK
        # model" contract is that population preparation works with
        # nothing supplied at all.
        spec = ModelSpec(date_col="date", market_col="market", markets=["UK"])
        assert spec.validate() == ["At least one media channel must be selected."]
        prepared, result = prepare_population_aware_observed_target([1.0, 2.0, 3.0])
        assert list(prepared) == [1.0, 2.0, 3.0]
        assert result.population_treatment_active is False

    def test_no_treatment_spec_argument_is_the_default(self):
        signature = inspect.signature(prepare_population_aware_observed_target)
        assert signature.parameters["treatment_spec"].default is None


class TestInactivePathHasZeroNumericalEffect:
    def test_none_spec_returns_the_identical_values(self):
        observed = [10.0, 0.0, 42.5, -3.0]
        prepared, result = prepare_population_aware_observed_target(observed)
        assert prepared is observed
        assert prepared == observed
        assert result == PopulationPreparationResult(
            population_treatment_active=False,
            count_preservation_verified=True,
            population_reference_id_used=None,
        )

    def test_explicitly_inactive_spec_returns_the_identical_values(self):
        observed = [5, 6, 7]
        spec = _spec()  # default is_active=False
        prepared, result = prepare_population_aware_observed_target(
            observed, treatment_spec=spec
        )
        assert prepared == observed
        assert result.count_preservation_verified is True
        assert result.population_reference_id_used is None

    def test_negative_and_zero_counts_pass_through_unchanged(self):
        # The preparation boundary must not itself impose any positivity
        # rule on the observed target - that is the outcome's own concern,
        # not population's.
        observed = [0, -1, 1_000_000]
        prepared, _ = prepare_population_aware_observed_target(observed)
        assert prepared == observed

    def test_inactive_path_requires_no_population_reference(self):
        # No reference of any kind is passed anywhere - and the function
        # signature has no parameter through which one even could be for
        # the inactive path.
        signature = inspect.signature(prepare_population_aware_observed_target)
        assert "population_reference" not in signature.parameters
        assert "reference" not in signature.parameters
        assert "population_records" not in signature.parameters
        prepared, result = prepare_population_aware_observed_target([1.0])
        assert result.population_treatment_active is False


class TestNoAutomaticAnnualMapping:
    def test_resolver_has_no_period_or_year_or_week_parameter(self):
        from ancestry_mmm.core.population_reference import (
            resolve_single_population_reference,
        )

        signature = inspect.signature(resolve_single_population_reference)
        for forbidden in ("model_period", "week", "year", "date"):
            assert forbidden not in signature.parameters

    def test_preparation_boundary_has_no_period_or_year_or_week_parameter(self):
        signature = inspect.signature(prepare_population_aware_observed_target)
        for forbidden in ("model_period", "week", "year", "date", "reference_year"):
            assert forbidden not in signature.parameters


class TestActiveTreatmentFailsClosed:
    def test_active_outcome_treatment_raises_not_silently_downgrades(self):
        with pytest.raises(PopulationTreatmentUnresolvedError):
            prepare_population_aware_observed_target(
                [1.0, 2.0], treatment_spec=_active_outcome_spec()
            )

    def test_active_predictor_treatment_raises_not_silently_downgrades(self):
        with pytest.raises(PopulationTreatmentUnresolvedError):
            prepare_population_aware_observed_target(
                [1.0, 2.0], treatment_spec=_active_predictor_spec()
            )

    def test_error_message_names_the_unresolved_decisions(self):
        with pytest.raises(PopulationTreatmentUnresolvedError, match="DD-020"):
            prepare_population_aware_observed_target(
                [1.0], treatment_spec=_active_outcome_spec()
            )
        with pytest.raises(PopulationTreatmentUnresolvedError, match="MD-025"):
            prepare_population_aware_observed_target(
                [1.0], treatment_spec=_active_outcome_spec()
            )

    def test_no_result_object_is_ever_returned_for_an_active_specification(self):
        # A silent downgrade would show up as a returned
        # PopulationPreparationResult with population_treatment_active=True.
        # That must be structurally impossible: the dataclass itself is
        # never constructed on the active path, only raised past.
        try:
            prepare_population_aware_observed_target(
                [1.0], treatment_spec=_active_outcome_spec()
            )
            raised = False
        except PopulationTreatmentUnresolvedError:
            raised = True
        assert raised is True


class TestObservedCountRemainsUnchanged:
    def test_governed_observed_count_equals_prepared_observed_count(self):
        governed_observed_count = [12, 15, 9, 0, 30]
        prepared_observed_count, result = prepare_population_aware_observed_target(
            governed_observed_count
        )
        assert prepared_observed_count == governed_observed_count
        assert result.count_preservation_verified is True


class TestPopulationDependencyFingerprint:
    def test_none_spec_returns_none(self):
        assert population_dependency_fingerprint(None) is None

    def test_inactive_spec_returns_none(self):
        assert population_dependency_fingerprint(_spec()) is None

    def test_active_spec_returns_a_real_fingerprint(self):
        fingerprint = population_dependency_fingerprint(_active_outcome_spec())
        assert isinstance(fingerprint, str)
        assert len(fingerprint) == 64

    def test_active_fingerprint_is_deterministic(self):
        spec = _active_outcome_spec()
        assert population_dependency_fingerprint(
            spec
        ) == population_dependency_fingerprint(spec)

    def test_active_fingerprint_changes_when_reference_records_change(self):
        spec = _active_outcome_spec()
        fp_a = population_dependency_fingerprint(spec, reference_records=[_reference()])
        fp_b = population_dependency_fingerprint(
            spec, reference_records=[_reference(population=2_000_000.0)]
        )
        assert fp_a != fp_b

    def test_unused_population_reference_never_staled_the_inactive_case(self):
        # This is the AD-019 conditional-staleness contract in miniature:
        # changing/adding a reference while treatment stays inactive must
        # not change the (always-None) fingerprint contribution at all.
        inactive_spec = _spec()
        fp_before = population_dependency_fingerprint(
            inactive_spec, reference_records=[]
        )
        fp_after = population_dependency_fingerprint(
            inactive_spec,
            reference_records=[
                _reference(),
                _reference(population_reference_id="pop-2"),
            ],
        )
        assert fp_before is None
        assert fp_after is None
        assert fp_before == fp_after


class TestGeometricMeanNeverCalledAutomatically:
    def test_never_called_automatically_by_the_preparation_boundary(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise AssertionError(
                "geometric_mean_population must never be called automatically"
            )

        monkeypatch.setattr(population_treatment, "geometric_mean_population", _boom)
        with pytest.raises(PopulationTreatmentUnresolvedError):
            prepare_population_aware_observed_target(
                [1.0, 2.0], treatment_spec=_active_outcome_spec()
            )

    def test_never_called_automatically_by_the_dependency_fingerprint(
        self, monkeypatch
    ):
        def _boom(*args, **kwargs):
            raise AssertionError(
                "geometric_mean_population must never be called automatically"
            )

        monkeypatch.setattr(population_treatment, "geometric_mean_population", _boom)
        population_dependency_fingerprint(
            _active_outcome_spec(), reference_records=[_reference()]
        )

    def test_specification_construction_never_calls_it(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise AssertionError(
                "geometric_mean_population must never be called automatically"
            )

        monkeypatch.setattr(population_treatment, "geometric_mean_population", _boom)
        _active_outcome_spec()
        _active_predictor_spec()
        _spec(outcome_population_treatment=OUTCOME_POPULATION_TREATMENT_NONE)


class TestNoMarketDescriptorsFallback:
    def test_preparation_boundary_has_no_market_descriptors_parameter(self):
        signature = inspect.signature(prepare_population_aware_observed_target)
        assert "market_descriptors" not in signature.parameters
        assert "descriptors" not in signature.parameters

    def test_resolver_has_no_market_descriptors_parameter(self):
        from ancestry_mmm.core.population_reference import (
            resolve_single_population_reference,
        )

        signature = inspect.signature(resolve_single_population_reference)
        assert "market_descriptors" not in signature.parameters
        assert "descriptors" not in signature.parameters

    def test_a_populated_market_descriptors_value_has_no_effect_on_resolution(self):
        # Even when a legacy informational scalar exists for this exact
        # market, an empty governed reference list still fails closed to
        # None - proving there is no code path from one to the other.
        from ancestry_mmm.core.population_reference import (
            resolve_single_population_reference,
        )

        MarketDescriptors(population=999_999_999.0)  # legacy, unrelated object
        assert resolve_single_population_reference("UK", []) is None

    def test_inactive_preparation_is_unaffected_by_market_descriptors_existing(self):
        MarketDescriptors(population=42.0)  # legacy, unrelated object
        prepared, result = prepare_population_aware_observed_target([1.0, 2.0])
        assert prepared == [1.0, 2.0]
        assert result.population_treatment_active is False
