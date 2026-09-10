# REQ-FX-006: FX Reporting, Currency-Labelled Economics, and Year-on-Year Translation Decomposition

## PRD source

`Ancestry_MMM_Governed_FX_Translation_Requirements_Addendum.md`, Section
13 ("Reporting"), Section 14 ("Year-on-year decomposition"), and Section
15 ("Persistence and staleness") — reconciled by Work Package 7 of
`Media-Mix-Lab Coding LLM Next Steps 2026-08-27`, under the same
2026-08-22 architecture approval cited by `REQ-FX-001`.

## Approval and traceability

Approved for implementation by the task-specific implementation brief
cited above (2026-08-27). Target-state contract only. Extends
`AGENTS.md`'s existing "Mathematical rules" (outcome-scale, posterior-
aggregated business response) with an FX-specific reporting and
decomposition contract; does not restate or weaken those existing rules.

## Capability status

Zero implementation. No local/USD/constant-currency reporting toggle, no
currency-labelled CPA/ROI, and no FX component in year-on-year
decomposition exists anywhere in this repository. `core.canonical_curves`
already carries ISO local/reporting currency and dated FX governance for
curve economics (per `REPO_REVIEW_AND_NEXT_STEPS.md`'s "Completed
foundation" record of the G2A.2 delivery), which this record extends to
reporting and year-on-year views rather than replaces.

## Requirement

### 1. Every monetary report supports four currency views

A monetary report must be able to render: the original transaction
currency; the market reporting currency; the USD/group reporting
currency; and a constant-currency comparison. The currency selector must
never recalculate from a live API — it must read only the scenario or
model's persisted FX snapshot (`REQ-FX-002`'s immutable rate set).

### 2. CPA/ROI labels always carry their currency

Every CPA/ROI figure must display its currency explicitly (e.g. "Average
CPA (GBP)", "Marginal ROI (USD)"). An unqualified currency symbol must
never be shown when more than one currency is present in the same
report context.

### 3. Year-on-year decomposition separates operational performance from translation

Year-on-year reporting must support three distinct views, each answering
a different question, never conflated into one number: a **local-
currency view** (each period's own local spend/values — did marketing
become more or less efficient for the market team?); a **reported-USD
view** (each period's historical translation rate — what did Ancestry
report in USD each period?); and a **constant-currency USD view**
(both periods recalculated using one approved reference-rate set,
normally the comparison period or budget rate — what would the change
have been without exchange-rate movement?).

### 4. FX is one explicit, separately attributed decomposition component

A year-on-year CPA/ROI decomposition must carry FX translation as its
own explicit component, distinct from and never merged into media-price
inflation, alongside the other already-governed components (underlying
response/effectiveness, spend/saturation, channel/product/segment mix,
timing/carryover, promotions/price, capacity, external conditions, and
definition change).

### 5. Persisted FX dependency and staleness triggers

A model, curve, scenario, and report must persist its FX dependency
identity: historical FX-rate-set ID and fingerprint, market/group/model
reporting currencies, future FX assumption ID and fingerprint (where
applicable), and the conversion policy applied. Staleness must follow: a
changed historical rate set stales the prepared data, model, curve,
scenario, and report; a changed future FX assumption stales scenario and
recommendation economics; a changed reporting-currency *selection* alone
is a presentation change only, never a staleness trigger; and a changed
conversion policy stales every dependent calculation.

## Explicitly excluded (decision-required, not approved by this record)

See `docs/wp7_governed_fx_finance_decision_package.md`. In summary, this
record does not approve:

- which reference-rate set is used for the constant-currency view by
  default (prior-year, current-year, or budget rate — Section 20 item 7);
- rounding/display precision for any reported currency figure (Section
  20 item 8).

## Affected modules

None yet — target-state contract only. Anticipated future affected
modules (not created by this record): `core.report`, `core.
reporting_rollups`, and `core.canonical_curves`'s existing currency
governance, extended for the local/USD/constant-currency toggle and the
year-on-year FX decomposition component.

## Required tests

- `ancestry_mmm/tests/test_outcome_approval.py::TestAuthorityConsistency::test_approved_requirements_readme_exists`
- `ancestry_mmm/tests/test_outcome_approval.py::TestAuthorityConsistency::test_index_json_exists`
- `ancestry_mmm/tests/test_outcome_approval.py::TestAuthorityConsistency::test_index_json_is_valid`
- `ancestry_mmm/tests/test_outcome_approval.py::TestAuthorityConsistency::test_indexed_records_exist`
- `ancestry_mmm/tests/test_requirements_index_conformance.py::test_requirement_ids_are_unique`
- `ancestry_mmm/tests/test_requirements_index_conformance.py::test_every_record_path_exists`
- `ancestry_mmm/tests/test_requirements_index_conformance.py::test_every_indexed_test_node_is_collectable`
- `ancestry_mmm/tests/test_governed_fx_authority_reconciliation.py::TestGovernedFXOverlayReconciled::test_req_fx_006_indexed_and_classified_incomplete`

## Migration impact

None. No schema, persisted artefact, or application code changes as a
result of this record.

## Unresolved decisions

All items under "Explicitly excluded" above, tracked by
`docs/wp7_governed_fx_finance_decision_package.md`.

## Owner

Finance / Platform engineering (reporting contract approved;
constant-currency reference-rate default and display precision remain
Finance-owned).

## Approval date

2026-08-27



## Addendum, 2026-08-30 (Phase D): architecture implemented (Decision 13 build-out)

Per the user's explicit 2026-08-30 authorisation (see wp7's updated
text), `ancestry_mmm/core/fx_reporting.py` now implements the four-value
currency-view vocabulary (Requirement 1), `label_currency_figure`
(Requirement 2, fails closed when a figure's currency is ambiguous),
`FxTranslationDecompositionComponent` (Requirement 4's FX component,
deliberately self-contained since none of the other seven decomposition
components this requirement lists exist anywhere in this repository
yet - see the decision record's explicit scope boundary), and
`FxDependencySnapshot`/`assess_fx_staleness_triggers` (Requirement 5).
Full detail in
`docs/governed_fx_contract_implementation_decision_record.md`. No
reference-rate-set default for the constant-currency view, or display/
rounding precision, is invented - every item under "Explicitly
excluded" above remains exactly as open as before this addendum.

## Addendum, 2026-09-10: historical outcome-valuation ROI is currency-aware

UK FH MMM implementation brief audit finding: `attributable_spend` (the
market's native media-input currency) and the governed
`WeeklyOutcomeValuationRecord` catalogue's `currency` can differ, and the
historical ROI path (`application.outcome_valuation_reporting_service`,
`pages/07_Results_Curve_Bank.py`'s "Economic outcome valuation & ROI"
section) had no FX awareness at all - `attribution.spend` was displayed
labelled with the *value's* currency regardless of what currency it was
actually computed in, and ROI divided the two without any conversion or
block.

`HistoricalOutcomeValuationRequest` gains `spend_currency`, `fx_rate_set`,
`fx_rate_records`, and `fx_as_of_date`. When `spend_currency` differs from
the valuation catalogue's currency, `OutcomeValuationReportingService`
resolves an approved rate via `application.fx_service.
resolve_approved_fx_rate` - the same approval-status/fingerprint-checked,
as-of-date lookup Official Curve Generation already uses for monetary
curves (`pages/13_Official_Curve_Generation.py`) - never a second,
parallel FX-lookup mechanism. Spend is converted into the value's
currency before ROI is computed, so `attribution.spend`/`attribution.
currency` are always mutually consistent by construction. When no
approved rate covers the pair, ROI (and the spend figure) are withheld
with an explicit warning, exactly like the pre-existing "zero/absent
spend means no ROI" contract - never a fabricated or mislabelled figure.
`spend_currency=None` (not yet governed for a market) leaves existing
single-currency reporting byte-for-byte unchanged.

The Results page resolves `spend_currency` from the same
`MarketCurrency.local_currency` Official Curve Generation reads, and now
renders `result.warnings` (previously computed but never displayed).

This closes the currency-labelled-ROI gap for this one reporting surface
only. Year-on-year FX decomposition (Requirement 4's remaining seven
components), a reference-rate-set default for the constant-currency view,
and display/rounding precision remain exactly as open as before.

### Affected modules (this addendum)

- `ancestry_mmm/application/outcome_valuation_reporting_service.py`
- `ancestry_mmm/pages/07_Results_Curve_Bank.py`

### Required tests (this addendum)

- `ancestry_mmm/tests/test_outcome_valuation_reporting_service.py::TestSpendCurrencyMismatch` (all tests)
- `ancestry_mmm/tests/test_outcome_valuation_reporting_apptest.py::TestSpendCurrencyMismatchOnTheLivePage` (all tests) -
  drives the real page end to end (not `OutcomeValuationReportingService` in
  isolation), proving `_fx_request_kwargs` actually wires the governed
  market currency through and the resulting warning actually renders
