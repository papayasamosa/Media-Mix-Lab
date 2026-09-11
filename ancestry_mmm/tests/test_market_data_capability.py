"""Tests for core.market_data_capability (REQ-COVERAGE-001 S6, Work Package
5): whether the current rectangular PyMC engine can validly fit a
ModelSpec's markets x channels, using the governed coverage matrix as the
sole source of truth. Mirrors test_graph_model_compiler.py's
TestCheckEngineCapability in spirit (REQ-GRAPH-001's analogous structural
check).
"""

from ancestry_mmm.core.coverage import (
    CoverageSegment,
    FrequencyMetadata,
    STATE_ESTIMATED,
    STATE_MODELLED,
    STATE_NOT_APPLICABLE,
    STATE_OBSERVED_ZERO,
    STATE_SUPPRESSED,
    STATE_UNAVAILABLE_SOURCE,
    STATE_UNKNOWN,
    VariableCoverageMatrix,
    VariableCoverageRecord,
)
from ancestry_mmm.core.market_data_capability import (
    ENGINE_PYMC_RECTANGULAR,
    FR_MOD_015_DECISION_REPORT,
    check_market_channel_capability,
)
from ancestry_mmm.core.missing_media_evidence import (
    EstimationEvidenceSummary,
    EstimationReadinessPolicy,
    HoldoutEvaluationResult,
)


def _frequency() -> FrequencyMetadata:
    return FrequencyMetadata(
        native_frequency="weekly",
        target_frequency="weekly",
        variable_class="flow_count",
    )


def _resolved_record(
    variable_id: str, market: str, **overrides
) -> VariableCoverageRecord:
    defaults = dict(
        variable_id=variable_id,
        source_id="media",
        source_version=1,
        market=market,
        frequency=_frequency(),
        coverage_segments=(),
    )
    defaults.update(overrides)
    return VariableCoverageRecord(**defaults)


def _unresolved_record(variable_id: str, market: str) -> VariableCoverageRecord:
    return _resolved_record(
        variable_id,
        market,
        coverage_segments=(
            CoverageSegment(
                period_start="2026-01-01", period_end="2026-01-08", state=STATE_UNKNOWN
            ),
        ),
    )


def _matrix(*records: VariableCoverageRecord) -> VariableCoverageMatrix:
    return VariableCoverageMatrix(
        matrix_id="m1", matrix_version=1, generated_at="2026-01-01", records=records
    )


class TestCheckMarketChannelCapability:
    def test_no_coverage_matrix_marks_every_cell_unsupported(self):
        result = check_market_channel_capability(["UK"], ["TV"], None)
        assert result.supported is False
        assert len(result.issues) == 1
        assert result.issues[0].market == "UK"
        assert result.issues[0].channel == "TV"
        assert "No coverage matrix" in result.issues[0].reason
        assert result.decision_report == FR_MOD_015_DECISION_REPORT

    def test_fully_resolved_coverage_is_supported(self):
        matrix = _matrix(
            _resolved_record("TV", "UK"),
            _resolved_record("Search", "UK"),
        )
        result = check_market_channel_capability(["UK"], ["TV", "Search"], matrix)
        assert result.supported is True
        assert result.issues == ()
        assert result.decision_report == ""

    def test_missing_record_for_a_channel_market_pair_is_an_issue(self):
        matrix = _matrix(_resolved_record("TV", "UK"))
        result = check_market_channel_capability(["UK"], ["TV", "Search"], matrix)
        assert result.supported is False
        assert len(result.issues) == 1
        assert result.issues[0].channel == "Search"
        assert "No coverage record" in result.issues[0].reason

    def test_unresolved_coverage_is_an_issue(self):
        matrix = _matrix(_unresolved_record("TV", "UK"))
        result = check_market_channel_capability(["UK"], ["TV"], matrix)
        assert result.supported is False
        assert "not a genuinely observed number" in result.issues[0].reason

    def test_approved_for_official_use_clears_an_unresolved_gap(self):
        record = _resolved_record(
            "TV",
            "UK",
            coverage_segments=(
                CoverageSegment(
                    period_start="2026-01-01",
                    period_end="2026-01-08",
                    state=STATE_UNKNOWN,
                ),
            ),
            proposed_treatment="use as-is",
            approved_treatment="use as-is",
            treatment_status="approved",
            treatment_approved_by="reviewer",
            treatment_approved_at="2026-01-01",
            approved_for_official_use=True,
        )
        matrix = _matrix(record)
        result = check_market_channel_capability(["UK"], ["TV"], matrix)
        assert result.supported is True

    def test_ragged_market_missing_a_channel_entirely_is_unsupported_not_fabricated(
        self,
    ):
        """REQ-COVERAGE-001 S6: a market genuinely lacking a channel (no
        coverage record for it at all, e.g. Australia never ran TV) must be
        reported unsupported, never silently treated as zero spend."""
        matrix = _matrix(
            _resolved_record("TV", "UK"),
            _resolved_record("TV", "AU"),
            _resolved_record("DNA_Media", "UK"),
            # AU has no DNA_Media record at all - it never ran this channel.
        )
        result = check_market_channel_capability(
            ["UK", "AU"], ["TV", "DNA_Media"], matrix
        )
        assert result.supported is False
        assert len(result.issues) == 1
        assert result.issues[0].market == "AU"
        assert result.issues[0].channel == "DNA_Media"

    def test_multiple_scoped_records_for_the_same_cell_all_must_resolve(self):
        """A coverage matrix built with product/segment scoping can have
        more than one record per (channel, market) - since channels aren't
        product/segment-scoped in ModelSpec, every matching record must be
        resolved for the cell to count as supported (fail-closed, not an
        invented single-record rule)."""
        matrix = _matrix(
            _resolved_record("TV", "UK", product="DNA"),
            _resolved_record(
                "TV",
                "UK",
                product="FH",
                coverage_segments=(
                    CoverageSegment(
                        period_start="2026-01-01",
                        period_end="2026-01-08",
                        state=STATE_UNKNOWN,
                    ),
                ),
            ),
        )
        result = check_market_channel_capability(["UK"], ["TV"], matrix)
        assert result.supported is False
        assert result.issues[0].market == "UK"
        assert result.issues[0].channel == "TV"

    def test_engine_defaults_to_pymc_hierarchical_rectangular(self):
        result = check_market_channel_capability(["UK"], ["TV"], None)
        assert result.engine == ENGINE_PYMC_RECTANGULAR

    def test_custom_engine_name_is_carried_through(self):
        result = check_market_channel_capability(
            ["UK"], ["TV"], None, engine="future_ragged_engine"
        )
        assert result.engine == "future_ragged_engine"

    def test_to_dict_is_json_shaped(self):
        matrix = _matrix(_resolved_record("TV", "UK"))
        result = check_market_channel_capability(["UK"], ["TV"], matrix)
        payload = result.to_dict()
        assert payload == {
            "engine": ENGINE_PYMC_RECTANGULAR,
            "markets": ["UK"],
            "channels": ["TV"],
            "supported": True,
            "issues": [],
            "recommendation_only_notes": [],
            "decision_report": "",
        }

    def test_empty_markets_or_channels_is_trivially_supported(self):
        result = check_market_channel_capability([], [], None)
        assert result.supported is True
        assert result.issues == ()


class TestNonObservedStatesAreUnsupported:
    """Review finding on PR #158: `is_officially_unresolved` only blocks
    `unknown`/`missing_expected` - a coverage segment recorded as
    `not_applicable`/`unavailable_source`/`suppressed`/`estimated`/
    `modelled` is equally not a genuinely observed source number
    (REQ-COVERAGE-001 S1, S2), and must be reported unsupported here too,
    not silently treated as fine to fit on."""

    def test_observed_zero_is_supported(self):
        matrix = _matrix(
            _resolved_record(
                "TV",
                "UK",
                coverage_segments=(
                    CoverageSegment(
                        period_start="2026-01-01",
                        period_end="2026-01-08",
                        state=STATE_OBSERVED_ZERO,
                    ),
                ),
            )
        )
        result = check_market_channel_capability(["UK"], ["TV"], matrix)
        assert result.supported is True

    def test_not_applicable_unavailable_suppressed_estimated_modelled_are_unsupported(
        self,
    ):
        for state in (
            STATE_NOT_APPLICABLE,
            STATE_UNAVAILABLE_SOURCE,
            STATE_SUPPRESSED,
            STATE_ESTIMATED,
            STATE_MODELLED,
        ):
            matrix = _matrix(
                _resolved_record(
                    "TV",
                    "UK",
                    coverage_segments=(
                        CoverageSegment(
                            period_start="2026-01-01",
                            period_end="2026-01-08",
                            state=state,
                        ),
                    ),
                )
            )
            result = check_market_channel_capability(["UK"], ["TV"], matrix)
            assert result.supported is False, state

    def test_approved_for_official_use_clears_a_non_observed_state_too(self):
        record = _resolved_record(
            "TV",
            "UK",
            coverage_segments=(
                CoverageSegment(
                    period_start="2026-01-01",
                    period_end="2026-01-08",
                    state=STATE_ESTIMATED,
                ),
            ),
            proposed_treatment="use governed estimate",
            approved_treatment="use governed estimate",
            treatment_status="approved",
            treatment_approved_by="reviewer",
            treatment_approved_at="2026-01-01",
            approved_for_official_use=True,
        )
        matrix = _matrix(record)
        result = check_market_channel_capability(["UK"], ["TV"], matrix)
        assert result.supported is True


def _approved_estimated_record(
    variable_id: str = "TV",
    market: str = "UK",
    *,
    gap_start: str = "2026-02-01",
    gap_end: str = "2026-02-08",
    observed_start: str = "2026-01-01",
    observed_end: str = "2026-03-01",
) -> VariableCoverageRecord:
    return _resolved_record(
        variable_id,
        market,
        coverage_segments=(
            CoverageSegment(
                period_start=gap_start, period_end=gap_end, state=STATE_ESTIMATED
            ),
        ),
        observed_start=observed_start,
        observed_end=observed_end,
        proposed_treatment="use governed estimate",
        approved_treatment="use governed estimate",
        treatment_status="approved",
        treatment_approved_by="reviewer",
        treatment_approved_at="2026-01-01",
        approved_for_official_use=True,
    )


def _adopted_policy(**overrides) -> EstimationReadinessPolicy:
    """An `EstimationReadinessPolicy` that has actually gone through
    Product/Finance approval (`is_recommendation_only=False`) - the only
    kind of policy allowed to gate the official capability result."""
    defaults = dict(
        is_recommendation_only=False,
        approved_by="finance-reviewer",
        approved_at="2026-01-01",
    )
    defaults.update(overrides)
    return EstimationReadinessPolicy(**defaults)


class TestEstimationReadinessPolicyIntegration:
    """UK FH MMM brief (2026-09-10) Workstream D follow-up: wiring
    assess_estimation_readiness into the actual production fit-readiness
    gate, not just leaving it as a standalone module. `approved_for_
    official_use=True` alone still suffices when no policy is supplied
    (backward compatible with every existing caller); a supplied policy
    additionally scrutinises estimated/modelled segments only."""

    def test_no_policy_supplied_is_unchanged_from_today(self):
        matrix = _matrix(_approved_estimated_record())
        result = check_market_channel_capability(["UK"], ["TV"], matrix)
        assert result.supported is True

    def test_policy_supplied_but_gap_within_limits_still_supported(self):
        matrix = _matrix(_approved_estimated_record())
        policy = EstimationReadinessPolicy(
            policy_id="p1", max_missing_week_count=4, max_consecutive_missing_run=4
        )
        result = check_market_channel_capability(
            ["UK"], ["TV"], matrix, estimation_readiness_policy=policy
        )
        assert result.supported is True

    def test_policy_supplied_and_gap_exceeds_missing_week_count_blocks(self):
        matrix = _matrix(_approved_estimated_record())
        policy = _adopted_policy(policy_id="p1", max_missing_week_count=1)
        result = check_market_channel_capability(
            ["UK"], ["TV"], matrix, estimation_readiness_policy=policy
        )
        assert result.supported is False
        assert "does not meet policy 'p1'" in result.issues[0].reason

    def test_policy_requiring_evidence_with_none_supplied_blocks(self):
        matrix = _matrix(_approved_estimated_record())
        policy = _adopted_policy(policy_id="p1", max_reconstruction_error_mape=20.0)
        result = check_market_channel_capability(
            ["UK"], ["TV"], matrix, estimation_readiness_policy=policy
        )
        assert result.supported is False

    def test_policy_requiring_evidence_with_matching_evidence_supplied_passes(self):
        # _approved_estimated_record()'s default gap (2026-02-01..2026-02-08)
        # is 2 weeks - the evidence below must match that exact length.
        matrix = _matrix(_approved_estimated_record())
        policy = EstimationReadinessPolicy(
            policy_id="p1", max_reconstruction_error_mape=50.0
        )
        evidence = EstimationEvidenceSummary(
            variable_id="TV",
            market="UK",
            evaluated_at="2026-09-10",
            n_observed_weeks_used=10,
            results=(
                HoldoutEvaluationResult(
                    method_name="flat_fill",
                    method_description="test",
                    holdout_gap_length_weeks=2,
                    holdout_position="middle",
                    holdout_start_week="2026-01-15",
                    n_holdout_weeks=2,
                    reconstruction_error_mae=5.0,
                    reconstruction_error_mape=10.0,
                ),
            ),
        )
        result = check_market_channel_capability(
            ["UK"],
            ["TV"],
            matrix,
            estimation_readiness_policy=policy,
            estimation_evidence_by_variable={("TV", "UK"): evidence},
        )
        assert result.supported is True

    def test_edge_gap_blocked_by_an_adopted_policy(self):
        matrix = _matrix(
            _approved_estimated_record(
                gap_start="2026-01-01",
                gap_end="2026-01-08",
                observed_start="2026-01-01",
                observed_end="2026-03-01",
            )
        )
        policy = _adopted_policy(policy_id="p1")
        result = check_market_channel_capability(
            ["UK"], ["TV"], matrix, estimation_readiness_policy=policy
        )
        assert result.supported is False

    def test_policy_never_examines_non_estimated_states(self):
        """A policy only re-examines a state an analyst has already marked
        estimated/modelled - it must never become a second path for
        unknown/missing_expected to slip through unapproved."""
        matrix = _matrix(_unresolved_record("TV", "UK"))
        policy = EstimationReadinessPolicy(policy_id="p1")
        result = check_market_channel_capability(
            ["UK"], ["TV"], matrix, estimation_readiness_policy=policy
        )
        assert result.supported is False
        assert "not a genuinely observed number" in result.issues[0].reason

    def test_policy_does_not_affect_fully_observed_records(self):
        matrix = _matrix(_resolved_record("TV", "UK"))
        policy = EstimationReadinessPolicy(policy_id="p1", max_missing_week_count=0)
        result = check_market_channel_capability(
            ["UK"], ["TV"], matrix, estimation_readiness_policy=policy
        )
        assert result.supported is True


def _mape_evidence(
    *, variable_id: str, market: str, mape: float, gap_length_weeks: int = 2
) -> EstimationEvidenceSummary:
    return EstimationEvidenceSummary(
        variable_id=variable_id,
        market=market,
        evaluated_at="2026-09-10",
        n_observed_weeks_used=10,
        results=(
            HoldoutEvaluationResult(
                method_name="flat_fill",
                method_description="test",
                holdout_gap_length_weeks=gap_length_weeks,
                holdout_position="middle",
                holdout_start_week="2026-01-15",
                n_holdout_weeks=gap_length_weeks,
                reconstruction_error_mae=5.0,
                reconstruction_error_mape=mape,
            ),
        ),
    )


class TestEvidenceIsScopedByMarket:
    """Regression (automated review finding, P1): the same `variable_id`
    can exist in more than one market (e.g. "TV" in both UK and AU).
    Evidence measured for one market must never approve or block the
    same variable in a different market - `estimation_evidence_by_
    variable` is keyed by `(variable_id, market)`, never `variable_id`
    alone."""

    def test_each_market_uses_only_its_own_evidence(self):
        # Same variable_id ("TV") in two markets: UK's evidence passes the
        # policy, AU's evidence fails it - if evidence were shared by
        # variable_id alone, both markets would get the same verdict.
        matrix = _matrix(
            _approved_estimated_record("TV", "UK"),
            _approved_estimated_record("TV", "AU"),
        )
        policy = _adopted_policy(policy_id="p1", max_reconstruction_error_mape=20.0)
        evidence_by_variable = {
            ("TV", "UK"): _mape_evidence(variable_id="TV", market="UK", mape=10.0),
            ("TV", "AU"): _mape_evidence(variable_id="TV", market="AU", mape=90.0),
        }
        result = check_market_channel_capability(
            ["UK", "AU"],
            ["TV"],
            matrix,
            estimation_readiness_policy=policy,
            estimation_evidence_by_variable=evidence_by_variable,
        )
        assert result.supported is False
        assert len(result.issues) == 1
        assert result.issues[0].market == "AU"
        assert result.issues[0].channel == "TV"

    def test_evidence_supplied_only_for_one_market_never_covers_another(self):
        """Only UK has an evidence entry; AU (same variable_id, no entry
        under its own market key) must be treated as having no evidence at
        all, never silently approved using UK's."""
        matrix = _matrix(
            _approved_estimated_record("TV", "UK"),
            _approved_estimated_record("TV", "AU"),
        )
        policy = _adopted_policy(policy_id="p1", max_reconstruction_error_mape=20.0)
        evidence_by_variable = {
            ("TV", "UK"): _mape_evidence(variable_id="TV", market="UK", mape=10.0),
        }
        result = check_market_channel_capability(
            ["UK", "AU"],
            ["TV"],
            matrix,
            estimation_readiness_policy=policy,
            estimation_evidence_by_variable=evidence_by_variable,
        )
        assert result.supported is False
        assert len(result.issues) == 1
        assert result.issues[0].market == "AU"
        assert "requires reconstruction-error evidence, but none" in (
            result.issues[0].reason
        )


class TestRecommendationOnlyPolicyNeverGatesOfficialReadiness:
    """Regression (automated review finding, P2): `is_recommendation_
    only=True` (the default, unadopted-by-Product/Finance state) must
    never gate the official capability result - only an adopted policy
    (`is_recommendation_only=False`, which requires `approved_by`/
    `approved_at`) can."""

    def test_recommendation_only_policy_cannot_block_official_readiness(self):
        matrix = _matrix(_approved_estimated_record())
        policy = EstimationReadinessPolicy(
            policy_id="p1",
            max_missing_week_count=1,  # recommendation-only by default
        )
        result = check_market_channel_capability(
            ["UK"], ["TV"], matrix, estimation_readiness_policy=policy
        )
        assert policy.is_recommendation_only is True
        assert result.supported is True
        assert result.issues == ()
        # The finding still exists - it is surfaced diagnostically, not
        # silently dropped.
        assert len(result.recommendation_only_notes) == 1
        assert result.recommendation_only_notes[0].market == "UK"
        assert result.recommendation_only_notes[0].channel == "TV"
        assert "does not meet policy 'p1'" in result.recommendation_only_notes[0].reason

    def test_adopted_policy_can_block_readiness_when_thresholds_fail(self):
        matrix = _matrix(_approved_estimated_record())
        policy = _adopted_policy(policy_id="p1", max_missing_week_count=1)
        result = check_market_channel_capability(
            ["UK"], ["TV"], matrix, estimation_readiness_policy=policy
        )
        assert policy.is_recommendation_only is False
        assert result.supported is False
        assert len(result.issues) == 1
        assert result.recommendation_only_notes == ()

    def test_distinction_is_visible_in_to_dict(self):
        """The same threshold failure lands in a different, clearly-named
        field depending on adoption status - never ambiguous about which
        one actually blocks."""
        matrix = _matrix(_approved_estimated_record())
        recommendation_only_policy = EstimationReadinessPolicy(
            policy_id="p1", max_missing_week_count=1
        )
        adopted_policy = _adopted_policy(policy_id="p1", max_missing_week_count=1)

        recommendation_result = check_market_channel_capability(
            ["UK"],
            ["TV"],
            matrix,
            estimation_readiness_policy=recommendation_only_policy,
        ).to_dict()
        adopted_result = check_market_channel_capability(
            ["UK"], ["TV"], matrix, estimation_readiness_policy=adopted_policy
        ).to_dict()

        assert recommendation_result["supported"] is True
        assert recommendation_result["issues"] == []
        assert len(recommendation_result["recommendation_only_notes"]) == 1

        assert adopted_result["supported"] is False
        assert len(adopted_result["issues"]) == 1
        assert adopted_result["recommendation_only_notes"] == []
