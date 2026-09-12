# REQ-COVERAGE-002: Missing-media gap diagnostics and estimation-evidence framework

**Status:** approved for implementation
**Decision date:** 2026-09-10
**Scope:** gap classification, method-agnostic estimation-evidence harness, and a
fail-closed readiness gate for missing media/activity data - a dependent capability
of `REQ-COVERAGE-001`, not a reopening of it.

## Decision

`REQ-COVERAGE-001` established the canonical missingness-state vocabulary and
explicitly left two things out of scope for "a future, separately-approved
requirement": any specific imputation formula, and any specific validation
threshold or coverage-percentage cutoff. The UK FH MMM implementation brief
(2026-09-10, section 8, Workstream D) supplies exactly that scope, framed as "the
main area that still needs technical work," with an explicit instruction that
"there is not yet an approved universal number of missing weeks" and that any
threshold recommendation "must be clearly labelled as a recommendation until
approved."

This record approves building the framework the brief asks for - diagnostics, gap
classification, a method-agnostic estimation-evidence harness, and a fail-closed
readiness gate - without approving any specific numeric threshold or any specific
imputation formula as official. Those remain open, exactly as `REQ-COVERAGE-001`
left them.

## Requirement

1. **Gap diagnostics** (`diagnose_gaps`): classify every gap-state run in an
   existing `core.coverage.VariableCoverageRecord` by consecutive-run length,
   edge-vs-internal position relative to the record's observed history, overlap
   with a governed named-event occurrence (scoped to the event's own
   `market_scope`), and (only when a companion record is explicitly supplied)
   cross-measure evidence such as "is spend observed during this delivery gap."
   Never infers a state the coverage record itself does not already carry -
   this is classification of existing states, not a new missingness vocabulary.
2. **Estimation-evidence harness** (`evaluate_candidate_reconstruction_method`):
   given an already-fully-observed series, carve synthetic holdout gaps of
   caller-specified lengths/positions out of it, call a caller-supplied candidate
   reconstruction method to reconstruct the held-out weeks from the remainder, and
   score MAE/MAPE against the real, known values. Selects, endorses, or
   hard-codes no specific imputation formula - the candidate method is always
   supplied by the caller.
3. **Evidence summary** (`EstimationEvidenceSummary`): a plain record of which
   candidate methods were evaluated for a variable, at which gap lengths, with
   what error - never a verdict or approval field.
4. **Fail-closed readiness gate** (`assess_estimation_readiness`): given a gap's
   diagnostics and an explicit `EstimationReadinessPolicy`, return a readiness
   classification. `policy=None` always returns `blocked_no_policy` - this
   function never assumes, infers, or defaults a missing-week/coverage-percentage
   threshold. A policy is a plain, versioned, attributable record
   (`EstimationReadinessPolicy`, mirroring `core.coverage.DefinitionBreak`'s
   approval-requires-attribution pattern): every threshold field defaults to
   `None` ("not configured, not checked"), `allow_edge_gaps` defaults to
   `False`, and `is_recommendation_only` defaults to `True` until
   `approved_by`/`approved_at` are supplied.
5. **Design note, not an approval** (`docs/missing_media_threshold_recommendation.md`):
   a synthetic-data evidence base for a human reviewer (Product/Finance) to adopt,
   amend, or reject via a future, separately-scoped decision record - mirroring
   `docs/frequency_conversion_method_options.md`'s established pattern for the
   analogous `REQ-COVERAGE-001` §4 open choice. Explicitly does not propose a
   numeric MAPE ceiling, and states plainly that real UK FH data (or synthetic
   gaps carved out of real channels) must be run through the same harness before
   any policy is actually adopted.

## What this record does not approve

- Any specific numeric value for `EstimationReadinessPolicy`'s threshold fields.
- Any specific imputation/reconstruction method as the official one for any
  channel or activity.
- Registration of any method into `core.frequency_alignment`'s (separate,
  still-empty) frequency-conversion method registry - that registry concerns
  changing a variable's *frequency*, not filling a gap in an otherwise-correct
  frequency, and remains `REQ-COVERAGE-001` §4's own open scope.
- Automatic detection of an `activity_id`'s semantic grain changing through time
  (a related but distinct brief item, Workstream C) - investigated separately
  and found to require a business signal this record's scope does not supply;
  not built here.

## Affected modules

- `ancestry_mmm/core/missing_media_evidence.py` (new)
- `ancestry_mmm/tests/test_missing_media_evidence.py` (new)
- `docs/missing_media_threshold_recommendation.md` (new)

## Required tests

- `ancestry_mmm/tests/test_outcome_approval.py::TestAuthorityConsistency::test_approved_requirements_readme_exists`
- `ancestry_mmm/tests/test_outcome_approval.py::TestAuthorityConsistency::test_index_json_exists`
- `ancestry_mmm/tests/test_outcome_approval.py::TestAuthorityConsistency::test_index_json_is_valid`
- `ancestry_mmm/tests/test_outcome_approval.py::TestAuthorityConsistency::test_indexed_records_exist`
- `ancestry_mmm/tests/test_requirements_index_conformance.py::test_requirement_ids_are_unique`
- `ancestry_mmm/tests/test_requirements_index_conformance.py::test_every_record_path_exists`
- `ancestry_mmm/tests/test_requirements_index_conformance.py::test_every_indexed_test_node_is_collectable`
- `ancestry_mmm/tests/test_missing_media_evidence.py` (all tests)

## Migration impact

None. Entirely new, additive module; no existing schema, persisted artefact, or
application-code behaviour changes.

## Unresolved decisions

- The exact `EstimationReadinessPolicy` threshold values (missing-week count,
  consecutive-run length, MAPE ceiling) - deferred to Product/Finance, per
  `docs/missing_media_threshold_recommendation.md`'s recommendation (not an
  approval).
- Which candidate reconstruction method(s), if any, should become the approved
  default for a given activity/channel - deferred; this record approves the
  evaluation harness only, never a chosen method.
- Automatic activity-grain-change detection (Workstream C) - not resolved by
  this record; the existing analyst-declared `core.coverage.DefinitionBreak`
  mechanism remains the only supported path.

## Addendum, 2026-09-10: wired into the single authoritative production fit-readiness gate

Per the immediate follow-up instructions, `assess_estimation_readiness` is
now wired into the real gate, not left standalone. Traced the actual call
chain first (`04_Model_Config.py` -> `application.official_preparation_
service.review_official_preparation` -> `core.official_preparation.
build_official_capability_report` -> `core.market_data_capability.
check_market_channel_capability` -> `core.frequency_alignment.assess_
official_preparation`'s `capability_evidence` check -> `OfficialPreparation
Result.ready` -> `05_Model_Training.py`'s `_official_fit_gate_blocked`) to
confirm there is exactly one authoritative gate for media/channel coverage,
not several competing ones - `check_market_channel_capability`'s existing
`has_unapproved_non_observed_coverage` check is the single point every
downstream consumer already reads faithfully with no duplicate logic.

`check_market_channel_capability`, `build_official_capability_report`, and
`review_official_preparation` all gain optional `estimation_readiness_
policy`/`estimation_evidence_by_variable` parameters, threaded straight
through. Semantics, exactly as this record's core text already specified:
`approved_for_official_use=True` alone still suffices when no policy is
supplied (every existing caller, including `04_Model_Config.py`, passes
none today and is completely unaffected - confirmed by the full existing
regression suite passing unmodified). When a policy *is* supplied, an
`estimated`/`modelled` segment on an otherwise-approved record is
additionally required to pass `assess_estimation_readiness` (reusing
`diagnose_gaps` scoped to exactly those two states - no duplicated
diagnostic logic); `unknown`/`missing_expected`/`not_applicable`/
`unavailable_source`/`suppressed` segments remain hard-blocked regardless
of any policy, exactly as before - a policy only re-examines a state an
analyst has already explicitly marked estimated, never a genuinely
unresolved one.

No project-level UI for *configuring* a policy is added by this addendum -
building one would be premature given no approved threshold exists yet
(`docs/missing_media_threshold_recommendation.md` remains a recommendation
only). The capability is reachable today by any caller (a script, a test,
or a future UI control) that constructs an `EstimationReadinessPolicy` and
passes it through the existing parameter chain; wiring an actual UI control
into `04_Model_Config.py` is deferred until a policy exists to configure.

### Affected modules (this addendum)

- `ancestry_mmm/core/market_data_capability.py`
- `ancestry_mmm/core/official_preparation.py`
- `ancestry_mmm/application/official_preparation_service.py`
- `ancestry_mmm/pages/03_Structure_Segments_Markets.py` (NBT
  `maturity_window_days` UI field and readiness read-out - a related
  integration gap found during the same pass: the field existed on
  `NetBillthroughCompletenessMetadata` with no UI control to actually set
  it)

### Required tests (this addendum)

- `ancestry_mmm/tests/test_market_data_capability.py::TestEstimationReadinessPolicyIntegration` (all tests)

## Owner

Data Science / Platform engineering (framework); Product / Finance (any adopted
threshold policy, per `REQ-COVERAGE-001`'s existing ownership split).

## Human traceability

Derived from `UK_FH_MMM_Autonomous_Implementation_Brief_2026-09-10.md`, section 8
("Workstream D: missing media data policy"). Complements `REQ-COVERAGE-001`,
which this record does not supersede or reopen.
