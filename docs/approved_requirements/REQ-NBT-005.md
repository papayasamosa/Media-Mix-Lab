# REQ-NBT-005: UK Family History production NBT maturity readiness window

**Status:** approved for implementation
**Decision date:** 2026-09-10
**Scope:** current UK Family History production onboarding, readiness/reporting surfaces only

## Decision

For the current UK Family History production delivery, official MMM
readiness treats the latest supplied Net Bill-Through week as mature once
**30 days** have elapsed between `data_as_of_date` and
`latest_complete_net_billthrough_week`. This is a more conservative,
production-specific readiness window - distinct from, and not a
replacement for, `REQ-NBT-002`'s 14-day *historical-test* completeness
horizon, which `REQ-NBT-004` already forbids treating as a production
default.

In normal operation this readiness window should not block the MMM,
because the analysis is expected to run more than 30 days after the data
cutoff. Historical mature NBT values are not expected to change materially
once the window has elapsed; this decision does not authorise trimming,
forward-filling, or otherwise altering outcome data - it only gates whether
the *latest* signup cohorts are treated as read for official use.

This is a surfaced readiness signal, not a new hard block on the existing
structural-completeness gate (`validate_supplied_net_billthrough`,
`assert_supplied_net_billthrough_complete`), which continues to validate
coverage, non-negativity, and weekly alignment exactly as before.

## Scope

- `ancestry_mmm/core/net_billthrough.py` - `NetBillthroughCompletenessMetadata.maturity_window_days`
  (new optional field, default `None`) and `assess_official_maturity_readiness`
  (new function)
- No change to `validate_supplied_net_billthrough`,
  `assert_supplied_net_billthrough_complete`, or
  `validate_nbt_completeness_metadata_for_outcome` - the existing
  structural-completeness gate is unaffected
- Does not set a value for `maturity_window_days` in any script or
  fixture; the number becomes governed configuration only when a specific
  project's supplied completeness metadata sets it explicitly, per
  `REQ-NBT-004`'s "must come from the supplied source metadata" principle

## Required tests

- `ancestry_mmm/tests/test_net_billthrough.py::TestOfficialMaturityReadiness::test_no_metadata_is_not_assessed`
- `ancestry_mmm/tests/test_net_billthrough.py::TestOfficialMaturityReadiness::test_unconfigured_window_is_not_assessed_not_false`
- `ancestry_mmm/tests/test_net_billthrough.py::TestOfficialMaturityReadiness::test_thirty_day_window_mature_when_elapsed`
- `ancestry_mmm/tests/test_net_billthrough.py::TestOfficialMaturityReadiness::test_thirty_day_window_not_mature_when_recent`
- `ancestry_mmm/tests/test_net_billthrough.py::TestOfficialMaturityReadiness::test_accepts_dict_metadata`
- `ancestry_mmm/tests/test_net_billthrough.py::TestOfficialMaturityReadiness::test_maturity_window_days_changes_completeness_fingerprint`

## Owner

Product / Finance (business window), Modelling / Platform engineering
(implementation)

## Affected modules

- `ancestry_mmm/core/net_billthrough.py`
- `docs/decision_log.md`

## Human traceability

Derived from `UK_FH_MMM_Autonomous_Implementation_Brief_2026-09-10.md`,
section 3.5 ("Maturity and completeness"). Complements `REQ-NBT-002`
(historical-test-only completeness rule) and `REQ-NBT-004` (production
evidence boundary), neither of which this record supersedes.

## Addendum, 2026-09-10: UI control added - the field was previously unreachable

Found during the next pass's production-configuration verification: the
`maturity_window_days` field existed on `NetBillthroughCompletenessMetadata`
with zero UI surface anywhere in the app - an analyst could never actually
set it through the real Structure Segments/Markets page, only via a script
or a test. Added a `st.number_input` (0 = not configured) to the existing
NBT completeness form on `pages/03_Structure_Segments_Markets.py`, plus a
live readiness read-out via `assess_official_maturity_readiness` so the
effect of the configured window is visible immediately, not only after a
fit or a Results-page visit.

### Affected modules (this addendum)

- `ancestry_mmm/pages/03_Structure_Segments_Markets.py`

### Required tests (this addendum)

- `ancestry_mmm/tests/test_structure_net_billthrough_apptest.py::TestNBTMaturityWindowUI` (all tests)
