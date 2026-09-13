# REQ-POPULATION-001: Governed Country-Level Population Reference and Treatment Specification

## PRD source

`Ancestry_MMM_PRD_Part_3_Coherent_v1_13_Governed_Population_Adjustment.md`
("Focused v1.13 update", section 26.20), `Part_4_Coherent_v1_8` (section
15.6, `AD-019` - resolved), `Part_5_Coherent_v1_6` (sections 7.7, 12.9,
12.10, `DD-020` - unresolved), `Part_6_Coherent_v1_11` (sections 5.8, 6.7,
7.2.1, `MD-025` - unresolved), `Part_7_Coherent_v1_10` (sections 3.15,
8.12, 9.3), `Part_9_Coherent_v1_7` (focused v1.7 update), `Part_10_
Coherent_v1_8` (focused v1.8 update, `UX-028` - resolved) - reconciled by
`UK_MMM_Governed_Population_By_Year_Implementation_Instructions.md`
(2026-09-12).

## Approval and traceability

Approved for implementation by the task-specific implementation brief
cited above (2026-09-12). Reconciles a genuine gap between that brief's
premise (that a prior chat had already resolved the annual/by-year
modelling-reference-period question in the PRD) and the actual PRD text
read during this pass: `Part 5 v1.6`'s `DD-020` and `Part 6 v1.11`'s
`MD-025` both still list "whether one annual, midpoint, model-period-
average or another approved reference period is used for each fit" as an
open decision, not a resolved one. See `docs/population_reference_
period_policy_decision.md` for the full reconciliation and the brief's
own built-in fallback instruction (section 28) for exactly this scenario,
which this record and its implementation follow.

**2026-09-13 narrow follow-up:** the first pass's "Capability status"
below originally said object 4 (the prepared population-aware model
frame) was not implemented at all. That went slightly further than the
PRD permits - Part 6 v1.11 section 36.1 and its acceptance criterion 26
require the population-treatment schema, reference resolution, and
count-preservation contract to be *available to the modelling path* even
while treatment stays inactive, not merely present as disconnected
utilities. This follow-up adds that narrow integration (see Requirement
6-8 below) without resolving `DD-020`/`MD-025` or implementing annual
mapping, active exposure, or predictor normalisation.

## Capability status

Implemented: the governed-reference and treatment-specification objects
(Part 4 v1.8 section 15.6's objects 2 and 3), and, as of the 2026-09-13
follow-up, the *inactive* path of object 4 (the prepared population-
aware model frame) - a real, tested model-preparation boundary
(`core.population_preparation`) that every existing UK model already
satisfies with zero configuration and zero numerical effect, plus
conditional fingerprint semantics (`core.fingerprint.
fingerprint_model_spec`'s opt-in `population_fit_fingerprint` parameter).

Not implemented: the *active* path of object 4 - no wiring of a
population exposure/offset term into `core.hierarchical_model`'s PyMC
count likelihood, and no annual reference-period resolution. Any attempt
to invoke the active path raises `PopulationTreatmentUnresolvedError`
rather than running or silently downgrading to inactive. See "Explicitly
excluded" below.

## Requirement

### 1. Governed population reference (`core.population_reference`)

A single approved market-population observation must record: a stable
`population_reference_id`; `market_id` (must resolve to a market the
current project actually configures); `population` (strictly positive,
finite); `population_basis` (closed vocabulary, currently only
`total_resident_population` - Part 5 v1.6 section 7.7's approved default;
a media audience universe such as "Adults 18+" must never be
substituted); `reference_year` (optional, integral, plausible-range);
`reference_period_start`/`reference_period_end`/`as_of_date` (optional);
`source_name`/`source_version_id`/`source_reference`; `owner`;
`approval_status` (`pending`/`approved`/`rejected`, `approved_by`/
`approved_at` required together iff approved).

References are collected into a versioned, immutable-once-used
`PopulationReferenceSet` (mirrors `core.fx_rates.FXRateSet`'s "immutable
identity, new version on change" pattern exactly): a `records_fingerprint`
over its constituent records, and its own `approval_status`/`approved_by`/
`approved_at`.

### 2. Resolution is single-reference-only; annual multi-reference selection is not implemented

`resolve_single_population_reference(market_id, records)` implements the
*only* resolution rule Part 5 v1.6 section 7.7 and Part 4 v1.8 section
15.6 currently approve: a population-enabled model resolves **exactly
one** applicable approved reference per market. Zero applicable records
resolves to `None` (fail closed). More than one applicable approved
record for the same market raises `AmbiguousPopulationReferenceError`
rather than guessing (e.g. "use the latest year") - which record to
prefer when several annual records exist for one market is exactly
`DD-020`'s open question, and this function must never resolve it
unilaterally.

### 3. Population treatment specification (`core.population_treatment`)

`PopulationTreatmentSpecification` is an explicit, versioned,
project-scoped decision, separate from whether a population reference
happens to exist. It always defaults to `outcome_population_treatment=
"none"` and `predictor_population_treatment="none"` (fully inactive,
`is_active=False`) and is never constructed implicitly from population-
reference file or record presence anywhere in this codebase. Enabling
`predictor_population_treatment="selected_eligible_predictors"` requires
a non-empty `eligible_measure_units`, and construction blocks outright if
any requested unit is on the protected list (GRPs, TVRs, reach
percentages, rates, percentages, indices - Part 3 v1.13).

### 4. Exposure/predictor-normalisation math is implemented as tested utilities, not wired into the model, and is not itself an approved policy

`population_exposure_log_term(population, reference_scale)` implements
Part 6 v1.11 section 7.2.1's `log(population/reference_scale)` fixed
exposure term's *arithmetic* (coefficient fixed at one); both arguments
are required, with no default, so it cannot silently pick a policy value
on a caller's behalf. `population_normalised_predictor_value(raw_value,
population, unit_scale)` implements its predictor-normalisation rule the
same way. `geometric_mean_population` is a **policy-neutral mathematical
utility only** - it is not, and must not be described as, the approved
`P_ref` centring rule; `MD-025` (Part 6 v1.11) leaves that decision open,
and nothing in this codebase calls this function automatically or uses
its result as a default. All three are pure, tested functions, callable
only by explicit future invocation once the relevant policy is approved.
None is called from `core.hierarchical_model`'s actual PyMC graph, and
none is called automatically by `core.population_preparation` or
`core.population_treatment` - see "Explicitly excluded".

### 5. Ingestion and persistence

`application.population_service.build_population_reference_set` validates
an analyst-supplied file strictly at upload time (required columns
`market`/`population`/`population_basis`/`reference_year`/`source`; any
other column is ignored; a malformed row aborts the whole upload, naming
the row - mirrors `application.fx_service.build_manual_fx_rate_set`
exactly). `core.persistence.resolve_imported_population_reference_
records`/`_set`/`_treatment_specification` quarantine a malformed record
individually on project import (mirrors `resolve_imported_fx_rate_
records`/`_set` exactly) rather than aborting the whole import. The
project bundle carries `config/population_reference_set.json`,
`config/population_reference_records.json`, and `config/population_
treatment_specification.json`, each independently optional and defaulting
to absent/`None`.

### 6. Count preservation is now a real, executable boundary for the inactive path

`core.population_preparation.prepare_population_aware_observed_target`
(2026-09-13 follow-up) is the count-preservation boundary Part 3 v1.13 /
Part 6 v1.11 section 6.7 / Part 7 v1.10 section 3.15 require. For every
existing UK model (`treatment_spec=None`, or any specification with
`is_active=False`) it returns the supplied observed counts unchanged and
`count_preservation_verified=True` - true by construction, since nothing
in this path can touch the target, not merely true because no caller
happens to invoke a treatment that doesn't exist. It requires no
population reference, resolves no `reference_year`, and builds no weekly
population series. An active specification is never allowed to reach a
"prepared" result at all - see Requirement 7.

### 7. Active treatment fails closed, never downgrades silently

`prepare_population_aware_observed_target` raises
`PopulationTreatmentUnresolvedError` the instant `treatment_spec.
is_active` is `True` (`outcome_population_treatment` and/or `predictor_
population_treatment` set to anything other than `"none"`). The error
names `DD-020` and `MD-025` explicitly and points at `docs/population_
reference_period_policy_decision.md`. `PopulationTreatmentSpecification`
may still
*represent* `exposure_or_offset`/`selected_eligible_predictors` as a
schema value (Requirement 3) - only *using* one for actual preparation is
blocked.

### 8. Conditional fingerprint semantics (`AD-019`)

`core.fingerprint.fingerprint_model_spec` gained an opt-in `population_
fit_fingerprint` parameter (2026-09-13 follow-up), following the exact
same pattern already established for `named_event_fit_fingerprint`/
`calibration_fit_fingerprint`: omitted from the hashed payload entirely
when falsy. `core.population_preparation.population_dependency_
fingerprint(treatment_spec, reference_records)` returns `None` whenever
treatment is inactive - so a population file/reference change can never
stale a fit that doesn't consume it - and a real, deterministic hash only
when `treatment_spec.is_active`. No current call site can reach the
active branch in production (Requirement 7 blocks it first); this
satisfies `AD-019`'s acceptance criteria as a dependency contract/test,
not as part of an executable production-fit route, exactly as the
2026-09-13 follow-up brief permits.

### 9. No fallback to `MarketDescriptors.population`

Neither `resolve_single_population_reference` nor
`prepare_population_aware_observed_target` accepts a `core.market_config.
MarketDescriptors` object as input - there is no parameter through which
the pre-existing, purely-informational per-market scalar could be
consulted as a governed population reference. Regression-tested in
`test_population_preparation.py::TestNoMarketDescriptorsFallback`.

## Explicitly excluded (decision-required or capability-deferred, not approved by this record)

- **`DD-020`/`MD-025`'s reference-period policy** - whether one annual,
  midpoint, model-period-average, or another rule selects among several
  approved annual records for one market. See `docs/population_
  reference_period_policy_decision.md`.
- **Actually wiring `population_exposure_log_term` into `core.
  hierarchical_model`'s `eta`/`mu` construction for an active
  specification.** `prepare_population_aware_observed_target` raises
  before this could ever happen. This would (a) require `DD-020` to be
  resolved for any market with more than one approved annual record, and
  (b) require an approved multi-market model specification, since Part 6
  v1.11 section 5.8 and Part 10 v1.8's `UX-028` both confirm a population
  term constant within one market gives no cross-market identification
  benefit - nothing in the approved UK-only delivery needs this.
- **The `P_ref` centring-rule default** (`MD-025`, Part 6 v1.11 section
  7.2.1) - `geometric_mean_population` is a policy-neutral utility, never
  a default, never called automatically by anything (see its own
  docstring and `test_population_preparation.py::
  TestGeometricMeanNeverCalledAutomatically`).
- **Predictor-normalisation wiring into `core.hierarchical_model`'s media
  transformation pipeline** - same dependency as the exposure wiring
  above; the deterministic math is implemented and tested, the pipeline
  hookup is not, and it is equally blocked by `prepare_population_aware_
  observed_target`'s fail-closed behaviour for any active specification.
- **`ModelSpec` (`core.schema`) does not gain a new field.** Population
  treatment is threaded through as a sibling parameter at the point of
  use (mirroring how `causal_graph_structural_fingerprint`/`search_
  object_fit_fingerprint` are handled - separate governed objects, not
  fields nested inside `ModelSpec`'s dict), avoiding a one-time
  fingerprint-breaking change to every existing model for a field that
  would always be `None`.
- **A Streamlit workflow page** for uploading/reviewing population
  references and configuring treatment (Part 10 v1.8's intended technical
  journey) - not built by this record; core/application/persistence only.
- **An analyst-facing upload-guide section** (`scripts/build_data_upload_
  guide_assets.py`) describing where to upload a population file in the
  app - deliberately not added alongside the missing page above. The
  guide's existing FX section names real, working page/button labels;
  adding a "Population reference" section with no matching UI would
  document a workflow analysts cannot actually use yet. Add it together
  with the page in the same future pass.

## Affected modules

- `ancestry_mmm/core/population_reference.py` (new)
- `ancestry_mmm/core/population_treatment.py` (new)
- `ancestry_mmm/core/population_preparation.py` (new, 2026-09-13 follow-up)
- `ancestry_mmm/application/population_service.py` (new)
- `ancestry_mmm/core/persistence.py`
- `ancestry_mmm/core/fingerprint.py` (2026-09-13 follow-up: opt-in `population_fit_fingerprint` parameter)
- `docs/approved_requirements/REQ-POPULATION-001.md`
- `docs/approved_requirements/index.json`
- `docs/approved_requirements/README.md`
- `docs/population_reference_period_policy_decision.md` (new)
- `docs/decision_log.md`

## Required tests

- `ancestry_mmm/tests/test_outcome_approval.py::TestAuthorityConsistency::test_approved_requirements_readme_exists`
- `ancestry_mmm/tests/test_outcome_approval.py::TestAuthorityConsistency::test_index_json_exists`
- `ancestry_mmm/tests/test_outcome_approval.py::TestAuthorityConsistency::test_index_json_is_valid`
- `ancestry_mmm/tests/test_outcome_approval.py::TestAuthorityConsistency::test_indexed_records_exist`
- `ancestry_mmm/tests/test_requirements_index_conformance.py::test_requirement_ids_are_unique`
- `ancestry_mmm/tests/test_requirements_index_conformance.py::test_every_record_path_exists`
- `ancestry_mmm/tests/test_requirements_index_conformance.py::test_every_indexed_test_node_is_collectable`
- `ancestry_mmm/tests/test_population_reference.py` (all tests)
- `ancestry_mmm/tests/test_population_treatment.py` (all tests)
- `ancestry_mmm/tests/test_population_service.py` (all tests)
- `ancestry_mmm/tests/test_persistence.py::test_resolve_imported_population_reference_records_absent_resolves_empty`
- `ancestry_mmm/tests/test_persistence.py::test_resolve_imported_population_reference_records_valid_round_trips`
- `ancestry_mmm/tests/test_persistence.py::test_resolve_imported_population_reference_records_quarantines_malformed_but_keeps_valid_ones`
- `ancestry_mmm/tests/test_persistence.py::test_resolve_imported_population_reference_records_quarantines_non_mapping_entries`
- `ancestry_mmm/tests/test_persistence.py::test_resolve_imported_population_reference_set_absent_resolves_none`
- `ancestry_mmm/tests/test_persistence.py::test_resolve_imported_population_reference_set_valid_round_trips`
- `ancestry_mmm/tests/test_persistence.py::test_resolve_imported_population_reference_set_reports_malformed_set_by_id`
- `ancestry_mmm/tests/test_persistence.py::test_resolve_imported_population_treatment_specification_absent_resolves_none`
- `ancestry_mmm/tests/test_persistence.py::test_resolve_imported_population_treatment_specification_valid_round_trips`
- `ancestry_mmm/tests/test_persistence.py::test_resolve_imported_population_treatment_specification_reports_malformed_by_id`
- `ancestry_mmm/tests/test_population_preparation.py` (all tests, 2026-09-13 follow-up)
- `ancestry_mmm/tests/test_fingerprint.py::TestFingerprintModelSpecPopulationFitFingerprint` (all tests, 2026-09-13 follow-up)

## Migration impact

None. No pre-existing persisted bundle carries any of the three new
`config/population_*.json` files; their absence resolves to `None`/`[]`,
which is the existing behaviour for every current project.

## Unresolved decisions

- `DD-020`/`MD-025`: the population reference-period policy (annual /
  midpoint / model-period-average / other) for a market with more than
  one approved annual reference. See `docs/population_reference_period_
  policy_decision.md`. Business/governance decision, not a production
  blocker (no approved model specification currently activates population
  treatment).
- The real local file's `population_basis` values (e.g. `total_residents`)
  do not match the approved canonical vocabulary (`total_resident_
  population`) - ingestion correctly rejects them today; reconciling the
  label (alias vs. relabel the source file) is an analyst/governance
  action, not a coding decision, and is not resolved by this record.

## Owner

Product/Finance (population basis and reference-period policy);
Platform engineering (governed-reference and treatment-specification
architecture - implemented this pass).

## Approval date

2026-09-12 (initial); 2026-09-13 (narrow follow-up adding the inactive-
path model-preparation boundary, conditional fingerprint semantics, and
fail-closed activation guard - same approval, no re-approval required
since it narrows rather than expands what is active)
