"""Tests for `ancestry_mmm.core.population_treatment` (REQ-POPULATION-001).
Every population value used is a clearly synthetic test value."""

import math

import pytest

from ancestry_mmm.core.population_treatment import (
    OUTCOME_POPULATION_TREATMENT_EXPOSURE_OR_OFFSET,
    OUTCOME_POPULATION_TREATMENT_NONE,
    PREDICTOR_POPULATION_TREATMENT_NONE,
    PREDICTOR_POPULATION_TREATMENT_SELECTED_ELIGIBLE_PREDICTORS,
    PopulationTreatmentSpecification,
    geometric_mean_population,
    is_predictor_unit_eligible_for_population_normalisation,
    is_predictor_unit_protected,
    population_exposure_log_term,
    population_normalised_predictor_value,
)


def _spec(**overrides) -> PopulationTreatmentSpecification:
    defaults = dict(
        population_treatment_spec_id="spec-1",
        project_id="proj-1",
        market_scope=("UK",),
        owner="test_owner",
    )
    defaults.update(overrides)
    return PopulationTreatmentSpecification(**defaults)


class TestPopulationTreatmentSpecificationDefaults:
    def test_default_specification_is_fully_inactive(self):
        spec = _spec()
        assert spec.outcome_population_treatment == OUTCOME_POPULATION_TREATMENT_NONE
        assert (
            spec.predictor_population_treatment == PREDICTOR_POPULATION_TREATMENT_NONE
        )
        assert spec.is_active is False

    def test_enabling_outcome_treatment_makes_it_active(self):
        spec = _spec(
            outcome_population_treatment=OUTCOME_POPULATION_TREATMENT_EXPOSURE_OR_OFFSET
        )
        assert spec.is_active is True

    def test_enabling_predictor_treatment_makes_it_active(self):
        spec = _spec(
            predictor_population_treatment=(
                PREDICTOR_POPULATION_TREATMENT_SELECTED_ELIGIBLE_PREDICTORS
            ),
            eligible_measure_units=("impressions",),
        )
        assert spec.is_active is True

    def test_round_trips(self):
        spec = _spec(
            predictor_population_treatment=(
                PREDICTOR_POPULATION_TREATMENT_SELECTED_ELIGIBLE_PREDICTORS
            ),
            eligible_measure_units=("impressions", "clicks"),
            population_reference_map={"UK": "pop-uk-1"},
        )
        assert PopulationTreatmentSpecification.from_dict(spec.to_dict()) == spec


class TestPopulationTreatmentSpecificationValidation:
    def test_unknown_outcome_treatment_rejected(self):
        with pytest.raises(ValueError):
            _spec(outcome_population_treatment="rescale_the_count")

    def test_unknown_predictor_treatment_rejected(self):
        with pytest.raises(ValueError):
            _spec(predictor_population_treatment="rescale_everything")

    def test_selected_eligible_predictors_requires_units(self):
        with pytest.raises(ValueError):
            _spec(
                predictor_population_treatment=(
                    PREDICTOR_POPULATION_TREATMENT_SELECTED_ELIGIBLE_PREDICTORS
                ),
                eligible_measure_units=(),
            )

    @pytest.mark.parametrize(
        "protected_unit",
        [
            "GRP",
            "tvr",
            "Reach_Percentage",
            "Index",
            "%",
            "pct",
            "percent",
            "reach %",
            "rates",
            "indices",
            "index_0_to_1",
        ],
    )
    def test_protected_units_cannot_be_declared_eligible(self, protected_unit):
        with pytest.raises(ValueError):
            _spec(
                predictor_population_treatment=(
                    PREDICTOR_POPULATION_TREATMENT_SELECTED_ELIGIBLE_PREDICTORS
                ),
                eligible_measure_units=(protected_unit,),
            )

    def test_approved_requires_approver(self):
        with pytest.raises(ValueError):
            _spec(approval_status="approved")

    @pytest.mark.parametrize("status", ["pending", "rejected"])
    def test_non_approved_rejects_stale_approver_metadata(self, status):
        """Codex P2 (2026-09-13, third pass): the symmetric case - a
        pending/rejected specification must not carry approver metadata
        that contradicts its own status."""
        with pytest.raises(ValueError):
            _spec(approval_status=status, approved_by="reviewer")
        with pytest.raises(ValueError):
            _spec(approval_status=status, approved_at="2026-09-12")
        _spec(approval_status=status)  # neither set - succeeds

    def test_omitted_schema_version_defaults_to_current(self):
        assert _spec().schema_version == 1

    @pytest.mark.parametrize("bad_version", [999, 0, "1", "abc", None, 1.5])
    def test_unsupported_schema_version_rejected(self, bad_version):
        with pytest.raises(ValueError):
            _spec(schema_version=bad_version)


class TestProtectedUnits:
    @pytest.mark.parametrize(
        "unit",
        [
            "GRP",
            "GRPs",
            "TVR",
            "TVRs",
            "reach percentage",
            "rate",
            "Percentage",
            "index",
        ],
    )
    def test_known_protected_units_are_protected(self, unit):
        assert is_predictor_unit_protected(unit) is True

    @pytest.mark.parametrize(
        "unit",
        [
            "%",
            "Pct",
            "PCT",
            "percent",
            "percents",
            "reach %",
            "Reach%",
            "reach_pct",
            "reach percent",
            "rates",
            "Rates",
            "indices",
            "Indices",
            "indexes",
        ],
    )
    def test_governed_aliases_are_also_protected(self, unit):
        """Codex P2 (2026-09-13): the original exact-string check was too
        narrow to catch these ordinary governed aliases."""
        assert is_predictor_unit_protected(unit) is True

    @pytest.mark.parametrize("unit", ["impressions", "clicks", "spend", "sends"])
    def test_extensive_units_are_not_protected(self, unit):
        assert is_predictor_unit_protected(unit) is False

    @pytest.mark.parametrize(
        "unit",
        [
            "conversion_rate_index",  # contains "rate" and "index" as fragments
            "aggregate",  # contains "gr" fragments, unrelated to GRP
            "percentagewise_delivery",  # contains "percentage" as a fragment
        ],
    )
    def test_unrelated_units_containing_protected_fragments_are_not_protected(
        self, unit
    ):
        """The canonicalisation is an exact-identity match, never a
        substring search - a unit that merely contains "rate", "index" or
        "percentage" as part of an unrelated word must not be caught."""
        assert is_predictor_unit_protected(unit) is False

    @pytest.mark.parametrize(
        "unit",
        ["index_0_to_1", "Index_0_To_1", "index_0_to_100", "index-0-to-1"],
    )
    def test_governed_index_range_family_is_protected(self, unit):
        """Codex P2 (2026-09-13, second pass): the repository's existing
        governed SEO unit `core.seo_visibility.
        SEO_POSITIONAL_VISIBILITY_METRIC.unit == "index_0_to_1"` must be
        classified as an index, not left unprotected because it isn't the
        bare word "index"."""
        assert is_predictor_unit_protected(unit) is True

    @pytest.mark.parametrize(
        "unit",
        [
            "index_abc",  # not a numeric range - not the governed family
            "index_0",  # missing the "_to_<upper>" half
            "rate_0_to_1",  # a different word entirely, not the index family
        ],
    )
    def test_non_range_shaped_units_are_not_swept_in_by_the_family_rule(self, unit):
        assert is_predictor_unit_protected(unit) is False


class TestEligibilityHelper:
    def test_ineligible_when_predictor_treatment_disabled(self):
        spec = _spec()
        assert (
            is_predictor_unit_eligible_for_population_normalisation("impressions", spec)
            is False
        )

    def test_eligible_when_declared_and_not_protected(self):
        spec = _spec(
            predictor_population_treatment=(
                PREDICTOR_POPULATION_TREATMENT_SELECTED_ELIGIBLE_PREDICTORS
            ),
            eligible_measure_units=("impressions",),
        )
        assert (
            is_predictor_unit_eligible_for_population_normalisation("impressions", spec)
            is True
        )
        assert (
            is_predictor_unit_eligible_for_population_normalisation("clicks", spec)
            is False
        )

    @pytest.mark.parametrize(
        "protected_unit",
        ["GRP", "%", "pct", "reach %", "rates", "indices", "index_0_to_1"],
    )
    def test_protected_unit_never_eligible_even_if_declared_elsewhere(
        self, protected_unit
    ):
        # A protected unit can never even be constructed into eligible_measure_units
        # (TestProtectedUnits above), so this asserts the helper's own defence in
        # depth - a specification must not be able to list a protected unit as
        # eligible and then have this helper return True for it.
        spec = _spec(
            predictor_population_treatment=(
                PREDICTOR_POPULATION_TREATMENT_SELECTED_ELIGIBLE_PREDICTORS
            ),
            eligible_measure_units=("impressions",),
        )
        assert (
            is_predictor_unit_eligible_for_population_normalisation(
                protected_unit, spec
            )
            is False
        )


class TestGeometricMeanPopulation:
    def test_single_value_returns_itself(self):
        assert geometric_mean_population([100.0]) == pytest.approx(100.0)

    def test_geometric_mean_of_two_values(self):
        assert geometric_mean_population([100.0, 400.0]) == pytest.approx(200.0)

    def test_empty_sequence_rejected(self):
        with pytest.raises(ValueError):
            geometric_mean_population([])

    def test_non_positive_value_rejected(self):
        with pytest.raises(ValueError):
            geometric_mean_population([100.0, 0.0])
        with pytest.raises(ValueError):
            geometric_mean_population([100.0, -5.0])

    def test_non_finite_value_rejected(self):
        with pytest.raises(ValueError):
            geometric_mean_population([100.0, float("nan")])


class TestPopulationExposureLogTerm:
    def test_population_equal_to_reference_scale_is_zero(self):
        assert population_exposure_log_term(1_000_000.0, 1_000_000.0) == pytest.approx(
            0.0
        )

    def test_larger_population_gives_positive_term(self):
        assert population_exposure_log_term(2_000_000.0, 1_000_000.0) == pytest.approx(
            math.log(2)
        )

    def test_smaller_population_gives_negative_term(self):
        assert population_exposure_log_term(500_000.0, 1_000_000.0) == pytest.approx(
            math.log(0.5)
        )

    @pytest.mark.parametrize("population", [0.0, -1.0, float("nan"), float("inf")])
    def test_invalid_population_rejected(self, population):
        with pytest.raises(ValueError):
            population_exposure_log_term(population, 1_000_000.0)

    @pytest.mark.parametrize("reference_scale", [0.0, -1.0, float("nan"), float("inf")])
    def test_invalid_reference_scale_rejected(self, reference_scale):
        with pytest.raises(ValueError):
            population_exposure_log_term(1_000_000.0, reference_scale)


class TestPopulationNormalisedPredictorValue:
    def test_basic_division_and_scale(self):
        # (10 / 5) * 3 = 6.
        assert population_normalised_predictor_value(
            10.0, 5.0, unit_scale=3.0
        ) == pytest.approx(6.0)

    def test_default_unit_scale_is_one(self):
        assert population_normalised_predictor_value(500.0, 1000.0) == pytest.approx(
            0.5
        )

    @pytest.mark.parametrize("population", [0.0, -1.0, float("nan")])
    def test_invalid_population_rejected(self, population):
        with pytest.raises(ValueError):
            population_normalised_predictor_value(100.0, population)

    def test_invalid_unit_scale_rejected(self):
        with pytest.raises(ValueError):
            population_normalised_predictor_value(100.0, 1000.0, unit_scale=0.0)
