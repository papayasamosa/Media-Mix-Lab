"""Tests for core.missing_media_evidence (UK FH MMM brief, 2026-09-10,
Workstream D): gap diagnostics, the holdout estimation-evidence harness,
and the fail-closed readiness gate.
"""

from __future__ import annotations

import pytest

from ancestry_mmm.core.coverage import (
    STATE_MISSING_EXPECTED,
    STATE_OBSERVED_ZERO,
    STATE_UNKNOWN,
    CoverageSegment,
    FrequencyMetadata,
    VariableCoverageRecord,
)
from ancestry_mmm.core.missing_media_evidence import (
    READINESS_BLOCKED_EDGE_GAP,
    READINESS_BLOCKED_EXCEEDS_CONSECUTIVE_RUN,
    READINESS_BLOCKED_EXCEEDS_MISSING_WEEK_COUNT,
    READINESS_BLOCKED_EXCEEDS_RECONSTRUCTION_ERROR,
    READINESS_BLOCKED_NO_EVIDENCE,
    READINESS_BLOCKED_NO_POLICY,
    READINESS_ESTIMABLE_WITH_EVIDENCE,
    EstimationEvidenceSummary,
    EstimationReadinessPolicy,
    GapDiagnostics,
    assess_estimation_readiness,
    diagnose_gaps,
    evaluate_candidate_reconstruction_method,
)
from ancestry_mmm.core.named_events import NamedEventOccurrence


def _freq() -> FrequencyMetadata:
    return FrequencyMetadata(
        native_frequency="weekly", target_frequency="weekly", variable_class="flow_count"
    )


def _record(**overrides) -> VariableCoverageRecord:
    defaults = dict(
        variable_id="tv_uk",
        source_id="src1",
        source_version=1,
        market="UK",
        frequency=_freq(),
        coverage_segments=(
            CoverageSegment(
                period_start="2025-01-06",
                period_end="2025-01-27",
                state=STATE_OBSERVED_ZERO,
            ),
            CoverageSegment(
                period_start="2025-02-03",
                period_end="2025-02-17",
                state=STATE_MISSING_EXPECTED,
            ),
            CoverageSegment(
                period_start="2025-02-24",
                period_end="2025-03-10",
                state=STATE_OBSERVED_ZERO,
            ),
        ),
        observed_start="2025-01-06",
        observed_end="2025-03-10",
    )
    defaults.update(overrides)
    return VariableCoverageRecord(**defaults)


class TestDiagnoseGaps:
    def test_internal_gap_is_classified_correctly(self):
        diagnostics = diagnose_gaps(_record())
        assert len(diagnostics) == 1
        gap = diagnostics[0]
        assert gap.gap_start == "2025-02-03"
        assert gap.missing_week_count == 3
        assert gap.is_internal is True
        assert gap.is_at_start_of_history is False
        assert gap.is_at_end_of_history is False

    def test_edge_gap_at_start_is_classified_correctly(self):
        record = _record(
            coverage_segments=(
                CoverageSegment(
                    period_start="2025-01-06",
                    period_end="2025-01-20",
                    state=STATE_MISSING_EXPECTED,
                ),
                CoverageSegment(
                    period_start="2025-01-27",
                    period_end="2025-03-10",
                    state=STATE_OBSERVED_ZERO,
                ),
            ),
        )
        diagnostics = diagnose_gaps(record)
        assert len(diagnostics) == 1
        assert diagnostics[0].is_at_start_of_history is True
        assert diagnostics[0].is_internal is False

    def test_unknown_state_is_a_gap_by_default(self):
        record = _record(
            coverage_segments=(
                CoverageSegment(
                    period_start="2025-01-06",
                    period_end="2025-01-20",
                    state=STATE_UNKNOWN,
                ),
                CoverageSegment(
                    period_start="2025-01-27",
                    period_end="2025-03-10",
                    state=STATE_OBSERVED_ZERO,
                ),
            ),
        )
        diagnostics = diagnose_gaps(record)
        assert len(diagnostics) == 1
        assert diagnostics[0].state == STATE_UNKNOWN

    def test_observed_zero_segments_are_never_gaps(self):
        record = _record(
            coverage_segments=(
                CoverageSegment(
                    period_start="2025-01-06",
                    period_end="2025-03-10",
                    state=STATE_OBSERVED_ZERO,
                ),
            ),
        )
        assert diagnose_gaps(record) == ()

    def test_named_event_overlap_is_detected_only_within_market_scope(self):
        occurrence_in_scope = NamedEventOccurrence(
            event_id="black_friday_2025",
            event_version=1,
            display_name="Black Friday 2025",
            start_date="2025-02-10",
            end_date="2025-02-12",
            market_scope=("UK",),
            source_id="events_src",
        )
        occurrence_out_of_scope = NamedEventOccurrence(
            event_id="au_only_event",
            event_version=1,
            display_name="AU-only event",
            start_date="2025-02-10",
            end_date="2025-02-12",
            market_scope=("AU",),
            source_id="events_src",
        )
        diagnostics = diagnose_gaps(
            _record(),
            named_event_occurrences=(occurrence_in_scope, occurrence_out_of_scope),
        )
        assert diagnostics[0].overlapping_named_event_ids == ("black_friday_2025",)

    def test_spend_companion_evidence_when_covering_and_when_absent(self):
        spend_covers = _record(
            variable_id="tv_uk_spend",
            coverage_segments=(
                CoverageSegment(
                    period_start="2025-01-06",
                    period_end="2025-03-10",
                    state=STATE_OBSERVED_ZERO,
                ),
            ),
        )
        diagnostics = diagnose_gaps(_record(), spend_companion=spend_covers)
        assert diagnostics[0].spend_observed_during_gap is True

        no_companion_diagnostics = diagnose_gaps(_record())
        assert no_companion_diagnostics[0].spend_observed_during_gap is None

    def test_companion_with_no_overlapping_segment_is_none_not_false(self):
        spend_no_coverage_in_window = _record(
            variable_id="tv_uk_spend",
            coverage_segments=(
                CoverageSegment(
                    period_start="2025-01-06",
                    period_end="2025-01-27",
                    state=STATE_OBSERVED_ZERO,
                ),
            ),
        )
        diagnostics = diagnose_gaps(
            _record(), spend_companion=spend_no_coverage_in_window
        )
        assert diagnostics[0].spend_observed_during_gap is None


class TestEvaluateCandidateReconstructionMethod:
    WEEKS = [
        "2025-01-06",
        "2025-01-13",
        "2025-01-20",
        "2025-01-27",
        "2025-02-03",
        "2025-02-10",
        "2025-02-17",
        "2025-02-24",
    ]
    VALUES = [100.0, 110.0, 105.0, 120.0, 115.0, 125.0, 130.0, 128.0]

    @staticmethod
    def _flat_fill(remaining_weeks, remaining_values, held_out_weeks):
        return [remaining_values[-1]] * len(held_out_weeks)

    def test_returns_one_result_per_valid_gap_length_and_position(self):
        results = evaluate_candidate_reconstruction_method(
            self.WEEKS,
            self.VALUES,
            method_name="flat_fill",
            method_description="test",
            reconstruct=self._flat_fill,
            holdout_gap_lengths=(1, 2),
            holdout_positions=("start", "middle", "end"),
        )
        assert len(results) == 6
        assert {r.holdout_gap_length_weeks for r in results} == {1, 2}
        assert {r.holdout_position for r in results} == {"start", "middle", "end"}

    def test_gap_length_that_does_not_fit_is_skipped_not_padded(self):
        results = evaluate_candidate_reconstruction_method(
            self.WEEKS,
            self.VALUES,
            method_name="flat_fill",
            method_description="test",
            reconstruct=self._flat_fill,
            holdout_gap_lengths=(100,),
        )
        assert results == ()

    def test_mae_is_computed_correctly(self):
        results = evaluate_candidate_reconstruction_method(
            self.WEEKS,
            self.VALUES,
            method_name="flat_fill",
            method_description="test",
            reconstruct=self._flat_fill,
            holdout_gap_lengths=(1,),
            holdout_positions=("end",),
        )
        assert len(results) == 1
        # Held-out true value is the last observed (128.0); flat-fill
        # predicts the value immediately preceding the gap (130.0).
        assert results[0].reconstruction_error_mae == pytest.approx(2.0)

    def test_mape_is_none_when_a_true_value_is_zero(self):
        weeks = ["2025-01-06", "2025-01-13", "2025-01-20"]
        values = [0.0, 10.0, 20.0]

        def flat_fill(remaining_weeks, remaining_values, held_out_weeks):
            return [remaining_values[0]] * len(held_out_weeks)

        results = evaluate_candidate_reconstruction_method(
            weeks,
            values,
            method_name="flat_fill",
            method_description="test",
            reconstruct=flat_fill,
            holdout_gap_lengths=(1,),
            holdout_positions=("start",),
        )
        assert len(results) == 1
        assert results[0].reconstruction_error_mape is None

    def test_reconstruct_returning_wrong_length_raises(self):
        def broken(remaining_weeks, remaining_values, held_out_weeks):
            return [1.0]  # always one value, regardless of gap length

        with pytest.raises(ValueError, match="broken_method"):
            evaluate_candidate_reconstruction_method(
                self.WEEKS,
                self.VALUES,
                method_name="broken_method",
                method_description="test",
                reconstruct=broken,
                holdout_gap_lengths=(2,),
                holdout_positions=("start",),
            )

    def test_mismatched_input_lengths_raise(self):
        with pytest.raises(ValueError):
            evaluate_candidate_reconstruction_method(
                self.WEEKS,
                self.VALUES[:-1],
                method_name="flat_fill",
                method_description="test",
                reconstruct=self._flat_fill,
            )


class TestEstimationReadinessPolicy:
    def test_recommendation_only_by_default(self):
        policy = EstimationReadinessPolicy(policy_id="p1")
        assert policy.is_recommendation_only is True

    def test_adopted_policy_requires_attribution(self):
        with pytest.raises(ValueError, match="approved_by"):
            EstimationReadinessPolicy(policy_id="p1", is_recommendation_only=False)

    def test_adopted_policy_with_attribution_succeeds(self):
        policy = EstimationReadinessPolicy(
            policy_id="p1",
            is_recommendation_only=False,
            approved_by="finance",
            approved_at="2026-09-10",
        )
        assert policy.approved_by == "finance"

    def test_negative_thresholds_rejected(self):
        with pytest.raises(ValueError):
            EstimationReadinessPolicy(policy_id="p1", max_missing_week_count=-1)


class TestAssessEstimationReadiness:
    def _internal_gap(self, **overrides) -> GapDiagnostics:
        defaults = dict(
            variable_id="tv_uk",
            market="UK",
            gap_start="2025-02-03",
            gap_end="2025-02-17",
            state=STATE_MISSING_EXPECTED,
            missing_week_count=3,
            is_internal=True,
            is_at_start_of_history=False,
            is_at_end_of_history=False,
        )
        defaults.update(overrides)
        return GapDiagnostics(**defaults)

    def test_no_policy_always_blocks(self):
        result = assess_estimation_readiness(self._internal_gap(), policy=None)
        assert result.status == READINESS_BLOCKED_NO_POLICY

    def test_edge_gap_blocked_unless_policy_allows_it(self):
        edge_gap = self._internal_gap(is_internal=False, is_at_end_of_history=True)
        policy = EstimationReadinessPolicy(policy_id="p1")
        assert (
            assess_estimation_readiness(edge_gap, policy=policy).status
            == READINESS_BLOCKED_EDGE_GAP
        )
        permissive_policy = EstimationReadinessPolicy(
            policy_id="p2", allow_edge_gaps=True
        )
        assert (
            assess_estimation_readiness(edge_gap, policy=permissive_policy).status
            == READINESS_ESTIMABLE_WITH_EVIDENCE
        )

    def test_exceeds_missing_week_count_blocks(self):
        policy = EstimationReadinessPolicy(policy_id="p1", max_missing_week_count=2)
        result = assess_estimation_readiness(self._internal_gap(), policy=policy)
        assert result.status == READINESS_BLOCKED_EXCEEDS_MISSING_WEEK_COUNT

    def test_exceeds_consecutive_run_blocks(self):
        policy = EstimationReadinessPolicy(
            policy_id="p1", max_consecutive_missing_run=2
        )
        result = assess_estimation_readiness(self._internal_gap(), policy=policy)
        assert result.status == READINESS_BLOCKED_EXCEEDS_CONSECUTIVE_RUN

    def test_within_missing_week_count_and_run_is_estimable(self):
        policy = EstimationReadinessPolicy(
            policy_id="p1", max_missing_week_count=4, max_consecutive_missing_run=4
        )
        result = assess_estimation_readiness(self._internal_gap(), policy=policy)
        assert result.status == READINESS_ESTIMABLE_WITH_EVIDENCE

    def test_mape_threshold_without_evidence_blocks(self):
        policy = EstimationReadinessPolicy(
            policy_id="p1", max_reconstruction_error_mape=20.0
        )
        result = assess_estimation_readiness(
            self._internal_gap(), policy=policy, evidence=None
        )
        assert result.status == READINESS_BLOCKED_NO_EVIDENCE

    def test_mape_within_threshold_is_estimable(self):
        results = evaluate_candidate_reconstruction_method(
            TestEvaluateCandidateReconstructionMethod.WEEKS,
            TestEvaluateCandidateReconstructionMethod.VALUES,
            method_name="flat_fill",
            method_description="test",
            reconstruct=TestEvaluateCandidateReconstructionMethod._flat_fill,
            holdout_gap_lengths=(1,),
            holdout_positions=("end",),
        )
        evidence = EstimationEvidenceSummary(
            variable_id="tv_uk",
            market="UK",
            evaluated_at="2026-09-10",
            n_observed_weeks_used=8,
            results=results,
        )
        policy = EstimationReadinessPolicy(
            policy_id="p1", max_reconstruction_error_mape=50.0
        )
        result = assess_estimation_readiness(
            self._internal_gap(), policy=policy, evidence=evidence
        )
        assert result.status == READINESS_ESTIMABLE_WITH_EVIDENCE

    def test_mape_exceeding_threshold_blocks(self):
        results = evaluate_candidate_reconstruction_method(
            TestEvaluateCandidateReconstructionMethod.WEEKS,
            TestEvaluateCandidateReconstructionMethod.VALUES,
            method_name="flat_fill",
            method_description="test",
            reconstruct=TestEvaluateCandidateReconstructionMethod._flat_fill,
            holdout_gap_lengths=(1,),
            holdout_positions=("end",),
        )
        evidence = EstimationEvidenceSummary(
            variable_id="tv_uk",
            market="UK",
            evaluated_at="2026-09-10",
            n_observed_weeks_used=8,
            results=results,
        )
        policy = EstimationReadinessPolicy(
            policy_id="p1", max_reconstruction_error_mape=0.1
        )
        result = assess_estimation_readiness(
            self._internal_gap(), policy=policy, evidence=evidence
        )
        assert result.status == READINESS_BLOCKED_EXCEEDS_RECONSTRUCTION_ERROR
