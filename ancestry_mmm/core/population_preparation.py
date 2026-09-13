"""Population model-preparation boundary (`REQ-POPULATION-001`).

Part 6 v1.11 section 36.1 and its acceptance criterion 26 require the
population-treatment schema, population-reference resolution, and
count-preservation contract to be *available to the modelling path* even
while the first UK-only model leaves population treatment inactive - not
merely present as an unused, disconnected utility module. This module is
that integration point: object 4 of Part 4 v1.8 section 15.6's four-object
architecture ("prepared population-aware model frame"), for the inactive
case only.

Deliberately narrow:

- `prepare_population_aware_observed_target` executes only the inactive
  (`not_applicable`) path. It requires no population reference, resolves
  no `reference_year` against any model period, builds no weekly
  population series, and returns the supplied observed counts unchanged -
  trivially satisfying count preservation because nothing touches them.
- Any attempt to actually *use* `exposure_or_offset` or
  `selected_eligible_predictors` for real model preparation raises
  `PopulationTreatmentUnresolvedError` - a deliberate, governed blocking
  result, never a silent downgrade to `none`. Part 5 v1.6's `DD-020` and
  Part 6 v1.11's `MD-025` (see `docs/population_reference_period_policy_
  decision.md`) remain unresolved, so no path may activate the treatment
  it names.
- `population_dependency_fingerprint` implements Part 4 v1.8 `AD-019`'s
  conditional fingerprint semantics: it returns `None` whenever treatment
  is inactive (so a population file/reference change can never stale an
  unrelated fit - it never enters the hash at all), and a real,
  deterministic hash only when treatment is active. Because no path can
  reach that active case in production (the function above blocks it),
  this second branch is exercised only as a dependency contract/test
  today, not as part of an executable production-fit route - exactly as
  Part 4 v1.8 `AD-019`'s acceptance criteria require it to be available,
  without requiring an approved multi-market model to exist yet.

Never reads `core.market_config.MarketDescriptors.population` (the
pre-existing, purely-informational per-market scalar) - neither function
below accepts one as input, so there is no code path by which that
legacy descriptor could be consulted as a fallback population reference.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional, Sequence, Tuple

from .population_reference import (
    PopulationReferenceRecord,
    compute_population_records_fingerprint,
)
from .population_treatment import PopulationTreatmentSpecification


class PopulationTreatmentUnresolvedError(RuntimeError):
    """Raised when model preparation is asked to actually apply population
    treatment (`exposure_or_offset` and/or `selected_eligible_predictors`)
    while the reference-period/centring-rule policy required to do so
    remains unapproved (`DD-020`/`MD-025`). Callers must never catch this
    and proceed as though the specification were inactive - that would be
    exactly the silent downgrade this module exists to prevent."""


@dataclass(frozen=True)
class PopulationPreparationResult:
    """Outcome of `prepare_population_aware_observed_target`. Reachable
    today only with `population_treatment_active=False` -
    `PopulationTreatmentUnresolvedError` is raised before this could ever
    be constructed with `population_treatment_active=True`."""

    population_treatment_active: bool
    count_preservation_verified: bool
    population_reference_id_used: Optional[str] = None


def prepare_population_aware_observed_target(
    observed_counts: Optional[Sequence[Any]],
    treatment_spec: Optional[PopulationTreatmentSpecification] = None,
) -> Tuple[Optional[Sequence[Any]], PopulationPreparationResult]:
    """The count-preservation boundary (Part 3 v1.13 / Part 6 v1.11
    section 6.7 / Part 7 v1.10 section 3.15): proves
    `governed observed count == prepared observed count`.

    `treatment_spec=None` (the default - every existing UK model) and any
    specification with `is_active=False` take the identical inactive
    path: `observed_counts` is returned as the exact same object, no
    population reference is required or resolved, no `reference_year` is
    mapped to any model period, and no weekly population series is
    constructed. `count_preservation_verified=True` here is not a
    reconciliation performed against a treatment that changed something -
    it is trivially true because nothing in this path can alter the
    target.

    An active specification raises `PopulationTreatmentUnresolvedError`
    rather than returning a result - see the module docstring.
    """
    if treatment_spec is None or not treatment_spec.is_active:
        return observed_counts, PopulationPreparationResult(
            population_treatment_active=False,
            count_preservation_verified=True,
            population_reference_id_used=None,
        )
    raise PopulationTreatmentUnresolvedError(
        "Population treatment was requested "
        f"(outcome_population_treatment={treatment_spec.outcome_population_treatment!r}, "
        f"predictor_population_treatment={treatment_spec.predictor_population_treatment!r}) "
        "but the population reference-period/centring-rule policy required to "
        "activate it is unresolved (Part 5 v1.6 DD-020 / Part 6 v1.11 MD-025 - "
        "see docs/population_reference_period_policy_decision.md). This is a "
        "governed blocking result: model preparation must stop here, never "
        "proceed as though outcome_population_treatment/predictor_population_"
        "treatment were 'none'."
    )


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def population_dependency_fingerprint(
    treatment_spec: Optional[PopulationTreatmentSpecification],
    reference_records: Sequence[PopulationReferenceRecord] = (),
) -> Optional[str]:
    """Part 4 v1.8 `AD-019`'s conditional fingerprint contract.

    Returns `None` whenever `treatment_spec` is `None` or inactive - the
    caller (e.g. `core.fingerprint.fingerprint_model_spec`'s
    `population_fit_fingerprint` parameter) must treat `None` as "omit
    entirely", exactly like `named_event_fit_fingerprint`/
    `calibration_fit_fingerprint`'s existing opt-in pattern - so that a
    population file or reference change can never affect the fingerprint
    of a fit that does not use it.

    Returns a deterministic sha256 hash of the treatment specification
    plus the fingerprint of the reference records it would depend on only
    when `treatment_spec.is_active`. This branch is a dependency contract
    - it is never reached by a production fit today, because
    `prepare_population_aware_observed_target` raises before an active
    specification could be used to prepare anything.
    """
    if treatment_spec is None or not treatment_spec.is_active:
        return None
    payload = {
        "schema_version": 1,
        "population_treatment_specification": treatment_spec.to_dict(),
        "population_records_fingerprint": compute_population_records_fingerprint(
            reference_records
        ),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
