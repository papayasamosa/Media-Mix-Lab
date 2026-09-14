"""WP1 (`Media-Mix-Lab: Coding LLM Next Steps After PR #253`):
application.model_fit_service - the engine-selection boundary between
Streamlit pages and core.hierarchical_model/core.market_specific_model.

Follows this suite's convention (see test_hierarchical_model.py's module
docstring) of avoiding a real PyMC model build except where genuinely
needed - engine resolution and the fit-readiness gate are pure Python and
tested directly; only the dispatch tests build a (small, fast) real model.
"""

import numpy as np
import pytest

from ancestry_mmm.application import model_fit_service
from ancestry_mmm.application.model_fit_service import (
    MODEL_TYPE_MARKET_SPECIFIC,
    MODEL_TYPE_SHARED,
    ModelFitServiceError,
    build_model_for_spec,
    check_candidate_a_fit_readiness,
    resolve_engine,
)
from ancestry_mmm.core.population_preparation import PopulationTreatmentUnresolvedError
from ancestry_mmm.core.population_treatment import (
    OUTCOME_POPULATION_TREATMENT_EXPOSURE_OR_OFFSET,
    PopulationTreatmentSpecification,
)
from ancestry_mmm.core.causal_graph import (
    CausalEdge,
    CausalGraph,
    EDGE_ROLE_CAPACITY_CONSTRAINED,
    EDGE_ROLE_DIRECT,
    EDGE_ROLE_MEDIATED,
    GRAPH_STATUS_APPROVED,
    NODE_ROLE_CAPACITY_OR_CAP,
    NODE_ROLE_DEMAND_CAPTURE,
    NODE_ROLE_INTERVENTION,
    NODE_ROLE_OUTCOME,
    CausalNode,
)
from ancestry_mmm.core.search_capacity import (
    SEARCH_CANDIDATE_A_ENGINE,
    CandidateASearchFitInputs,
    SearchCandidateASpec,
)
from ancestry_mmm.core.search_objects import (
    SEARCH_ROLE_DEMAND,
    SEARCH_ROLE_DIRECT_NAV_CAPTURE,
    SEARCH_ROLE_ORGANIC_CAPTURE,
    SEARCH_ROLE_PAID_CAP,
    SEARCH_ROLE_PAID_DELIVERY,
    SEARCH_ROLE_PAID_SPEND,
    UNIT_EXPOSURE_COUNT,
    UNIT_MONETARY,
    UNIT_RESPONSE_COUNT,
    SearchObjectDefinition,
)


def _ordinary_graph() -> CausalGraph:
    return CausalGraph(
        graph_id="ordinary",
        nodes=[
            CausalNode(node_id="TV", role=NODE_ROLE_INTERVENTION),
            CausalNode(node_id="fh_new", role=NODE_ROLE_OUTCOME),
        ],
        edges=[CausalEdge("TV", "fh_new", role=EDGE_ROLE_DIRECT)],
        status=GRAPH_STATUS_APPROVED,
    )


def _unsupported_graph() -> CausalGraph:
    """A graph with a mediated edge but none of the other Candidate A
    structure - neither engine can compile this."""
    return CausalGraph(
        graph_id="unsupported",
        nodes=[
            CausalNode(node_id="TV", role=NODE_ROLE_INTERVENTION),
            CausalNode(node_id="mystery", role=NODE_ROLE_DEMAND_CAPTURE),
            CausalNode(node_id="fh_new", role=NODE_ROLE_OUTCOME),
        ],
        edges=[CausalEdge("TV", "mystery", role=EDGE_ROLE_MEDIATED)],
        status=GRAPH_STATUS_APPROVED,
    )


def _candidate_a_graph() -> CausalGraph:
    nodes = [
        CausalNode(node_id="SearchBrand", role=NODE_ROLE_INTERVENTION),
        CausalNode(node_id="fh_new", role=NODE_ROLE_OUTCOME),
        CausalNode(
            node_id="demand_node",
            role=NODE_ROLE_DEMAND_CAPTURE,
            search_object_id="obj_demand",
        ),
        CausalNode(
            node_id="cap_node",
            role=NODE_ROLE_CAPACITY_OR_CAP,
            search_object_id="obj_cap",
        ),
        CausalNode(
            node_id="organic_node",
            role=NODE_ROLE_DEMAND_CAPTURE,
            search_object_id="obj_organic",
        ),
        CausalNode(
            node_id="direct_node",
            role=NODE_ROLE_DEMAND_CAPTURE,
            search_object_id="obj_direct",
        ),
    ]
    edges = [
        CausalEdge("SearchBrand", "fh_new", role=EDGE_ROLE_DIRECT),
        CausalEdge("SearchBrand", "demand_node", role=EDGE_ROLE_MEDIATED),
        CausalEdge("demand_node", "fh_new", role=EDGE_ROLE_MEDIATED),
        CausalEdge("demand_node", "cap_node", role=EDGE_ROLE_CAPACITY_CONSTRAINED),
        CausalEdge("organic_node", "fh_new", role=EDGE_ROLE_DIRECT),
        CausalEdge("direct_node", "fh_new", role=EDGE_ROLE_DIRECT),
    ]
    return CausalGraph(
        graph_id="candidate_a", nodes=nodes, edges=edges, status=GRAPH_STATUS_APPROVED
    )


def _search_objects() -> list[SearchObjectDefinition]:
    return [
        SearchObjectDefinition(
            search_object_id="obj_demand",
            search_role=SEARCH_ROLE_DEMAND,
            source_column="search_demand_raw",
            unit=UNIT_EXPOSURE_COUNT,
        ),
        SearchObjectDefinition(
            search_object_id="obj_cap",
            search_role=SEARCH_ROLE_PAID_CAP,
            source_column="search_cap_raw",
            unit=UNIT_EXPOSURE_COUNT,
        ),
        SearchObjectDefinition(
            search_object_id="obj_organic",
            search_role=SEARCH_ROLE_ORGANIC_CAPTURE,
            source_column="search_organic_raw",
            unit=UNIT_RESPONSE_COUNT,
        ),
        SearchObjectDefinition(
            search_object_id="obj_direct",
            search_role=SEARCH_ROLE_DIRECT_NAV_CAPTURE,
            source_column="search_direct_raw",
            unit=UNIT_RESPONSE_COUNT,
        ),
        SearchObjectDefinition(
            search_object_id="obj_spend",
            search_role=SEARCH_ROLE_PAID_SPEND,
            source_column="search_spend_raw",
            unit=UNIT_MONETARY,
            currency="GBP",
        ),
        SearchObjectDefinition(
            search_object_id="obj_delivery",
            search_role=SEARCH_ROLE_PAID_DELIVERY,
            source_column="search_delivery_raw",
            unit=UNIT_EXPOSURE_COUNT,
        ),
    ]


class TestResolveEngine:
    def test_no_graph_returns_ordinary_engine(self):
        from ancestry_mmm.core.graph_model_compiler import (
            GRAPH_ENGINE_PYMC_HIERARCHICAL,
        )

        assert resolve_engine(causal_graph=None) == GRAPH_ENGINE_PYMC_HIERARCHICAL

    def test_ordinary_compatible_graph_returns_ordinary_engine(self):
        from ancestry_mmm.core.graph_model_compiler import (
            GRAPH_ENGINE_PYMC_HIERARCHICAL,
        )

        assert (
            resolve_engine(causal_graph=_ordinary_graph())
            == GRAPH_ENGINE_PYMC_HIERARCHICAL
        )

    def test_ordinary_graph_ignores_unrelated_search_objects(self):
        """Registering a Search object never changes fitting behaviour by
        itself (REQ-SEARCH-001 S7) - an ordinary graph must not route to
        Candidate A merely because Search objects exist somewhere."""
        from ancestry_mmm.core.graph_model_compiler import (
            GRAPH_ENGINE_PYMC_HIERARCHICAL,
        )

        assert (
            resolve_engine(
                causal_graph=_ordinary_graph(), search_objects=_search_objects()
            )
            == GRAPH_ENGINE_PYMC_HIERARCHICAL
        )

    def test_candidate_a_graph_returns_candidate_a_engine(self):
        assert (
            resolve_engine(
                causal_graph=_candidate_a_graph(), search_objects=_search_objects()
            )
            == SEARCH_CANDIDATE_A_ENGINE
        )

    def test_unsupported_graph_raises(self):
        with pytest.raises(ModelFitServiceError):
            resolve_engine(causal_graph=_unsupported_graph())


class TestCheckCandidateAFitReadiness:
    def _spec(self, **overrides) -> SearchCandidateASpec:
        defaults = dict(
            outcome_definition_id="fh_new",
            outcome_definition_version="1",
            outcome_definition_fingerprint="fp",
            market_scope="UK",
            demand_object_id="obj_demand",
            paid_spend_object_id="obj_spend",
            paid_delivery_object_id="obj_delivery",
            paid_cap_object_id="obj_cap",
            organic_capture_object_id="obj_organic",
            direct_navigation_object_id="obj_direct",
            cap_provenance="observed_platform",
            cap_provenance_status="resolved",
        )
        defaults.update(overrides)
        return SearchCandidateASpec(**defaults)

    def _fit_inputs(self, n=12, cap_value=1000.0) -> CandidateASearchFitInputs:
        rng = np.random.default_rng(0)
        return CandidateASearchFitInputs(
            spec=self._spec(),
            demand_channel_names=["SearchBrand"],
            paid_search_delivery=rng.uniform(5, 15, size=n),
            paid_search_cap=np.full(n, cap_value),
            organic_search_capture=rng.uniform(5, 15, size=n),
            direct_navigation_capture=rng.uniform(5, 15, size=n),
            search_objects=_search_objects(),
        )

    def test_unresolved_cap_provenance_blocks_readiness(self):
        fit_inputs = CandidateASearchFitInputs(
            spec=self._spec(cap_provenance="", cap_provenance_status="unresolved"),
            demand_channel_names=["SearchBrand"],
            paid_search_delivery=np.full(20, 5.0),
            paid_search_cap=np.full(20, 100.0),
            organic_search_capture=np.full(20, 5.0),
            direct_navigation_capture=np.full(20, 5.0),
            search_objects=_search_objects(),
        )
        readiness = check_candidate_a_fit_readiness(
            spec=fit_inputs.spec, fit_inputs=fit_inputs
        )
        assert not readiness.is_ready
        assert readiness.blocking_reasons


class TestBuildModelForSpec:
    @staticmethod
    def _frame():
        n = 8
        rng = np.random.default_rng(0)
        return {
            "markets": ["UK"],
            "market_idx": np.zeros(n, dtype=int),
            "market_bounds": [(0, n)],
            "channels": ["TV"],
            "dna_channel_idx": [],
            "outcome_ids": ["fh_new"],
            "X_media": rng.uniform(50, 150, size=(n, 1)),
            "Y": rng.uniform(8, 15, size=(n, 1)),
            "promo": np.zeros((n, 1)),
            "X_controls": np.zeros((n, 0)),
            "control_names": [],
            "fourier": np.zeros((n, 2)),
            "trend": np.linspace(1.0, 1.1, n),
            "unpooled_markets": [],
        }

    @staticmethod
    def _model_spec():
        from ancestry_mmm.core.schema import ModelSpec

        return ModelSpec(
            date_col="date",
            market_col="market",
            markets=["UK"],
            segment_outcomes={"New": "fh_new_gsa"},
            channels=["TV"],
        )

    def test_no_graph_dispatches_to_shared_ordinary_builder(self):
        from ancestry_mmm.core.graph_model_compiler import (
            GRAPH_ENGINE_PYMC_HIERARCHICAL,
        )

        result = build_model_for_spec(
            frame=self._frame(),
            model_spec=self._model_spec(),
            model_type=MODEL_TYPE_SHARED,
        )
        assert result.engine == GRAPH_ENGINE_PYMC_HIERARCHICAL
        assert result.model_type == MODEL_TYPE_SHARED
        assert result.candidate_a_readiness is None

    def test_candidate_a_engine_without_fit_inputs_raises(self):
        with pytest.raises(ModelFitServiceError):
            build_model_for_spec(
                frame=self._frame(),
                model_spec=self._model_spec(),
                model_type=MODEL_TYPE_SHARED,
                causal_graph=_candidate_a_graph(),
                search_objects=_search_objects(),
                candidate_a_fit_inputs=None,
            )

    def test_candidate_a_engine_with_market_specific_model_type_raises(self):
        with pytest.raises(ModelFitServiceError):
            build_model_for_spec(
                frame=self._frame(),
                model_spec=self._model_spec(),
                model_type=MODEL_TYPE_MARKET_SPECIFIC,
                causal_graph=_candidate_a_graph(),
                search_objects=_search_objects(),
            )


def _inactive_population_spec() -> PopulationTreatmentSpecification:
    return PopulationTreatmentSpecification(
        population_treatment_spec_id="spec-1",
        project_id="proj-1",
        market_scope=("UK",),
        owner="test_owner",
    )


def _active_population_spec() -> PopulationTreatmentSpecification:
    return PopulationTreatmentSpecification(
        population_treatment_spec_id="spec-1",
        project_id="proj-1",
        market_scope=("UK",),
        owner="test_owner",
        outcome_population_treatment=OUTCOME_POPULATION_TREATMENT_EXPOSURE_OR_OFFSET,
    )


class TestBuildModelForSpecPopulationBoundary:
    """REQ-POPULATION-001, 2026-09-13 review follow-up (Codex P1): the
    population-preparation boundary must actually run inside the real fit
    orchestration path (`build_model_for_spec`), covering ordinary shared,
    market-specific, and Candidate A dispatch, rather than existing only
    as a disconnected utility."""

    _frame = staticmethod(TestBuildModelForSpec._frame)
    _model_spec = staticmethod(TestBuildModelForSpec._model_spec)

    def test_no_population_treatment_dispatches_exactly_as_before(self):
        result = build_model_for_spec(
            frame=self._frame(),
            model_spec=self._model_spec(),
            model_type=MODEL_TYPE_SHARED,
        )
        assert result.population_preparation_result is not None
        assert result.population_preparation_result.population_treatment_active is False
        assert result.population_preparation_result.count_preservation_verified is True

    def test_explicitly_inactive_population_treatment_preserves_observed_target(self):
        result = build_model_for_spec(
            frame=self._frame(),
            model_spec=self._model_spec(),
            model_type=MODEL_TYPE_SHARED,
            population_treatment=_inactive_population_spec(),
        )
        assert result.population_preparation_result.population_treatment_active is False
        assert result.population_preparation_result.count_preservation_verified is True

    def test_the_boundary_is_actually_invoked_with_the_frames_own_target(
        self, monkeypatch
    ):
        frame = self._frame()
        calls = []
        original = model_fit_service.prepare_population_aware_observed_target

        def _spy(observed_counts, treatment_spec=None):
            calls.append((observed_counts, treatment_spec))
            return original(observed_counts, treatment_spec=treatment_spec)

        monkeypatch.setattr(
            model_fit_service, "prepare_population_aware_observed_target", _spy
        )
        build_model_for_spec(
            frame=frame, model_spec=self._model_spec(), model_type=MODEL_TYPE_SHARED
        )
        assert len(calls) == 1
        observed_counts, treatment_spec = calls[0]
        assert observed_counts is frame["Y"]
        assert treatment_spec is None

    def test_active_outcome_treatment_blocks_before_shared_dispatch(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise AssertionError("build_fh_hierarchical_model must not be called")

        monkeypatch.setattr(model_fit_service, "build_fh_hierarchical_model", _boom)
        with pytest.raises(PopulationTreatmentUnresolvedError):
            build_model_for_spec(
                frame=self._frame(),
                model_spec=self._model_spec(),
                model_type=MODEL_TYPE_SHARED,
                population_treatment=_active_population_spec(),
            )

    def test_active_treatment_blocks_before_market_specific_dispatch(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise AssertionError("build_fh_market_specific_model must not be called")

        monkeypatch.setattr(model_fit_service, "build_fh_market_specific_model", _boom)
        with pytest.raises(PopulationTreatmentUnresolvedError):
            build_model_for_spec(
                frame=self._frame(),
                model_spec=self._model_spec(),
                model_type=MODEL_TYPE_MARKET_SPECIFIC,
                population_treatment=_active_population_spec(),
            )

    def test_active_treatment_blocks_before_candidate_a_dispatch(self, monkeypatch):
        # Deliberately omit candidate_a_fit_inputs - if the population guard
        # did not run first, this would instead raise ModelFitServiceError
        # for missing Candidate A fit inputs. Getting
        # PopulationTreatmentUnresolvedError instead proves the guard
        # preempts every other check, including Candidate A dispatch.
        def _boom(*args, **kwargs):
            raise AssertionError("build_fh_hierarchical_model must not be called")

        monkeypatch.setattr(model_fit_service, "build_fh_hierarchical_model", _boom)
        with pytest.raises(PopulationTreatmentUnresolvedError):
            build_model_for_spec(
                frame=self._frame(),
                model_spec=self._model_spec(),
                model_type=MODEL_TYPE_SHARED,
                causal_graph=_candidate_a_graph(),
                search_objects=_search_objects(),
                candidate_a_fit_inputs=None,
                population_treatment=_active_population_spec(),
            )

    def test_active_treatment_error_names_the_unresolved_decisions(self):
        with pytest.raises(PopulationTreatmentUnresolvedError, match="DD-020"):
            build_model_for_spec(
                frame=self._frame(),
                model_spec=self._model_spec(),
                model_type=MODEL_TYPE_SHARED,
                population_treatment=_active_population_spec(),
            )
        with pytest.raises(PopulationTreatmentUnresolvedError, match="MD-025"):
            build_model_for_spec(
                frame=self._frame(),
                model_spec=self._model_spec(),
                model_type=MODEL_TYPE_SHARED,
                population_treatment=_active_population_spec(),
            )

    def test_existing_model_fitting_behaviour_unchanged_when_population_absent(self):
        from ancestry_mmm.core.graph_model_compiler import (
            GRAPH_ENGINE_PYMC_HIERARCHICAL,
        )

        baseline = build_model_for_spec(
            frame=self._frame(),
            model_spec=self._model_spec(),
            model_type=MODEL_TYPE_SHARED,
        )
        with_none = build_model_for_spec(
            frame=self._frame(),
            model_spec=self._model_spec(),
            model_type=MODEL_TYPE_SHARED,
            population_treatment=None,
        )
        assert baseline.engine == with_none.engine == GRAPH_ENGINE_PYMC_HIERARCHICAL
        assert baseline.model_type == with_none.model_type == MODEL_TYPE_SHARED
