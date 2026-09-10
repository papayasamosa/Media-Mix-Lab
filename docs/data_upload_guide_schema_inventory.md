# Data-upload guide schema inventory

Status: temporary source-backed inventory retained with the guide for traceability.
Repository baseline (pass 1/2, 2026-09-03): `2bd8e9a8a197f121d1176e61566d6122313e44e9`.
Repository baseline (pass 3 drift re-verification, 2026-09-07): `origin/main` after `706dcb33` ("UK production decisions and durable fitting", PR #351). `templates.py`, `template_downloads.py`, `outcomes.py`, and `outcome_group_totals.py` are byte-identical across both baselines — no drift in the core outcome/activity/context contract itself. The drift found in pass 3 is additive governed capability in `core/search_intent_taxonomy.py` and `core/seo_visibility.py`, plus production-NBT authority sources (`core/net_billthrough.py`, `docs/uk_production_onboarding_runbook.md`, `docs/approved_requirements/REQ-NBT-001..004.md`) that pass 1/2 did not cite. See `Ancestry_MMM_Data_Upload_Guide_REVIEW.md` for the full pass-3 findings.

## Logical domains and physical tables

| Logical domain | Required sheet(s) | Optional sheet(s) | Grain / source shape | Governing code |
|---|---|---|---|---|
| Outcomes | `outcomes`, `outcome_dictionary` | `outcome_completeness` | Wide; one row per `period_start × market`; one source column per outcome | `ancestry_mmm/data/templates.py`, `core/outcomes.py` |
| Activity and Media | `activity_data`, `activity_dictionary` | — | Tidy/long; at minimum `period_start × market × activity_id`; raw measures remain separate | `ancestry_mmm/data/templates.py`, `core/activities.py`, `core/media_units.py` |
| Context and External Factors | `context_data`, `variable_dictionary` | `events` | Tidy/long; native-frequency observations | `ancestry_mmm/data/templates.py`, `core/coverage.py`, `core/frequency_alignment.py` |
| Experiment Evidence | `experiment_evidence` | — | Evidence registry rows; not a fit input by upload alone | `ancestry_mmm/data/templates.py`, `core/experiments.py`, `application/experiment_service.py` |

Logical domain does not mean one file. `source_pack_adoption.py` accepts multiple physical files per domain and merges only compatible keys; a workbook can hold multiple recognised sheets. `market` is always a row-level field.

## Current v2 contracts

### Outcomes

- Required dictionary v2 columns: `outcome_id`, `source_column`, `product`, `metric_key`, `metric`, `segment_dimension`, `segment`, `outcome_group_id`, `outcome_group_label`, `outcome_family_key`, `group_aggregation`.
- Optional canonical definition columns accepted by the parser: `unit`, `aggregation_type`, `date_basis`, `maturity_required`, `role`, `included_in_fit`, `include_in_default_reporting`, `include_in_official_total`, `include_in_value`, `include_in_optimisation`, `definition_version`, `event_definition`, `cohort_or_attribution_basis`, `completeness_or_maturity_policy`, `exclusions`, `reconciliation_source`, `business_owner`, `effective_from`, `effective_to`, `value_weight`, `value_currency`.
- Optional completeness columns: `outcome_id`, `data_as_of_date`, `model_start_week`, `model_end_week`, `latest_complete_net_billthrough_week`, `maturity_rule_description`, `source_owner`.
- `source_column` must exactly exist in `outcomes`; definitions are not inferred from IDs or column names. GSA, Sign-up, Gross Bill Through, Bill Through, Net Bill Through, revenue, contribution, and LTV remain distinct. Supplied weekly NBT is accepted only under the approved definition/completeness boundary; raw event-level NBT reconstruction is not an upload path.
- `outcome_group_id` is semantic grouping/reconciliation metadata. A group does not automatically choose components, total-only, or descriptive fit treatment.
- UK production NBT boundary (`docs/uk_production_onboarding_runbook.md`, `REQ-NBT-001..004`, `core/net_billthrough.py`): three separate FH NBT outcomes (`fh_net_billthrough_count_new`, `fh_net_billthrough_count_dna_cross_sell`, `fh_net_billthrough_count_winback`); GSA stays a distinct secondary measure and is never used to reconstruct NBT; production requires its own maturity/completeness evidence bundle (definition, exclusions, reconciliation source, `data_as_of_date`, source fingerprint) and is not the bounded historical-test 14-day rule. `definition_version`/`definition_fingerprint` on completeness metadata are parser-computed from the matching `outcome_dictionary` row (`templates.py`), not analyst-supplied completeness columns — confirmed still accurate in the current guide.

### Activity and Media

- Required raw columns: `period_start`, `market`, `activity_id`.
- Required base dictionary columns: `activity_id`, `market`, `pooling_group_id`, `channel`, `platform`, `campaign_type`, `marketing_objective`, `funnel_stage`, `product_advertised`, `message_type`, `activity_ownership`, `intended_model_role`, `model_input_column`, `model_input_measure`, `economic_treatment`, `planning_eligibility`, `source`.
- v2 extra dictionary columns: `model_input_unit`, `model_input_kind`, `spend_column`, `response_unit_column`, `response_unit`, `currency`, `effective_from`, `effective_to`.
- The parser selects `model_input_measure` from raw data and writes to `model_input_column` at the canonical wide boundary. v2 physical mappings are retained for review; they are not silently turned into a cost contract.
- `pooling_group_id` is identity only and does not force pooling. Paid, owned, earned, and external-event records share the Activity domain but use explicit ownership and model role. Missing is not zero.
- Since the 2026-09-03 baseline, `core/search_intent_taxonomy.py` added a governed deeper Non-Brand Search child-group catalogue (`governed_search_intent_groups`, `validate_search_intent_group_catalogue`, `resolve_search_intent_model_grain`, `roll_up_paid_search_reporting_hierarchy`): only `brand_search`/`non_brand_search` are pre-approved; a child starts `approval_status="draft"`, cannot be fitted at the same model grain as its parent, and has no planning/cost-bearing treatment until child-level observed data and governed cost support exist. As of 2026-09-10, `activity_definitions_from_dictionary` (`templates.py`) does auto-map `search_intent_group_id`/`search_platform` from a standard workbook when the two columns are present (optional - most activities are not Paid Search); catalogue-level cross-validation against the approved taxonomy (unknown group id, parent/child double-fit) still happens at Channel Media Units save time, the same timing as a UI-entered value.

### Context and External Factors

- Required raw columns: `period_start`, `market`, `variable_id`, `value`, `native_frequency`.
- Required dictionary columns: `variable_id`, `variable_class`, `native_frequency`, `role`.
- v2 extras: `source`, `scope`, `effective_from`, `effective_to`, `unit`.
- Variable classes: `flow_count`, `stock_level`, `rate_index`, `survey_measurement`, `event_flag`. Approved future roles are documented in the guide. No default monthly/quarterly-to-weekly conversion currently exists; native frequency is preserved and later alignment must be governed.
- Optional `events` columns: `event_id`, `event_name`, `start_date`, `end_date`. Event family/treatment is not inferred.

## Special paths verified

| Feature | Current source shape / boundary | Consequence if absent |
|---|---|---|
| Candidate A Search | Dedicated observations: `period_start`, `market`, `paid_search_delivery`, `paid_search_cap`, `organic_search_capture`, `direct_navigation_capture`; complete weekly market grid; non-negative finite values; delivery/cap rule | Candidate A mediation/capacity output is unavailable; upload does not infer demand or calibration |
| Google Trends Candidate A | Dedicated weekly `week`, `raw_index` plus query metadata; 0–100 relative index; suppressed zero semantics | No Candidate A demand anchor |
| SEO/GSC | Dedicated `market`, `week`, `dimension_label`, `position`, `impressions`, optional `clicks`; impression-weighted inverse-position visibility; since 2026-09-03, `seo_group_id`/`seo_group_name` (`SEO_GROUP_BRAND`/`SEO_GROUP_NON_BRAND`, default `seo_visibility`) support selecting Brand/Non-Brand/deeper groups individually per `core/seo_visibility.py` | No SEO visibility pathway; not a proxy for organic capture |
| Outcome valuation | Separate `valuation_kind`, `market`, `week`, `segment`, `denominator_outcome_id`, `quality_status`, `segment_dimension`, `aggregate_value`, `currency`, `source`, `source_version`, `schema_version`, `horizon_months` | Count fit can proceed; economic reporting/ROI is blocked |
| Experiment evidence | `experiment_id`, `activity_id`, `market`, `start_date`, `end_date` at upload; adoption needs method/estimand/estimate/uncertainty/source/status | Evidence remains source-only and does not calibrate a fit |

## Authority and inspection record

    - Implementation brief: `D:\ORIGIAL D DRIVE\008 Ancestry UK MMM - 2026\LLM_Instructions_Build_Ancestry_MMM_Data_Upload_Guide_v2.md`.
- Approved requirements: REQ-DATAIN-001, REQ-COVERAGE-001, REQ-ACTIVITY-001, REQ-OUT-001/002/003, REQ-NBT-001/002/003/004, REQ-SEARCH-001/002/004/005, REQ-SEO-001, REQ-EVENT-001, REQ-EXPMODE-001, REQ-CALIB-001, REQ-ECON-002/003, REQ-FUTURE-001, and REQ-FX-001–006.
- Templates and parser: `ancestry_mmm/data/templates.py`, `template_downloads.py`, `loader.py`, `source_pack_adoption.py`, `source_inventory.py`.
- UI: `ancestry_mmm/pages/01_Data_Upload.py`, dedicated Search/SEO/valuation/evidence paths in application/core.
- UK production authority (pass 3): `docs/uk_production_onboarding_runbook.md`, `docs/approved_requirements/REQ-NBT-001.md` through `REQ-NBT-004.md`, `ancestry_mmm/core/net_billthrough.py`.
- Search/SEO governed-capability sources (pass 3): `ancestry_mmm/core/search_intent_taxonomy.py`, `ancestry_mmm/core/seo_visibility.py`, `ancestry_mmm/core/activities.py`.
- Tests inspected: `ancestry_mmm/tests/test_templates.py`, `test_outcome_source_pack_v2.py`, `test_source_pack_adoption_wp3.py`, and `test_template_downloads_wp8.py`.

## Known implementation/documentation gaps carried to review

1. Generated standard outcome examples use the display string `DNA cross-sell`, while the approved core constant is `DNA_CrossSell`; current parser validation accepts both because it requires a nonblank supplied segment rather than normalising it. The guide does not silently alter existing app behaviour; use the project-approved spelling consistently and review the template/parser mismatch. Confirmed still open at the pass-3 baseline (`template_downloads.py` unchanged since 2026-09-03).
2. Closed 2026-09-10 (parser and builder both): search taxonomy fields exist on the governed `ActivityDefinition` and admin UI, the standard source dictionary parser (`activity_definitions_from_dictionary`) maps `search_intent_group_id`/`search_platform` from a standard workbook when the two columns are present, and this builder now offers both as governed, dropdown-validated BUILDER-sheet columns (amber, optional) that round-trip through the real parser for Brand/Google, Non-Brand/Bing, and platform-unspecified aggregate-Search rows alike.
3. The generic downloadable sample outcome dictionary (`template_downloads.py`) still teaches GSA ids (`fh_gsa_new`, etc.) as its worked example, not the UK production NBT ids. This is accurate to disclose, not to silently fix — the sample is deliberately generic/cross-project, and UK production ids come from the approved UK source pack, not the generic sample. The guide now says this explicitly (see the UK production NBT note and its FAQ entry).
