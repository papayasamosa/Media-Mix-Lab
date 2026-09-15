"""Governed named-event adoption boundary (Work Package 1 of
`Media-Mix-Lab: Coding LLM Next Steps Post PR #297`, `REQ-EVENT-001`;
extended by the event-upload-contract implementation brief for the
preferred seven-column source contract and automatic type-policy
adoption).

Connects the optional Context `events` source table to the governed
named-event registry (`core.named_events`) and the project lifecycle -
without implementing any event-response mathematics beyond the approved
automatic policy resolution in `core.named_event_type_policy`.

Two source contracts are supported:

- **Legacy (four columns)**: `event_id`/`event_name`/`start_date`/
  `end_date` only. Market scope, source lineage and the optional family
  link must be analyst-supplied at this boundary (`adopt_source_event_
  occurrence`, `missing_occurrence_adoption_fields`) - never invented.
- **Preferred (seven columns, `data.templates.EVENT_UPLOAD_COLUMNS`)**:
  adds `event_family_id`, `event_type` and `market` as explicit source
  columns, enabling automatic bulk adoption (`bulk_adopt_preferred_event_
  rows`) - the row itself now supplies the governance metadata that the
  legacy path requires the analyst to retype. `event_type` resolves to a
  family classification and an automatic `EventResponseDefinition`
  through `core.named_event_type_policy`'s explicit, non-text-inferring
  resolver only.

Contract invariants (both paths):

- an uploaded Context events row never becomes a governed occurrence
  automatically without an explicit adoption call (a single-row call for
  the legacy path, a bulk call the analyst triggers for the preferred
  path - never a background/implicit action);
- the factual interval (`start_date`/`end_date`) is preserved verbatim -
  never shifted;
- event-family classification, temporal treatment and lead/lag support
  are **never** inferred from `event_name` free text - only from the
  explicit `event_type` source column (preferred path) or explicit
  analyst input (legacy path);
- the registry is immutable and lineage-versioned; every edit is a new
  version, never an in-place mutation;
- response definitions reference a registered family and use exactly
  the closed four-value temporal-treatment vocabulary;
- nothing in this service computes event-relative features itself; it
  only registers the governed `transformation_method_reference` that
  `core.named_event_fit_inputs` later consumes at fit time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, TypeVar

import pandas as pd

from ancestry_mmm.core.named_event_response import NAMED_EVENT_RESPONSE_STRUCTURE
from ancestry_mmm.core.named_event_type_policy import (
    CLASSIFICATION_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED,
    CLASSIFICATION_STATUS_RESPONSE_POLICY_REQUIRED,
    EVENT_TYPE_PROMOTION,
    EventTypeResponsePolicy,
    default_response_definition_id,
    normalise_event_type,
    resolve_event_type_policy,
    resolve_family_classification,
)
from ancestry_mmm.core.named_events import (
    DEFAULT_EVENT_EVIDENCE_STATUS,
    EVENT_REGISTRY_SCHEMA_VERSION,
    EventResponseDefinition,
    NamedEventFamily,
    NamedEventOccurrence,
    current_family_versions,
    current_occurrence_versions,
    current_response_definition_versions,
    new_family_version,
    new_occurrence_version,
    new_response_definition_version,
    validate_registry_references,
)
from ancestry_mmm.data.templates import EVENT_UPLOAD_COLUMNS

# Source-row columns the standard Context `events` template carries
# (legacy four-column contract).
_SOURCE_ROW_COLUMNS = ("event_id", "event_name", "start_date", "end_date")

# Occurrence fields a raw legacy source events row can never supply by
# itself. They are required by the record contract and must be
# analyst-supplied at this boundary - never invented, defaulted, or
# zero-filled.
ANALYST_REQUIRED_FIELDS = ("market", "source_id")


def missing_occurrence_adoption_fields(
    row: Mapping[str, Any], analyst_input: Mapping[str, Any]
) -> Tuple[str, ...]:
    """The field names that still block adopting `row` into a full
    `NamedEventOccurrence`. Source-row-derived fields are checked against
    the row itself; the remaining required fields against the analyst's
    input. Never returns a fabricated default as if it were supplied."""
    missing = []
    for column in _SOURCE_ROW_COLUMNS:
        if not row.get(column):
            missing.append(column)
    for field in ANALYST_REQUIRED_FIELDS:
        if not analyst_input.get(field):
            missing.append(field)
    return tuple(missing)


def adopt_source_event_occurrence(
    row: Mapping[str, Any],
    analyst_input: Mapping[str, Any],
) -> NamedEventOccurrence:
    """Adopt one Context events row into a governed, version-1
    `NamedEventOccurrence`. Raises `ValueError` listing every missing
    required field - the row is never adopted with a fabricated value.

    The source row supplies identity and the factual interval only.
    `event_name` becomes the free-text `display_name`; it is never used
    to derive classification, treatment or support - no such derivation
    exists anywhere in this module."""
    missing = missing_occurrence_adoption_fields(row, analyst_input)
    if missing:
        raise ValueError(
            "Cannot adopt this event occurrence row - missing required "
            f"field(s): {', '.join(missing)}."
        )
    family_id = analyst_input.get("family_id") or None
    return NamedEventOccurrence(
        event_id=str(row["event_id"]),
        event_version=1,
        display_name=str(row["event_name"]),
        start_date=str(row["start_date"]),
        end_date=str(row["end_date"]),
        market_scope=tuple(str(m) for m in analyst_input["market"]),
        source_id=str(analyst_input["source_id"]),
        source_version=(
            int(analyst_input["source_version"])
            if analyst_input.get("source_version") is not None
            else None
        ),
        family_id=family_id,
    )


def new_family(
    *,
    family_id: str,
    display_name: str,
    classification: str,
    market_scope: Sequence[str] = (),
    product_scope: Sequence[str] = (),
    outcome_scope: Sequence[str] = (),
    classification_status: str = DEFAULT_EVENT_EVIDENCE_STATUS,
    metadata: Optional[Mapping[str, Any]] = None,
) -> NamedEventFamily:
    """Construct a governed, version-1 event family. `classification` is
    the analyst-supplied governed classification - this function never
    derives it from `display_name` or any other text."""
    return NamedEventFamily(
        family_id=str(family_id),
        family_version=1,
        display_name=str(display_name),
        classification=str(classification),
        classification_status=str(classification_status),
        market_scope=tuple(market_scope),
        product_scope=tuple(product_scope),
        outcome_scope=tuple(outcome_scope),
        metadata=dict(metadata or {}),
    )


def new_response_definition(
    *,
    response_definition_id: str,
    family_id: str,
    treatment: str,
    max_lead: int,
    max_lag: int,
    transformation_method_reference: str,
    market_scope: Sequence[str] = (),
    product_scope: Sequence[str] = (),
    outcome_scope: Sequence[str] = (),
    evidence_status: str = DEFAULT_EVENT_EVIDENCE_STATUS,
    metadata: Optional[Mapping[str, Any]] = None,
) -> EventResponseDefinition:
    """Construct a governed, version-1 response definition. `treatment`
    must be one of the closed four-value vocabulary (validated by the
    record); the transformation-method reference is an opaque governed
    string - no kernel is selected here."""
    return EventResponseDefinition(
        response_definition_id=str(response_definition_id),
        response_definition_version=1,
        family_id=str(family_id),
        treatment=str(treatment),
        max_lead=int(max_lead),
        max_lag=int(max_lag),
        transformation_method_reference=str(transformation_method_reference),
        market_scope=tuple(market_scope),
        product_scope=tuple(product_scope),
        outcome_scope=tuple(outcome_scope),
        evidence_status=str(evidence_status),
        metadata=dict(metadata or {}),
    )


def register_family(
    records: Sequence[NamedEventFamily], record: NamedEventFamily
) -> Tuple[NamedEventFamily, ...]:
    """Append a family to the registry. Re-registering content identical
    (version ignored) to the current version is an idempotent no-op;
    differing content raises - the registry is immutable, so an edit is a
    new version via `new_registered_family_version`, never a mutation."""
    return _register(
        records, record, "family_id", "family_version", current_family_versions
    )


def register_occurrence(
    records: Sequence[NamedEventOccurrence], record: NamedEventOccurrence
) -> Tuple[NamedEventOccurrence, ...]:
    """Append an occurrence to the registry (immutability contract
    identical to `register_family`)."""
    return _register(
        records, record, "event_id", "event_version", current_occurrence_versions
    )


def register_response_definition(
    records: Sequence[EventResponseDefinition], record: EventResponseDefinition
) -> Tuple[EventResponseDefinition, ...]:
    """Append a response definition to the registry (immutability
    contract identical to `register_family`)."""
    return _register(
        records,
        record,
        "response_definition_id",
        "response_definition_version",
        current_response_definition_versions,
    )


_RecordT = TypeVar("_RecordT")


def _register(
    records: Sequence[_RecordT],
    record: _RecordT,
    id_field: str,
    version_field: str,
    current_fn: Any,
) -> Tuple[_RecordT, ...]:
    current = {getattr(rec, id_field): rec for rec in current_fn(records)}
    existing = current.get(getattr(record, id_field))
    if existing is not None:
        existing_dict = dict(getattr(existing, "to_dict")())
        incoming_dict = dict(getattr(record, "to_dict")())
        existing_dict.pop(version_field, None)
        incoming_dict.pop(version_field, None)
        if existing_dict == incoming_dict:
            return tuple(records)
        raise ValueError(
            f"{getattr(record, id_field)!r} is already registered with "
            "different content - create a new version instead of mutating "
            "the registry."
        )
    return tuple(records) + (record,)


def new_registered_family_version(
    records: Sequence[NamedEventFamily], family_id: str, **changes: Any
) -> Tuple[NamedEventFamily, ...]:
    current = {rec.family_id: rec for rec in current_family_versions(records)}
    if family_id not in current:
        raise ValueError(
            f"Family {family_id!r} is not registered - register it before "
            "creating a new version."
        )
    return tuple(records) + (new_family_version(current[family_id], **changes),)


def new_registered_occurrence_version(
    records: Sequence[NamedEventOccurrence], event_id: str, **changes: Any
) -> Tuple[NamedEventOccurrence, ...]:
    current = {rec.event_id: rec for rec in current_occurrence_versions(records)}
    if event_id not in current:
        raise ValueError(
            f"Occurrence {event_id!r} is not registered - adopt it before "
            "creating a new version."
        )
    return tuple(records) + (new_occurrence_version(current[event_id], **changes),)


def new_registered_response_definition_version(
    records: Sequence[EventResponseDefinition],
    response_definition_id: str,
    **changes: Any,
) -> Tuple[EventResponseDefinition, ...]:
    current = {
        rec.response_definition_id: rec
        for rec in current_response_definition_versions(records)
    }
    if response_definition_id not in current:
        raise ValueError(
            f"Response definition {response_definition_id!r} is not "
            "registered - register it before creating a new version."
        )
    return tuple(records) + (
        new_response_definition_version(current[response_definition_id], **changes),
    )


def registry_problems(
    families: Sequence[NamedEventFamily],
    occurrences: Sequence[NamedEventOccurrence],
    definitions: Sequence[EventResponseDefinition],
) -> Tuple[str, ...]:
    """Reference-validation problems across the registry (empty tuple =
    no problems). A response definition must reference a registered
    family; an occurrence's family link, if set, must too."""
    return validate_registry_references(families, occurrences, definitions)


def registry_to_dict(
    families: Sequence[NamedEventFamily],
    occurrences: Sequence[NamedEventOccurrence],
    definitions: Sequence[EventResponseDefinition],
) -> dict:
    """Serialise the full registry for project export - one stable dict
    with its own record-level `schema_version` so an importer can reject
    an unrecognised future schema instead of guessing."""
    return {
        "schema_version": EVENT_REGISTRY_SCHEMA_VERSION,
        "families": [rec.to_dict() for rec in families],
        "occurrences": [rec.to_dict() for rec in occurrences],
        "response_definitions": [rec.to_dict() for rec in definitions],
    }


def registry_has_content(
    families: Sequence[NamedEventFamily],
    occurrences: Sequence[NamedEventOccurrence],
    definitions: Sequence[EventResponseDefinition],
) -> bool:
    """Whether any part of the registry is non-empty - exporters use this
    to decide whether to write the registry file at all, keeping older
    bundles byte-comparable."""
    return bool(families or occurrences or definitions)


# --- Preferred seven-column source contract (implementation brief) --------


def _is_blank_preferred_value(value: Any) -> bool:
    """True for anything that must never be adopted as a governed field
    value: `None`, a pandas/NumPy null (`NaN`/`NaT` - a spreadsheet cell
    pandas leaves empty, whose Python truth value is `True`, is exactly
    the case `if not row.get(column)` used to miss), or a whitespace-only
    string. Never raises on a scalar; `pd.isna` on a non-scalar (a list-
    like accidentally stored in a cell) raises `ValueError`, which is
    treated as "not a blank scalar" rather than propagated - this
    function's job is null-detection, not shape validation."""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, str) and not value.strip():
        return True
    return False


def missing_preferred_row_fields(row: Mapping[str, Any]) -> Tuple[str, ...]:
    """The `data.templates.EVENT_UPLOAD_COLUMNS` fields still blank on
    `row` - including a pandas/NumPy null (`NaN`/`NaT`), never just a
    falsey Python value, so a genuinely missing cell can never be adopted
    as the literal governed string `"nan"`/`"NaT"`. An empty result does
    not by itself mean the row is adoptable - `end_date >= start_date`
    and family/event_type consistency are checked separately, at
    adoption time, so a single bad row never masks the reason another row
    in the same batch failed."""
    return tuple(
        column
        for column in EVENT_UPLOAD_COLUMNS
        if _is_blank_preferred_value(row.get(column))
    )


def is_preferred_source_row(row: Mapping[str, Any]) -> bool:
    """True when `row` supplies the full seven-column preferred contract
    (`event_family_id`, `event_type` and `market` all present) rather
    than only the legacy four columns, which still require manual
    analyst completion via `adopt_source_event_occurrence`."""
    return not missing_preferred_row_fields(row)


@dataclass(frozen=True)
class RowAdoptionResult:
    """The outcome of attempting to adopt one preferred-contract source
    row within a `bulk_adopt_preferred_event_rows` call."""

    event_id: str
    adopted: bool
    problems: Tuple[str, ...] = ()
    created_family: bool = False
    created_response_definition: bool = False
    response_policy_required: bool = False


@dataclass(frozen=True)
class BulkAdoptionOutcome:
    """The registry state after a `bulk_adopt_preferred_event_rows` call,
    plus a per-row report. `families`/`occurrences`/`response_definitions`
    already include every successfully adopted row - callers persist
    these directly, mirroring the single-row adoption functions above."""

    families: Tuple[NamedEventFamily, ...]
    occurrences: Tuple[NamedEventOccurrence, ...]
    response_definitions: Tuple[EventResponseDefinition, ...]
    results: Tuple[RowAdoptionResult, ...] = ()

    @property
    def adopted_count(self) -> int:
        return sum(1 for result in self.results if result.adopted)


def _normalised_type_label(event_type: Any) -> str:
    canonical = normalise_event_type(
        event_type if isinstance(event_type, str) else None
    )
    if canonical is not None:
        return canonical
    return str(event_type).strip().lower() if isinstance(event_type, str) else ""


def _conflicting_batch_families(
    rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Tuple[str, ...]]:
    """`event_family_id` values for which this batch itself supplies more
    than one distinct `event_type` label (after alias/case normalisation)
    - implementation brief section 5.1: "if source rows for the same
    family disagree on event_type, block adoption and explain the
    conflict." Rows with a blank `event_family_id` are not considered
    here; `missing_preferred_row_fields` already reports those."""
    labels_by_family: Dict[str, set] = {}
    for row in rows:
        family_id = row.get("event_family_id")
        event_type = row.get("event_type")
        if not family_id or not event_type:
            continue
        labels_by_family.setdefault(str(family_id), set()).add(
            _normalised_type_label(event_type)
        )
    return {
        family_id: tuple(sorted(labels))
        for family_id, labels in labels_by_family.items()
        if len(labels) > 1
    }


def _response_definition_matches_policy(
    definition: EventResponseDefinition, policy: EventTypeResponsePolicy
) -> bool:
    """Whether `definition` (an existing, current, opted-in response
    definition for a family) is fit-compatible with the automatic
    `event_type` policy for a new row - compared on the actual
    fit-relevant fields (`core.named_event_fit_inputs` consumes exactly
    these plus the transformation reference, never the definition's own
    id), never on `response_definition_id` equality."""
    return (
        definition.treatment == policy.treatment
        and definition.max_lead == policy.max_lead
        and definition.max_lag == policy.max_lag
        and definition.transformation_method_reference
        == policy.transformation_method_reference
    )


def bulk_adopt_preferred_event_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    source_id: str,
    source_version: Optional[int],
    families: Sequence[NamedEventFamily],
    occurrences: Sequence[NamedEventOccurrence],
    response_definitions: Sequence[EventResponseDefinition],
) -> BulkAdoptionOutcome:
    """Adopt every valid preferred-contract row in `rows` in one governed
    pass (implementation brief section 5: "provide a practical bulk-adopt
    path for valid rows"). For each row this may:

    1. register a new `NamedEventFamily` (`event_family_id` not yet
       registered) - classification resolved from `event_type` via
       `core.named_event_type_policy`, or marked `response_policy_
       required` when `event_type` has no automatic policy (brief
       section 6.2: an unsupported type is retained as governed metadata
       but never silently opted into fitting);
    2. verify an already-registered family's classification is
       compatible with this row's resolved classification - a genuine
       mismatch blocks that row rather than silently reclassifying the
       family (section 5.1). An unresolvable `event_type` is also
       blocked here if the family already has a current opted-in (fitted)
       response definition - joining would otherwise let the occurrence
       be silently fitted through that existing family-level definition
       with no governed classification of its own;
    3. register the `NamedEventOccurrence` (factual dates preserved
       verbatim);
    4. register or reuse the family's response definition when
       `event_type` resolves to an automatic policy - reuse is decided by
       inspecting every current, opted-in response definition already
       registered for the family (never by `response_definition_id`
       equality with the deterministic default id alone): exactly one
       fit-compatible definition is reused as-is (repeated yearly rows
       for the same family never create a second one); a materially
       conflicting definition, or more than one already-current opted-in
       definition for the family, blocks the row instead of ever creating
       a second opted-in definition for the same family (which would
       otherwise produce two fit blocks - and a duplicate
       `event_coefs_<family>_<market>` PyMC variable - for one family/
       market at fit time).

    A row that fails validation, a within-batch family/event_type
    conflict, or a genuine cross-registration conflict is skipped with an
    explanatory `RowAdoptionResult` - it never raises and never blocks
    unrelated rows in the same batch.

    **Row atomicity**: each row's family/occurrence/response-definition
    work is staged against local candidate copies of the registries and
    committed back to the authoritative `current_families`/
    `current_occurrences`/`current_definitions` lists only once every step
    for that row has succeeded. A row reported as `adopted=False` -
    whatever stage it failed at - therefore leaves no trace in the
    returned registries; a previously committed row in the same batch is
    never affected by a later row's failure.
    """
    current_families: List[NamedEventFamily] = list(families)
    current_occurrences: List[NamedEventOccurrence] = list(occurrences)
    current_definitions: List[EventResponseDefinition] = list(response_definitions)
    conflicted_families = _conflicting_batch_families(rows)
    results: List[RowAdoptionResult] = []

    for row in rows:
        _raw_event_id = row.get("event_id")
        event_id = (
            "(missing event_id)"
            if _is_blank_preferred_value(_raw_event_id)
            else str(_raw_event_id)
        )

        missing = missing_preferred_row_fields(row)
        if missing:
            results.append(
                RowAdoptionResult(
                    event_id=event_id,
                    adopted=False,
                    problems=(f"missing required field(s): {', '.join(missing)}",),
                )
            )
            continue

        family_id = str(row["event_family_id"])
        if family_id in conflicted_families:
            results.append(
                RowAdoptionResult(
                    event_id=event_id,
                    adopted=False,
                    problems=(
                        f"event_family_id {family_id!r} has conflicting event_type "
                        f"values across the uploaded rows ({conflicted_families[family_id]!r})"
                        " - resolve the conflict before adopting.",
                    ),
                )
            )
            continue

        # Classification (governed metadata: what kind of family this is)
        # and automatic response-definition policy (whether an
        # EventResponseDefinition can be auto-created) are resolved
        # separately - `event_type="promotion"` resolves a real
        # classification ("promotional") but currently has no automatic
        # response policy (see `core.named_event_type_policy` module
        # docstring), which must not collapse it into "unsupported type".
        resolved_classification = resolve_family_classification(row["event_type"])
        policy = resolve_event_type_policy(row["event_type"])
        existing_family = next(
            (
                f
                for f in current_family_versions(current_families)
                if f.family_id == family_id
            ),
            None,
        )

        # Stage this row's mutations against candidate copies of the
        # authoritative registries - only committed back to
        # current_families/current_occurrences/current_definitions once
        # every step below succeeds (row atomicity, see docstring).
        candidate_families = list(current_families)
        candidate_occurrences = list(current_occurrences)
        candidate_definitions = list(current_definitions)

        created_family = False
        response_policy_required = policy is None
        if existing_family is None:
            if policy is not None:
                classification_status = DEFAULT_EVENT_EVIDENCE_STATUS
            elif normalise_event_type(row["event_type"]) == EVENT_TYPE_PROMOTION:
                # A recognised, classified type ("promotional") with a
                # disclosed, decision-required statistical-method gap -
                # not merely "unsupported event_type". See `docs/
                # named_event_promotional_window_decision_package.md`.
                classification_status = (
                    CLASSIFICATION_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED
                )
            else:
                classification_status = CLASSIFICATION_STATUS_RESPONSE_POLICY_REQUIRED
            family_record = new_family(
                family_id=family_id,
                display_name=str(row["event_name"]),
                classification=resolved_classification or str(row["event_type"]),
                classification_status=classification_status,
            )
            candidate_families = list(
                register_family(candidate_families, family_record)
            )
            created_family = True
        else:
            has_fitted_definition = any(
                d.family_id == family_id
                and d.transformation_method_reference == NAMED_EVENT_RESPONSE_STRUCTURE
                for d in current_response_definition_versions(candidate_definitions)
            )
            if resolved_classification is None:
                if has_fitted_definition:
                    results.append(
                        RowAdoptionResult(
                            event_id=event_id,
                            adopted=False,
                            problems=(
                                f"event_type {row['event_type']!r} does not resolve "
                                "to a recognised classification, and family "
                                f"{family_id!r} already has a fitted response "
                                "definition - joining would silently include this "
                                "occurrence in fitting without a governed "
                                "classification.",
                            ),
                        )
                    )
                    continue
                # An unrecognised type against a family with no fitted
                # definition yet stays governed metadata only, exactly as
                # before - never silently opted into fitting (section
                # 6.2), and there is no already-fitted definition here for
                # it to be silently consumed by.
            elif existing_family.classification != resolved_classification:
                results.append(
                    RowAdoptionResult(
                        event_id=event_id,
                        adopted=False,
                        problems=(
                            f"event_type {row['event_type']!r} resolves to classification "
                            f"{resolved_classification!r}, which conflicts with family "
                            f"{family_id!r}'s already-registered classification "
                            f"{existing_family.classification!r}.",
                        ),
                    )
                )
                continue

        try:
            occurrence = adopt_source_event_occurrence(
                {
                    k: row.get(k)
                    for k in ("event_id", "event_name", "start_date", "end_date")
                },
                {
                    "market": [str(row["market"])],
                    "source_id": source_id,
                    "source_version": source_version,
                    "family_id": family_id,
                },
            )
            candidate_occurrences = list(
                register_occurrence(candidate_occurrences, occurrence)
            )
        except ValueError as exc:
            results.append(
                RowAdoptionResult(
                    event_id=event_id,
                    adopted=False,
                    problems=(str(exc),),
                    response_policy_required=response_policy_required,
                )
            )
            continue

        created_definition = False
        if policy is not None:
            opted_in_family_definitions = [
                d
                for d in current_response_definition_versions(candidate_definitions)
                if d.family_id == family_id
                and d.transformation_method_reference == NAMED_EVENT_RESPONSE_STRUCTURE
            ]
            if len(opted_in_family_definitions) > 1:
                results.append(
                    RowAdoptionResult(
                        event_id=event_id,
                        adopted=False,
                        problems=(
                            f"family {family_id!r} already has "
                            f"{len(opted_in_family_definitions)} current opted-in "
                            "response definitions - ambiguous governance; resolve "
                            "the existing definitions before adopting further rows.",
                        ),
                        response_policy_required=response_policy_required,
                    )
                )
                continue
            if len(opted_in_family_definitions) == 1:
                existing_definition = opted_in_family_definitions[0]
                if not _response_definition_matches_policy(existing_definition, policy):
                    results.append(
                        RowAdoptionResult(
                            event_id=event_id,
                            adopted=False,
                            problems=(
                                f"family {family_id!r} already has an opted-in "
                                "response definition "
                                f"{existing_definition.response_definition_id!r} "
                                "whose window (treatment="
                                f"{existing_definition.treatment!r}, max_lead="
                                f"{existing_definition.max_lead}, max_lag="
                                f"{existing_definition.max_lag}) conflicts with the "
                                f"automatic policy for event_type {row['event_type']!r} "
                                f"(treatment={policy.treatment!r}, "
                                f"max_lead={policy.max_lead}, max_lag={policy.max_lag}) "
                                "- reconcile the definitions before adopting.",
                            ),
                            response_policy_required=response_policy_required,
                        )
                    )
                    continue
                # Reuse the existing opted-in definition as-is - identical
                # fit-relevant window, nothing new to register (section
                # 6.1: repeated yearly rows reuse one definition; never a
                # second opted-in definition for the same family).
            else:
                definition_id = default_response_definition_id(family_id)
                new_definition = new_response_definition(
                    response_definition_id=definition_id,
                    family_id=family_id,
                    treatment=policy.treatment,
                    max_lead=policy.max_lead,
                    max_lag=policy.max_lag,
                    transformation_method_reference=policy.transformation_method_reference,
                )
                try:
                    candidate_definitions = list(
                        register_response_definition(
                            candidate_definitions, new_definition
                        )
                    )
                    created_definition = True
                except ValueError as exc:
                    results.append(
                        RowAdoptionResult(
                            event_id=event_id,
                            adopted=False,
                            problems=(str(exc),),
                            response_policy_required=response_policy_required,
                        )
                    )
                    continue

        # Every step for this row succeeded - commit the staged
        # candidates as the new authoritative state.
        current_families = candidate_families
        current_occurrences = candidate_occurrences
        current_definitions = candidate_definitions
        results.append(
            RowAdoptionResult(
                event_id=event_id,
                adopted=True,
                created_family=created_family,
                created_response_definition=created_definition,
                response_policy_required=response_policy_required,
            )
        )

    return BulkAdoptionOutcome(
        families=tuple(current_families),
        occurrences=tuple(current_occurrences),
        response_definitions=tuple(current_definitions),
        results=tuple(results),
    )
