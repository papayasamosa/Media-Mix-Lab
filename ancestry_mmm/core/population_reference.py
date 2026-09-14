"""Governed country-level population reference data (`REQ-POPULATION-001`).

Population is a governed market-size reference, not an ordinary Context
variable and not the pre-existing purely-informational
`core.market_config.MarketDescriptors.population` scalar (which
`market_config.py` documents explicitly as unused downstream - this module
is a wholly separate concept with its own provenance, versioning and
approval state; the two are never merged).

Mirrors `core.fx_rates`'s established shape exactly (frozen dataclasses,
`__post_init__` validation, `to_dict`/`from_dict`, a `compute_*_fingerprint`
helper, and an immutable "new version on change" pattern mirroring
`core.coverage.SourceVersion`):

1. `PopulationReferenceRecord` - one approved market-population observation,
   supplied *by year* (`reference_year`), with basis, source, version and
   approval state (Part 5 v1.6 section 7.7).
2. `PopulationReferenceSet` - a versioned, immutable-once-used collection of
   records (mirrors `FXRateSet`).
3. `resolve_single_population_reference` - the *only* resolution rule
   currently approved (Part 5 v1.6 section 7.7 / Part 4 v1.8 section 15.6):
   a population-enabled model must resolve **exactly one** applicable
   approved reference per market; more than one is blocking, not an
   automatic pick.

What this module deliberately does NOT implement: any rule that maps a
specific model period/week to "its" year's population reference when a
market has more than one approved annual record. Part 5 v1.6's `DD-020`
("market-population reference source and period policy") leaves open
"whether one annual, midpoint, model-period-average or another approved
reference period is used for each fit" - this is a real, currently
unresolved decision, not a coding gap. See
`docs/population_reference_period_policy_decision.md`. Ingesting and
storing multiple annual records per market is unambiguous and implemented
here; *selecting among them automatically* is not.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple, cast

POPULATION_REFERENCE_SCHEMA_VERSION = 1

# Part 5 v1.6 section 7.7 / Part 3 v1.13: total resident population is the
# only currently approved basis. A media audience universe (e.g. "Adults
# 18+", "ABC1 Adults 45+") must never be substituted for it.
POPULATION_BASIS_TOTAL_RESIDENT_POPULATION = "total_resident_population"

POPULATION_BASES = (POPULATION_BASIS_TOTAL_RESIDENT_POPULATION,)

_MIN_PLAUSIBLE_YEAR = 1900
_MAX_PLAUSIBLE_YEAR = 2200

APPROVAL_STATUSES = ("pending", "approved", "rejected")


@dataclass(frozen=True)
class PopulationReferenceRecord:
    """One approved market-population observation (Part 5 v1.6 section 7.7
    `dim_market_population_reference`). Population is reference data keyed
    to market identity, not an ordinary weekly control series."""

    population_reference_id: str
    market_id: str
    population: float
    population_basis: str
    source_name: str
    owner: str
    reference_year: Optional[int] = None
    reference_period_start: Optional[str] = None
    reference_period_end: Optional[str] = None
    as_of_date: Optional[str] = None
    source_version_id: Optional[str] = None
    source_reference: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    approval_status: str = "pending"
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    created_at: Optional[str] = None
    schema_version: int = POPULATION_REFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.population_reference_id, str)
            or not self.population_reference_id
        ):
            # Codex P2 (2026-09-13, fourth pass): a truthiness-only check
            # let a non-string id (list/dict/int from a malformed imported
            # JSON record) through construction; it then crashed later,
            # uncaught, inside compute_population_records_fingerprint's
            # sorted() - which mixes str/non-str keys - rather than being
            # quarantined here at the domain boundary where the import
            # resolver's existing except (..., ValueError, ...) already
            # catches it. Fail here, at construction, not at the sort site.
            raise ValueError(
                "PopulationReferenceRecord requires a non-empty string "
                f"population_reference_id, got {self.population_reference_id!r} "
                f"({type(self.population_reference_id).__name__})."
            )
        if not isinstance(self.market_id, str) or not self.market_id:
            # Codex P2 (2026-09-13, fifth pass): same principle as
            # population_reference_id above - a truthiness-only check let
            # a non-string market_id (e.g. a JSON array `["UK"]`) through
            # construction. It then crashed later, uncaught, in
            # validate_population_records's set-membership test
            # (`record.market_id not in known`) and its `(market_id,
            # reference_year)` dict key, both of which require market_id
            # to be hashable. Fail here, at construction, so the record is
            # quarantined by the existing import-quarantine mechanism
            # instead of crashing validation.
            raise ValueError(
                "PopulationReferenceRecord requires a non-empty string market_id, "
                f"got {self.market_id!r} ({type(self.market_id).__name__})."
            )
        if not self.source_name:
            raise ValueError("PopulationReferenceRecord requires a source_name.")
        if not self.owner:
            raise ValueError("PopulationReferenceRecord requires an owner.")
        if not isinstance(self.population, (int, float)) or isinstance(
            self.population, bool
        ):
            raise ValueError(
                "PopulationReferenceRecord.population must be numeric, got "
                f"{type(self.population).__name__}."
            )
        if not math.isfinite(self.population):
            raise ValueError("PopulationReferenceRecord.population must be finite.")
        if self.population <= 0:
            raise ValueError(
                "PopulationReferenceRecord.population must be strictly positive."
            )
        if self.population_basis not in POPULATION_BASES:
            raise ValueError(
                f"PopulationReferenceRecord: unknown population_basis "
                f"{self.population_basis!r} (expected one of {POPULATION_BASES})."
            )
        if self.reference_year is not None:
            if isinstance(self.reference_year, bool) or not isinstance(
                self.reference_year, int
            ):
                raise ValueError(
                    "PopulationReferenceRecord.reference_year must be an integer year, got "
                    f"{self.reference_year!r}."
                )
            if not (_MIN_PLAUSIBLE_YEAR <= self.reference_year <= _MAX_PLAUSIBLE_YEAR):
                raise ValueError(
                    "PopulationReferenceRecord.reference_year "
                    f"{self.reference_year!r} is outside the plausible range "
                    f"[{_MIN_PLAUSIBLE_YEAR}, {_MAX_PLAUSIBLE_YEAR}]."
                )
        if self.approval_status not in APPROVAL_STATUSES:
            raise ValueError(
                f"PopulationReferenceRecord: unknown approval_status {self.approval_status!r} "
                f"(expected one of {APPROVAL_STATUSES})."
            )
        if self.approval_status == "approved" and not (
            self.approved_by and self.approved_at
        ):
            raise ValueError(
                "PopulationReferenceRecord: approval_status='approved' requires "
                "approved_by and approved_at."
            )
        if self.approval_status != "approved" and (
            self.approved_by or self.approved_at
        ):
            # Codex P2 (2026-09-13, third pass): the reverse of the check
            # above - a pending/rejected record must not carry stale
            # approver metadata that contradicts its own status. Exported
            # audit metadata must never claim an approval its status
            # doesn't hold.
            raise ValueError(
                "PopulationReferenceRecord: approved_by/approved_at must not be "
                f"set when approval_status={self.approval_status!r} (only "
                "'approved' records may carry approver metadata)."
            )
        if self.schema_version != POPULATION_REFERENCE_SCHEMA_VERSION:
            raise ValueError(
                "PopulationReferenceRecord: unsupported schema_version "
                f"{self.schema_version!r}; this build only understands "
                f"{POPULATION_REFERENCE_SCHEMA_VERSION} (mirrors `core.curve_"
                "artifact`/`core.prefit_run`'s exact-match schema-version "
                "convention - an omitted value defaults to the current "
                "version via the dataclass field default, but an explicitly "
                "supplied future, zero, or malformed version must fail "
                "closed here rather than being silently accepted)."
            )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> "PopulationReferenceRecord":
        known = set(cls.__dataclass_fields__)
        return cls(**cast(Any, {k: v for k, v in values.items() if k in known}))


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def compute_population_records_fingerprint(
    records: Sequence[PopulationReferenceRecord],
) -> str:
    """The single sanctioned way to compute a `PopulationReferenceSet.
    records_fingerprint` - mirrors `core.fx_rates.compute_records_
    fingerprint` exactly, never reimplemented by callers."""
    payload = [
        record.to_dict()
        for record in sorted(records, key=lambda r: r.population_reference_id)
    ]
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PopulationReferenceSet:
    """A versioned, immutable-once-used collection of
    `PopulationReferenceRecord`s. Mirrors `core.fx_rates.FXRateSet`'s
    "immutable identity, new version on change" pattern: a refreshed or
    corrected upload must create a new `PopulationReferenceSet` (new
    `reference_set_version`, new `records_fingerprint`), never mutate an
    in-use set in place."""

    reference_set_id: str
    reference_set_version: int
    name: str
    source_name: str
    retrieved_at: str
    records_fingerprint: str
    approval_status: str = "pending"
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    schema_version: int = POPULATION_REFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.reference_set_id, str) or not self.reference_set_id:
            # 2026-09-14: same principle as PopulationReferenceRecord's
            # population_reference_id/market_id fixes - the field is
            # declared `reference_set_id: str` above, but a truthiness-
            # only check let a non-string value (e.g. a JSON array) through
            # silently. This is the object's own governed identity field,
            # not ordinary descriptive metadata.
            raise ValueError(
                "PopulationReferenceSet requires a non-empty string "
                f"reference_set_id, got {self.reference_set_id!r} "
                f"({type(self.reference_set_id).__name__})."
            )
        if self.reference_set_version < 1:
            raise ValueError(
                "PopulationReferenceSet.reference_set_version must be >= 1."
            )
        if len(self.records_fingerprint) != 64:
            raise ValueError(
                "PopulationReferenceSet.records_fingerprint must be a "
                "64-character sha256 hex digest."
            )
        if self.approval_status not in APPROVAL_STATUSES:
            raise ValueError(
                f"PopulationReferenceSet: unknown approval_status {self.approval_status!r}."
            )
        if self.approval_status == "approved" and not (
            self.approved_by and self.approved_at
        ):
            raise ValueError(
                "PopulationReferenceSet: approval_status='approved' requires "
                "approved_by and approved_at."
            )
        if self.approval_status != "approved" and (
            self.approved_by or self.approved_at
        ):
            raise ValueError(
                "PopulationReferenceSet: approved_by/approved_at must not be set "
                f"when approval_status={self.approval_status!r} (only 'approved' "
                "sets may carry approver metadata)."
            )
        if self.schema_version != POPULATION_REFERENCE_SCHEMA_VERSION:
            raise ValueError(
                "PopulationReferenceSet: unsupported schema_version "
                f"{self.schema_version!r}; this build only understands "
                f"{POPULATION_REFERENCE_SCHEMA_VERSION}."
            )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> "PopulationReferenceSet":
        known = set(cls.__dataclass_fields__)
        return cls(**cast(Any, {k: v for k, v in values.items() if k in known}))


def new_reference_set_version(
    reference_set: PopulationReferenceSet, **changes: Any
) -> PopulationReferenceSet:
    """Apply an edit to a reference set as a new version - never an
    in-place mutation of a set that may already be in use (`reference_
    set` itself is returned unchanged; only a new object is built).

    Codex P2 (2026-09-13, third pass): approval belongs to the exact
    governed version/content that was reviewed - it must never carry
    forward automatically onto a new version. No equivalent existing
    versioning helper in this repository (e.g. `core.fx_rates.new_rate_
    set_version`) resets approval either, so this is a deliberate,
    stricter invariant for population data rather than a mirrored
    pattern: every call defaults the new version to `approval_status=
    "pending"` with `approved_by`/`approved_at` cleared, *unless the
    caller explicitly supplies all three of those fields together in
    this exact call* - there is no route by which the previous version's
    approver metadata is silently reused. A genuine reapproval of new
    content remains possible, but only as that explicit action, never as
    a side effect of omitting approval fields while changing something
    else (such as `records_fingerprint`)."""
    from dataclasses import replace

    for locked_field in ("reference_set_id", "reference_set_version"):
        if locked_field in changes:
            raise ValueError(
                f"{locked_field!r} is lineage/version identity and cannot "
                "be set via new_reference_set_version."
            )
    changes.setdefault("approval_status", "pending")
    changes.setdefault("approved_by", None)
    changes.setdefault("approved_at", None)
    return replace(
        reference_set,
        reference_set_version=reference_set.reference_set_version + 1,
        **changes,
    )


@dataclass(frozen=True)
class PopulationValidationIssue:
    """One quarantine/validation finding against a candidate population
    record - never a silent drop."""

    population_reference_id: str
    reason: str


def validate_population_records(
    records: Sequence[PopulationReferenceRecord],
    known_market_ids: Sequence[str],
) -> Tuple[PopulationValidationIssue, ...]:
    """Cross-record validation beyond each record's own `__post_init__`
    (Part 5 v1.6 section 7.7 / Part 4 v1.8 section 15.6):

    - `market_id` must resolve to a market the current project actually
      configures (governed market identity, never free-text matching);
    - duplicate *applicable* (approved) records for the same
      `(market_id, reference_year)` are blocking until resolved - never
      silently averaged, summed or last-write-wins.

    Returns an empty tuple when nothing is wrong. Never raises for a data
    problem - callers decide whether an issue blocks their specific use."""
    issues: list[PopulationValidationIssue] = []
    known = set(known_market_ids)
    seen_market_year: dict[Tuple[str, Optional[int]], list[str]] = {}
    for record in records:
        if record.market_id not in known:
            issues.append(
                PopulationValidationIssue(
                    population_reference_id=record.population_reference_id,
                    reason=(
                        f"market_id {record.market_id!r} does not resolve to a "
                        "governed market configured for this project."
                    ),
                )
            )
        if record.approval_status == "approved":
            key = (record.market_id, record.reference_year)
            seen_market_year.setdefault(key, []).append(record.population_reference_id)

    for (market_id, reference_year), ids in seen_market_year.items():
        if len(ids) > 1:
            for population_reference_id in ids:
                issues.append(
                    PopulationValidationIssue(
                        population_reference_id=population_reference_id,
                        reason=(
                            f"duplicate approved population reference for market "
                            f"{market_id!r}, reference_year={reference_year!r}: "
                            f"{sorted(ids)} all apply - blocking until resolved."
                        ),
                    )
                )
    return tuple(issues)


class AmbiguousPopulationReferenceError(ValueError):
    """Raised when a market has more than one applicable approved
    population reference and no approved reference-set rule exists to
    choose among them (Part 5 v1.6 `DD-020` - unresolved)."""


def resolve_single_population_reference(
    market_id: str,
    records: Sequence[PopulationReferenceRecord],
) -> Optional[PopulationReferenceRecord]:
    """The only population-reference resolution rule currently approved
    (Part 5 v1.6 section 7.7, Part 4 v1.8 section 15.6): a population-
    enabled model must resolve *exactly one* applicable approved reference
    per included market.

    - zero applicable approved records for `market_id` -> returns `None`
      (fail closed; callers must block population treatment for this
      market rather than default to anything);
    - exactly one -> returns it;
    - more than one -> raises `AmbiguousPopulationReferenceError`. This is
      not a bug to silently work around: which of several annual records
      to use is exactly Part 5 v1.6's open `DD-020` decision (one annual,
      midpoint, model-period-average, or another policy). This function
      must never guess (e.g. "latest year") on that open decision's
      behalf - see `docs/population_reference_period_policy_decision.md`.
    """
    applicable = [
        record
        for record in records
        if record.market_id == market_id and record.approval_status == "approved"
    ]
    if not applicable:
        return None
    if len(applicable) > 1:
        ids = sorted(record.population_reference_id for record in applicable)
        raise AmbiguousPopulationReferenceError(
            f"market {market_id!r} has {len(applicable)} applicable approved "
            f"population references ({ids}) and no approved reference-set "
            "rule exists to select among them (Part 5 v1.6 DD-020 is "
            "unresolved) - resolve to exactly one approved reference before "
            "enabling population treatment for this market."
        )
    return applicable[0]
