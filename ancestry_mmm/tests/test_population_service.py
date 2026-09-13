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
