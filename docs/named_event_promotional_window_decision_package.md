# Named-event promotional-family response-window decision package

Status: decision support only. No statistical method is selected,
enabled, or implemented by this package for the promotional family. This
document records an implementation-time finding surfaced while building
the event-upload-contract implementation brief (seven-column Context
`events` source contract, automatic type-policy adoption, and the
date-to-period interval-overlap fix) against the already-approved
`REQ-EVENT-001`/`REQ-EVENT-002` contracts and the already-resolved
`docs/named_event_response_method_decision_record.md`. It does not amend,
supersede, or add capability-status text to either approved requirement
record.

## Where this sits relative to the already-resolved decision record

`docs/named_event_response_method_decision_record.md` ("Decision 12")
resolved the named-event statistical response method for the `gifting`
and `remembrance`/commemorative families: S3 (regularised cubic B-spline
basis over the family's lead/lag window, `Normal(0, tau)` coefficients,
`tau ~ HalfNormal(1.0)`), with family-specific windows of 6-week
anticipatory lead (gifting) and 2-week post-event lag (remembrance).
Both families operate over a *non-degenerate* window
(`max_lead_weeks + max_lag_weeks > 0`), which the approved cubic B-spline
construction (`core.named_event_response.build_spline_basis`) requires
and correctly supports.

That same decision record's own dimension 5 resolution for the
**promotional** family is deliberately different in kind, not merely in
number:

> Promotional family (`post_event`, window-bounded): `max_lead_weeks=0`,
> `max_lag_weeks=None` (not a fixed generic number — Decision 12's own
> text requires this window be bounded to the ACTUAL declared active
> period of the specific promotion instance, a per-promotion data-driven
> bound, not a global constant this record could invent).

No response *structure* was ever selected for that per-occurrence-bounded
case — dimension 1-3's S3 selection was made using WP2's fixed
symmetric-window evidence and was never validated for a window whose
width is zero (or otherwise occurrence-dependent rather than a governed
family constant). This package is where that specific, narrower gap is
recorded.

## The operational problem

The event-upload-contract implementation brief's own section 9
instructed: "implement the smallest mathematically coherent change that
makes the existing approved promotional contract operational... do not
simply set an arbitrary one-week lag in order to make a spline helper
accept the data... if achieving this requires changing the
already-approved named-event statistical estimand... stop and report the
exact conflict before choosing a new statistical method."

Two independent facts converge into a genuine gap, not merely an
implementation bug:

1. The brief's own date-to-period interval-overlap fix
   (`core.named_event_fit_inputs.weeks_overlapping_event_interval`) is
   implemented and correct: a multi-week promotion (e.g. Black Friday
   spanning two calendar weeks) now activates every model period it
   overlaps, exactly as a "bounded to the actual declared active period"
   contract requires, with no invented pre/post-event extension. This
   part is not blocked and is already implemented and tested.
2. Representing that bounded activation as a *model term* — the actual
   `EventResponseDefinition`/`build_spline_basis` machinery — requires a
   literal `(max_lead_weeks, max_lag_weeks)` window. The only window that
   adds no invented extension beyond the factual interval already
   captured by point 1 is `(0, 0)`. `core.named_event_response.
   build_spline_basis` requires a non-degenerate window and deliberately
   raises `ValueError` for `(0, 0)` rather than guess (see its own
   `test_rejects_fully_degenerate_window`) — a degree-3 B-spline over a
   zero-width domain is not a well-defined construction of the exact
   approved kernel family.

Two ways to close that gap were considered and both were rejected as
outside this implementation's authority:

- **Fabricate a nonzero lead/lag** (e.g. `max_lag_weeks=1`) purely to
  make `build_spline_basis` accept the window. Rejected: the brief
  explicitly forbids this ("do not simply set an arbitrary one-week
  lag... to make a spline helper accept the data"), and it would invent
  post-event support the promotional family's own approved contract
  says must not exist.
- **Substitute a different, lower-order basis** (e.g. a single
  all-ones/degree-0 indicator column) for the zero-width case only.
  Rejected as a unilateral implementation choice: this is a genuine,
  if small, deviation from the exact degree-3 cubic B-spline kernel
  Decision 12 selected and WP2 validated — choosing it without a
  decision record would be exactly the "silently choose a new
  statistical method" the brief instructs against.

## Decision required

Whoever owns Decision 12 (Marketing Data Science / Model Governance,
per that record's own "Ownership" section) must choose one of, or
another option not listed here:

1. **Approve a documented degree-0/indicator extension of S3** for the
   zero-width-window case only — i.e. when a family's approved window is
   `(0, 0)`, the "distributed basis" degenerates to a single coefficient
   applied uniformly across every activated period, with the same
   `Normal(0, tau)` shrinkage mechanism already approved. This keeps the
   promotional family's *shrinkage/regularisation* method identical to
   the rest of S3 and changes only the (degenerate) basis shape. If
   approved, this requires: a targeted PyMC graph test, NumPy replay
   parity, and a synthetic-recovery check for a planted flat/bounded
   promotional effect (mirroring the existing gifting/remembrance
   recovery evidence, at the promotional family's own real window rather
   than WP2's fixed testbed window).
2. **Approve a different mechanism** for per-occurrence-bounded support
   entirely — e.g. a per-promotion indicator variable outside the
   family-level spline-window framework, closer to how
   `core.promotions` already represents governed promotion intervals for
   other purposes. This would need its own decision on how (or whether)
   it participates in the same shrinkage/pooling machinery as
   `gifting`/`remembrance`.
3. **Explicitly defer promotional-family fitting** as a known, accepted
   platform limitation until real UK data and business priority justify
   resolving it, leaving the current implementation (governed metadata
   only, never auto-fitted) as the standing behaviour.

This package does not choose between these. No candidate is selected,
enabled, or implemented by it.

## Current implementation behaviour pending this decision

Until this is resolved, the current implementation (event-upload-contract
brief, 2026-09-14):

- adopts a `promotion`/`promotional` `event_type` source row into a
  governed `NamedEventFamily` and `NamedEventOccurrence` exactly like any
  other supported type — factual dates preserved verbatim, family
  classification resolved to `"promotional"` (never derived from
  `event_name`, never left as an unclassified raw string);
- never auto-creates an `EventResponseDefinition` for that family
  (`core.named_event_type_policy.resolve_event_type_policy` returns
  `None` for `promotion`/`promotional`) — the family's
  `classification_status` is set to
  `"promotional_window_unresolved"` (distinct from the generic
  `"response_policy_required"` status used for a genuinely unrecognised
  `event_type`, so the UI can state the specific, deliberate reason
  rather than an ambiguous "unsupported type");
- is visibly reported, both at adoption time and persistently in the
  governed-registry view (`pages/01_Data_Upload.py`) and in the Model
  Training fit proposal (`pages/05_Model_Training.py`), as registered but
  **not** included in the fitted named-event response, with the reason
  stated explicitly — never silently absent and never contributing a
  zero effect as though it had been modelled and found immaterial;
- a manual, advanced override that forces a response definition with a
  literal `(0, 0)` window through the existing admin form does **not**
  raise: `core.named_event_fit_inputs.build_named_event_fit_inputs`
  deliberately skips a degenerate window before it would ever reach
  `build_spline_basis`'s `ValueError` ("a response definition recorded
  with no support at all simply contributes nothing, never an error at
  fit time"). Left on its own that is a silent, invisible exclusion, not
  a visible one — which is exactly why `core.named_event_fit_inputs.
  families_excluded_from_fitting`/`families_without_opted_in_response_
  definition` (added as part of the same work that found this gap) exist
  as the surfacing mechanism: every UI surface that reports what a fit
  or the registry contains must call one of them and display the result,
  so an excluded family is always shown, never merely absent.

## Traceability

`REQ-EVENT-001` (governed occurrence/family/response-definition
contracts; this package changes nothing in that record), `REQ-EVENT-002`
(future replay — inherits whatever this decision resolves, once
resolved), `docs/named_event_response_method_decision_record.md`
(Decision 12 — the already-resolved method this package's gap sits
outside of), `docs/wp2_named_event_statistical_method_decision_package.md`
(the original seven-dimension decision framework this narrower gap is a
sub-case of dimension 5), event-upload-contract implementation brief
(where the gap was found while making the promotional contract
operational for multi-week interval overlap).

## Ownership

Marketing Data Science / Model Governance, mirroring
`docs/named_event_response_method_decision_record.md`'s own ownership.
The coding agent does not select an option from "Decision required"
above.
