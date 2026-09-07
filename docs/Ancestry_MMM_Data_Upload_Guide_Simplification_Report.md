# Ancestry MMM data-upload guide — usability simplification report

Status: complete. This report covers a from-first-principles usability rewrite of `docs/Ancestry_MMM_Data_Upload_Guide.html`. It does not change the application parser, schema, model, or upload behaviour, and it does not redesign the three Excel ID builders — only the HTML guide and its generator (`scripts/build_data_upload_guide_assets.py`) changed.

## Why this pass exists

PR #360 made the guide *accurate* against current code. It did not make the guide *usable*: every field got equal prominence in one large RAG table per domain, with no distinction between "the app cannot work without this" and "this exists for governance and can wait." This pass is a contract-first necessity review — not a copy-edit — that re-derives what the application genuinely needs from the real parser, validators, and consuming code, then rewrites the guide around that.

## 1. Fields reviewed

### Outcomes (`outcome_dictionary`)

| Tier | Fields |
|---|---|
| Essential | `outcome_id`, `source_column`, `product`, `metric_key`, `metric`, `segment` (plus `period_start`, `market` on the raw `outcomes` sheet) |
| Conditionally essential | `segment_dimension`, `outcome_group_id`/`outcome_group_label`/`outcome_family_key`/`group_aggregation` (only for governed outcome groups — `core/outcomes.py:1418-1515`), `role`/`included_in_fit`/`include_in_default_reporting`/`include_in_official_total`/`include_in_value`/`include_in_optimisation` (eligibility flags, `core/outcomes.py:888-906`), `definition_version`/`event_definition`/`cohort_or_attribution_basis`/`completeness_or_maturity_policy`/`exclusions`/`reconciliation_source`/`business_owner` (official-approval-only, `outcome_approval.py:361-380`), `value_weight`/`value_currency` (value/ROI objective only) |
| Optional / governance-reporting metadata | `unit`, `aggregation_type` (usually auto-derived from `metric_key`, `core/outcomes.py:551-563`), `effective_from`, `effective_to` |
| **Redundant-looking but currently required by schema** | none in this domain — all schema-required columns (`outcome_id` through `group_aggregation`) have at least a conditional behavioural use; the group fields are schema-required-as-a-column but their *values* are correctly optional/blank when no group is used |
| **Schema-present but not currently used by the app** | `date_basis`, `maturity_required` — `core/outcomes.py:488-490` states directly: "schema and validation only; no transformation reads or computes these fields yet." The guide now says this explicitly rather than asking an analyst to carefully fill in a field nothing reads. |

### Activity and Media (`activity_dictionary`)

| Tier | Fields |
|---|---|
| Essential | `activity_id`, `channel` (also the fallback source for `model_input_column` when it's blank), `intended_model_role`, `model_input_column`, `model_input_measure`, `economic_treatment`, `planning_eligibility`, `source` |
| Conditionally essential | `activity_ownership` (only changes behaviour for `external_event` + `optimisable`, `activities.py:182,207-211`), `campaign_type` (Search-taxonomy validation gate only, `activities.py:80-85,221-230`), `search_intent_group_id`/`search_platform` (Search taxonomy only, and still not auto-mapped from a standard workbook — see finding below) |
| Optional / reporting-only metadata | `pooling_group_id`, `funnel_stage`, `marketing_objective`, `product_advertised`, `message_type`, `platform` — confirmed never read by fit, canonicalisation, or planning/optimisation code; only reporting rollups and causal-graph display metadata read them |
| **Flagged as currently inert (the biggest finding of this pass)** | `model_input_unit`, `model_input_kind`, `spend_column`, `response_unit_column`, `response_unit` — these v2 optional dictionary columns parse into `activity_semantic_mappings` (`templates.py:619-660`), which `source_pack_adoption.py:152-181` turns into a review-status message that literally says *"the source upload does not apply it automatically."* The real, governed unit/cost-mapping configuration an analyst must actually do lives in separate objects (`ChannelMediaUnitConfig` in Channel Media Units, `MediaInputSpec` in Curve Generation). Filling these five dictionary columns in has no functional effect today. The guide now tells analysts this directly instead of asking them to carefully fill in fields that currently do nothing. |

### Context and External Factors (`variable_dictionary`)

Essential: `variable_id`, `value`, `native_frequency`, `variable_class`, `role` (plus `period_start`, `market` on `context_data`). Conditional: `source`, `scope` (only matter once a variable goes through "adoption" review). Optional: `effective_from`, `effective_to`, `unit`.

### Outcome Valuation (FH LTR / DNA revenue) — separate upload, confirmed correctly isolated

Required columns unchanged and confirmed: `valuation_kind, market, week, segment, denominator_outcome_id, quality_status, segment_dimension, aggregate_value, currency, source, source_version, schema_version, horizon_months`. All 13 are effectively required by the record's own validation (`core/outcome_valuation.py`); none are decorative.

## 2. Simplifications made

- **Restructured every domain section** from a single flat RAG table into: purpose → do-I-need-it → what one row means → sheets → **Fields you must fill in** (essential only, 4-column: field / meaning / what to enter / example) → **Fields you may need** (conditional, with an explicit "when do I need this?" column) → **Optional metadata** (compact, de-emphasised) → worked example → common mistakes → a collapsible **"Full technical field reference"** holding the complete RAG table for power users and auditors. Nothing was deleted — everything from the old RAG tables is still present, just reordered and progressively disclosed.
- **Added a "What do I actually need to upload?" section at the very top** of the guide (before any domain detail), with an upload-type table covering all 9 distinct upload surfaces the application exposes (Outcomes, Activity and Media, Context, Outcome Valuation, Experiment Evidence, Candidate A, Google Trends anchor, SEO/GSC, demo data), each tagged with whether it's required, optional, or feature-specific, and where to get it.
- **Added a dedicated "Optional: FH LTR and DNA revenue" section**, stating plainly it is not part of the Outcomes workbook, with its real grain, its real required columns, what `aggregate_value` actually does (divided against the denominator's observed count, never multiplied or invented), and the 48-month rule.
- **Added an honest callout for the five currently-inert Activity dictionary columns** (see finding above) instead of writing lengthy correct-sounding explanations for fields that do nothing today.
- **Added a callout that `date_basis`/`maturity_required` are schema-present but not currently used**, so analysts stop treating them as meaningful.
- **Trimmed the FAQ** from 47 entries to 27, removing ones that now duplicate a table row (e.g. "What is model_input_measure?", "What are the context variable classes?") and adding two genuinely new ones that were missing: what to do when an upload is rejected/warned, and (via the upload-type table) where FH LTR fits.
- **Removed the separate "Minimum checklist" / "Add these when available" lists** per domain — they overlapped almost entirely with the new required/conditional tables and were dropped to avoid saying the same thing twice, per the brief's own instruction to avoid repeated explanations.
- **Renamed "Advanced boundaries" to "Add these later"**, reordered its content to lead with "do I need this now? (no)" for each add-on, and moved the deep Search-taxonomy object-model explanation later in that section rather than up front.
- Kept every governed enum value, every requirement-ID reference, and every UK production NBT fact from the accuracy pass — this is a restructuring and prioritisation pass, not a fact-removal pass.

## 3. Controlled values

Every field shown in a "Fields you must fill in" or "Fields you may need" table that has a fixed set of accepted values states them inline in the "what to enter" / "what it means" column (for example `intended_model_role`: intervention, mediator, demand_capture, control, or event; `planning_eligibility`: optimisable, scenario_only, fixed, or excluded; `variable_class`: the five approved classes). The complete, exhaustive allowed-value list for every field (including ones not prominent enough to repeat inline) remains in each domain's collapsible "Full technical field reference," which reuses the same `OUTCOME_RAG`/`ACTIVITY_RAG`/`CONTEXT_RAG`/`COMPLETENESS_RAG` data structures the three Excel builders' Reference sheets are generated from — one source of truth, not a hand-duplicated list. Guard tests (`test_activity_ownership_rag_lists_every_governed_value`, `test_planning_eligibility_rag_lists_every_governed_value`, `test_funnel_stage_rag_lists_every_governed_value`, `test_variable_class_dropdown_matches_governed_classes`) already assert this stays in sync with the live governed constants; unchanged by this pass.

## 4. Remaining schema concerns (not fixed here — documentation pass only)

1. **`model_input_unit`, `model_input_kind`, `spend_column`, `response_unit_column`, `response_unit` are write-only in the standard activity dictionary.** This is a genuine schema/API design concern, not a documentation problem: an analyst can fill these in believing they configure units and cost mapping, and nothing happens. Recommendation for a future pass: either wire `activity_definitions_from_dictionary` to actually apply these into `ChannelMediaUnitConfig`/`MediaInputSpec` on adoption, or remove them from the standard dictionary template and point analysts straight at the UI screens that actually consume this information. **Classification: SCHEMA/API DESIGN PROBLEM.**
2. **`date_basis`/`maturity_required` are schema-present but functionally inert today** (`core/outcomes.py:488-490`). Low priority since they don't mislead analysts about a *different* screen doing the real work — they're just unused. **Classification: POSSIBLE REDUNDANT FIELD**, worth revisiting once maturity-rule automation is actually built.
3. **`search_intent_group_id`/`search_platform` still aren't auto-mapped from a standard workbook** (`activity_definitions_from_dictionary`, `templates.py:569-616`), even though the governed Search-taxonomy machinery around them grew substantially in a recent change. Carried over unchanged from the PR #360 accuracy pass — still a documented boundary, not fixed here. **Classification: DOCUMENTATION PROBLEM (already handled — clearly labelled boundary in the guide), with an underlying SCHEMA/API DESIGN gap worth closing eventually.**
4. **`template_downloads.py` sample data spelling** (`DNA cross-sell` vs. canonical `DNA_CrossSell`) — unchanged, still open, still documented as a known boundary. **Classification: POSSIBLE REDUNDANT/inconsistent FIELD VALUE**, not an application bug (the parser tolerates both).

None of these were changed in application/schema code in this pass, consistent with the brief's scope rule.

## 5. Readability review

**Human review (mandatory, primary check).** A manual "confused analyst" pass was run against the finished guide, answering all ten of the brief's test questions using only the HTML:

| Question | Answered where |
|---|---|
| What file do I need? | "What do I actually need to upload?" section, first thing after the hero |
| Where do I download it? | Upload-type table's "Where to get it" column |
| Which sheet do I fill in? | Each domain's "Sheets in this workbook" subsection |
| What does one row mean? | Each domain's "What does one row mean?" subsection |
| Which columns are mandatory? | "Fields you must fill in" table, essential fields only |
| Which columns can I ignore? | "Optional metadata" table, plus explicit inert-field and schema-present-but-unused callouts |
| What exact values can I choose? | Inline in the required/conditional tables, exhaustively in the collapsible technical reference |
| Where does my actual time-series data go? | The raw sheet named in "Sheets in this workbook," shown in the worked example |
| What happens after I upload it? | "How uploading works" numbered steps |
| What should I do if validation fails? | New FAQ entry added specifically to close this gap during the walkthrough |

One real gap was found and fixed during this walkthrough: the original rewrite draft did not clearly answer "what do I do if validation fails" — a new FAQ entry was added to close it.

**Automated heuristic (supporting evidence only, per the brief's own instruction that automated scoring is not a substitute for human review).** A stdlib-only Flesch-Kincaid approximation (no `textstat` dependency available or added) was run over the visible prose (excluding `<code>`/`<pre>` identifiers):

| | Pre-simplification guide | This pass |
|---|---|---|
| Average sentence length | 11.9 words | 12.7 words |
| Average syllables/word | 1.78 | 1.69 |
| Approx. Flesch-Kincaid grade | 10.0 | 9.3 |

The word-level score moves only modestly, because a technical upload guide still legitimately uses domain vocabulary (reconciliation, optimisation, canonicalisation) inside its field tables. The real improvement this pass makes is structural, not lexical: an analyst now sees "3 files, here's what's essential" before any schema detail, essential/conditional/optional fields are visually and positionally separated instead of uniformly RAG-coded, and the previously prominent full technical tables are still complete but demoted into collapsible, clearly-labelled "for power users and auditors" sections. That structural change is what the manual walkthrough actually tests, and is the more reliable measure of usability for this kind of document.
