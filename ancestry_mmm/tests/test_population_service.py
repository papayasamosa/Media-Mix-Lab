"""Tests for `application.population_service` (REQ-POPULATION-001). No
actual population figure appears anywhere in this file - every value used
is a clearly synthetic test value. The real file
(`.local-data/Population by Market.xlsx`) is never read here - it is used
only for one-off, manual format verification outside the automated test
suite, and is never committed."""

import pandas as pd
import pytest

from ancestry_mmm.application.population_service import (
    PopulationUploadValidationError,
    build_population_reference_set,
)


def _valid_frame(**overrides) -> pd.DataFrame:
    rows = overrides.pop(
        "rows",
        [
            {
                "market": "UK",
                "population": 1_000_000,
                "population_basis": "total_resident_population",
                "reference_year": 2024,
                "source": "synthetic_source",
            },
            {
                "market": "AU",
                "population": 500_000,
                "population_basis": "total_resident_population",
                "reference_year": 2024,
                "source": "synthetic_source",
            },
        ],
    )
    return pd.DataFrame(rows).astype(object)


def _build(frame, **kwargs):
    defaults = dict(
        reference_set_id="set-1",
        reference_set_version=1,
        name="Synthetic population set",
        source_name="synthetic_source",
        owner="test_owner",
    )
    defaults.update(kwargs)
    return build_population_reference_set(frame, **defaults)


class TestBuildPopulationReferenceSet:
    def test_valid_upload_builds_set_and_records(self):
        reference_set, records = _build(_valid_frame())
        assert len(records) == 2
        assert {r.market_id for r in records} == {"UK", "AU"}
        assert reference_set.approval_status == "pending"
        assert all(r.approval_status == "pending" for r in records)

    def test_extra_columns_are_ignored(self):
        frame = _valid_frame()
        frame["Median Age"] = [40.1, 38.2]
        frame["Unnamed: 5"] = [None, None]
        _, records = _build(frame)
        assert len(records) == 2

    def test_missing_required_column_rejected(self):
        frame = _valid_frame().drop(columns=["reference_year"])
        with pytest.raises(PopulationUploadValidationError):
            _build(frame)

    def test_empty_upload_rejected(self):
        frame = _valid_frame().iloc[0:0]
        with pytest.raises(PopulationUploadValidationError):
            _build(frame)

    def test_missing_market_in_a_row_rejected(self):
        frame = _valid_frame()
        frame.loc[0, "market"] = None
        with pytest.raises(PopulationUploadValidationError, match="row 1"):
            _build(frame)

    def test_non_numeric_population_rejected(self):
        frame = _valid_frame()
        frame.loc[1, "population"] = "not-a-number"
        with pytest.raises(PopulationUploadValidationError, match="row 2"):
            _build(frame)

    def test_zero_population_rejected(self):
        frame = _valid_frame()
        frame.loc[0, "population"] = 0
        with pytest.raises(PopulationUploadValidationError):
            _build(frame)

    def test_unknown_basis_rejected(self):
        # Mirrors the real-world finding that the analyst-supplied file
        # uses a non-canonical basis label - ingestion must not silently
        # accept an alias for the approved vocabulary.
        frame = _valid_frame()
        frame.loc[0, "population_basis"] = "total_residents"
        with pytest.raises(PopulationUploadValidationError, match="row 1"):
            _build(frame)

    def test_non_integral_reference_year_rejected(self):
        frame = _valid_frame()
        frame.loc[0, "reference_year"] = 2024.5
        with pytest.raises(PopulationUploadValidationError, match="row 1"):
            _build(frame)

    def test_implausible_reference_year_rejected(self):
        # Mirrors the real-world anomaly: a population-sized number
        # sitting in the reference_year column.
        frame = _valid_frame()
        frame.loc[0, "reference_year"] = 27_284_236
        with pytest.raises(PopulationUploadValidationError, match="row 1"):
            _build(frame)

    @pytest.mark.parametrize("bad_year", [float("inf"), float("-inf")])
    def test_non_finite_reference_year_rejected_as_validation_error(self, bad_year):
        """Codex P2 (2026-09-13, fourth pass): int(round(float(inf)))
        raises OverflowError, which must surface as the documented,
        row-indexed PopulationUploadValidationError - never a raw
        OverflowError leaking out of the upload path."""
        frame = _valid_frame()
        frame.loc[0, "reference_year"] = bad_year
        with pytest.raises(PopulationUploadValidationError, match="row 1"):
            _build(frame)

    def test_ordinary_integral_year_still_works(self):
        frame = _valid_frame()
        frame.loc[0, "reference_year"] = 2024
        _, records = _build(frame)
        assert records[0].reference_year == 2024

    def test_missing_reference_year_is_allowed(self):
        frame = _valid_frame()
        frame.loc[0, "reference_year"] = None
        _, records = _build(frame)
        assert records[0].reference_year is None

    def test_unknown_market_rejected_when_known_markets_supplied(self):
        frame = _valid_frame()
        with pytest.raises(PopulationUploadValidationError):
            _build(frame, known_market_ids=["UK"])  # AU is not configured

    def test_unknown_market_allowed_when_known_markets_not_supplied(self):
        frame = _valid_frame()
        _, records = _build(frame)  # no known_market_ids -> no cross-check
        assert len(records) == 2

    def test_approval_status_and_approver_pass_through_uniformly(self):
        reference_set, records = _build(
            _valid_frame(),
            approval_status="approved",
            approved_by="reviewer",
            approved_at="2026-09-12",
            known_market_ids=["UK", "AU"],
        )
        assert reference_set.approval_status == "approved"
        assert all(r.approval_status == "approved" for r in records)
        assert all(r.approved_by == "reviewer" for r in records)

    def test_records_fingerprint_matches_a_direct_recomputation(self):
        from ancestry_mmm.application.population_service import (
            compute_population_records_fingerprint,
        )

        reference_set, records = _build(_valid_frame())
        assert (
            reference_set.records_fingerprint
            == compute_population_records_fingerprint(records)
        )

    def test_missing_metadata_rejected(self):
        with pytest.raises(PopulationUploadValidationError):
            _build(_valid_frame(), name="")


class TestRowNumberingIndependentOfDataFrameIndex:
    """Codex P2 (2026-09-14, seventh review pass): row-error messages
    must use a plain positional ordinal, never arithmetic on the caller's
    own DataFrame index - `index + 1` previously crashed for a
    non-numeric (e.g. string) index instead of raising the documented
    `PopulationUploadValidationError`."""

    def test_ordinary_numeric_index_unaffected(self):
        frame = _valid_frame()
        frame.loc[1, "market"] = None
        with pytest.raises(PopulationUploadValidationError, match="row 2"):
            _build(frame)

    def test_string_indexed_dataframe_with_valid_rows_succeeds(self):
        frame = _valid_frame()
        frame.index = ["uk-row", "au-row"]
        _, records = _build(frame)
        assert len(records) == 2
        assert {r.market_id for r in records} == {"UK", "AU"}

    def test_string_indexed_dataframe_invalid_row_raises_documented_error(self):
        frame = _valid_frame()
        frame.index = ["uk-row", "au-row"]
        frame.loc["au-row", "market"] = None
        with pytest.raises(PopulationUploadValidationError, match="row 2"):
            _build(frame)

    def test_string_indexed_dataframe_does_not_mutate_caller_index(self):
        frame = _valid_frame()
        frame.index = ["uk-row", "au-row"]
        original_index = list(frame.index)
        _build(frame)
        assert list(frame.index) == original_index


class TestDirectlyApprovedDuplicateRejection:
    """Codex P2 (2026-09-13, second pass): `approval_status="approved"`
    has no later approval stage in this path, so duplicate approved rows
    for the same (market, reference_year) must block creation here."""

    @staticmethod
    def _duplicate_same_year_frame() -> pd.DataFrame:
        return _valid_frame(
            rows=[
                {
                    "market": "UK",
                    "population": 1_000_000,
                    "population_basis": "total_resident_population",
                    "reference_year": 2024,
                    "source": "synthetic_source",
                },
                {
                    "market": "UK",
                    "population": 1_100_000,
                    "population_basis": "total_resident_population",
                    "reference_year": 2024,
                    "source": "synthetic_source",
                },
            ]
        )

    @staticmethod
    def _different_years_frame() -> pd.DataFrame:
        return _valid_frame(
            rows=[
                {
                    "market": "UK",
                    "population": 1_000_000,
                    "population_basis": "total_resident_population",
                    "reference_year": 2023,
                    "source": "synthetic_source",
                },
                {
                    "market": "UK",
                    "population": 1_100_000,
                    "population_basis": "total_resident_population",
                    "reference_year": 2024,
                    "source": "synthetic_source",
                },
            ]
        )

    def test_two_directly_approved_rows_same_market_and_year_rejected(self):
        with pytest.raises(PopulationUploadValidationError, match="duplicate approved"):
            _build(
                self._duplicate_same_year_frame(),
                approval_status="approved",
                approved_by="reviewer",
                approved_at="2026-09-13",
                known_market_ids=["UK"],
            )

    def test_two_directly_approved_rows_different_years_allowed(self):
        _, records = _build(
            self._different_years_frame(),
            approval_status="approved",
            approved_by="reviewer",
            approved_at="2026-09-13",
            known_market_ids=["UK"],
        )
        assert len(records) == 2
        assert {r.reference_year for r in records} == {2023, 2024}

    def test_pending_upload_with_duplicate_year_is_unaffected(self):
        # Default approval_status="pending" - unchanged behaviour: no
        # later approval stage assumption applies here, so this must not
        # start blocking pending uploads that worked before this fix, and
        # a pending upload still needs no known_market_ids at all.
        _, records = _build(self._duplicate_same_year_frame())
        assert len(records) == 2

    def test_unresolved_market_validation_still_works_when_supplied(self):
        # Regression check: the pre-existing known_market_ids behaviour
        # must survive this change unchanged.
        with pytest.raises(PopulationUploadValidationError):
            _build(_valid_frame(), known_market_ids=["UK"])  # AU is not configured

    def test_unresolved_market_and_duplicate_can_both_be_reported_together(self):
        frame = self._duplicate_same_year_frame()
        with pytest.raises(PopulationUploadValidationError) as exc_info:
            _build(
                frame,
                approval_status="approved",
                approved_by="reviewer",
                approved_at="2026-09-13",
                known_market_ids=["AU"],  # UK is not configured either
            )
        message = str(exc_info.value)
        assert "duplicate approved" in message
        assert "does not resolve to a governed market" in message


class TestApprovedUploadsRequireGovernedMarkets:
    """Codex P2 (2026-09-13, third pass): approval_status="approved"
    while known_market_ids=None let market-resolution validation be
    skipped entirely - fixed to fail closed up front."""

    def test_approved_with_no_governed_market_list_fails(self):
        with pytest.raises(
            PopulationUploadValidationError, match="requires known_market_ids"
        ):
            _build(
                _valid_frame(),
                approval_status="approved",
                approved_by="reviewer",
                approved_at="2026-09-13",
            )

    def test_approved_with_valid_governed_markets_succeeds(self):
        reference_set, records = _build(
            _valid_frame(),
            approval_status="approved",
            approved_by="reviewer",
            approved_at="2026-09-13",
            known_market_ids=["UK", "AU"],
        )
        assert reference_set.approval_status == "approved"
        assert len(records) == 2

    def test_approved_with_typo_market_fails(self):
        with pytest.raises(PopulationUploadValidationError, match="governed market"):
            _build(
                _valid_frame(),
                approval_status="approved",
                approved_by="reviewer",
                approved_at="2026-09-13",
                known_market_ids=["UK"],  # AU is not configured
            )

    def test_pending_upload_still_needs_no_governed_market_list(self):
        # Default approval_status="pending" - unaffected by this fix; the
        # existing pre-approval collection workflow is unchanged.
        _, records = _build(_valid_frame())
        assert len(records) == 2

    def test_approved_upload_is_never_silently_downgraded_to_pending(self):
        # A rejected approved-upload attempt must raise, not quietly
        # return a pending set instead.
        with pytest.raises(PopulationUploadValidationError):
            _build(
                _valid_frame(),
                approval_status="approved",
                approved_by="reviewer",
                approved_at="2026-09-13",
            )
