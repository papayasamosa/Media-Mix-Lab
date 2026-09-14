"""Tests for `ancestry_mmm.core.population_reference` (REQ-POPULATION-001).
Every population value used is a clearly synthetic test value - no real
figure from `.local-data/Population by Market.xlsx` appears anywhere in
this file."""

import pytest

from ancestry_mmm.core.population_reference import (
    POPULATION_BASIS_TOTAL_RESIDENT_POPULATION,
    AmbiguousPopulationReferenceError,
    PopulationReferenceRecord,
    PopulationReferenceSet,
    compute_population_records_fingerprint,
    new_reference_set_version,
    resolve_single_population_reference,
    validate_population_records,
)


def _record(**overrides) -> PopulationReferenceRecord:
    defaults = dict(
        population_reference_id="pop-1",
        market_id="UK",
        population=1_000_000.0,
        population_basis=POPULATION_BASIS_TOTAL_RESIDENT_POPULATION,
        source_name="synthetic_source",
        owner="test_owner",
        reference_year=2024,
    )
    defaults.update(overrides)
    return PopulationReferenceRecord(**defaults)


class TestPopulationReferenceRecord:
    def test_valid_record_round_trips(self):
        record = _record()
        assert PopulationReferenceRecord.from_dict(record.to_dict()) == record

    def test_missing_id_rejected(self):
        with pytest.raises(ValueError):
            _record(population_reference_id="")

    @pytest.mark.parametrize(
        "bad_id", [[1, 2, 3], {"a": 1}, 42, 3.14, None, True], ids=repr
    )
    def test_non_string_id_rejected(self, bad_id):
        """Codex P2 (2026-09-13, fourth pass): a non-string
        population_reference_id (e.g. from a malformed imported JSON
        record) must fail at construction, not construct successfully
        and crash later inside compute_population_records_fingerprint's
        sorted() call, which cannot compare a non-string key against a
        string one."""
        with pytest.raises(ValueError):
            _record(population_reference_id=bad_id)

    def test_valid_string_id_still_accepted(self):
        record = _record(population_reference_id="pop-valid-1")
        assert record.population_reference_id == "pop-valid-1"

    @pytest.mark.parametrize(
        "bad_market_id", [["UK"], {"a": 1}, 42, 3.14, None, True], ids=repr
    )
    def test_non_string_market_id_rejected(self, bad_market_id):
        """Codex P2 (2026-09-13, fifth pass): same principle as the
        population_reference_id fix above - a non-string market_id (e.g.
        a malformed imported JSON array) must fail at construction, not
        construct successfully and crash later inside
        validate_population_records's set-membership test or
        (market_id, reference_year) dict key, both of which require
        market_id to be hashable."""
        with pytest.raises(ValueError):
            _record(market_id=bad_market_id)

    def test_valid_string_market_id_still_accepted(self):
        record = _record(market_id="AU")
        assert record.market_id == "AU"

    def test_non_finite_population_rejected(self):
        with pytest.raises(ValueError):
            _record(population=float("nan"))
        with pytest.raises(ValueError):
            _record(population=float("inf"))

    def test_zero_or_negative_population_rejected(self):
        with pytest.raises(ValueError):
            _record(population=0.0)
        with pytest.raises(ValueError):
            _record(population=-1.0)

    def test_ordinary_positive_integer_population_accepted(self):
        record = _record(population=1_000_000)
        assert record.population == 1_000_000

    def test_ordinary_positive_float_population_accepted(self):
        record = _record(population=1_000_000.5)
        assert record.population == 1_000_000.5

    @pytest.mark.parametrize(
        "bad_population",
        [0, 0.0, -1, -1.0, float("nan"), float("inf"), float("-inf")],
        ids=[
            "zero-int",
            "zero-float",
            "negative-int",
            "negative-float",
            "nan",
            "inf",
            "-inf",
        ],
    )
    def test_invalid_population_values_rejected(self, bad_population):
        with pytest.raises(ValueError):
            _record(population=bad_population)

    def test_oversized_integer_population_rejected_as_value_error(self):
        """Codex P2 (2026-09-14, eighth review pass): an arbitrary-
        precision Python int too large to represent as a float (e.g.
        10**400) previously made `math.isfinite` itself raise
        `OverflowError` - a different exception type than every other
        population validation failure in this dataclass, and one the
        import-quarantine mechanism's `except (TypeError, ValueError,
        ...)` does not catch. It must now raise the same `ValueError`
        this dataclass already uses for other invalid population values,
        never be clamped, truncated, or silently substituted."""
        with pytest.raises(ValueError):
            _record(population=10**400)

    def test_unknown_basis_rejected(self):
        # Mirrors the real-world finding that the analyst-supplied file
        # uses a non-canonical basis label ("total_residents") - the
        # canonical vocabulary must not silently accept an alias.
        with pytest.raises(ValueError):
            _record(population_basis="total_residents")

    def test_non_integral_or_implausible_year_rejected(self):
        with pytest.raises(ValueError):
            _record(reference_year=2024.5)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            _record(reference_year=27_000_000)  # the real-file anomaly shape

    def test_reference_year_is_optional(self):
        record = _record(reference_year=None)
        assert record.reference_year is None

    def test_approved_requires_approver(self):
        with pytest.raises(ValueError):
            _record(approval_status="approved")
        # Providing both succeeds.
        _record(
            approval_status="approved", approved_by="reviewer", approved_at="2026-09-12"
        )

    @pytest.mark.parametrize("status", ["pending", "rejected"])
    def test_non_approved_rejects_stale_approver_metadata(self, status):
        """Codex P2 (2026-09-13, third pass): the symmetric case of
        test_approved_requires_approver - a pending/rejected record must
        not carry approver metadata that contradicts its own status."""
        with pytest.raises(ValueError):
            _record(approval_status=status, approved_by="reviewer")
        with pytest.raises(ValueError):
            _record(approval_status=status, approved_at="2026-09-12")
        with pytest.raises(ValueError):
            _record(
                approval_status=status,
                approved_by="reviewer",
                approved_at="2026-09-12",
            )
        # Neither set - the ordinary case - succeeds.
        _record(approval_status=status)

    def test_unknown_approval_status_rejected(self):
        with pytest.raises(ValueError):
            _record(approval_status="maybe")

    def test_omitted_schema_version_defaults_to_current(self):
        record = _record()
        assert record.schema_version == 1

    @pytest.mark.parametrize("bad_version", [999, 0, "1", "abc", None, 1.5])
    def test_unsupported_schema_version_rejected(self, bad_version):
        with pytest.raises(ValueError):
            _record(schema_version=bad_version)

    @pytest.mark.parametrize("bad_version", [True, False, 1.0])
    def test_schema_version_type_impostors_rejected(self, bad_version):
        """Codex P2 (2026-09-14, sixth review pass): `True == 1` and
        `1.0 == 1` in Python, so equality alone must not be trusted -
        a bool or float impostor for the correct value must still be
        rejected."""
        with pytest.raises(ValueError):
            _record(schema_version=bad_version)

    def test_correct_integer_schema_version_accepted(self):
        record = _record(schema_version=1)
        assert record.schema_version == 1
        assert type(record.schema_version) is int


class TestPopulationReferenceSet:
    def _fingerprint(self, records):
        return compute_population_records_fingerprint(records)

    def test_valid_set_round_trips(self):
        record = _record()
        reference_set = PopulationReferenceSet(
            reference_set_id="set-1",
            reference_set_version=1,
            name="Synthetic set",
            source_name="synthetic_source",
            retrieved_at="2026-09-12T00:00:00Z",
            records_fingerprint=self._fingerprint([record]),
        )
        assert (
            PopulationReferenceSet.from_dict(reference_set.to_dict()) == reference_set
        )

    @pytest.mark.parametrize("bad_id", [["s1"], {"a": 1}, 42, 3.14, None], ids=repr)
    def test_non_string_reference_set_id_rejected(self, bad_id):
        """2026-09-14: reference_set_id is declared `str` above - a
        truthiness-only check let a non-string value (e.g. a JSON array)
        through silently, the same defect class already fixed for
        PopulationReferenceRecord's population_reference_id/market_id."""
        with pytest.raises(ValueError):
            PopulationReferenceSet(
                reference_set_id=bad_id,
                reference_set_version=1,
                name="Synthetic set",
                source_name="synthetic_source",
                retrieved_at="2026-09-12T00:00:00Z",
                records_fingerprint=self._fingerprint([_record()]),
            )

    def test_valid_string_reference_set_id_still_accepted(self):
        reference_set = PopulationReferenceSet(
            reference_set_id="set-valid-1",
            reference_set_version=1,
            name="Synthetic set",
            source_name="synthetic_source",
            retrieved_at="2026-09-12T00:00:00Z",
            records_fingerprint=self._fingerprint([_record()]),
        )
        assert reference_set.reference_set_id == "set-valid-1"

    def test_short_fingerprint_rejected(self):
        with pytest.raises(ValueError):
            PopulationReferenceSet(
                reference_set_id="set-1",
                reference_set_version=1,
                name="Synthetic set",
                source_name="synthetic_source",
                retrieved_at="2026-09-12T00:00:00Z",
                records_fingerprint="not-a-real-hash",
            )

    def test_omitted_schema_version_defaults_to_current(self):
        reference_set = PopulationReferenceSet(
            reference_set_id="set-1",
            reference_set_version=1,
            name="Synthetic set",
            source_name="synthetic_source",
            retrieved_at="2026-09-12T00:00:00Z",
            records_fingerprint=self._fingerprint([_record()]),
        )
        assert reference_set.schema_version == 1

    @pytest.mark.parametrize("bad_version", [999, 0, "1", "abc", None, 1.5])
    def test_unsupported_schema_version_rejected(self, bad_version):
        with pytest.raises(ValueError):
            PopulationReferenceSet(
                reference_set_id="set-1",
                reference_set_version=1,
                name="Synthetic set",
                source_name="synthetic_source",
                retrieved_at="2026-09-12T00:00:00Z",
                records_fingerprint=self._fingerprint([_record()]),
                schema_version=bad_version,
            )

    @pytest.mark.parametrize("bad_version", [True, False, 1.0])
    def test_schema_version_type_impostors_rejected(self, bad_version):
        with pytest.raises(ValueError):
            PopulationReferenceSet(
                reference_set_id="set-1",
                reference_set_version=1,
                name="Synthetic set",
                source_name="synthetic_source",
                retrieved_at="2026-09-12T00:00:00Z",
                records_fingerprint=self._fingerprint([_record()]),
                schema_version=bad_version,
            )

    @pytest.mark.parametrize(
        "bad_version", [True, 1.0, 1.5, "1", None, 0, [1], {"v": 1}]
    )
    def test_non_integer_reference_set_version_rejected(self, bad_version):
        """Codex P2 (2026-09-14, sixth review pass): reference_set_version
        is a positive-integer counter, not a fixed schema constant, but
        the same bool/float/string-impostor risk applies to it."""
        with pytest.raises(ValueError):
            PopulationReferenceSet(
                reference_set_id="set-1",
                reference_set_version=bad_version,
                name="Synthetic set",
                source_name="synthetic_source",
                retrieved_at="2026-09-12T00:00:00Z",
                records_fingerprint=self._fingerprint([_record()]),
            )

    def test_correct_integer_reference_set_version_accepted(self):
        reference_set = PopulationReferenceSet(
            reference_set_id="set-1",
            reference_set_version=2,
            name="Synthetic set",
            source_name="synthetic_source",
            retrieved_at="2026-09-12T00:00:00Z",
            records_fingerprint=self._fingerprint([_record()]),
        )
        assert reference_set.reference_set_version == 2

    def test_approved_requires_approver(self):
        with pytest.raises(ValueError):
            PopulationReferenceSet(
                reference_set_id="set-1",
                reference_set_version=1,
                name="Synthetic set",
                source_name="synthetic_source",
                retrieved_at="2026-09-12T00:00:00Z",
                records_fingerprint=self._fingerprint([_record()]),
                approval_status="approved",
            )

    @pytest.mark.parametrize("status", ["pending", "rejected"])
    def test_non_approved_rejects_stale_approver_metadata(self, status):
        with pytest.raises(ValueError):
            PopulationReferenceSet(
                reference_set_id="set-1",
                reference_set_version=1,
                name="Synthetic set",
                source_name="synthetic_source",
                retrieved_at="2026-09-12T00:00:00Z",
                records_fingerprint=self._fingerprint([_record()]),
                approval_status=status,
                approved_by="reviewer",
            )

    def test_new_version_bumps_version_and_blocks_identity_edits(self):
        record = _record()
        reference_set = PopulationReferenceSet(
            reference_set_id="set-1",
            reference_set_version=1,
            name="Synthetic set",
            source_name="synthetic_source",
            retrieved_at="2026-09-12T00:00:00Z",
            records_fingerprint=self._fingerprint([record]),
        )
        bumped = new_reference_set_version(reference_set, name="Revised synthetic set")
        assert bumped.reference_set_version == 2
        assert bumped.reference_set_id == reference_set.reference_set_id
        with pytest.raises(ValueError):
            new_reference_set_version(reference_set, reference_set_version=99)


class TestNewReferenceSetVersionApprovalReset:
    """Codex P2 (2026-09-13, third pass): approval belongs to the exact
    governed version/content that was reviewed - it must never carry
    forward automatically onto a new version. No equivalent existing
    versioning helper resets approval either, so this module adopts the
    simpler invariant: every new version defaults to pending unless the
    caller explicitly supplies a fresh, complete approval in the same
    call (an explicit, separate reapproval action)."""

    def _fingerprint(self, records):
        return compute_population_records_fingerprint(records)

    def _approved_v1(self) -> PopulationReferenceSet:
        return PopulationReferenceSet(
            reference_set_id="set-1",
            reference_set_version=1,
            name="Synthetic set",
            source_name="synthetic_source",
            retrieved_at="2026-09-12T00:00:00Z",
            records_fingerprint=self._fingerprint([_record()]),
            approval_status="approved",
            approved_by="reviewer",
            approved_at="2026-09-12",
        )

    def test_approved_v1_remains_approved_and_unchanged(self):
        v1 = self._approved_v1()
        new_reference_set_version(v1, name="Revised synthetic set")
        assert v1.approval_status == "approved"
        assert v1.approved_by == "reviewer"
        assert v1.approved_at == "2026-09-12"
        assert v1.reference_set_version == 1

    def test_materially_changed_v2_is_pending_with_no_approval_metadata(self):
        v1 = self._approved_v1()
        v2 = new_reference_set_version(v1, name="Revised synthetic set")
        assert v2.approval_status == "pending"
        assert v2.approved_by is None
        assert v2.approved_at is None
        assert v2.reference_set_version == 2

    def test_corrected_records_fingerprint_cannot_inherit_approval(self):
        v1 = self._approved_v1()
        corrected_fingerprint = self._fingerprint(
            [_record(population_reference_id="pop-2")]
        )
        v2 = new_reference_set_version(v1, records_fingerprint=corrected_fingerprint)
        assert v2.records_fingerprint == corrected_fingerprint
        assert v2.approval_status == "pending"
        assert v2.approved_by is None
        assert v2.approved_at is None

    def test_new_version_function_does_not_mutate_v1(self):
        v1 = self._approved_v1()
        original_status = v1.approval_status
        original_by = v1.approved_by
        original_at = v1.approved_at
        new_reference_set_version(
            v1, records_fingerprint=self._fingerprint([_record()])
        )
        assert v1.approval_status == original_status
        assert v1.approved_by == original_by
        assert v1.approved_at == original_at

    def test_explicit_reapproval_remains_a_separate_supported_action(self):
        v1 = self._approved_v1()
        v2 = new_reference_set_version(
            v1,
            records_fingerprint=self._fingerprint(
                [_record(population_reference_id="pop-2")]
            ),
            approval_status="approved",
            approved_by="second_reviewer",
            approved_at="2026-09-13",
        )
        assert v2.approval_status == "approved"
        assert v2.approved_by == "second_reviewer"
        assert v2.approved_at == "2026-09-13"
        # v1's own approval is still untouched by this explicit v2 reapproval.
        assert v1.approved_by == "reviewer"


class TestValidatePopulationRecords:
    def test_unresolved_market_is_flagged(self):
        record = _record(market_id="ZZ")
        issues = validate_population_records([record], known_market_ids=["UK", "AU"])
        assert any(
            "does not resolve to a governed market" in issue.reason for issue in issues
        )

    def test_known_market_has_no_market_issue(self):
        record = _record(market_id="UK")
        issues = validate_population_records([record], known_market_ids=["UK", "AU"])
        assert not any(
            "does not resolve to a governed market" in issue.reason for issue in issues
        )

    def test_duplicate_approved_market_year_is_blocking(self):
        one = _record(
            population_reference_id="pop-1",
            approval_status="approved",
            approved_by="reviewer",
            approved_at="2026-09-12",
        )
        two = _record(
            population_reference_id="pop-2",
            approval_status="approved",
            approved_by="reviewer",
            approved_at="2026-09-12",
        )
        issues = validate_population_records([one, two], known_market_ids=["UK"])
        reasons = [issue.reason for issue in issues]
        assert any(
            "duplicate approved population reference" in reason for reason in reasons
        )
        assert (
            len([r for r in reasons if "duplicate approved population reference" in r])
            == 2
        )

    def test_duplicate_pending_records_are_not_blocking(self):
        # Only *approved* duplicates are blocking - two pending uploads for
        # the same market/year are an ordinary, unresolved review state.
        one = _record(population_reference_id="pop-1", approval_status="pending")
        two = _record(population_reference_id="pop-2", approval_status="pending")
        issues = validate_population_records([one, two], known_market_ids=["UK"])
        assert not any(
            "duplicate approved population reference" in i.reason for i in issues
        )

    def test_no_issues_returns_empty_tuple(self):
        record = _record(
            approval_status="approved", approved_by="reviewer", approved_at="2026-09-12"
        )
        assert validate_population_records([record], known_market_ids=["UK"]) == ()


class TestResolveSinglePopulationReference:
    def _approved(self, **overrides):
        defaults = dict(
            approval_status="approved", approved_by="reviewer", approved_at="2026-09-12"
        )
        defaults.update(overrides)
        return _record(**defaults)

    def test_zero_applicable_returns_none(self):
        record = _record(market_id="UK", approval_status="pending")
        assert resolve_single_population_reference("UK", [record]) is None

    def test_exactly_one_applicable_is_returned(self):
        record = self._approved(market_id="UK")
        assert resolve_single_population_reference("UK", [record]) == record

    def test_more_than_one_applicable_raises_ambiguous_not_a_guess(self):
        one = self._approved(
            population_reference_id="pop-1", market_id="UK", reference_year=2023
        )
        two = self._approved(
            population_reference_id="pop-2", market_id="UK", reference_year=2024
        )
        with pytest.raises(AmbiguousPopulationReferenceError):
            resolve_single_population_reference("UK", [one, two])

    def test_only_the_requested_market_is_considered(self):
        uk = self._approved(population_reference_id="pop-uk", market_id="UK")
        au = self._approved(population_reference_id="pop-au", market_id="AU")
        assert resolve_single_population_reference("UK", [uk, au]) == uk

    def test_pending_records_are_never_applicable(self):
        pending = _record(market_id="UK", approval_status="pending")
        assert resolve_single_population_reference("UK", [pending]) is None
