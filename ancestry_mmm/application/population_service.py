"""Application boundary for governed population-reference uploads
(`REQ-POPULATION-001`).

Mirrors `ancestry_mmm.application.fx_service.build_manual_fx_rate_set`
exactly: validate an analyst-supplied file strictly at upload time (any
malformed row aborts the whole upload, naming the offending row), never
supply a value the file didn't contain, and never activate anything -
this module only builds a `PopulationReferenceSet`/`PopulationReferenceRecord`
tuple; population treatment is a wholly separate, explicitly-saved decision
(`core.population_treatment.PopulationTreatmentSpecification`).

The approved minimal physical format (Part 5 v1.6 section 7.7) is five
columns: ``market``, ``population``, ``population_basis``,
``reference_year``, ``source``. Any other column present in the workbook
(e.g. a pasted supplementary detail table) is ignored, never guessed at.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple
from uuid import uuid4

import pandas as pd

from ancestry_mmm.core.population_reference import (
    PopulationReferenceRecord,
    PopulationReferenceSet,
    compute_population_records_fingerprint,
    validate_population_records,
)

_REQUIRED_COLUMNS = (
    "market",
    "population",
    "population_basis",
    "reference_year",
    "source",
)


class PopulationUploadValidationError(ValueError):
    """Raised when a population upload cannot become a governed reference set."""


def _read_upload(source: Any) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy()
    name = getattr(source, "name", None) or (
        str(source) if isinstance(source, Path) else None
    )
    if name and str(name).lower().endswith((".xlsx", ".xls", ".xlsm")):
        workbook = pd.ExcelFile(source)
        if len(workbook.sheet_names) > 1:
            raise PopulationUploadValidationError(
                "Population upload workbook contains multiple sheets. Sheets must "
                "not be combined silently - use a single-sheet workbook."
            )
        return pd.read_excel(workbook, sheet_name=workbook.sheet_names[0])
    if isinstance(source, (bytes, bytearray)):
        return pd.read_csv(BytesIO(bytes(source)))
    if isinstance(source, str):
        return pd.read_csv(StringIO(source))
    if isinstance(source, Path):
        return pd.read_csv(source)
    if hasattr(source, "read"):
        return pd.read_csv(source)
    raise PopulationUploadValidationError(
        "Population upload must be a DataFrame, CSV/XLSX path, text, bytes, or readable file."
    )


def build_population_reference_set(
    source: Any,
    *,
    reference_set_id: str,
    reference_set_version: int,
    name: str,
    source_name: str,
    owner: str,
    known_market_ids: Optional[Sequence[str]] = None,
    retrieved_at: Optional[str] = None,
    approval_status: str = "pending",
    approved_by: Optional[str] = None,
    approved_at: Optional[str] = None,
) -> Tuple[PopulationReferenceSet, List[PopulationReferenceRecord]]:
    """Validate an analyst-supplied population file and build its
    immutable reference set.

    Required columns are ``market``, ``population``, ``population_basis``,
    ``reference_year`` and ``source``. Every other column is ignored. The
    service rejects malformed rows, non-finite/non-positive population
    values, out-of-range years, and (when ``known_market_ids`` is
    supplied) markets the current project does not configure. Records are
    built with ``approval_status="pending"`` by default - saving them does
    not approve them, and building a set never activates population
    treatment (see `core.population_treatment`).
    """
    if not reference_set_id or not name or not source_name or not owner:
        raise PopulationUploadValidationError(
            "reference_set_id, name, source_name, and owner are required."
        )
    frame = _read_upload(source)
    missing = sorted(set(_REQUIRED_COLUMNS) - set(frame.columns))
    if missing:
        raise PopulationUploadValidationError(
            "Population upload is missing required column(s): " + ", ".join(missing)
        )
    if frame.empty:
        raise PopulationUploadValidationError("Population upload contains no rows.")

    records: List[PopulationReferenceRecord] = []
    for index, values in frame.iterrows():
        try:
            if pd.isna(values["market"]):
                raise ValueError("market is required")
            market_id = str(values["market"]).strip()
            if not market_id:
                raise ValueError("market is required")
            population_raw = values["population"]
            if pd.isna(population_raw):
                raise ValueError("population is required")
            population = float(population_raw)
            population_basis = str(values["population_basis"]).strip()
            reference_year_raw = values.get("reference_year")
            reference_year = None
            if not pd.isna(reference_year_raw):
                reference_year = int(round(float(reference_year_raw)))
                if reference_year != float(reference_year_raw):
                    raise ValueError(
                        f"reference_year must be an integral year, got {reference_year_raw!r}"
                    )
            if pd.isna(values["source"]):
                raise ValueError("source is required")
            row_source_name = str(values["source"]).strip()
            if not row_source_name:
                raise ValueError("source is required")

            records.append(
                PopulationReferenceRecord(
                    population_reference_id=str(uuid4()),
                    market_id=market_id,
                    population=population,
                    population_basis=population_basis,
                    source_name=row_source_name,
                    owner=owner,
                    reference_year=reference_year,
                    approval_status=approval_status,
                    approved_by=approved_by,
                    approved_at=approved_at,
                    created_at=retrieved_at or datetime.now(timezone.utc).isoformat(),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PopulationUploadValidationError(
                f"Population upload row {index + 1} is invalid: {exc}"
            ) from exc

    if known_market_ids is not None:
        issues = validate_population_records(records, known_market_ids)
        # Only the "unresolved market" class of issue is upload-blocking here;
        # duplicate-approved-year issues are re-checked at approval time, since
        # a fresh upload defaults every record to "pending".
        unresolved_market_issues = [
            issue
            for issue in issues
            if "does not resolve to a governed market" in issue.reason
        ]
        if unresolved_market_issues:
            raise PopulationUploadValidationError(
                "Population upload validation failed: "
                + "; ".join(issue.reason for issue in unresolved_market_issues)
            )

    records_fingerprint = compute_population_records_fingerprint(records)
    reference_set = PopulationReferenceSet(
        reference_set_id=reference_set_id,
        reference_set_version=reference_set_version,
        name=name,
        source_name=source_name,
        retrieved_at=retrieved_at or datetime.now(timezone.utc).isoformat(),
        records_fingerprint=records_fingerprint,
        approval_status=approval_status,
        approved_by=approved_by,
        approved_at=approved_at,
    )
    return reference_set, records
