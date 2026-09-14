"""Governed population-treatment specification (`REQ-POPULATION-001`).

Part 4 v1.8 section 15.6 requires four objects to stay independently
traceable: the raw governed outcome observation, the governed population
reference (`core.population_reference`), the population-treatment
specification (this module), and the prepared population-aware model
frame. This module implements the third object only.

Population treatment is an explicit, versioned, fit-relevant *decision*,
separate from whether a population reference happens to exist
(Part 5 v1.6 section 12.9; Part 10 v1.8's "merely placing a population
reference file in storage must not activate population treatment").
`PopulationTreatmentSpecification` therefore always defaults to `"none"`/
`"none"` (fully inactive) and is never constructed implicitly from file
presence anywhere in this codebase.

What this module deliberately does NOT implement: wiring this
specification into `core.hierarchical_model`'s PyMC count likelihood. The
statistical exposure form itself is fully specified for the case of one
population reference per market (Part 6 v1.11 section 7.2.1:
`log(mu) = log(population/reference_scale) + eta`), and
`population_exposure_log_term`/`geometric_mean_population` below implement
and test that math as standalone utilities. But actually consuming it
inside `eta` would (a) require resolving Part 5 v1.6's open `DD-020`
reference-period policy for any market with more than one approved annual
record, and (b) make population a new fit-relevant fingerprint input
(`core.fingerprint._model_relevant_market_config` currently excludes
population deliberately, since nothing reads it -
`ancestry_mmm/core/fingerprint.py` lines ~89-98 document that such a move
is itself a fingerprint-breaking change). Both remain open per
`docs/population_reference_period_policy_decision.md`, and the current
production model is UK-only, where Part 6 v1.11 section 5.8 and Part 10
v1.8's UX-028 both confirm a constant-within-market population term would
give no cross-market identification benefit anyway. Wiring it in is
therefore left as a target platform capability, not implemented here.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional, Sequence, Tuple, cast

POPULATION_TREATMENT_SCHEMA_VERSION = 1

# Part 5 v1.6 section 12.9.
OUTCOME_POPULATION_TREATMENT_NONE = "none"
OUTCOME_POPULATION_TREATMENT_EXPOSURE_OR_OFFSET = "exposure_or_offset"
OUTCOME_POPULATION_TREATMENT_APPROVED_EQUIVALENT = "approved_equivalent"

OUTCOME_POPULATION_TREATMENTS = (
    OUTCOME_POPULATION_TREATMENT_NONE,
    OUTCOME_POPULATION_TREATMENT_EXPOSURE_OR_OFFSET,
    OUTCOME_POPULATION_TREATMENT_APPROVED_EQUIVALENT,
)

PREDICTOR_POPULATION_TREATMENT_NONE = "none"
PREDICTOR_POPULATION_TREATMENT_SELECTED_ELIGIBLE_PREDICTORS = (
    "selected_eligible_predictors"
)

PREDICTOR_POPULATION_TREATMENTS = (
    PREDICTOR_POPULATION_TREATMENT_NONE,
    PREDICTOR_POPULATION_TREATMENT_SELECTED_ELIGIBLE_PREDICTORS,
)

# Part 3 v1.13 / Part 6 v1.11 / Part 10 v1.8: already audience-relative or
# normalised measures are ineligible for automatic population division by
# default (GRPs, TVRs, reach percentages, rates, percentages, indices).
#
# 2026-09-13 review follow-up (Codex P2): the original exact-string list
# below was too narrow - it caught neither the bare "%" symbol nor plural
# forms such as "indices". Matching is now done through an explicit
# canonicalisation step (`_canonicalise_unit_label`) plus a closed alias
# table, rather than a substring search - a substring check could reject
# an unrelated unit that merely happens to contain "rate" or "index" as a
# fragment (e.g. a hypothetical "conversion_rate_index" spend metric),
# which this repository's governed-unit-vocabulary convention (see
# `core.search_objects.SEARCH_UNITS`'s closed-list pattern) treats as a
# defect, not acceptable caution.

# Canonical protected-measure identities.
_PROTECTED_GRP = "grp"
_PROTECTED_TVR = "tvr"
_PROTECTED_PERCENTAGE = "percentage"
_PROTECTED_REACH_PERCENTAGE = "reach_percentage"
_PROTECTED_RATE = "rate"
_PROTECTED_INDEX = "index"

PROTECTED_UNIT_CANONICAL_FORMS = frozenset(
    {
        _PROTECTED_GRP,
        _PROTECTED_TVR,
        _PROTECTED_PERCENTAGE,
        _PROTECTED_REACH_PERCENTAGE,
        _PROTECTED_RATE,
        _PROTECTED_INDEX,
    }
)

# Every governed alias a canonicalised unit label may take, mapped to its
# canonical identity above. Closed and explicit - never extended by a
# substring/fuzzy match at lookup time.
_PROTECTED_UNIT_ALIASES = {
    "grp": _PROTECTED_GRP,
    "grps": _PROTECTED_GRP,
    "tvr": _PROTECTED_TVR,
    "tvrs": _PROTECTED_TVR,
    "percent": _PROTECTED_PERCENTAGE,
    "percents": _PROTECTED_PERCENTAGE,
    "pct": _PROTECTED_PERCENTAGE,
    "percentage": _PROTECTED_PERCENTAGE,
    "percentages": _PROTECTED_PERCENTAGE,
    "reach_percent": _PROTECTED_REACH_PERCENTAGE,
    "reach_pct": _PROTECTED_REACH_PERCENTAGE,
    "reach_percentage": _PROTECTED_REACH_PERCENTAGE,
    "reach_percentages": _PROTECTED_REACH_PERCENTAGE,
    "rate": _PROTECTED_RATE,
    "rates": _PROTECTED_RATE,
    "index": _PROTECTED_INDEX,
    "indices": _PROTECTED_INDEX,
    "indexes": _PROTECTED_INDEX,
}

APPROVAL_STATUSES = ("pending", "approved", "rejected")

# Codex P2 (2026-09-13, second pass): the repository already defines a
# governed index unit with a numeric range suffix -
# `core.seo_visibility.SEO_POSITIONAL_VISIBILITY_METRIC.unit ==
# "index_0_to_1"` - which the exact-alias table above does not cover. That
# module's own naming convention is `index_<lower>_to_<upper>` (a governed
# "index family", not a free-form suffix), so this narrow, explicit regex
# recognises exactly that shape - never a bare substring search. A unit
# such as "conversion_rate_index" does not start with "index_" and is
# still correctly left unprotected.
_INDEX_RANGE_FAMILY_PATTERN = re.compile(r"^index_\d+_to_\d+$")


def _canonicalise_unit_label(unit: str) -> str:
    """Lowercase, trim, normalise the "%" symbol to the word "percent",
    and collapse whitespace/hyphens to a single underscore - e.g.
    `"Reach %"`, `"reach_pct"` and `"reach percentage"` all canonicalise
    to `"reach_percent"`/`"reach_percentage"`-shaped keys that
    `_PROTECTED_UNIT_ALIASES` resolves identically. Purely mechanical
    normalisation - never a fuzzy or substring match."""
    normalised = unit.strip().lower().replace("%", " percent ")
    normalised = re.sub(r"[\s\-]+", "_", normalised)
    return normalised.strip("_")


def is_predictor_unit_protected(unit: str) -> bool:
    """`True` when `unit` is an already-normalised/audience-relative
    measure that must never be automatically population-divided (Part 3
    v1.13: GRPs, TVRs, reach percentages, rates, percentages, indices,
    their ordinary governed aliases - `%`, `pct`, plural forms such as
    `indices`/`rates`, and `reach %` - and the repository's own governed
    `index_<lower>_to_<upper>` range family, e.g. `index_0_to_1`
    (`core.seo_visibility`'s `SEO_POSITIONAL_VISIBILITY_METRIC`). Matching
    is unit-semantic (a governed unit label), never inferred from a
    column name alone - callers must pass the variable's governed unit,
    not its raw source header. Exact canonical-identity lookup, plus the
    one narrow numeric-range-family regex above - never a general
    substring match. An unrelated unit that merely contains "rate" or
    "index" as a fragment (e.g. "conversion_rate_index") is never caught."""
    canonical_label = _canonicalise_unit_label(unit)
    canonical = _PROTECTED_UNIT_ALIASES.get(canonical_label)
    if canonical is not None and canonical in PROTECTED_UNIT_CANONICAL_FORMS:
        return True
    return bool(_INDEX_RANGE_FAMILY_PATTERN.match(canonical_label))


@dataclass(frozen=True)
class PopulationTreatmentSpecification:
    """Explicit, versioned population-treatment decision (Part 5 v1.6
    section 12.9 `dim_population_treatment_specification`). Always
    inactive (`"none"`/`"none"`) unless an analyst explicitly saves a
    different specification - never inferred from population-reference
    file presence."""

    population_treatment_spec_id: str
    project_id: str
    market_scope: Tuple[str, ...]
    owner: str
    outcome_population_treatment: str = OUTCOME_POPULATION_TREATMENT_NONE
    predictor_population_treatment: str = PREDICTOR_POPULATION_TREATMENT_NONE
    eligible_measure_units: Tuple[str, ...] = ()
    centring_rule: Optional[str] = None
    count_preservation_required: bool = True
    original_count_scale_output_required: bool = True
    population_reference_map: Mapping[str, str] = field(default_factory=dict)
    specification_version: int = 1
    rationale: Optional[str] = None
    approval_status: str = "pending"
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    schema_version: int = POPULATION_TREATMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.population_treatment_spec_id, str) or not (
            self.population_treatment_spec_id
        ):
            # 2026-09-14: same principle as PopulationReferenceRecord's
            # population_reference_id/market_id and PopulationReferenceSet's
            # reference_set_id - this is the object's own governed identity
            # field (declared `population_treatment_spec_id: str` above),
            # not ordinary descriptive metadata.
            raise ValueError(
                "PopulationTreatmentSpecification requires a non-empty string "
                f"population_treatment_spec_id, got {self.population_treatment_spec_id!r} "
                f"({type(self.population_treatment_spec_id).__name__})."
            )
        if not self.project_id:
            raise ValueError("PopulationTreatmentSpecification requires a project_id.")
        if not self.owner:
            raise ValueError("PopulationTreatmentSpecification requires an owner.")
        if self.outcome_population_treatment not in OUTCOME_POPULATION_TREATMENTS:
            raise ValueError(
                "PopulationTreatmentSpecification: unknown outcome_population_treatment "
                f"{self.outcome_population_treatment!r} "
                f"(expected one of {OUTCOME_POPULATION_TREATMENTS})."
            )
        if self.predictor_population_treatment not in PREDICTOR_POPULATION_TREATMENTS:
            raise ValueError(
                "PopulationTreatmentSpecification: unknown predictor_population_treatment "
                f"{self.predictor_population_treatment!r} "
                f"(expected one of {PREDICTOR_POPULATION_TREATMENTS})."
            )
        if (
            self.predictor_population_treatment
            == PREDICTOR_POPULATION_TREATMENT_SELECTED_ELIGIBLE_PREDICTORS
            and not self.eligible_measure_units
        ):
            raise ValueError(
                "PopulationTreatmentSpecification: predictor_population_treatment="
                "'selected_eligible_predictors' requires a non-empty eligible_measure_units."
            )
        protected_requested = [
            unit
            for unit in self.eligible_measure_units
            if is_predictor_unit_protected(unit)
        ]
        if protected_requested:
            raise ValueError(
                "PopulationTreatmentSpecification: eligible_measure_units includes "
                f"protected (already-normalised) units {protected_requested} - these "
                "must never be automatically population-divided."
            )
        if self.specification_version < 1:
            raise ValueError(
                "PopulationTreatmentSpecification.specification_version must be >= 1."
            )
        if self.approval_status not in APPROVAL_STATUSES:
            raise ValueError(
                "PopulationTreatmentSpecification: unknown approval_status "
                f"{self.approval_status!r}."
            )
        if self.approval_status == "approved" and not (
            self.approved_by and self.approved_at
        ):
            raise ValueError(
                "PopulationTreatmentSpecification: approval_status='approved' requires "
                "approved_by and approved_at."
            )
        if self.approval_status != "approved" and (
            self.approved_by or self.approved_at
        ):
            raise ValueError(
                "PopulationTreatmentSpecification: approved_by/approved_at must not "
                f"be set when approval_status={self.approval_status!r} (only "
                "'approved' specifications may carry approver metadata)."
            )
        if self.schema_version != POPULATION_TREATMENT_SCHEMA_VERSION:
            raise ValueError(
                "PopulationTreatmentSpecification: unsupported schema_version "
                f"{self.schema_version!r}; this build only understands "
                f"{POPULATION_TREATMENT_SCHEMA_VERSION}."
            )

    @property
    def is_active(self) -> bool:
        """`False` (`not_applicable`) iff both outcome and predictor
        treatment are `"none"`. The first UK release is expected to leave
        this `False` - Part 9 v1.7 and Part 10 v1.8's UX-028 both confirm
        that is a valid, unblocked state for a single-market model."""
        return (
            self.outcome_population_treatment != OUTCOME_POPULATION_TREATMENT_NONE
            or self.predictor_population_treatment
            != PREDICTOR_POPULATION_TREATMENT_NONE
        )

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["population_reference_map"] = dict(self.population_reference_map)
        return payload

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> "PopulationTreatmentSpecification":
        payload = dict(values)
        if "market_scope" in payload:
            payload["market_scope"] = tuple(payload["market_scope"] or ())
        if "eligible_measure_units" in payload:
            payload["eligible_measure_units"] = tuple(
                payload["eligible_measure_units"] or ()
            )
        if "population_reference_map" in payload:
            payload["population_reference_map"] = dict(
                payload["population_reference_map"] or {}
            )
        known = set(cls.__dataclass_fields__)
        return cls(**cast(Any, {k: v for k, v in payload.items() if k in known}))


def is_predictor_unit_eligible_for_population_normalisation(
    unit: str,
    spec: PopulationTreatmentSpecification,
) -> bool:
    """Eligibility comes from the saved specification's own
    `eligible_measure_units`, gated by the protected-unit list - never
    from a column-name heuristic (Part 5 v1.6 section 12.9)."""
    if (
        spec.predictor_population_treatment
        != PREDICTOR_POPULATION_TREATMENT_SELECTED_ELIGIBLE_PREDICTORS
    ):
        return False
    if is_predictor_unit_protected(unit):
        return False
    normalised = unit.strip().lower().replace(" ", "_")
    return normalised in {
        u.strip().lower().replace(" ", "_") for u in spec.eligible_measure_units
    }


def geometric_mean_population(populations: Sequence[float]) -> float:
    """A policy-neutral mathematical utility only - NOT the approved
    `P_ref` centring rule. Part 6 v1.11 section 7.2.1 names the geometric
    mean as one *possible* candidate ("preferably ... or another versioned
    fixed constant"), but `MD-025` (Part 6 v1.11) explicitly leaves the
    actual centring-rule decision open, alongside `DD-020`'s reference-
    period policy (see `docs/population_reference_period_policy_
    decision.md`). This function:

    - is never called automatically by anything in this codebase (not by
      `PopulationTreatmentSpecification`, not by `core.
      population_preparation`, not by any resolver) - it exists only for
      explicit, deliberate invocation by a future caller once a centring
      rule is actually approved;
    - must never become a default value for `centring_rule` or any other
      field;
    - takes no policy input from a specification or project - it is pure
      arithmetic over whatever population values the caller explicitly
      supplies, and computing a number with it does not make that number
      an approved `P_ref`.

    Approving this (or any other) centring rule remains `MD-025`'s open
    decision, not something this function's existence pre-empts."""
    if not populations:
        raise ValueError(
            "geometric_mean_population requires at least one population value."
        )
    for value in populations:
        if not math.isfinite(value) or value <= 0:
            raise ValueError(
                "geometric_mean_population requires strictly positive, finite values, "
                f"got {value!r}."
            )
    log_mean = sum(math.log(value) for value in populations) / len(populations)
    return math.exp(log_mean)


def population_exposure_log_term(population: float, reference_scale: float) -> float:
    """The fixed market-exposure log-term from Part 6 v1.11 section 7.2.1:
    `log(population / reference_scale)`, added to the linear predictor
    with its coefficient fixed at one. A pure, tested function - not yet
    called from `core.hierarchical_model` (see module docstring).

    Both arguments are required and have no default - `reference_scale`
    in particular is a policy-controlled `P_ref` choice (`MD-025` is still
    open on it; see `geometric_mean_population`'s docstring) that only a
    caller holding an actual approved value may supply. This function
    cannot silently pick one on a caller's behalf, and nothing in this
    codebase calls it automatically."""
    if not math.isfinite(population) or population <= 0:
        raise ValueError(
            "population_exposure_log_term requires a strictly positive, finite population."
        )
    if not math.isfinite(reference_scale) or reference_scale <= 0:
        raise ValueError(
            "population_exposure_log_term requires a strictly positive, finite reference_scale."
        )
    return math.log(population / reference_scale)


def population_normalised_predictor_value(
    raw_value: float, population: float, unit_scale: float = 1.0
) -> float:
    """The deterministic predictor-normalisation rule from Part 6 v1.11
    section 7.2.1: `adjusted_input = raw_input / population * unit_scale`.
    `unit_scale` may only produce convenient units (e.g. per-million
    residents) - it must never be learned from the outcome."""
    if not math.isfinite(population) or population <= 0:
        raise ValueError(
            "population_normalised_predictor_value requires a strictly positive, finite population."
        )
    if not math.isfinite(unit_scale) or unit_scale <= 0:
        raise ValueError(
            "population_normalised_predictor_value requires a strictly positive, finite unit_scale."
        )
    return (raw_value / population) * unit_scale
