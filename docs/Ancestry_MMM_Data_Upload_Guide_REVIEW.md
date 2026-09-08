# Ancestry MMM data-upload guide review

Status: complete for the supplied implementation brief. This review covers the documentation and analyst-tooling deliverables only. No application parser, model, schema, upload contract, or governance behaviour was changed.

## Baseline and scope

- Implementation brief: `D:\ORIGIAL D DRIVE\008 Ancestry UK MMM - 2026\LLM_Instructions_Build_Ancestry_MMM_Data_Upload_Guide_v2.md`
- Exact repository baseline before this work: `2bd8e9a8a197f121d1176e61566d6122313e44e9` (`HEAD`, `main`, and `origin/main` were aligned).
- Generator: `scripts/build_data_upload_guide_assets.py`
- The pre-existing dirty worktree changes were preserved: `.mcp.json`, `ancestry_mmm/core/outcome_group_totals.py`, `ancestry_mmm/tests/test_official_lifecycle_browser.py`, `.playwright-mcp/`, `designs/`, and `tools/`.

## Deliverables

- [HTML handbook](Ancestry_MMM_Data_Upload_Guide.html) — self-contained, browser-openable, responsive, print-friendly, with sticky navigation, anchors, a CSS relationship diagram, client-side section search, 41 FAQ accordions, glossary, and six full RAG tables.
- [Outcome ID Builder](Ancestry_MMM_Outcome_ID_Builder.xlsx)
- [Activity ID Builder](Ancestry_MMM_Activity_ID_Builder.xlsx)
- [Context Variable ID Builder](Ancestry_MMM_Context_Variable_ID_Builder.xlsx)
- [Temporary schema inventory](data_upload_guide_schema_inventory.md)
- This review note.

The builders have `ID Builder`, `Reference`, `Read me`, and `Examples` sheets. They use formulas, dropdown validation, conditional formatting, Excel tables, collision checks, manual overrides, final IDs, and dictionary previews. They contain no VBA. They use modern Excel `LET`, `TEXTJOIN`, and `REGEXREPLACE` functions; the workbook Read me sheet states this requirement.

## Sources inspected

### Repository contracts

- `ancestry_mmm/data/templates.py` — current v1/v2 sheet names, required columns, schema detection, parser behaviour, outcome definitions, completeness, activity mappings, and native-frequency canonicalisation.
- `ancestry_mmm/data/template_downloads.py` — current downloadable source-pack shapes and filenames.
- `ancestry_mmm/data/loader.py` — standard workbook versus generic first-sheet loading and provenance.
- `ancestry_mmm/data/source_pack_adoption.py` — multi-file merge, duplicate/conflict handling, and adoption statuses.
- `ancestry_mmm/data/source_inventory.py` — physical-file/table lineage.
- `ancestry_mmm/core/outcomes.py` — outcome registry, segment dimensions, eligibility, grouping, NBT/LTR/DNA distinctions, and approved FH segments.
- `ancestry_mmm/core/activities.py`, `media_units.py`, and `media_costs.py` — activity identity, role/ownership, model-input versus spend/response units, and cost-mapping boundaries.
- `ancestry_mmm/core/coverage.py` and `frequency_alignment.py` — variable classes, missingness states, native-frequency preservation, and no-default-conversion rule.
- `ancestry_mmm/core/search_objects.py`, `search_intent_taxonomy.py`, and `google_trends_anchor.py` — Search object separation, Brand/Non-Brand × Google/Bing leaves, cap semantics, Trends anchor metadata, and suppressed-zero handling.
- `ancestry_mmm/core/seo_visibility.py` — dedicated GSC/SEO visibility shape and its separation from organic Search capture.
- `ancestry_mmm/application/candidate_a_input_service.py` and `outcome_valuation_input_service.py` — Candidate A and valuation upload contracts.
- `ancestry_mmm/pages/01_Data_Upload.py` — current analyst-facing workflow, separate valuation/evidence/events paths, and “logical category is not a physical file” wording.

### Approved authority records

The guide and inventory cite the relevant approved records, including `REQ-DATAIN-001`, `REQ-COVERAGE-001`, `REQ-ACTIVITY-001`, `REQ-OUT-001` through `REQ-OUT-003`, `REQ-NBT-001` and `REQ-NBT-002`, `REQ-SEARCH-001`, `REQ-SEARCH-002`, `REQ-SEARCH-004`, `REQ-SEARCH-005`, `REQ-SEO-001`, `REQ-EVENT-001`, `REQ-EXPMODE-001`, `REQ-CALIB-001`, `REQ-ECON-002`, `REQ-ECON-003`, `REQ-FUTURE-001`, and `REQ-FX-001` through `REQ-FX-006`.

### Tests inspected and exercised

- `ancestry_mmm/tests/test_templates.py`
- `ancestry_mmm/tests/test_outcome_source_pack_v2.py`
- `ancestry_mmm/tests/test_source_pack_adoption_wp3.py`
- `ancestry_mmm/tests/test_template_downloads_wp8.py`

## Technical review findings

### Confirmed and implemented in the guide

- The three core logical domains are explicit. Multiple physical files per domain and multiple tables per workbook are explained.
- `market` is described as a row-level key, never a filename inference.
- Outcomes are documented as wide `period_start × market` data with a separate v2 dictionary and optional completeness metadata.
- Family History New, Winback, and DNA cross-sell are kept separate. DNA relationship and purchase-recipient partitions are not silently combined.
- GSA, Sign-up, Gross Bill Through, Bill Through, Net Bill Through, revenue, contribution, and LTV are described as distinct measures. NBT is not pre-populated or reconstructed from raw billing events.
- Activity is documented as tidy-long source data. The difference between `model_input_measure` (raw source measure) and `model_input_column` (post-pivot model-ready destination) is shown in a worked example.
- Model input, realised spend, physical response/delivery, currency, cost mappings, and response units are kept separate. TVRs, GRPs, impressions, clicks, spots, and visits are not treated as currency by default.
- `pooling_group_id` is described as a cross-market identity aid, not an instruction to pool.
- Paid, owned, and earned activity remain in the same logical Activity domain with explicit ownership and model role.
- Missing is repeatedly distinguished from observed zero. The guide does not recommend fake weekly rows or a default frequency conversion.
- The full Search object model is tabled. Brand/Non-Brand and Google/Bing leaves are explicit; PMax, Demand Gen, and YouTube are not auto-classified as Paid Search. A cap is a constraint, not realised spend. Residual incrementality is a model output, not an input.
- Candidate A, Google Trends, SEO/GSC, valuation, experiments, named events, FX, cost mappings, and future-variable roles are labelled as separate or advanced paths with their absent-data consequences and approval boundaries.
- RAG tables state column existence, value completeness, plain-English meaning, good example, purpose, missing-data consequence, consumer, format, and allowed blank cases. Status is always written, never conveyed by colour alone.

### Pre-existing implementation gaps documented, not fixed

1. **Medium — outcome example spelling mismatch.** `ancestry_mmm/data/template_downloads.py` emits `DNA cross-sell`, while the approved core constant is `DNA_CrossSell`. The current parser accepts both because it requires a supplied nonblank segment rather than normalising this label. The guide does not silently change the app or the existing downloadable template. Follow-up: reconcile the template/example spelling with the approved project vocabulary and add a regression test before making the value canonical.
2. **Medium — Search taxonomy mapping gap at the standard upload boundary.** `search_intent_group_id` and `search_platform` exist on the governed activity model and admin UI, but `activity_definitions_from_dictionary` currently maps the base dictionary fields and does not automatically apply those Search fields from a standard source workbook. The guide calls this out as a dedicated mapping/admin boundary and avoids claiming that a workbook upload alone creates the taxonomy. Follow-up: decide and implement a governed mapping contract, with parser round-trip and taxonomy validation tests, if analysts must supply these fields in the standard workbook.

No Critical or High issue was introduced or left hidden in the new deliverables. The two Medium findings are existing app/documentation boundary issues and are explicitly visible in the guide and inventory, as required by the brief.

## Executable validation

### Generator and static workbook checks

- `uv run python scripts/build_data_upload_guide_assets.py` — passed; regenerated the three workbooks, the HTML, and the inventory.
- `python -m py_compile scripts/build_data_upload_guide_assets.py` — passed.
- Each workbook opened with `openpyxl` and contained the expected sheets, an Excel table, formulas, data validations, examples, and RAG reference columns.
- Outcome workbook: 5 realistic pre-filled candidate rows plus blank rows; 32 formula cells; 3 dropdown validations.
- Activity workbook: 6 realistic pre-filled candidate rows plus blank rows; 32 formula cells; 2 dropdown validations.
- Context workbook: 5 realistic pre-filled candidate rows plus blank rows; 32 formula cells; 1 dropdown validation.
- All three builders include `COUNTIF` collision checks, override-to-final-ID formulas, dictionary previews, and formulas with no `#REF!`, `#NAME?`, or `#VALUE!` tokens.
- A Python mirror check passed for lower-casing, punctuation normalisation, underscore collapse, trimming, and rejection of `nan`, `none`, and `n/a` placeholders. It also confirmed the presence of formula-based `TEXTJOIN` and `COUNTIF` logic.
- Excel/LibreOffice was not installed in the environment, so Excel formula evaluation was checked structurally and with the mirror semantics; the workbooks are configured to recalculate on open. This is the only validation limitation of the builders.

### Real parser/canonicaliser checks

The current generated standard templates were passed through `build_standard_template`, `parse_standard_workbook`, and `canonicalize_standard_workbook` for all three core domains:

| Domain | Parser result | Canonicaliser result |
|---|---|---|
| Outcomes | valid; required tables recognised | valid; 10 outcome definitions loaded |
| Activity and Media | valid; required tables recognised | valid; model-input media frame shape `(2, 3)` |
| Context and External Factors | valid; required tables and optional events recognised | valid; native context frame shape `(2, 3)` |

The focused source-pack suite passed with the coverage plugin disabled so the result measures the selected tests rather than the repository-wide threshold:

```text
28 passed in 15.36s
```

The same focused selection without `--no-cov` also had 28 passing tests but exited on the repository’s configured `fail-under=30` threshold because a narrow subset produced 18.85% total coverage. That is a test-command coverage-policy result, not a failing source-pack assertion.

## HTML/browser validation

The guide was served from a temporary local HTTP server and exercised with Playwright.

- Page title: `Ancestry MMM Data Upload Guide`.
- Required anchors present: workflow, Outcomes, Activity, Context, advanced, FAQ, glossary, and review.
- FAQ count: 41 accordion questions, exceeding the 30-question minimum.
- RAG table count: 6, including core dictionaries, outcome completeness, events, and experiment evidence.
- No external images, fonts, stylesheets, or scripts are referenced; the guide is self-contained.
- Client-side section search was exercised and correctly hid unrelated sections.
- At a 390 × 844 viewport, document `scrollWidth` was 375 and there was no horizontal viewport overflow.
- The only console error was a temporary-server `404` for optional `/favicon.ico`; the guide itself loaded and ran without JavaScript errors. The temporary server and screenshot were removed after review.

## Review process and iterations

- Repository navigation used the local Graphify project map before broad source searches, followed by direct source inspection.
- A separate technical/analyst checklist pass was performed after generation. The environment exposed no sub-agent tool, so no separate sub-agent reviewer was available; this limitation is recorded rather than implied away.
- Iteration 1: schema inventory, handbook, and first builder generation.
- Iteration 2: fixed workbook table header/spacer generation and re-generated all assets.
- Iteration 3: added complete RAG reference columns, outcome completeness/events/evidence tables, and explicit Search/valuation/future-role boundaries; re-ran parser, workbook, and browser checks.
- Total implementation iterations: 3.

## Business decisions the guide does not invent

- The first UK outcome remains a project decision among approved outcome definitions; NBT is not a default.
- Exact FH NBT denominator and valuation mappings remain project/governance decisions.
- Historical valuation rates are weekly and draw-level when used; future value requires an explicit scenario assumption.
- FX provider/rate-set/rounding choices remain Finance-governed; a currency field alone does not convert anything.
- Frequency alignment method is not invented. Native monthly/quarterly observations remain native until a governed method is approved.
- Candidate A Search mediation/capacity, SEO causal role, experiment calibration, planning eligibility, and optimisation eligibility remain separately governed. Uploading a source or evidence row does not grant those permissions.

## Pass 3 — 2026-09-07 drift re-verification

Status: complete. This pass re-audits Pass 1/2's deliverables (still untracked in the worktree, dated 2026-09-03) against the current repository, on branch `docs/data-upload-guide-and-builders-review` created from `origin/main` at commit `706dcb33` ("UK production decisions and durable fitting", PR #351). Pass 1/2's own baseline was `2bd8e9a8`.

### Why a re-check was needed

`706dcb33` landed after the Pass 1/2 baseline and its title suggested exactly the area Part 9 of the review brief cares about most: official UK production NBT versus the historical-test 14-day rule. Two independent audits (one per domain group) re-diffed every source file Pass 1/2 cited, against the current branch.

### What actually changed since the Pass 1/2 baseline

- `ancestry_mmm/data/templates.py`, `template_downloads.py`, `core/outcomes.py`, and `core/outcome_group_totals.py` are **byte-identical** to the Pass 1/2 baseline. The core outcome/activity/context contract itself has not drifted.
- `core/search_intent_taxonomy.py` (+~625 lines) and `core/seo_visibility.py` (+~237 lines) added genuine new governed capability that Pass 1/2 could not have documented:
  - A governed deeper Non-Brand Search child-group catalogue (`governed_search_intent_groups`, `validate_search_intent_group_catalogue`, `resolve_search_intent_model_grain`, `roll_up_paid_search_reporting_hierarchy`). Only `brand_search`/`non_brand_search` are pre-approved; a new child starts `approval_status="draft"`, cannot be fitted at the same model grain as its approved parent, and has no planning eligibility or cost-bearing economic treatment until child-level observed data and governed cost support exist.
  - Multi-group SEO visibility (`seo_group_id`/`seo_group_name`, `SEO_GROUP_BRAND`/`SEO_GROUP_NON_BRAND`, default group `seo_visibility`) — Brand and Non-Brand (or an explicitly governed deeper child) can now be selected individually per market/week rather than blended into one series.
- Pass 1/2's own source list never cited `ancestry_mmm/core/net_billthrough.py`, `docs/uk_production_onboarding_runbook.md`, or `docs/approved_requirements/REQ-NBT-001.md` through `REQ-NBT-004.md` — the actual authority for the production-vs-historical-test-14-day distinction. These were present at the Pass 1/2 baseline too; they were simply outside that pass's source list. This pass reads them directly and grounds the guide's UK production section in them.

### Content gaps found in the Pass 1/2 guide and fixed in this pass

1. **No dedicated UK production NBT section.** The guide's structure (brief Part 6, item 16) calls for a "Production NBT-specific note where relevant" as its own thing; Pass 1/2 only touched NBT incidentally inside FAQ entries and RAG cells. Added a labelled, non-universal "UK production Net Bill Through (NBT)" block to the Outcomes section naming the three separate `fh_net_billthrough_count_new`/`_dna_cross_sell`/`_winback` outcomes, the GSA-stays-secondary rule, the production completeness/evidence bundle requirement, and an explicit statement that this is not the illustrative 14-day historical-test rule shown elsewhere in the guide.
2. **The illustrative 14-day maturity example read as if it could be a production default.** The `maturity_rule_description`/`completeness_or_maturity_policy` RAG rows and a new "common mistakes" bullet now explicitly flag the illustrative 14-day example as historical-test-only, not a production default.
3. **No mention of the new governed deeper Non-Brand Search capability.** Added a paragraph to the Search taxonomy section (and RAG note, FAQ entries) describing the governed catalogue, draft status, parent/child model-grain exclusivity, and the planning/cost-support gate on deeper children — matching the brief's "support deeper Non-Brand taxonomy where actual data supports it, not forced" instruction.
4. **No mention of the new SEO multi-group capability.** Added a paragraph to the SEO section (and FAQ entry) describing `seo_group_id`/`seo_group_name`, the Brand/Non-Brand grouping, and the default single-group fallback.
5. **The downloadable generic sample workbook still teaches GSA, not NBT.** Confirmed `template_downloads.py` is unchanged and still uses GSA ids as its worked example. This is legitimate (the generic sample is deliberately cross-project), but the guide previously didn't say so. Added an explicit FAQ entry and outcomes note so an analyst is not misled into thinking the generic sample already reflects the UK production choice.

### Two things checked and found already correct (no change needed)

- `definition_version`/`definition_fingerprint`: confirmed the guide's `outcome_completeness` RAG table (`COMPLETENESS_RAG`) never lists these as analyst-fillable completeness columns — they only appear in the `outcome_dictionary`-level `OUTCOME_RAG` table, which matches `templates.py`'s actual optional canonical definition columns. `definition_fingerprint` specifically is parser-computed and correctly never appears anywhere in the guide's field lists.
- `business_owner` (dictionary, optional, "owner who approves the definition") versus `source_owner` (completeness, required-if-sheet-present, "owner of the completeness metadata/source"): the existing plain-English descriptions were already distinct enough; no conflation found.

### The two Pass 1/2 Medium findings remain open, confirmed unchanged, still documented as boundaries (not app-code fixes)

1. `template_downloads.py` sample data still emits the display string `DNA cross-sell` versus the canonical `DNA_CrossSell` core constant. File is byte-identical to the Pass 1/2 baseline.
2. `activity_definitions_from_dictionary` (`templates.py:569-616`) still does not auto-map `search_intent_group_id`/`search_platform` from a standard workbook, even though the downstream Search-taxonomy machinery around it grew substantially in `706dcb33`. Confirmed by direct line inspection of the current `templates.py`.

This is a documentation review; per the brief's own scope note (see Pass 1/2 above), these stay documented analyst-facing boundaries rather than app/parser code changes.

### Changes made this pass

- `scripts/build_data_upload_guide_assets.py`: added the UK production NBT section, the deeper Non-Brand Search and SEO-group paragraphs, five new FAQ entries, RAG-cell caveats on the illustrative 14-day example, and updated the schema inventory generator (new baseline note, new authority sources, updated known-gaps list). No workbook formula, dropdown, or table-structure code was touched — RAG data content only, since `add_rag_reference` feeds the same content into both the HTML and the three workbooks' Reference sheets from one source.
- Regenerated `Ancestry_MMM_Data_Upload_Guide.html`, all three `.xlsx` builders, and `data_upload_guide_schema_inventory.md` from the updated generator.
- Added `ancestry_mmm/tests/test_data_upload_guide_assets.py`: a guard test asserting the guide's controlled-value lists (variable classes, activity ownership/planning-eligibility/funnel-stage enums, Search taxonomy baseline ids, SEO group constants, the three UK NBT outcome ids) actually match the live governed constants, and that the generator produces all four expected output files. Spot-checked by deliberately breaking one value outside the tracked test file — the assertion correctly failed.

### Re-validation evidence

- **Generator**: `uv run python scripts/build_data_upload_guide_assets.py` — passed, regenerated all four outputs.
- **Contrast/browser QA** (`scripts/check_data_upload_guide_contrast.py` against the regenerated HTML served locally, Chromium via Playwright): `audited: 1626, contrast_failures: 0, missing_anchors: 0, duplicate_ids: 0, console_errors: 0, page_errors: 0, faq_open: true, search_works: true`, no horizontal overflow at 1440×900, 1280×720, or 390×844.
- **Excel COM validation** (Microsoft Excel 16.0 via COM, `Visible=false`/`DisplayAlerts=false`, run against copies so the shipped workbooks stay free of test rows): all three workbooks opened with 4 sheets, force-recalculated with zero formula-error tokens (`#REF!`/`#NAME?`/`#VALUE!`/`#N/A`/`#DIV/0!`/`#NULL!`/`#NUM!`), correctly computed a normalised ID from a populated + whitespace-padded test row (e.g. Outcome: `family_history_fh_gsa_new_test`), correctly flagged an exact-duplicate row (`AMBER: duplicate final ID`), saved, closed, reopened, and the computed Final ID persisted unchanged after reopen. No repair prompt or recovery log was produced. No stray `EXCEL.EXE` process remained afterward (only the pre-existing user workbook `Analysis FINAL - NEW 2.xlsm`, untouched).
- **Parser/canonicaliser round-trip**: `build_standard_template` → `parse_standard_workbook` → `canonicalize_standard_workbook` succeeded for Outcomes (2 sheets), Activity and Media (2 sheets), and Context and External Factors (3 sheets).
- **Regression tests**: `uv run python -m pytest --no-cov -q ancestry_mmm/tests/test_templates.py ancestry_mmm/tests/test_outcome_source_pack_v2.py ancestry_mmm/tests/test_source_pack_adoption_wp3.py ancestry_mmm/tests/test_template_downloads_wp8.py` — `28 passed in 15.78s`.
- **New guard test**: `ancestry_mmm/tests/test_data_upload_guide_assets.py` — `8 passed in 13.49s`.

### Scope note

This pass changed only documentation/tooling generator source and its generated outputs, plus one new test file. No application parser, schema, model, upload contract, or governance behaviour was changed, consistent with Pass 1/2's scope.

## Pass 4 — 2026-09-07 usability simplification

Status: complete. Full detail lives in the dedicated `Ancestry_MMM_Data_Upload_Guide_Simplification_Report.md`; this entry is a short pointer for the pass log.

The user identified that Pass 3's guide, while accurate, still read like a schema dump — every field equally prominent, no distinction between essential and governance-only. This pass re-derived field necessity from the real consuming code (not the guide) across three background audits (upload-route inventory, Outcome dictionary necessity + FH LTR contract, Activity dictionary necessity), then restructured the HTML around essential/conditional/optional tiers with progressive disclosure — full technical RAG tables kept, demoted into collapsible "Full technical field reference" blocks per domain.

Headline finding: five Activity v2 dictionary columns (`model_input_unit`, `model_input_kind`, `spend_column`, `response_unit_column`, `response_unit`) are currently write-only in the standard upload path — `source_pack_adoption.py` itself says "the source upload does not apply it automatically." The guide now tells analysts this directly rather than describing fields that currently have no effect. Also added: a top-of-guide "what do I actually need to upload" checklist and 9-row upload-type table, a dedicated FH LTR/DNA-revenue section (48-month rule, division-not-multiplication semantics, denominator validation), and an explicit note that `date_basis`/`maturity_required` are schema-present but not read by any transformation today.

Re-validated: generator runs clean; contrast/Playwright QA at 3 viewports — 0 failures (two real regressions were found and fixed during this pass: a long unbroken `<code>` filename overflowing the page at 390px, fixed via `overflow-wrap:anywhere`; and the client-side search check losing its match because the only occurrence of "outcome completeness" had moved inside a collapsed detail block, fixed by restoring the phrase to visible prose); Excel COM validation on all three regenerated workbooks (logic unchanged, evidence re-confirmed identical to Pass 3); parser/canonicaliser round-trip for all three domains; existing 28-test regression suite plus the guard test (now 10 assertions, 2 new) — 38 passed. A manual "confused analyst" walkthrough answered all 10 of the brief's test questions using only the new HTML, surfacing and fixing one real gap (no clear "what do I do if validation fails" answer — a new FAQ entry closes it).

No application parser, schema, model, or governance behaviour was changed. The three Excel ID builders were not redesigned — only regenerated (bytes differ only by embedded timestamp, as in Pass 3).

## Pass 5 — 2026-09-08 Dictionary Builders (replace the ID-only builders)

Status: complete. Following the merged `Ancestry_MMM_Upload_Schema_Necessity_Review.md` (design authority for this pass), the three narrow ID builders were replaced with full Dictionary Builder workbooks — `Ancestry_MMM_Outcome_Dictionary_Builder.xlsx`, `Ancestry_MMM_Activity_Dictionary_Builder.xlsx`, `Ancestry_MMM_Context_Dictionary_Builder.xlsx` — each producing the complete, upload-ready dictionary row (not just the ID) via a `START_HERE` / `BUILDER` / `DICTIONARY_OUTPUT` / `ALLOWED_VALUES` / `EXAMPLES` sheet structure. The old ID-only workbooks and their generator functions were removed (`git rm`); nothing in the repo depended on them beyond the now-updated guard test.

Every field was tiered (required / conditional / optional-advanced) per the necessity review, with dropdowns sourced by importing the live governed constants directly (`ancestry_mmm.core.activities`, `.coverage`, `.outcomes`, `.search_intent_taxonomy`, `ancestry_mmm.data.templates`) rather than hand-copying values — `DICTIONARY_OUTPUT`'s column list and order is derived programmatically from `templates.py`'s own schema constants for the same reason.

**Mandatory end-to-end validation (builder output → real parser) found and fixed three schema-acceptance bugs the necessity review's own tables did not anticipate** — recorded as a dated erratum at the top of `Ancestry_MMM_Upload_Schema_Necessity_Review.md`:

1. `segment_dimension` (Outcomes) is value-required today (`outcome_definitions_from_dictionary`), not merely column-required as the review's table implied by grouping it with the blank-safe outcome-group fields. Fixed by defaulting a blank BUILDER cell to the real `unspecified` enum member in `DICTIONARY_OUTPUT`, not leaving it truly blank.
2. Activity's `activity_ownership` and `market` dictionary columns are value-required (`activity_definitions_from_dictionary`) and were both required tier in the builder already, but missing from the necessity review's and guide's field tables — added.
3. Five of Activity's six "inert-but-required" columns (`funnel_stage`, `marketing_objective`, `product_advertised`, `message_type`, `platform` — not `pooling_group_id`) are value-required, not just column-required; a truly blank cell is rejected by `activity_definitions_from_dictionary` even though nothing reads the value. Fixed by defaulting blanks to `unclassified` (funnel_stage) or `not specified` (the rest) in `DICTIONARY_OUTPUT`.
4. `standard_sheet_specs` requires the *entire* v2 extra-column set as headers once any one v2 marker column is present — meaning Activity's five write-only columns and Context's `unit` cannot be dropped from the template while `currency`/`effective_from`/`effective_to` (Activity) or `source`/`scope` (Context) are kept, without the whole sheet being rejected as "missing required column(s)." Fixed by keeping these columns' headers in `DICTIONARY_OUTPUT`, always blank, never asked for in `BUILDER`.

**Re-validation evidence**:
- Generator (`python -m scripts.build_data_upload_guide_assets`) runs clean, producing the HTML guide, inventory, and three Dictionary Builders; the three old ID-builder `.xlsx` files no longer exist.
- `ruff check` and `ruff format --check` both clean on the two changed source files.
- `ancestry_mmm/tests/test_data_upload_guide_assets.py` — 21 passed, including new tests for exact `DICTIONARY_OUTPUT` column/order match against live schema constants, that write-only/unused fields never appear as `BUILDER` inputs, that `role` (Context) has no dropdown, and three parser round-trip tests (`parse_standard_workbook` → `canonicalize_standard_workbook`, zero errors, definitions/metadata returned) proving Dictionary Builder output is genuinely accepted end to end for all three domains.
- Excel COM validation (Microsoft Excel via COM, run against scratch copies, never the shipped files): all three workbooks open with the 5 expected sheets, force-recalculate with zero formula-error tokens, correctly compute a normalised Generated/Final ID from a populated test row, correctly flag an exact-duplicate row and a missing-required-field row in plain English, `DICTIONARY_OUTPUT` mirrors `BUILDER` live, list-validation dropdowns are present (`Validation.Type == xlList`), and all of the above persists after save/close/reopen.
- Contrast/Playwright QA on the regenerated HTML: 1691 elements audited, 0 contrast failures, 0 missing anchors, 0 duplicate ids, 0 console/page errors, FAQ and search both functional, 0 horizontal overflow at 1440×900/1280×720/390×844.

**HTML alignment**: each domain section now has a "Dictionary Builder" subsection (what it does / what to fill in / what's generated / dropdown fields / acceptable values / optional-advanced fields / where the output goes), and the two FAQ entries that referenced "the ID builder" now reference the Dictionary Builder and its `Manual override`/`DICTIONARY_OUTPUT` mechanics; a new FAQ entry clarifies the builders are optional convenience, not a requirement. While fixing the field-tier tables to match the erratum above, `activity_ownership` and `market` were also added to the Activity "Fields you must fill in" table (previously missing entirely), and `segment_dimension`'s and the five inert Activity fields' conditional/optional descriptions were corrected to say a blank cell is not literally accepted, rather than implying it is.

No application, parser, schema, dataclass, or model-mathematics code was changed — this pass is documentation/tooling generator source and its generated outputs, plus test additions, exactly as scoped.

### Pass 5 addendum — 2026-09-08 technical-reference cleanup (pre-merge review feedback)

Review of PR #362 found the full technical reference (`OUTCOME_RAG`/`ACTIVITY_RAG`/`CONTEXT_RAG`) still described several fields as if they had live effect, contradicting the merged necessity review and the new builders themselves. Fixed, all against `Ancestry_MMM_Upload_Schema_Necessity_Review.md` as authority:

- `date_basis`/`maturity_required` (Outcomes): re-tagged `GREY — Legacy/unused` instead of `AMBER — Needed for some uses`; description rewritten to state plainly they are not read by any current transformation, matching the Outcome Dictionary Builder's decision to omit them from `DICTIONARY_OUTPUT` entirely.
- The five write-only Activity v2 columns (`model_input_unit`, `model_input_kind`, `spend_column`, `response_unit_column`, `response_unit`): re-tagged `GREY — Currently write-only`; description rewritten to state the value is parsed into a review-status record and never automatically applied, with the real configuration named (Channel Media Units, Curve Generation).
- Six Activity reporting/display-only columns (`pooling_group_id`, `platform`, `marketing_objective`, `funnel_stage`, `product_advertised`, `message_type`): descriptions rewritten to state plainly they are never read by fit, canonicalisation, or planning/optimisation code.
- Context's `variable_class`/`native_frequency`: descriptions rewritten to disclose that Page 15 (Data Coverage) re-asks for and re-defaults both regardless of what is uploaded.
- Context's `role`: status changed to `RED — Must provide, not currently enforced`; description rewritten to state no enum exists in code today despite being called governed in a comment.
- The main (non-collapsed) "Fields you must fill in" table for Context was carrying a contradictory, more optimistic description of the same three fields than the technical reference below it — corrected to match.

**Paid Search builder simplification**: the Activity Dictionary Builder previously asked for `search_platform`/`search_intent_group_id` as separate inputs purely to help build `activity_id`, even though neither is an `activity_dictionary` column today (`activity_definitions_from_dictionary` still doesn't map them from a standard workbook). No technical reason was found to keep them — `platform` and `campaign_type` are genuine dictionary columns already collected, produce IDs consistent with every other example in the guide (e.g. `paid_search_google_brand`), and avoid encoding taxonomy semantics into the ID that the uploaded dictionary itself doesn't carry. Removed both from `BUILDER`'s headers, dropdowns, ID-token inputs, and `ALLOWED_VALUES`; `platform` gained a soft Google/Bing suggestion dropdown. HTML prose (`START_HERE`, the guide's Dictionary Builder subsection) updated to match, retaining a clear note that the governed Search-taxonomy mapping is still configured separately after upload until the known auto-mapping gap is closed.

Six new regression tests lock these corrections in (RAG status/wording assertions per field group, a check that `BUILDER` never offers `search_platform`/`search_intent_group_id`, and a check that exactly 3 identity inputs — not 5 — get hidden ID-token columns). Generator docstring and this test file's docstring updated from "ID builders" to "Dictionary Builders".

Re-validated: generator runs clean; `ruff check`/`ruff format --check` clean; `ancestry_mmm/tests/test_data_upload_guide_assets.py` — 28 passed (6 new); broader regression set (`test_templates.py`, `test_outcome_source_pack_v2.py`, `test_source_pack_adoption_wp3.py`, `test_template_downloads_wp8.py` plus the guide tests) — 56 passed; Excel COM validation on all three regenerated workbooks (zero formula errors, correct ID/status computation, `paid_search_google_brand_test` now generated cleanly from platform+campaign_type alone, persists through save/reopen); Playwright contrast/functional QA — 1689 elements audited, 0 failures, 0 horizontal overflow at all 3 viewports.

No application, parser, schema, dataclass, or model-mathematics code was changed in this addendum either.
