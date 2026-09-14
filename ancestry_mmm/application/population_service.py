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

import math
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple
from uuid import uuid4

import pandas as pd

from ancestry_mmm.core.population_reference import (
    PopulationReferenceRecord,
    PopulationReferenceSet,
    PopulationValidationIssue,
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

    When ``approval_status="approved"`` is passed directly (there is no
    separate, later approval stage in this call), duplicate approved
    references for the same ``(market_id, reference_year)`` also block
    creation - this repository has no subsequent step that would otherwise
    catch them. A ``"pending"`` upload (the default) is unaffected.
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
    for row_number, (_index, values) in enumerate(frame.iterrows(), start=1):
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
                reference_year_float = float(reference_year_raw)
                # Codex P2 (2026-09-13, fourth pass): check finiteness
                # deliberately, before rounding - round(inf) raises the
                # unrelated exception type OverflowError, which the
                # surrounding except (KeyError, TypeError, ValueError)
                # below did not catch, leaking a raw crash instead of the
                # documented, row-indexed PopulationUploadValidationError.
                if not math.isfinite(reference_year_float):
                    raise ValueError(
                        f"reference_year must be finite, got {reference_year_raw!r}"
                    )
                reference_year = int(round(reference_year_float))
                if reference_year != reference_year_float:
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
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            # OverflowError is caught defensively alongside the explicit
            # math.isfinite() check above - the deliberate check is what
            # identifies a non-finite reference_year, this is only a
            # backstop for any other row-processing overflow.
            #
            # Codex P2 (2026-09-14, seventh review pass): `row_number` is
            # a plain enumeration ordinal, not the DataFrame's own index
            # label - a caller-supplied DataFrame with a non-numeric
            # index (e.g. a string index) previously reached `index + 1`
            # here and raised a second, undocumented `TypeError` instead
            # of this method's documented `PopulationUploadValidationError`.
            # The DataFrame itself is never mutated (no index reset) to
            # get this numbering.
            raise PopulationUploadValidationError(
                f"Population upload row {row_number} is invalid: {exc}"
            ) from exc

    # Codex P2 (2026-09-13, third pass): a directly approved upload must
    # not be able to skip governed market resolution merely by omitting
    # known_market_ids - fail closed up front rather than silently
    # treating the omission as "no market check requested". Pending
    # uploads may still be collected before a governed market universe is
    # known (the existing, unchanged pre-approval workflow).
    if approval_status == "approved" and known_market_ids is None:
        raise PopulationUploadValidationError(
            "Population upload validation failed: approval_status='approved' "
            "requires known_market_ids to be supplied - a directly approved "
            "upload cannot skip governed market resolution."
        )

    # Codex P2 (2026-09-13, second pass): `validate_population_records`
    # always runs now, not only when `known_market_ids` is supplied -
    # duplicate-approved-year detection does not use `known_market_ids` at
    # all (it only groups approved records by (market_id, reference_year)),
    # so gating the whole call behind it wrongly skipped duplicate
    # detection whenever a caller omitted `known_market_ids`. Passing `()`
    # when it is `None` is safe: it makes every record "unresolved market"
    # by construction, but those issues are only ever escalated below when
    # `known_market_ids is not None` - the previous behaviour there is
    # unchanged.
    issues = validate_population_records(records, known_market_ids or ())
    blocking_issues: List[PopulationValidationIssue] = []
    if known_market_ids is not None:
        blocking_issues.extend(
            issue
            for issue in issues
            if "does not resolve to a governed market" in issue.reason
        )
    if approval_status == "approved":
        # There is no later approval stage in this path - a directly
        # approved upload's own duplicate-approved-year rows must block
        # here, never be waved through on the assumption a subsequent
        # review will catch them. A "pending" upload (the default) is
        # unaffected - its records are not yet approved, so this branch
        # never fires for it, preserving today's pending-upload behaviour.
        # (known_market_ids is guaranteed not None here - checked above.)
        blocking_issues.extend(
            issue
            for issue in issues
            if "duplicate approved population reference" in issue.reason
        )
    if blocking_issues:
        raise PopulationUploadValidationError(
            "Population upload validation failed: "
            + "; ".join(issue.reason for issue in blocking_issues)
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
