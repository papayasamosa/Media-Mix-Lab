# Population reference-period policy: open decision (`DD-020`/`MD-025`)

## Status

**Open. Business/governance decision required. Not a current production
blocker.** No approved model specification currently enables population
treatment for any project, and the current production model is UK-only,
where the PRD itself confirms this decision has no fitting consequence
yet (see "Why this is not a blocker" below).

## What is open

`Ancestry_MMM_PRD_Part_5_Coherent_v1_6_Governed_Population_Adjustment_
Data_Contracts.md`'s `DD-020` ("market-population reference source and
period policy") states:

> The population basis for the approved country-level multi-market
> capability is already resolved as total resident population. Confirm
> the operational source and update policy for each market, including:
> - authoritative or approved source hierarchy;
> - **whether one annual, midpoint, model-period-average or another
>   approved reference period is used for each fit**;
> - refresh cadence and revision handling;
> - treatment when a source revises a historical population estimate;
> - owner and approval route;
> - whether future planning uses the fitted reference or a separately
>   governed future population assumption.

`Ancestry_MMM_PRD_Part_6_Coherent_v1_11_Governed_Population_Adjustment.md`'s
`MD-025` restates the same open item ("authoritative population source
and reference-period policy for each country") alongside the also-open
`P_ref` centring-rule confirmation.

Both documents are dated 2026-09-12 - the same revision batch supplied
for this implementation pass - and neither resolves the question.

## Why this matters

The population source file is supplied **by year** (`Population by
Market.xlsx`: `market`, `population`, `population_basis`, `reference_
year`, `source` - one row per market per year, several years per
market). Part 5 v1.6 section 7.7 and Part 4 v1.8 section 15.6 both state
the *currently approved* resolution rule is that a population-enabled
model resolves **exactly one** applicable approved reference per market
- not "the reference for the year each observation falls in." Whether
several annual rows per market should instead resolve *by year* (2023
population -> 2023 model periods, 2024 population -> 2024 model periods,
etc.), by a fixed single year, by a midpoint, or by a model-period
average is precisely what `DD-020` leaves open.

An implementation must not treat "the source data happen to be annual"
as implicit permission to build per-year model exposure - that would
invent the resolution `DD-020` explicitly reserves for approval.

## Why this is not a current production blocker

- Part 9 v1.7's focused update and Part 10 v1.8's `UX-028` both state
  explicitly: *"the UK-only first-release reporting path is not blocked
  by population-aware reporting where the approved model is single-
  market and population treatment is `not_applicable`."*
- Part 6 v1.11 section 5.8 and Part 10 v1.8 both note that a population
  term constant within a single market gives **no cross-market
  identification benefit** - so even once `DD-020` is resolved, it would
  not change anything about the current UK-only fit until an approved
  multi-market (UK/AU/CA) model specification exists.
- `core.population_treatment.PopulationTreatmentSpecification` always
  defaults to fully inactive (`is_active=False`) and is never constructed
  from population-reference file or record presence - so nothing in the
  codebase can silently start depending on `DD-020`'s answer.
- `core.population_reference.resolve_single_population_reference` fails
  closed (`AmbiguousPopulationReferenceError`) rather than guessing
  whenever a market has more than one applicable approved reference -
  so even a future analyst who approves several annual records for one
  market cannot accidentally trigger an unapproved resolution policy.

## What is implemented in the meantime (unambiguous, per the
implementation brief's own fallback instruction for exactly this
scenario)

1. Governed ingestion and storage of the annual source
   (`core.population_reference.PopulationReferenceRecord`, one row per
   market per year, `reference_year` retained) - unambiguous; storing
   several approved annual records per market is explicitly supported by
   the schema.
2. Population treatment kept inactive by construction
   (`core.population_treatment.PopulationTreatmentSpecification`) -
   matches `UX-028`.
3. This document, recording the open decision.
4. `resolve_single_population_reference` implements only the currently-
   approved single-reference rule and raises, rather than guesses, when
   `DD-020` would need to be consulted.

## Recommended next step

Product/Finance (or whichever reviewer owns population-treatment
decisions per `REQ-POPULATION-001`'s ownership split) approves - or
rejects/amends - a specific reference-period policy for `DD-020`/`MD-025`
before any approved model specification is allowed to set
`outcome_population_treatment` or `predictor_population_treatment` to
anything other than `"none"` for a market with more than one approved
annual population reference. Candidate policies to choose among (not a
recommendation, since the PRD itself does not recommend one):

- **by-year**: each canonical model period resolves to its own calendar
  year's approved reference (requires an approved rule for weeks crossing
  a year boundary - also not yet specified anywhere in the PRD);
- **fixed single year**: one analyst-selected year's reference applies to
  the whole fit, regardless of observation date;
- **midpoint**: the reference for the year at the midpoint of the model
  window;
- **model-period average**: an average (mean/geometric mean) of the
  approved annual references spanning the model window.

Once a policy is approved, implementing it requires (a) a new resolver
function alongside `resolve_single_population_reference` implementing the
approved rule, (b) wiring `core.population_treatment.
population_exposure_log_term` into `core.hierarchical_model`'s `eta`
construction, and (c) moving population from the excluded to the
included side of `core.fingerprint._model_relevant_market_config` (or its
successor), since consuming it in the model makes it a fit-relevant
dependency for the first time.
