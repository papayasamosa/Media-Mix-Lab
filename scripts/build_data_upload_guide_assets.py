"""Build the analyst-facing Ancestry MMM data-upload guide and Dictionary Builders.

This is a documentation/tooling generator.  It does not change the application
parser, schemas, model, or upload behaviour.  The generated workbooks are
deliberately source-pack shaped and use ordinary Excel formulas and validation
lists so an analyst can inspect and edit them without VBA.
"""

from __future__ import annotations

import html
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

from ancestry_mmm.core.activities import (
    ECONOMIC_TREATMENTS,
    FUNNEL_STAGES,
    MARKETING_OBJECTIVE_SUGGESTIONS,
    MODEL_ROLES,
    OWNERSHIP,
    PLANNING_ELIGIBILITY,
)
from ancestry_mmm.core.coverage import (
    DOMAIN_ACTIVITY_AND_MEDIA,
    DOMAIN_CONTEXT_AND_EXTERNAL_FACTORS,
    VARIABLE_CLASSES,
)
from ancestry_mmm.core.outcomes import (
    KNOWN_PRODUCTS,
    METRIC_KEY_CUSTOM,
    METRIC_REGISTRY,
    OUTCOME_GROUP_AGGREGATIONS,
    OUTCOME_ROLES,
    SEGMENT_DIMENSIONS,
)
from ancestry_mmm.data.templates import (
    OUTCOME_DICTIONARY_V2_COLUMNS,
    STANDARD_SHEET_SPECS,
    _ACTIVITY_V2_EXTRA_COLUMNS,
    _CONTEXT_V2_EXTRA_COLUMNS,
    _OUTCOME_DEFINITION_OPTIONAL_COLUMNS,
)


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

# --- Dictionary Builder governed contracts ----------------------------------
#
# Derived directly from the live schema/core modules (never hand-copied) so
# the builders cannot silently drift from what the parser actually accepts.
# See docs/Ancestry_MMM_Upload_Schema_Necessity_Review.md for why each
# "omitted" field below is left out of the builder rather than asked for.

ACTIVITY_DICTIONARY_BASE_COLUMNS = next(
    spec.required_columns
    for spec in STANDARD_SHEET_SPECS[DOMAIN_ACTIVITY_AND_MEDIA]
    if spec.sheet_name == "activity_dictionary"
)
CONTEXT_DICTIONARY_BASE_COLUMNS = next(
    spec.required_columns
    for spec in STANDARD_SHEET_SPECS[DOMAIN_CONTEXT_AND_EXTERNAL_FACTORS]
    if spec.sheet_name == "variable_dictionary"
)

# Confirmed inert/unenforced today (necessity review) -- omitted from the
# BUILDER's analyst-facing questions. Outcome's two fields are genuinely
# optional columns with no bundling requirement, so they are dropped from
# DICTIONARY_OUTPUT entirely. Activity's five write-only columns and
# Context's `unit` cannot be safely dropped from DICTIONARY_OUTPUT the same
# way: `standard_sheet_specs` requires the *entire* v2 extra-column set as
# headers once any one v2 marker is present (confirmed by feeding this
# builder's own output through `parse_standard_workbook` -- dropping them
# made the parser reject the whole sheet as "missing required column(s)").
# Since Activity/Context DICTIONARY_OUTPUT must keep other v2 columns
# (currency/effective_from/effective_to; source/scope), these stay present
# as blank columns -- not asked for in BUILDER, but not deleted either.
OUTCOME_OMITTED_OPTIONAL_COLUMNS = {"date_basis", "maturity_required"}
ACTIVITY_OMITTED_V2_COLUMNS: set[str] = set()
CONTEXT_OMITTED_V2_COLUMNS: set[str] = set()
ACTIVITY_WRITE_ONLY_V2_COLUMNS = {
    "model_input_unit",
    "model_input_kind",
    "spend_column",
    "response_unit_column",
    "response_unit",
}
CONTEXT_UNUSED_V2_COLUMNS = {"unit"}

OUTCOME_DICTIONARY_OUTPUT_COLUMNS = list(OUTCOME_DICTIONARY_V2_COLUMNS) + [
    c
    for c in _OUTCOME_DEFINITION_OPTIONAL_COLUMNS
    if c not in OUTCOME_OMITTED_OPTIONAL_COLUMNS
]
ACTIVITY_DICTIONARY_OUTPUT_COLUMNS = list(ACTIVITY_DICTIONARY_BASE_COLUMNS) + [
    c for c in _ACTIVITY_V2_EXTRA_COLUMNS if c not in ACTIVITY_OMITTED_V2_COLUMNS
]
CONTEXT_DICTIONARY_OUTPUT_COLUMNS = list(CONTEXT_DICTIONARY_BASE_COLUMNS) + [
    c for c in _CONTEXT_V2_EXTRA_COLUMNS if c not in CONTEXT_OMITTED_V2_COLUMNS
]

OUTCOME_METRIC_KEY_CHOICES = [*METRIC_REGISTRY.keys(), METRIC_KEY_CUSTOM]
TRUE_FALSE_BLANK = ["TRUE", "FALSE"]


RAG_HEAD = [
    "Field name",
    "Status",
    "Column must exist?",
    "Value must be filled in?",
    "Plain-English meaning",
    "Good example",
    "Why the tool needs it",
    "If missing",
    "Used by",
    "Allowed values / format",
    "Can be blank when...",
]


def rag_row(
    field: str,
    status: str,
    exists: str,
    filled: str,
    meaning: str,
    good: str,
    why: str,
    missing: str,
    used: str,
    fmt: str,
    blank: str,
) -> dict[str, str]:
    return dict(
        zip(
            RAG_HEAD,
            [
                field,
                status,
                exists,
                filled,
                meaning,
                good,
                why,
                missing,
                used,
                fmt,
                blank,
            ],
        )
    )


OUTCOME_RAG = [
    rag_row(
        "period_start",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Start date for the source period.",
        "2026-01-05",
        "Aligns rows to the source time grain.",
        "The table cannot be keyed or checked.",
        "outcomes",
        "ISO date; one source period",
        "Never for an outcomes row.",
    ),
    rag_row(
        "market",
        "RED — Must provide",
        "Yes",
        "Yes",
        "The market belonging to this row.",
        "UK",
        "Market is a row-level key; it is never inferred from the file name.",
        "The row is rejected or cannot be assigned safely.",
        "outcomes; all domains",
        "Stable market code or label",
        "Never for a usable row.",
    ),
    rag_row(
        "outcome_id",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Stable identity of the outcome definition.",
        "fh_gsa_new",
        "Joins the source column to its approved meaning.",
        "The outcome cannot be defined or fitted.",
        "outcome_dictionary; completeness",
        "Stable lowercase ID; no duplicates",
        "Never.",
    ),
    rag_row(
        "source_column",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Exact column in outcomes that holds the values.",
        "fh_gsa_new",
        "Connects the dictionary to the wide source table.",
        "The definition cannot be mapped to data.",
        "outcome_dictionary; parser",
        "Exact header spelling",
        "Never.",
    ),
    rag_row(
        "product",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Product family represented by the outcome.",
        "Family History",
        "Keeps Family History and DNA outcomes distinct.",
        "The definition is invalid.",
        "outcome registry; reporting",
        "Family History or DNA, or an approved product",
        "Never.",
    ),
    rag_row(
        "metric_key",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Stable registry key for the metric.",
        "fh_gsa",
        "Prevents meaning being guessed from a friendly label.",
        "The metric may be rejected or treated as custom.",
        "outcome registry; fit",
        "Approved key or explicit custom",
        "Never.",
    ),
    rag_row(
        "metric",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Human-readable metric name.",
        "GSA",
        "Makes the definition readable while the key stays stable.",
        "The definition is incomplete.",
        "dictionary; reports",
        "Do not use aliases as a substitute for a definition",
        "Never.",
    ),
    rag_row(
        "segment_dimension",
        "RED — Must provide",
        "Yes",
        "Yes",
        "What the segment label means.",
        "fh_customer_segment",
        "Stops the same label meaning different things.",
        "The segment cannot be interpreted safely.",
        "outcome registry; groups",
        "Approved dimension vocabulary",
        "Never.",
    ),
    rag_row(
        "segment",
        "RED — Must provide",
        "Yes",
        "Yes",
        "The supplied segment value.",
        "New",
        "Fits New, Winback, and DNA cross-sell separately where supported.",
        "The outcome cannot be assigned to a segment.",
        "fit; reporting",
        "Use source-approved labels; do not silently add DNA partitions",
        "Never.",
    ),
    rag_row(
        "outcome_group_id",
        "AMBER — Needed for some uses",
        "Yes",
        "No",
        "Optional semantic group identity.",
        "fh_gsa_family",
        "Describes components or a supplied total without choosing fit treatment.",
        "Group reconciliation or group views are unavailable.",
        "groups; reconciliation",
        "Stable ID; leave the complete group block blank if unused",
        "When no governed group exists.",
    ),
    rag_row(
        "outcome_group_label",
        "AMBER — Needed for some uses",
        "Yes",
        "No",
        "Readable group name.",
        "Family History GSA",
        "Explains the group to reviewers.",
        "The group is incomplete.",
        "groups; review",
        "Text",
        "When outcome_group_id is blank.",
    ),
    rag_row(
        "outcome_family_key",
        "AMBER — Needed for some uses",
        "Yes",
        "No",
        "Family key used for group semantics.",
        "fh_gsa",
        "Keeps group members in one outcome family.",
        "The group is incomplete.",
        "groups; reconciliation",
        "Stable registry/custom key",
        "When no group is used.",
    ),
    rag_row(
        "group_aggregation",
        "AMBER — Needed for some uses",
        "Yes",
        "No",
        "Whether the group is a sum or descriptive only.",
        "sum",
        "Controls reconciliation semantics; it does not automatically fit a total.",
        "The group cannot be used for governed reconciliation.",
        "groups; totals",
        "sum or none",
        "When outcome_group_id is blank.",
    ),
    rag_row(
        "unit",
        "AMBER — Needed for some uses",
        "Yes",
        "No",
        "Unit of the outcome value.",
        "GSA",
        "Separates counts, rates, currency, and indexes.",
        "The registry may supply a default; do not guess for custom metrics.",
        "definition; economics",
        "Approved unit text",
        "Only when the registry has an approved default.",
    ),
    rag_row(
        "aggregation_type",
        "AMBER — Needed for some uses",
        "Yes",
        "No",
        "How values aggregate.",
        "count",
        "A rate is not added like a count.",
        "Economic/reporting use is blocked or ambiguous.",
        "definition; reporting",
        "count, rate, currency, index",
        "When the registry supplies it.",
    ),
    rag_row(
        "date_basis",
        "GREY — Legacy/unused",
        "Yes",
        "No",
        "Intended date meaning for the outcome — accepted by the schema, but not read by any current transformation.",
        "signup_date",
        "It doesn't need it. `core/outcomes.py` states directly that this field is schema/validation only; no transformation reads or computes it today.",
        "Nothing changes — no current behaviour depends on this field being present.",
        "Not used by any current transformation or by the Outcome Dictionary Builder.",
        "Approved date-basis vocabulary, only if you add the column by hand outside the builder",
        "Always safe to leave out. The Outcome Dictionary Builder does not offer this column.",
    ),
    rag_row(
        "maturity_required",
        "GREY — Legacy/unused",
        "Yes",
        "No",
        "Intended flag for whether the outcome needs a maturity rule — accepted by the schema, but not read by any current transformation.",
        "TRUE",
        "It doesn't need it. The value is type-coerced and stored, but nothing downstream reads it today.",
        "Nothing changes — no current behaviour depends on this field being present.",
        "Not used by any current transformation or by the Outcome Dictionary Builder.",
        "TRUE/FALSE, only if you add the column by hand outside the builder",
        "Always safe to leave out. The Outcome Dictionary Builder does not offer this column.",
    ),
    rag_row(
        "role",
        "AMBER — Needed for some uses",
        "Yes",
        "No",
        "Use role for this outcome.",
        "primary",
        "Separates fit, secondary, funnel, and diagnostic uses.",
        "Eligibility defaults may not match the intended use.",
        "eligibility; reporting",
        "primary, secondary, funnel_intermediate, diagnostic",
        "When using the project default only.",
    ),
    rag_row(
        "included_in_fit",
        "AMBER — Needed for some uses",
        "Yes",
        "No",
        "Whether this outcome is included in fitting.",
        "TRUE",
        "Keeps definition and use decisions separate.",
        "The intended fit treatment is unclear.",
        "fit governance",
        "TRUE/FALSE",
        "When approval is not yet decided.",
    ),
    rag_row(
        "include_in_default_reporting",
        "AMBER — Needed for some uses",
        "Yes",
        "No",
        "Whether it appears in default reports.",
        "TRUE",
        "Prevents a fitted outcome becoming headline output by accident.",
        "Reporting eligibility is unclear.",
        "reporting governance",
        "TRUE/FALSE",
        "When it is diagnostic-only.",
    ),
    rag_row(
        "include_in_official_total",
        "AMBER — Needed for some uses",
        "Yes",
        "No",
        "Whether it can enter an official total.",
        "FALSE",
        "Official totals require explicit approval.",
        "Official total construction is blocked.",
        "official reporting",
        "TRUE/FALSE",
        "For non-total outcomes.",
    ),
    rag_row(
        "include_in_value",
        "AMBER — Needed for some uses",
        "Yes",
        "No",
        "Whether economic value may use it.",
        "TRUE",
        "Count, value, and rate layers stay distinct.",
        "CPA/ROI use is blocked for that outcome.",
        "valuation; economics",
        "TRUE/FALSE",
        "For count-only or diagnostic outcomes.",
    ),
    rag_row(
        "include_in_optimisation",
        "AMBER — Needed for some uses",
        "Yes",
        "No",
        "Whether optimisation may target it.",
        "FALSE",
        "Fit and optimisation eligibility are separate approvals.",
        "Optimisation is blocked for that outcome.",
        "optimisation governance",
        "TRUE/FALSE",
        "For diagnostic or unapproved outcomes.",
    ),
    rag_row(
        "definition_version",
        "AMBER — Needed for some uses",
        "Yes",
        "Yes for approval",
        "Version of the business definition.",
        "1.0",
        "Makes reports reproducible when definitions change.",
        "Official approval is incomplete.",
        "approval; persistence",
        "Version text or number",
        "During early draft only.",
    ),
    rag_row(
        "event_definition",
        "AMBER — Needed for some uses",
        "Yes",
        "Yes for approval",
        "What event is counted.",
        "Approved weekly GSA event",
        "Finance/Product can reconcile the definition.",
        "The outcome cannot be approved.",
        "approval; reconciliation",
        "Plain text with source reference",
        "During early draft only.",
    ),
    rag_row(
        "cohort_or_attribution_basis",
        "AMBER — Needed for some uses",
        "Yes",
        "Yes for approval",
        "How people are assigned to the period and segment.",
        "signup_date_attributed",
        "Prevents cohort and event bases being mixed.",
        "Official use is blocked.",
        "approval; value join",
        "Plain text or approved vocabulary",
        "During early draft only.",
    ),
    rag_row(
        "completeness_or_maturity_policy",
        "AMBER — Needed for some uses",
        "Yes",
        "Yes for approval",
        "Rule for when a period is complete.",
        "14-day source horizon (illustrative/historical-test example)",
        "Stops immature outcome periods being treated as final.",
        "Official reporting is blocked.",
        "completeness; approval",
        "Plain text; versioned; official UK production NBT uses its own approved production maturity rule, evidence, and exclusions — not this illustrative 14-day historical-test example",
        "Only for exploratory drafts.",
    ),
    rag_row(
        "exclusions",
        "AMBER — Needed for some uses",
        "Yes",
        "Yes for approval",
        "Rows or cases excluded from the definition.",
        "Test accounts excluded",
        "Keeps source reconciliation auditable.",
        "Approval is incomplete.",
        "approval; reconciliation",
        "Plain text",
        "When there are no exclusions, write none.",
    ),
    rag_row(
        "reconciliation_source",
        "AMBER — Needed for some uses",
        "Yes",
        "Yes for approval",
        "Source used to reconcile the measure.",
        "Finance weekly ledger v3",
        "Names the authority for the measure.",
        "Official use is blocked.",
        "approval; audit",
        "Plain text with version",
        "Only for exploratory drafts.",
    ),
    rag_row(
        "business_owner",
        "AMBER — Needed for some uses",
        "Yes",
        "Yes for approval",
        "Owner who approves the definition.",
        "Finance",
        "Makes decision ownership visible.",
        "The definition cannot be approved.",
        "approval; audit",
        "Text",
        "During early draft only.",
    ),
    rag_row(
        "effective_from",
        "GREEN — Optional",
        "Yes",
        "No",
        "Date the definition becomes active.",
        "2026-01-01",
        "Supports versioned definition history.",
        "No effective window is recorded.",
        "persistence; audit",
        "ISO date",
        "For a definition with no time-limited version.",
    ),
    rag_row(
        "effective_to",
        "GREEN — Optional",
        "Yes",
        "No",
        "Date the definition stops being active.",
        "2026-12-31",
        "Supports versioned definition history.",
        "No end window is recorded.",
        "persistence; audit",
        "ISO date",
        "For a current/open-ended definition.",
    ),
    rag_row(
        "value_weight",
        "AMBER — Needed for some uses",
        "Yes",
        "No",
        "Approved value per outcome, if supplied in the definition.",
        "42.50",
        "Only a governed mapping may turn counts into value.",
        "Value reporting is blocked; do not invent a value.",
        "economics; planning",
        "Number; not a rate unless explicitly defined",
        "For count-only models or separate valuation uploads.",
    ),
    rag_row(
        "value_currency",
        "AMBER — Needed for some uses",
        "Yes",
        "No",
        "Currency of an approved value weight.",
        "GBP",
        "Prevents mixing monetary units.",
        "Monetary output is blocked pending currency governance.",
        "economics; FX",
        "Uppercase ISO 4217 code",
        "When no monetary value is supplied.",
    ),
]


COMPLETENESS_RAG = [
    rag_row(
        "outcome_id",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Outcome definition covered by this completeness record.",
        "fh_net_billthrough_count_new",
        "Joins completeness metadata to one approved outcome.",
        "The metadata cannot be bound.",
        "outcome_completeness",
        "Existing outcome_id",
        "Never.",
    ),
    rag_row(
        "data_as_of_date",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Date through which the source is known.",
        "2026-02-14",
        "Shows how current the extract is.",
        "Freshness cannot be reviewed.",
        "completeness; audit",
        "ISO date",
        "Never.",
    ),
    rag_row(
        "model_start_week",
        "RED — Must provide",
        "Yes",
        "Yes",
        "First model week covered by the source.",
        "2026-01-05",
        "Checks the intended model window.",
        "Coverage cannot be checked.",
        "completeness",
        "ISO date",
        "Never.",
    ),
    rag_row(
        "model_end_week",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Last model week covered by the source.",
        "2026-02-09",
        "Checks the intended model window.",
        "Coverage cannot be checked.",
        "completeness",
        "ISO date",
        "Never.",
    ),
    rag_row(
        "latest_complete_net_billthrough_week",
        "RED — Must provide for NBT",
        "Yes",
        "Yes for NBT",
        "Latest week that is complete under the maturity rule.",
        "2026-01-26",
        "Stops immature NBT periods being treated as final.",
        "Official NBT use is blocked.",
        "NBT completeness; official reporting",
        "ISO date",
        "For non-NBT outcomes only if the project contract says not applicable.",
    ),
    rag_row(
        "maturity_rule_description",
        "RED — Must provide for maturity-sensitive outcomes",
        "Yes",
        "Yes",
        "Plain-English maturity/completeness rule.",
        "14-day horizon after week end (exploratory/historical-test example only)",
        "Explains why a period is complete.",
        "Official use is blocked.",
        "approval; audit",
        "Versioned text; for official UK production NBT this must be the approved production maturity rule, not the bounded historical-test 14-day rule",
        "For outcomes with no maturity requirement.",
    ),
    rag_row(
        "source_owner",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Owner of the completeness metadata/source.",
        "Finance Analytics",
        "Provides accountability for the extract.",
        "Completeness cannot be approved.",
        "audit; approval",
        "Text",
        "Never for governed metadata.",
    ),
]


ACTIVITY_RAG = [
    rag_row(
        "period_start",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Start date for the source period.",
        "2026-01-05",
        "Preserves the activity source grain.",
        "Rows cannot be aligned.",
        "activity_data",
        "ISO date",
        "Never.",
    ),
    rag_row(
        "market",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Market for this activity row or dictionary record.",
        "UK",
        "Market is explicit and row-level.",
        "The row cannot be assigned safely.",
        "activity_data; activity_dictionary",
        "Stable market code/label",
        "Never.",
    ),
    rag_row(
        "activity_id",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Stable identity of the activity at market × activity grain.",
        "paid_search_google_brand",
        "Joins raw observations to the dictionary.",
        "The activity cannot be mapped.",
        "activity_data; activity_dictionary",
        "Stable ID; unique within market",
        "Never.",
    ),
    rag_row(
        "pooling_group_id",
        "AMBER — Reporting/lineage only",
        "Yes",
        "No",
        "Optional cross-market identity for similar activity.",
        "paid_search_brand",
        "Supports lineage and comparison across markets; it does not force statistical pooling and is never read by any fit, canonicalisation, planning, or optimisation code — reporting/lineage only.",
        "Cross-market identity is not recorded; fitting is unaffected either way.",
        "hierarchy/lineage reporting only",
        "Stable ID",
        "When the activity has no governed cross-market peer.",
    ),
    rag_row(
        "channel",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Channel label used by the model and reports.",
        "Paid Search",
        "Separates activity identity from descriptive detail.",
        "The dictionary is rejected.",
        "activity dictionary; model input",
        "Text; do not use a generic Brand Search label",
        "Never.",
    ),
    rag_row(
        "platform",
        "AMBER — Reporting/display only",
        "Yes",
        "Yes for differentiated platform",
        "Buying or delivery platform.",
        "Google",
        "Helps distinguish Google and Bing in reports and the causal-graph display; the necessity review confirmed it is never read by fit, canonicalisation, or planning/optimisation code.",
        "Platform-level identity may collide in reports; fitting is unaffected either way.",
        "reporting rollups and causal-graph display only",
        "Text",
        "If platform is genuinely not applicable.",
    ),
    rag_row(
        "campaign_type",
        "AMBER — Needed for some uses",
        "Yes",
        "No",
        "Campaign or placement type.",
        "Brand",
        "Adds meaningful identity when platform/channel alone is not enough, and gates the Search-taxonomy fields (search_intent_group_id/search_platform can only be set when campaign_type is not one of the excluded PMax/Demand Gen/YouTube types) — its only other behavioural effect.",
        "Similar activities may collide in reports.",
        "activity identity; reports; Search-taxonomy gate",
        "Text",
        "When source has no campaign type.",
    ),
    rag_row(
        "marketing_objective",
        "AMBER — Reporting/display only",
        "Yes",
        "No",
        "Why the activity was run.",
        "acquisition/performance",
        "Supports reporting; it is not silently inferred. The necessity review confirmed it is never read by fit, canonicalisation, or planning/optimisation code.",
        "Objective reporting is incomplete; fitting is unaffected either way.",
        "reporting rollups and causal-graph display only",
        "Suggested vocabulary or documented custom",
        "When not supplied.",
    ),
    rag_row(
        "funnel_stage",
        "AMBER — Reporting/display only",
        "Yes",
        "Yes for governed classification",
        "Approved funnel position.",
        "performance_lower",
        "Supports pathway reporting without guessing — a closed vocabulary so reports can't silently acquire spelling variants. The necessity review confirmed it is never read by fit, canonicalisation, or planning/optimisation code, and its own governing comment (`activities.py`) states it is not read by model builders or causal-graph compilation either.",
        "Classification is incomplete in reports; fitting is unaffected either way.",
        "pathway/funnel reporting only",
        "brand_upper, mid_funnel, performance_lower, cross_funnel, not_applicable, unclassified",
        "Only while unclassified is explicitly accepted.",
    ),
    rag_row(
        "product_advertised",
        "AMBER — Reporting/display only",
        "Yes",
        "No",
        "Product in the creative or offer.",
        "Family History",
        "Separates FH, DNA, and cross-product activity in reports and the causal-graph display; the necessity review confirmed it is never read by fit, canonicalisation, or planning/optimisation code.",
        "Product reporting is incomplete; fitting is unaffected either way.",
        "reporting rollups and causal-graph display only",
        "Text; approved product names where known",
        "When activity is product-neutral.",
    ),
    rag_row(
        "message_type",
        "AMBER — Reporting/display only",
        "Yes",
        "No",
        "Message or offer type.",
        "brand",
        "Descriptive taxonomy for analysis; the necessity review confirmed it is never read by fit, canonicalisation, or planning/optimisation code.",
        "Message reporting is incomplete; fitting is unaffected either way.",
        "reporting rollups and causal-graph display only",
        "Text",
        "When not available.",
    ),
    rag_row(
        "activity_ownership",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Who controls or supplies the activity.",
        "paid",
        "Keeps paid, owned, earned, and events distinct.",
        "The activity is invalid.",
        "model role; economics",
        "paid, owned, earned, external_event",
        "Never.",
    ),
    rag_row(
        "intended_model_role",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Intended role in the model.",
        "intervention",
        "Separates treatments, controls, mediators, and demand capture.",
        "The activity is invalid or misclassified.",
        "model governance",
        "intervention, mediator, demand_capture, control, event",
        "Never.",
    ),
    rag_row(
        "model_input_column",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Destination column after tidy data is pivoted to model-ready form.",
        "uk_paid_search_google_brand",
        "Tells canonicalisation where the selected measure belongs.",
        "The model input cannot be created.",
        "canonicalisation; model frame",
        "Stable wide-column name",
        "Never.",
    ),
    rag_row(
        "model_input_measure",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Exact raw column selected as the model input.",
        "spend",
        "The parser selects this raw measure explicitly.",
        "The activity cannot be canonicalised.",
        "canonicalisation",
        "Exact raw header such as spend, clicks, impressions, GRPs",
        "Never.",
    ),
    rag_row(
        "economic_treatment",
        "RED — Must provide",
        "Yes",
        "Yes",
        "How cost/value is treated.",
        "paid_media_cost",
        "Keeps economics separate from physical measurement.",
        "The dictionary is invalid.",
        "economics; planning",
        "paid_media_cost, fully_loaded_cost, campaign_cost, response_only, not_applicable",
        "Never.",
    ),
    rag_row(
        "planning_eligibility",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Whether planning or optimisation may use the activity.",
        "optimisable",
        "Fit does not automatically grant planning rights.",
        "Planning treatment is unclear.",
        "planning; optimisation",
        "optimisable, scenario_only, fixed, excluded",
        "Never.",
    ),
    rag_row(
        "source",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Source system, file, or owner reference.",
        "Google Ads export 2026-08",
        "Preserves provenance and reviewability.",
        "The dictionary is invalid.",
        "audit; persistence",
        "Text with version/date preferred",
        "Never.",
    ),
    rag_row(
        "model_input_unit",
        "GREY — Currently write-only",
        "Yes",
        "No",
        "Intended unit of the selected model input — parsed and stored for review, but not applied by the standard upload path.",
        "GBP",
        "It doesn't apply this today. The value is parsed into a review-status record (`activity_semantic_mappings`); `source_pack_adoption.py` states directly that the upload does not apply it automatically. The real unit/cost mapping is entered separately, in Channel Media Units and Curve Generation, after upload.",
        "Nothing changes — the standard upload path doesn't read this value either way.",
        "Stored for manual review only; not read by canonicalisation, fit, or planning.",
        "GBP, impressions, clicks, GRP, TVR, etc., only if you choose to record it for review",
        "Always safe to leave blank. The Activity Dictionary Builder does not offer this column.",
    ),
    rag_row(
        "model_input_kind",
        "GREY — Currently write-only",
        "Yes",
        "No",
        "Intended flag for monetary spend vs. exposure — parsed and stored for review, but not applied by the standard upload path.",
        "monetary_spend",
        "It doesn't apply this today, for the same reason as model_input_unit: parsed into a review-status record only, never automatically applied. The real cost-contract mapping happens in Channel Media Units and Curve Generation after upload.",
        "Nothing changes — the standard upload path doesn't read this value either way.",
        "Stored for manual review only; not read by canonicalisation, fit, or planning.",
        "monetary_spend or exposure, only if you choose to record it for review",
        "Always safe to leave blank. The Activity Dictionary Builder does not offer this column.",
    ),
    rag_row(
        "spend_column",
        "GREY — Currently write-only",
        "Yes",
        "No",
        "Raw monetary spend column reference — parsed and stored for review, but not applied by the standard upload path.",
        "spend",
        "It doesn't apply this today, for the same reason as model_input_unit. The real spend/cost mapping happens in Channel Media Units and Curve Generation after upload.",
        "Nothing changes — the standard upload path doesn't read this value either way.",
        "Stored for manual review only; not read by canonicalisation, fit, or planning.",
        "Exact raw header, only if you choose to record it for review",
        "Always safe to leave blank. The Activity Dictionary Builder does not offer this column.",
    ),
    rag_row(
        "response_unit_column",
        "GREY — Currently write-only",
        "Yes",
        "No",
        "Raw delivery/response column reference — parsed and stored for review, but not applied by the standard upload path.",
        "clicks",
        "It doesn't apply this today, for the same reason as model_input_unit. The real response/unit mapping happens in Channel Media Units and Curve Generation after upload.",
        "Nothing changes — the standard upload path doesn't read this value either way.",
        "Stored for manual review only; not read by canonicalisation, fit, or planning.",
        "Exact raw header, only if you choose to record it for review",
        "Always safe to leave blank. The Activity Dictionary Builder does not offer this column.",
    ),
    rag_row(
        "response_unit",
        "GREY — Currently write-only",
        "Yes",
        "No",
        "Unit of the response column reference — parsed and stored for review, but not applied by the standard upload path.",
        "clicks",
        "It doesn't apply this today, for the same reason as model_input_unit. The real response/unit mapping happens in Channel Media Units and Curve Generation after upload.",
        "Nothing changes — the standard upload path doesn't read this value either way.",
        "Stored for manual review only; not read by canonicalisation, fit, or planning.",
        "Text, only if you choose to record it for review",
        "Always safe to leave blank. The Activity Dictionary Builder does not offer this column.",
    ),
    rag_row(
        "currency",
        "AMBER — Needed for some uses",
        "Yes",
        "No",
        "Currency of monetary spend.",
        "GBP",
        "Identifies the monetary unit; it does not perform FX conversion.",
        "Monetary economics is blocked pending mapping.",
        "economics; FX",
        "Uppercase ISO 4217",
        "For non-monetary activity.",
    ),
    rag_row(
        "effective_from",
        "GREEN — Optional",
        "Yes",
        "No",
        "Date this mapping becomes active.",
        "2026-01-01",
        "Supports versioned source mappings.",
        "No start window is recorded.",
        "audit; persistence",
        "ISO date",
        "For a stable mapping with no time window.",
    ),
    rag_row(
        "effective_to",
        "GREEN — Optional",
        "Yes",
        "No",
        "Date this mapping stops being active.",
        "2026-12-31",
        "Supports source mapping history.",
        "No end window is recorded.",
        "audit; persistence",
        "ISO date",
        "For a current/open-ended mapping.",
    ),
    rag_row(
        "search_intent_group_id",
        "AMBER — Needed for some uses",
        "Yes in the governed Search mapping",
        "Yes for Search taxonomy",
        "Search intent axis such as Brand or Non-Brand.",
        "brand_search",
        "Keeps Search leaves explicit instead of one generic Brand Search variable.",
        "Search taxonomy remains unclassified.",
        "Search mapping; reports",
        "brand_search or non_brand_search; a governed deeper Non-Brand child ID is also accepted once explicitly approved (starts draft)",
        "For non-Search activities.",
    ),
    rag_row(
        "search_platform",
        "AMBER — Needed for some uses",
        "Yes in the governed Search mapping",
        "Yes for Search taxonomy",
        "Search platform axis.",
        "google",
        "Keeps Google and Bing leaves distinct.",
        "Platform-level Search identity remains unclassified.",
        "Search mapping; reports",
        "google or bing",
        "For non-Search activities.",
    ),
]


CONTEXT_RAG = [
    rag_row(
        "period_start",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Start date of the native-frequency observation.",
        "2026-01-05",
        "Preserves the source frequency and row grain.",
        "The observation cannot be aligned.",
        "context_data",
        "ISO date",
        "Never.",
    ),
    rag_row(
        "market",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Market for the observation.",
        "UK",
        "Market is explicit, not inferred from file name.",
        "The observation cannot be assigned.",
        "context_data",
        "Stable market code/label",
        "Never.",
    ),
    rag_row(
        "variable_id",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Stable identity of the context variable.",
        "uk_cpi",
        "Joins observations to meaning and role.",
        "The variable cannot be used.",
        "context_data; variable_dictionary",
        "Stable ID; unique in dictionary",
        "Never.",
    ),
    rag_row(
        "value",
        "RED — Must provide",
        "Yes",
        "Yes unless state says unavailable",
        "Observed value at native frequency.",
        "132.4",
        "Carries the actual source observation without fake rows.",
        "The observation is missing; do not silently fill it.",
        "context_data",
        "Finite numeric value or governed missing state",
        "Only when an explicit missingness state is provided by the governed path.",
    ),
    rag_row(
        "native_frequency",
        "RED — Must provide (see override note)",
        "Yes",
        "Yes",
        "Frequency at which the source was observed.",
        "weekly",
        "Stops monthly or quarterly data being presented as weekly at upload time — this part is real. But the necessity review found the governed Coverage Matrix screen (Page 15) re-asks for this value independently and defaults every variable to weekly regardless of what you upload here; it is also duplicated as a required context_data row column that is confirmed never read into the pivot — a second, fully write-only copy.",
        "The source frequency is unknown at upload; if you do supply it, expect Page 15 to re-default it anyway.",
        "context_data (upload-time only; not read into the pivot); variable_dictionary (a non-blocking warning banner only, not enforced by Page 15)",
        "weekly, monthly, quarterly, yearly, daily, event",
        "Never.",
    ),
    rag_row(
        "variable_class",
        "RED — Must provide (see override note)",
        "Yes",
        "Yes",
        "Type of variable.",
        "rate_index",
        "Separates flows, stocks, rates, surveys, and event flags at upload time — this enum is real and validated. But the necessity review found the governed Coverage Matrix screen (Page 15) does not read this uploaded value at all: it defaults every variable to flow_count regardless, and the one place that does read it (a CI/diagnostic harness, not the analyst path) overrides it to rate_index anyway.",
        "The definition is rejected at upload (the column and a valid value are genuinely required); once uploaded, expect Page 15 to re-default it regardless.",
        "variable_dictionary at upload only (validated against the 5 approved classes); not read by Page 15's Coverage Matrix, the screen that actually governs this today",
        "flow_count, stock_level, rate_index, survey_measurement, event_flag",
        "Never for governed variables.",
    ),
    rag_row(
        "role",
        "RED — Must provide, not currently enforced",
        "Yes",
        "Yes",
        "Intended operational future/model role.",
        "exogenous_forecastable_control",
        'Intended to prevent an endogenous mediator being independently forecast — but the necessity review found no enum enforcement anywhere in the code today, despite being called "governed" in a code comment. It is currently indistinguishable from a free-text note field, and isn\'t even included in the one completeness check that looks at the rest of the Context metadata.',
        "Nothing currently blocks an upload over an invalid or missing role beyond the column needing to exist — this is a documentation-vs-code mismatch, not an enforced safeguard.",
        "Stored in variable_dictionary; not enum-validated by any current code path",
        "No enforced list today — free text in practice, despite the field's name. Documented example: exogenous_forecastable_control.",
        "Never for governed variables.",
    ),
    rag_row(
        "source",
        "AMBER — Needed for some uses",
        "Yes",
        "Yes for adoption",
        "Source system or owner reference.",
        "ONS CPI release",
        "Makes provenance visible.",
        "Context adoption remains under review.",
        "variable_dictionary; audit",
        "Text with version/date",
        "For an early draft only.",
    ),
    rag_row(
        "scope",
        "AMBER — Needed for some uses",
        "Yes",
        "Yes for adoption",
        "Geographic or business scope of the variable.",
        "UK",
        "Prevents a national series being mistaken for a market series.",
        "Adoption remains under review.",
        "variable_dictionary; alignment",
        "Text",
        "For an exploratory upload not yet adopted.",
    ),
    rag_row(
        "effective_from",
        "GREEN — Optional",
        "Yes",
        "No",
        "Date the dictionary mapping starts.",
        "2026-01-01",
        "Supports versioned context meaning.",
        "No mapping start is recorded.",
        "audit; persistence",
        "ISO date",
        "For an always-active mapping.",
    ),
    rag_row(
        "effective_to",
        "GREEN — Optional",
        "Yes",
        "No",
        "Date the dictionary mapping ends.",
        "2026-12-31",
        "Supports versioned context meaning.",
        "No mapping end is recorded.",
        "audit; persistence",
        "ISO date",
        "For an open-ended mapping.",
    ),
    rag_row(
        "unit",
        "AMBER — Needed for some uses",
        "Yes",
        "Yes for adoption",
        "Unit of the observed value.",
        "index",
        "Prevents rates, counts, and currency being mixed.",
        "Context adoption remains under review.",
        "variable_dictionary; economics",
        "Text",
        "For a variable whose unit is explicitly not applicable.",
    ),
]


EVENT_RAG = [
    rag_row(
        "event_id",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Stable event identity.",
        "black_friday_2026",
        "Keeps occurrences traceable.",
        "The event row is invalid.",
        "events",
        "Stable ID",
        "Never.",
    ),
    rag_row(
        "event_name",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Readable event name.",
        "Black Friday",
        "Makes the event understandable.",
        "The event row is invalid.",
        "events",
        "Text",
        "Never.",
    ),
    rag_row(
        "start_date",
        "RED — Must provide",
        "Yes",
        "Yes",
        "First date of the event window.",
        "2026-11-27",
        "Preserves the factual event window.",
        "The event cannot be used.",
        "events",
        "ISO date",
        "Never.",
    ),
    rag_row(
        "end_date",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Last date of the event window.",
        "2026-11-30",
        "Preserves the factual event window.",
        "The event cannot be used.",
        "events",
        "ISO date; on/after start",
        "Never.",
    ),
]


EXPERIMENT_RAG = [
    rag_row(
        "experiment_id",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Stable experiment identity.",
        "geo_lift_uk_01",
        "Links evidence to one experiment.",
        "The evidence cannot be reviewed.",
        "experiment_evidence",
        "Stable ID",
        "Never.",
    ),
    rag_row(
        "activity_id",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Activity affected by the experiment.",
        "paid_search_google_brand",
        "Links evidence to a governed activity.",
        "Evidence cannot be mapped.",
        "experiment_evidence",
        "Existing activity ID",
        "Never.",
    ),
    rag_row(
        "market",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Market in the experiment.",
        "UK",
        "Keeps experiment scope explicit.",
        "Evidence cannot be scoped.",
        "experiment_evidence",
        "Stable market code/label",
        "Never.",
    ),
    rag_row(
        "start_date",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Experiment start date.",
        "2026-03-01",
        "Defines the test window.",
        "Evidence cannot be checked.",
        "experiment_evidence",
        "ISO date",
        "Never.",
    ),
    rag_row(
        "end_date",
        "RED — Must provide",
        "Yes",
        "Yes",
        "Experiment end date.",
        "2026-03-28",
        "Defines the test window.",
        "Evidence cannot be checked.",
        "experiment_evidence",
        "ISO date; on/after start",
        "Never.",
    ),
]


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def html_table(rows: list[dict[str, str]], extra_class: str = "") -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in RAG_HEAD)
    body = []
    for row in rows:
        status = row["Status"]
        cls = (
            "red"
            if status.startswith("RED")
            else "amber"
            if status.startswith("AMBER")
            else "green"
            if status.startswith("GREEN")
            else "grey"
        )
        cells = []
        for h in RAG_HEAD:
            if h == "Status":
                cells.append(f'<td class="rag-{cls}">{esc(row[h])}</td>')
            else:
                cells.append(f"<td>{esc(row[h])}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f'<div class="table-wrap"><table class="rag {extra_class}"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def simple_table(headers: list[str], rows: list[list[str]], cls: str = "") -> str:
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    tr = []
    for row in rows:
        tr.append("<tr>" + "".join(f"<td>{esc(v)}</td>" for v in row) + "</tr>")
    return f'<div class="table-wrap"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{"".join(tr)}</tbody></table></div>'


def code_block(text: str) -> str:
    return f"<pre><code>{esc(text)}</code></pre>"


def mistakes(items: list[str]) -> str:
    return (
        '<ul class="mistakes">'
        + "".join(f"<li>{esc(item)}</li>" for item in items)
        + "</ul>"
    )


def bullet_list(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>"


def dictionary_builder_section(
    filename: str,
    dictionary_sheet: str,
    what_it_does: str,
    fill_in: list[str],
    generated: list[str],
    dropdown_fields: list[str],
    allowed_values_note: str,
    optional_advanced: list[str],
    data_sheet_note: str,
) -> str:
    return f"""
    <div class="callout builder">
      <h3>Dictionary Builder: <code>{esc(filename)}</code></h3>
      <p><b>What the builder does.</b> {what_it_does}</p>
      <p><b>What you need to fill in:</b></p>
      {bullet_list(fill_in)}
      <p><b>What is generated automatically:</b></p>
      {bullet_list(generated)}
      <p><b>Which fields use dropdowns:</b> {", ".join(f"<code>{esc(f)}</code>" for f in dropdown_fields)}.</p>
      <p><b>Exact acceptable values:</b> {allowed_values_note} See the workbook's own <code>ALLOWED_VALUES</code> sheet for the full, current list.</p>
      <p><b>Which fields are optional / advanced:</b></p>
      {bullet_list(optional_advanced)}
      <p><b>Where the output goes.</b> Copy the <code>DICTIONARY_OUTPUT</code> sheet's rows straight into the <code>{esc(dictionary_sheet)}</code> sheet of the standard upload workbook. {data_sheet_note}</p>
    </div>
    """


def domain_section(
    anchor: str,
    number: str,
    title: str,
    purpose: str,
    need_it: str,
    grain: str,
    sheets_note: str,
    raw_example: str,
    required_rows: list[list[str]],
    conditional_rows: list[list[str]],
    optional_rows: list[list[str]],
    rag: list[dict[str, str]],
    connection: str,
    common_mistakes: list[str],
    valid_invalid: list[list[str]],
    extra_html: str = "",
    builder_html: str = "",
) -> str:
    required_table = simple_table(
        ["Field", "What it means", "What to enter", "Example"], required_rows, "wide"
    )
    conditional_table = (
        simple_table(
            ["Field", "When do I need this?", "What it means"],
            conditional_rows,
            "wide",
        )
        if conditional_rows
        else ""
    )
    optional_table = (
        simple_table(["Field", "Note"], optional_rows, "compact")
        if optional_rows
        else ""
    )
    full_reference = (
        "<details><summary>Full technical field reference (every field, RAG-coded, for power users and auditors)</summary>"
        + html_table(rag, "wide")
        + "</details>"
    )
    return f"""
    <section id="{anchor}" class="domain section">
      <p class="eyebrow">Domain {number}</p><h2>{esc(title)}</h2>
      <p>{purpose}</p>
      <div class="callout"><b>Do I need this file?</b> {need_it}</div>
      <h3>What does one row mean?</h3><p>{grain}</p>
      <h3>Sheets in this workbook</h3><p>{sheets_note}</p>
      {builder_html}
      <h3>Example</h3>{code_block(raw_example)}<p>{connection}</p>
      <h3>Fields you must fill in</h3>{required_table}
      {"<h3>Fields you may need</h3>" + conditional_table if conditional_table else ""}
      {"<h3>Optional metadata</h3><p>Helpful for reporting and governance, but not needed for a first fit.</p>" + optional_table if optional_table else ""}
      <h3>Common mistakes</h3>{mistakes(common_mistakes)}
      <h3>Valid and invalid examples</h3>{simple_table(["Valid", "Invalid", "Why"], valid_invalid)}
      {extra_html}
      {full_reference}
    </section>
    """


def build_html() -> str:
    relationship = """
    <div class="diagram" role="img" aria-label="File relationship diagram">
      <div class="diagram-box outcome"><b>Outcomes workbook</b><span>outcomes + outcome_dictionary<br>+ optional completeness</span></div>
      <div class="arrow">joins on <b>source_column</b><br>and <b>outcome_id</b> →</div>
      <div class="diagram-box model"><b>Governed model inputs</b><span>definitions, eligibility,<br>native source data</span></div>
      <div class="arrow">separate boundary →</div>
      <div class="diagram-box activity"><b>Activity workbook</b><span>tidy activity_data<br>+ activity_dictionary</span></div>
      <div class="arrow">and →</div>
      <div class="diagram-box context"><b>Context workbook</b><span>tidy context_data<br>+ variable_dictionary + events</span></div>
    </div>
    """

    upload_types_table = simple_table(
        ["Upload", "Do I need it?", "What it's for", "Where to get it"],
        [
            [
                "Outcomes",
                "Yes — always",
                "The KPI numbers the model explains",
                "“Outcomes (v2)” download button",
            ],
            [
                "Activity and Media",
                "Yes — always",
                "Spend, clicks, impressions and other media/activity data",
                "“Activity and Media” download button",
            ],
            [
                "Context and External Factors",
                "Yes — always",
                "Controls like CPI, seasonality, and named events",
                "“Context and External Factors” download button",
            ],
            [
                "Outcome Valuation (FH LTR / DNA revenue)",
                "Only for monetary ROI reporting",
                "Turns counts into pound/dollar value",
                "“Download valuation template”, in its own section of the upload page",
            ],
            [
                "Experiment Evidence",
                "Only if you have a lift test or experiment to record",
                "Stores raw experiment/lift-test rows for future calibration",
                "“Experiment Evidence” download button",
            ],
            [
                "Candidate A Search observations",
                "Only for the Search capacity/mediation feature",
                "Weekly Search delivery, cap, and organic-capture numbers",
                "“Download Candidate A observation template”, on the Model Training page",
            ],
            [
                "Google Trends Brand Demand anchor",
                "Only for the Search capacity/mediation feature",
                "An approved weekly Brand-search-interest series",
                "Upload box on the Model Training page",
            ],
            [
                "SEO / Google Search Console visibility",
                "Only for the SEO visibility feature",
                "Organic search ranking/impression data",
                "Upload box on the Model Training page",
            ],
            [
                "Demo or realistic sample data",
                "No — exploration only",
                "Fake data to try the app before you have real data",
                "“Load demo data” button",
            ],
        ],
        "wide",
    )

    minimum_checklist_html = f"""
    <div class="callout">
      <b>Minimum for your first UK count-based model.</b> You need exactly three workbooks: Outcomes, Activity and Media, and Context and External Factors. Inside each, only a handful of fields are truly required — they are listed under <b>Fields you must fill in</b> in each section below. Everything else on this page is optional or only needed for a specific later feature.
    </div>
    {upload_types_table}
    <div class="callout warning">
      <b>Add later, once the first fit works:</b> FH LTR / DNA revenue value reporting, Experiment Evidence, Search capacity (Candidate A), SEO visibility, and named-event administration. See <a href="#add-later">Add these later</a>.
    </div>
    """

    faq = [
        (
            "What is the safest first upload?",
            'Upload the three required workbooks — Outcomes, Activity and Media, and Context — using the current templates. Fill in only the fields marked <b>Fields you must fill in</b> to start. See <a href="#workflow">the checklist</a>.',
        ),
        (
            "Can one domain use more than one physical file?",
            "Yes. You can upload several files for the same domain. The app merges them only when the keys and values agree.",
        ),
        (
            "Is market read from the filename?",
            "No. Market must be a column in every table, on every row. The app never guesses it from a filename.",
        ),
        (
            "Should I make all data weekly before uploading?",
            "No. Upload each source at whatever frequency it actually comes in (weekly, monthly, quarterly). Converting frequency is a separate, later step.",
        ),
        (
            "Are missing values the same as zero?",
            "No. A missing value means “we don't know.” A zero means “we checked, and it was zero.” Never use one to mean the other.",
        ),
        (
            "Which Family History segments are in scope?",
            "New, Winback, and DNA cross-sell. Don't invent a fourth segment without checking with the project first.",
        ),
        (
            "Are GSA and Net Bill Through the same metric?",
            "No. They are two different measures with different dates, cohorts, and approval needs. Keep them in separate columns.",
        ),
        (
            "What is the completeness sheet for?",
            "It records how fresh and complete an outcome's data is — useful for any KPI, and required for official UK production NBT.",
        ),
        (
            "Does production NBT use the 14-day example shown elsewhere in this guide?",
            "No. That 14-day rule is just an illustrative example for historical/test work. Production NBT uses its own approved rule and evidence — see the UK production NBT box in the Outcomes section.",
        ),
        (
            "Does the downloadable sample outcome workbook already use the NBT ids?",
            "No. The sample teaches the pattern with GSA ids. Real UK production NBT ids come from the approved UK source pack.",
        ),
        (
            "Does the activity ID need every metadata field?",
            "No. Use the smallest name that keeps every activity unique. Put descriptive detail in the dictionary fields instead of the ID.",
        ),
        (
            "Does pooling_group_id make the model pool markets together?",
            "No. It's just a label saying “these activities are comparable.” Pooling is a separate, later modelling choice.",
        ),
        (
            "Do spend and clicks mean the same thing?",
            "No. Spend is money. Clicks are a count of a physical response. Keep them in separate columns and pick one as the model input.",
        ),
        (
            "How are Brand and Non-Brand Search represented?",
            "As separate activities, tagged with search_intent_group_id (brand_search / non_brand_search) and search_platform (google / bing).",
        ),
        (
            "Can I add a deeper Non-Brand Search child group, like a specific sub-category?",
            "Only through a separate governed process, and it starts as “draft.” It can't be fitted alongside its parent group at the same time, and it has no budget-planning use until it has its own real cost data.",
        ),
        (
            "Can SEO visibility be split by Brand and Non-Brand?",
            "Yes, using seo_group_id. If you don't set a group, everything goes into one combined group.",
        ),
        (
            "Are PMax, Demand Gen, and YouTube the same as Paid Search?",
            "No. The app never assumes this just because the platform is Google. Classify them explicitly.",
        ),
        (
            "What is a Search cap?",
            "A spending or delivery ceiling — a limit, not money that was actually spent.",
        ),
        (
            "Can monthly context data be manually copied into every week?",
            "No. Upload it as monthly. Turning it into weekly numbers is a separate, governed step — don't invent weekly rows yourself.",
        ),
        (
            "Does uploading Experiment Evidence automatically change the model?",
            "No. It's stored as evidence only. A person has to separately review and approve it before it affects a model.",
        ),
        (
            "Is Outcome Valuation (FH LTR) part of the normal Outcomes workbook?",
            'No — it is a completely separate, optional upload. See <a href="#ltr">FH LTR and DNA revenue</a>.',
        ),
        (
            "Does a currency column convert money between currencies?",
            "No. It just labels what currency the number is in. Actual conversion needs a separate, approved exchange rate.",
        ),
        (
            "What happens if two rows have the same key (same date, market, and ID)?",
            "The upload is rejected and you're asked to fix it. The app never silently merges or adds duplicate rows together.",
        ),
        (
            "My upload was rejected, or shows a warning. What do I do?",
            "Read the exact message — it names the specific problem, such as a missing required column, a duplicate row, or the wrong sheet name. Fix that one thing and upload again. The app never guesses a fix or silently patches your file for you.",
        ),
        (
            "Why does the Dictionary Builder show a collision warning?",
            "Because two rows would end up with the exact same ID. Add one more distinguishing detail — don't just add a random number.",
        ),
        (
            "Can I override the ID the Dictionary Builder suggests?",
            "Yes, using the Manual override ID column. You're still responsible for keeping it unique and consistent with the dictionary.",
        ),
        (
            "Do I have to use the Dictionary Builders, or can I fill in the dictionary sheets by hand?",
            "You can do either — the builders are a convenience, not a requirement. Each one produces a normal <code>DICTIONARY_OUTPUT</code> sheet that you copy into the standard upload workbook; the parser can't tell the difference.",
        ),
        (
            "Where can I find the exact technical contract behind this guide?",
            'See the source files and tests listed in <a href="#review">Source and review</a>, and the collapsible “Full technical field reference” at the end of each section above.',
        ),
    ]
    faq_html = "".join(
        f"<details><summary>{esc(q)}</summary><p>{a}</p></details>" for q, a in faq
    )

    outcomes = domain_section(
        "outcomes",
        "1",
        "Outcomes",
        "Outcomes are the KPI numbers the model is trying to explain — things like sign-ups or Net Bill Through.",
        "Yes, always. Every project needs this workbook.",
        "One row is one market, in one week. Each KPI gets its own column — for example, one column for New GSA and another for Winback GSA.",
        "Two required sheets: <code>outcomes</code> (the actual weekly numbers) and <code>outcome_dictionary</code> (what each column means). One optional sheet: <code>outcome_completeness</code> — only needed for official or maturity-sensitive outcomes, including UK production NBT.",
        "period_start | market | fh_gsa_new | fh_gsa_dna_cross_sell | fh_gsa_winback\n2026-01-05   | UK     | 120        | 18                    | 9",
        [
            [
                "outcome_id",
                "A short, stable name for this outcome.",
                "Lowercase, no spaces. Never changes once other things reference it.",
                "fh_gsa_new",
            ],
            [
                "source_column",
                "The exact column header in the <code>outcomes</code> sheet that holds this KPI's numbers.",
                "Must match the outcomes-sheet header exactly, letter for letter.",
                "fh_gsa_new",
            ],
            [
                "product",
                "Which product line this KPI belongs to.",
                "Family History or DNA (or another approved product).",
                "Family History",
            ],
            [
                "metric_key",
                "The stable registry name for what's being measured.",
                "An approved key from the registry, or <code>custom</code> for a genuinely new measure.",
                "fh_gsa",
            ],
            [
                "metric",
                "The human-readable name of the measure.",
                "Plain text.",
                "GSA",
            ],
            [
                "segment",
                "Which customer group this row covers.",
                "New, Winback, DNA cross-sell, or another approved segment.",
                "New",
            ],
        ],
        [
            [
                "segment_dimension",
                "Only worth choosing deliberately if the same segment word could mean different things in different places — the app does require some value here, so write unspecified if none of the other options apply.",
                "Which approved vocabulary the segment value comes from.",
            ],
            [
                "outcome_group_id, outcome_group_label, outcome_family_key, group_aggregation",
                "Only if you want the app to know that several outcomes add up to a governed total.",
                "Fill in all four together, or leave all four blank — don't fill in some and skip others.",
            ],
            [
                "role, included_in_fit, include_in_default_reporting, include_in_official_total, include_in_value, include_in_optimisation",
                "Only if the sensible defaults don't match what you want (by default, a new outcome is treated as primary, fitted, and reported).",
                "Each is a separate on/off switch for one specific use.",
            ],
            [
                "definition_version, event_definition, cohort_or_attribution_basis, completeness_or_maturity_policy, exclusions, reconciliation_source, business_owner",
                "Only needed to get this outcome officially approved for production reporting.",
                "Together they record who defined the measure, exactly what it counts, and how it reconciles to Finance.",
            ],
            [
                "value_weight, value_currency",
                "Only if this outcome feeds ROI or monetary value reporting.",
                "A per-unit value and the currency it's in.",
            ],
        ],
        [
            [
                "unit, aggregation_type",
                "Usually filled in automatically from metric_key — you don't normally need to type these.",
            ],
            [
                "date_basis, maturity_required",
                "These columns exist in the sheet, but the app does not currently use them for anything. Safe to leave blank.",
            ],
            [
                "effective_from, effective_to",
                "Only useful if this definition's meaning changes at a known date.",
            ],
        ],
        OUTCOME_RAG,
        "In this example, the dictionary row for <code>outcome_id=fh_gsa_new</code> points at <code>source_column=fh_gsa_new</code> — the app checks that this column really exists in the <code>outcomes</code> sheet. It never guesses meaning from the ID itself.",
        [
            "Using “NBT” as a friendly nickname for GSA, or assuming sign-up → GSA → NBT always happens in that order.",
            "Uploading outcomes in long format — the standard contract expects one wide row per market-week.",
            "Leaving the dictionary fields blank and hoping the ID explains everything.",
            "Guessing product or segment from the column name instead of stating them.",
            "Adding new DNA splits (self-activated, gifted) without checking they're approved first.",
            "Reconstructing weekly NBT yourself from raw billing events — upload the already-governed weekly number instead.",
            "Treating the illustrative 14-day maturity example as the production NBT rule.",
        ],
        [
            [
                "fh_gsa_new with product=Family History, segment=New, metric_key=fh_gsa",
                "metric_key=fh_net_billthrough_count but metric says “GSA”",
                "The key, label, and definition disagree with each other.",
            ],
            [
                "outcome_group_id left blank for a standalone outcome",
                "group_aggregation=sum with no group ID set",
                "The four group fields must be filled in together, or all left blank.",
            ],
            [
                "GSA and NBT as two separate columns",
                "One column labelled “GSA/NBT”",
                "They are different measures with different rules — never combine them.",
            ],
        ],
        extra_html='<h3 id="ltr">Optional: FH LTR and DNA revenue</h3>'
        '<div class="callout warning"><b>FH LTR does not go in this Outcomes workbook.</b> It is a completely separate, optional upload.</div>'
        "<p>Use this only if you want monetary value or ROI reporting — it is not needed to get your first count-based fit working. Download it from its own “Optional weekly outcome valuations (FH LTR / DNA revenue)” section of the Data Upload page, using the “Download valuation template” button there.</p>"
        "<p>One row is one <code>valuation_kind</code> (fh_ltr or dna_revenue), in one market, in one week, for one segment. The required columns are <code>valuation_kind, market, week, segment, denominator_outcome_id, quality_status, segment_dimension, aggregate_value, currency, source, source_version, schema_version, horizon_months</code>.</p>"
        "<p><code>aggregate_value</code> is a total pound/dollar value for that market-week-segment cell, never a per-customer figure. The app divides it by the matching count outcome's real observed number to work out a rate per unit — it never multiplies or invents a rate. <code>denominator_outcome_id</code> must be a real, existing <code>outcome_id</code> from your Outcomes dictionary that counts things (not a rate), such as an approved NBT or GSA outcome — there is no default; you must name it explicitly.</p>"
        '<div class="callout"><b>The 48-month rule.</b> For <code>fh_ltr</code> rows, <code>horizon_months</code> must be exactly <b>48</b> — this is an approved, fixed rule, not a number you choose. For <code>dna_revenue</code> rows, leave <code>horizon_months</code> blank. Any other value is rejected.</p>'
        '<h3 id="uk-nbt-production">UK production Net Bill Through (NBT)</h3>'
        "<div class=\"callout warning\"><b>This is a specific UK production example, not a general rule.</b> It doesn't change anything above, and it doesn't apply automatically to other markets or projects.</div>"
        "<p>UK production uses three separate NBT outcomes: <code>fh_net_billthrough_count_new</code>, <code>fh_net_billthrough_count_dna_cross_sell</code>, and <code>fh_net_billthrough_count_winback</code>. They share <code>metric_key=fh_net_billthrough_count</code>, with New, DNA cross-sell, and Winback as separate <code>segment</code> values — the same pattern shown for GSA above. GSA stays a separate, secondary measure: NBT is never built from GSA, and GSA is never built from NBT.</p>"
        "<p>Production NBT needs its own completeness evidence supplied with the source pack — the approved definition, what's excluded, where it reconciles to, the data-as-of date, and a source fingerprint. This is a stricter, separate rule from the illustrative 14-day example used elsewhere in this guide for exploratory work. The full rule is recorded in <code>docs/uk_production_onboarding_runbook.md</code> and requirement records <code>REQ-NBT-001</code> through <code>REQ-NBT-004</code>; this guide only summarises them for someone preparing an upload.</p>"
        + "<h3>Optional outcome completeness sheet (<code>outcome_completeness</code>)</h3><p>Use the outcome completeness sheet for freshness, model-window, maturity, and ownership information. Required for official NBT use.</p>"
        + html_table(COMPLETENESS_RAG, "wide"),
        builder_html=dictionary_builder_section(
            "Ancestry_MMM_Outcome_Dictionary_Builder.xlsx",
            "outcome_dictionary",
            "Turns product, metric, and segment choices into a complete, upload-ready <code>outcome_dictionary</code> row and generates a stable <code>outcome_id</code> for you.",
            [
                "product, metric_key, segment, and metric — the same identity fields described above.",
                "source_column, if it needs to differ from the generated outcome_id (it defaults to the same value).",
            ],
            [
                "outcome_id — built from product, metric_key, and segment, the same way as the identity fields above.",
                "unit and aggregation_type are not asked for at all — the app fills them in automatically from metric_key for every registered metric.",
                "segment_dimension defaults to unspecified if you leave it blank — a real, accepted value, not a fabricated one. The live parser does require some value here (confirmed by testing this builder's output against it), so this default keeps a blank cell safe.",
            ],
            ["product", "metric_key", "segment_dimension", "group_aggregation", "role"],
            "product is Family History or DNA; metric_key is an approved registry key or custom; group_aggregation is sum or none; role is primary, secondary, funnel_intermediate, or diagnostic.",
            [
                "segment_dimension — only fill this in if the same segment word could mean different things in different places; otherwise the builder defaults it to unspecified for you.",
                "The four outcome-group fields — only needed if this outcome is one component of a governed semantic total.",
                "The five eligibility on/off switches — only needed to override the sensible role-based defaults.",
                "The seven official-approval fields — only needed to get this outcome approved for production reporting.",
                "value_weight / value_currency — only needed for ROI or monetary value reporting.",
                "date_basis and maturity_required are not offered by this builder: the app does not currently read either field (see the schema-necessity review). If your project needs them recorded anyway, add the columns and values by hand after copying the output.",
            ],
            "The actual weekly KPI numbers still go in the <code>outcomes</code> sheet, not this builder.",
        ),
    )

    activity = domain_section(
        "activity",
        "2",
        "Activity and Media",
        "Activity data describes what was delivered, spent, or observed for each marketing activity.",
        "Yes, always. Every project needs this workbook.",
        "One row is one activity, in one market, in one week. If you have spend, clicks, and impressions for the same activity, they're three columns on that same row.",
        "Two required sheets: <code>activity_data</code> (the actual weekly numbers) and <code>activity_dictionary</code> (what each activity is and how the app should treat it).",
        "period_start | market | activity_id                 | spend | impressions | clicks\n2026-01-05   | UK     | paid_search_google_brand   | 1200  | 180000      | 8200",
        [
            [
                "activity_id",
                "A stable name for this specific activity.",
                "Lowercase, unique within a market.",
                "paid_search_google_brand",
            ],
            [
                "channel",
                "The channel or reporting family.",
                "Plain text — be specific, not a generic label.",
                "Paid Search",
            ],
            [
                "market",
                "The market this activity_dictionary row applies to.",
                "The same market code used on the activity_data sheet.",
                "UK",
            ],
            [
                "activity_ownership",
                "Who controls or supplies the activity.",
                "paid, owned, earned, or external_event — this is a required choice; it cannot be left blank.",
                "paid",
            ],
            [
                "intended_model_role",
                "What role this activity plays in the model.",
                "intervention, mediator, demand_capture, control, or event.",
                "intervention",
            ],
            [
                "model_input_column",
                "The name the app gives this activity's number after processing.",
                "A stable, unique name — this is not a raw column from your data.",
                "uk_paid_search_google_brand",
            ],
            [
                "model_input_measure",
                "Which raw column (spend, clicks, impressions…) the model should actually be fitted on.",
                "The exact header of a real column in activity_data.",
                "spend",
            ],
            [
                "economic_treatment",
                "How cost is treated for this activity.",
                "paid_media_cost, fully_loaded_cost, campaign_cost, response_only, or not_applicable.",
                "paid_media_cost",
            ],
            [
                "planning_eligibility",
                "Whether this activity can be used in budget planning or optimisation.",
                "optimisable, scenario_only, fixed, or excluded.",
                "optimisable",
            ],
            [
                "source",
                "Where this data came from.",
                "Plain text, ideally with a date or version.",
                "Google Ads export 2026-08",
            ],
        ],
        [
            [
                "campaign_type",
                "Only needed to separate Brand and Non-Brand Paid Search — but the upload does currently reject a truly empty cell, so write not specified if it doesn't apply.",
                "Brand or Non-Brand.",
            ],
            [
                "search_intent_group_id, search_platform",
                "Only for Paid Search activities you want split by Brand/Non-Brand and Google/Bing.",
                "brand_search or non_brand_search; google or bing. Note: today these must be set up separately after upload — the standard sheet doesn't apply them automatically yet.",
            ],
        ],
        [
            [
                "platform, funnel_stage, product_advertised, marketing_objective, message_type, pooling_group_id",
                "Useful for reporting and dashboards, but the model and the optimiser don't read them. Fill in what you have; don't worry about getting them perfect. Except for pooling_group_id, the upload does currently reject a truly empty cell in these columns — write not specified (or unclassified for funnel_stage) rather than leaving one blank.",
            ],
        ],
        ACTIVITY_RAG,
        "For <code>activity_id=paid_search_google_brand</code> with <code>model_input_measure=spend</code>, the app takes the raw <code>spend</code> column and writes it into a new destination column, <code>model_input_column=uk_paid_search_google_brand</code>. That's why these two fields look similar but are different: one names a column already in your file, the other names a column the app is about to create.",
        [
            "Uploading activity data wide (one column per activity) — the standard contract expects tidy/long rows instead.",
            "Cramming every descriptive detail into the activity_id instead of using the dictionary fields.",
            "Treating model_input_column as if it were a column that should already exist in your raw file.",
            "Treating spend, clicks, and conversions as interchangeable without an explicit mapping.",
            "Filling in missing weeks with zero instead of leaving them out.",
            "Assuming an activity is automatically optimisable just because it was fitted.",
            "Calling PMax, Demand Gen, or YouTube “Paid Search” just because the platform is Google.",
        ],
        [
            [
                "spend selected as model_input_measure, unit GBP",
                "model_input_measure set to the destination column name",
                "The raw source column and the model-ready destination column are not the same thing.",
            ],
            [
                "Google Brand and Bing Brand as two separate activity_ids",
                "Google and Bing lumped into one “Brand Search” activity",
                "Platform identity has to be explicit, not buried in a filename or note.",
            ],
            [
                "A missing week left out of the sheet",
                "A missing week filled in as 0",
                "Missing and zero mean different things — don't guess.",
            ],
        ],
        extra_html='<div class="callout warning"><b>These five columns currently have no effect: <code>model_input_unit</code>, <code>model_input_kind</code>, <code>spend_column</code>, <code>response_unit_column</code>, <code>response_unit</code>.</b> They exist in the template, but today the app does not automatically apply them from this sheet — filling them in here changes nothing in the model. The real place to set units and cost mappings is inside the app, in Channel Media Units and Curve Generation, after your data is uploaded. You can leave these blank for your first upload.</div>',
        builder_html=dictionary_builder_section(
            "Ancestry_MMM_Activity_Dictionary_Builder.xlsx",
            "activity_dictionary",
            "Turns business-facing choices — channel, market, and (for Paid Search) platform and campaign type — into a complete, upload-ready <code>activity_dictionary</code> row and generates a stable <code>activity_id</code>.",
            [
                "channel, market, activity_ownership, intended_model_role, model_input_measure, economic_treatment, planning_eligibility, and source.",
                "model_input_column, if it needs to differ from the generated activity_id (it defaults to the same value).",
                "platform and campaign_type — the same two ordinary activity_dictionary fields any channel uses, not Search-only inputs — fill these in when they help distinguish one activity from another (Google vs Bing, Brand vs Non-Brand). If you leave either blank, DICTIONARY_OUTPUT fills in not specified for you, since the live parser currently rejects a truly empty value.",
            ],
            [
                "activity_id — built from channel plus whichever of platform and campaign_type you filled in, the same way as the standalone identity fields above.",
            ],
            [
                "activity_ownership",
                "intended_model_role",
                "economic_treatment",
                "planning_eligibility",
                "funnel_stage",
            ],
            "activity_ownership is paid, owned, earned, or external_event; intended_model_role is intervention, mediator, demand_capture, control, or event; economic_treatment is paid_media_cost, fully_loaded_cost, campaign_cost, response_only, or not_applicable; planning_eligibility is optimisable, scenario_only, fixed, or excluded.",
            [
                "pooling_group_id, funnel_stage, marketing_objective, product_advertised, and message_type — the necessity review confirmed the model, canonicalisation, and optimiser never read their values; only reporting rollups and the causal-graph display do. Fill in what you have. If you leave one blank, the DICTIONARY_OUTPUT sheet automatically fills in a harmless placeholder (unclassified for funnel_stage, not specified for the others) — testing this builder's output against the live parser confirmed a truly empty value is currently rejected for these columns, even though nothing meaningful reads them.",
                "currency, effective_from, effective_to — optional provenance metadata.",
            ],
            "This builder does not ask for model_input_unit, model_input_kind, spend_column, response_unit_column, or response_unit — the necessity review confirmed these five columns are currently write-only in the standard upload path (see the callout above). Their column headers still appear, blank, in DICTIONARY_OUTPUT, because the current schema requires them once other v2 columns are present — this builder just never asks you to fill them in. It also does not ask for search_platform or search_intent_group_id: they are not activity_dictionary columns today — activity_definitions_from_dictionary still doesn't map them from a standard workbook — so this builder does not pretend they are ordinary fields. Use platform and campaign_type above to keep your activity_id readable; the governed Search-taxonomy mapping (Brand/Non-Brand, Google/Bing at the ActivityDefinition level) is configured separately, after upload, until that mapping gap is closed. The actual weekly activity numbers still go in the <code>activity_data</code> sheet, not this builder.",
        ),
    )

    context = domain_section(
        "context",
        "3",
        "Context and External Factors",
        "Context data captures things outside your control that might explain changes in the outcome — like CPI, seasonality, or holidays.",
        "Yes, always. Every project needs this workbook.",
        "One row is one variable, in one market, at whatever frequency it's actually published — weekly, monthly, or quarterly.",
        "Two required sheets: <code>context_data</code> (the actual observations) and <code>variable_dictionary</code> (what each variable is). One optional sheet: <code>events</code> (named dates like Black Friday).",
        "period_start | market | variable_id | value | native_frequency\n2026-01-01   | UK     | uk_cpi      | 132.4 | monthly",
        [
            [
                "variable_id",
                "A stable name for this variable.",
                "Lowercase, unique in the dictionary.",
                "uk_cpi",
            ],
            [
                "value",
                "The actual number observed.",
                "A real number, or leave the row out entirely if truly unavailable — never a made-up placeholder.",
                "132.4",
            ],
            [
                "native_frequency",
                "How often this variable is actually published. Preserved at upload, but Page 15 (Data Coverage) re-asks separately and defaults to weekly regardless of what you enter here — treat this as upload-time metadata, not a setting Page 15 will honour.",
                "weekly, monthly, quarterly, yearly, daily, or event.",
                "monthly",
            ],
            [
                "variable_class",
                "What kind of variable this is. Page 15 (Data Coverage) does not read this uploaded value at all — it defaults every variable to flow_count regardless, so treat this as informational at upload time, not a setting Page 15 will honour.",
                "flow_count, stock_level, rate_index, survey_measurement, or event_flag.",
                "rate_index",
            ],
            [
                "role",
                "How this variable is intended to be used in forecasting. No enum is enforced anywhere in the app today, despite the name — this is currently free text; see the technical reference below.",
                "Free text today. A documented example is exogenous_forecastable_control — not a fixed list.",
                "exogenous_forecastable_control",
            ],
        ],
        [
            [
                "source, scope",
                "Only needed once this variable is reviewed for wider use (“adoption”), not for a first upload.",
                "Where it came from, and whether it's UK-specific or a wider series.",
            ],
        ],
        [
            [
                "effective_from, effective_to, unit",
                "Only fill these in if useful — they don't block anything if left blank.",
            ],
        ],
        CONTEXT_RAG,
        "The row for <code>variable_id=uk_cpi</code> joins to a dictionary row with <code>variable_class=rate_index</code> and <code>native_frequency=monthly</code>. The app keeps it monthly — it never invents a weekly number from a monthly one.",
        [
            "Copying a monthly number into every week of that month.",
            "Treating “unavailable” the same as zero.",
            "Reusing one variable_id for two different things with different units.",
            "Forecasting a variable that the model itself generates (like branded-search demand) as if it were an independent external input.",
            "Assuming the app will convert monthly data to weekly for you — it currently doesn't have a default conversion.",
        ],
        [
            [
                "uk_cpi stays monthly",
                "uk_cpi copied into four weekly rows",
                "The real publishing frequency must stay truthful.",
            ],
            [
                "variable_class=rate_index",
                "A made-up class not on the approved list",
                "Only the five approved classes are accepted.",
            ],
            [
                "A missing/suppressed value left out",
                "A missing/suppressed value entered as 0",
                "Missing is not the same as an observed zero.",
            ],
        ],
        extra_html="<h3>Optional events sheet</h3><p>A separate table for named dates — keep the real dates and a name; the app never guesses what kind of event it is or what effect it has.</p>"
        + html_table(EVENT_RAG, "wide"),
        builder_html=dictionary_builder_section(
            "Ancestry_MMM_Context_Dictionary_Builder.xlsx",
            "variable_dictionary",
            "Turns a variable's class and concept into a complete, upload-ready <code>variable_dictionary</code> row and generates a stable <code>variable_id</code>.",
            [
                "variable_class and a short concept name — used to build the id.",
                "native_frequency — how often the variable is actually published.",
                "role — free text today (see the caveat below); a short example is offered, not a fixed list.",
            ],
            [
                "variable_id — built from variable_class and the concept name, the same way as the identity field above.",
            ],
            ["variable_class"],
            "variable_class is one of the five approved classes: flow_count, stock_level, rate_index, survey_measurement, or event_flag.",
            [
                "source, scope — only needed once this variable is reviewed for wider use (“adoption”), not for a first upload.",
                "effective_from, effective_to — optional provenance metadata.",
            ],
            '<div class="callout warning"><b>Read this before filling in variable_class, native_frequency, and role.</b> The schema-necessity review found that the app\'s real governance screen (Page 15, Data Coverage) does not read the uploaded variable_class or native_frequency at all — it re-asks for both and defaults them itself regardless of what you upload here. role has no enforced list anywhere in the code today, so this builder offers it as free text rather than inventing a dropdown. Filling these in is still required for the upload to be accepted, but expect to confirm variable_class and native_frequency again on Page 15 after upload. This is a documented application limitation, not something this builder can fix. The actual observations still go in the <code>context_data</code> sheet, not this builder.</div>',
        ),
    )

    add_later_reference = simple_table(
        [
            "Add-on",
            "Do I need it now?",
            "What it unlocks",
            "Where to get it",
            "Key rule",
        ],
        [
            [
                "Experiment Evidence",
                "No",
                "Future ability to calibrate the model against a real lift test",
                "“Experiment Evidence” download button",
                "Uploading evidence never changes a model by itself — a person has to review and adopt it.",
            ],
            [
                "Candidate A Search observations",
                "No",
                "Search capacity/mediation modelling",
                "Model Training page → “Download Candidate A observation template”",
                "Needs a complete weekly grid with no gaps, and delivery must never exceed the cap.",
            ],
            [
                "Google Trends Brand Demand anchor",
                "No",
                "Feeds the Search capacity/mediation feature",
                "Model Training page, upload box",
                "A reading of 0 means “suppressed,” not “confirmed zero demand.”",
            ],
            [
                "SEO / Google Search Console visibility",
                "No",
                "A separate organic-search visibility measure",
                "Model Training page, upload box",
                "Never zero-fill a missing week, and it never carries a spend-based ROI.",
            ],
            [
                "Named events administration",
                "No",
                "Turns event dates from the Context events sheet into governed, reusable events",
                "“Named events administration” section of the Data Upload page",
                "The app never infers what kind of event it is — you classify it explicitly.",
            ],
        ],
        "wide",
    )

    search_table = simple_table(
        ["Object", "Unit", "Role / treatment", "Where it comes from"],
        [
            [
                "search_demand",
                "index or count",
                "demand signal, not paid",
                "Google Trends Brand Demand anchor, or another approved source",
            ],
            [
                "paid_search_spend",
                "currency",
                "a normal paid activity",
                "activity data + cost mapping",
            ],
            [
                "paid_search_delivery",
                "clicks or impressions",
                "descriptive delivery, not a second spend figure",
                "activity data",
            ],
            [
                "paid_search_cap",
                "currency or delivery unit",
                "a limit, not real spend",
                "Candidate A inputs",
            ],
            [
                "organic_search_capture",
                "response count",
                "an earned/organic result",
                "activity or dedicated source",
            ],
            [
                "residual Paid Search incrementality",
                "model output",
                "something the model calculates",
                "never a raw upload column",
            ],
        ],
        "compact",
    )

    advanced = f"""
    <section id="advanced" class="section">
      <p class="eyebrow">Add these later</p><h2 id="add-later">Optional and feature-specific uploads</h2>
      <p>None of these are needed to get your first count-based fit working. Uploading one of them doesn't automatically turn on the feature it belongs to — a person still reviews and approves it.</p>
      {add_later_reference}
      <h3>Why Search needs several separate objects, not one “Brand Search” column</h3>
      <p>{search_table}</p>
      <p>The minimum Search split is Google Brand, Bing Brand, Google Non-Brand, and Bing Non-Brand — four activities, not one. A deeper Non-Brand sub-category is possible through a separate governed process; it starts as “draft,” can't be modelled alongside its parent at the same time, and has no budget-planning use until it has its own real cost data. PMax, Demand Gen, and YouTube are never automatically treated as Paid Search just because the platform is Google.</p>
      <h3>Future-variable roles (for advanced/planning uploads)</h3>
      {simple_table(["Role", "Meaning", "Example"], [["planned decision variable", "Something a user sets, like spend or price", "Paid Search spend"], ["exogenous forecastable control", "An outside series you can reasonably forecast", "CPI or unemployment"], ["cost/translation assumption", "A conversion rate, like cost per click", "GBP per click"], ["endogenous funnel state", "Something the model itself generates", "Branded-search demand"], ["latent baseline state", "A background trend the model fits on its own", "Time-varying intercept"], ["fixed business assumption", "Held fixed unless a person changes it", "An approved business rule"]], "compact")}
    </section>
    """

    workflow = f"""
    <section id="workflow" class="section">
      <p class="eyebrow">Start here</p><h2>What do I actually need to upload?</h2>
      {minimum_checklist_html}
      <h3>How uploading works</h3>
      <ol class="steps"><li>Download the three required templates.</li><li>Fill in the dictionary fields marked “Fields you must fill in” before loading a large raw file.</li><li>Keep each source at its real, native frequency, and keep market as a column in every row.</li><li>Upload Outcomes, Activity and Media, and Context. Add anything from “Add these later” only once you actually need it.</li><li>Check the warnings the app shows you — missing values, duplicate rows, and how your fields were mapped.</li><li>A successful upload is not an approval. Reporting, planning, and optimisation are separate, later steps.</li></ol>
      <h3>Three words that prevent most mistakes</h3>
      {simple_table(["Word", "Means", "Does not mean"], [["raw", "exactly what your source file supplied", "a model-ready, cleaned-up table"], ["dictionary", "what a column means and how it's governed", "permission to guess at missing values"], ["canonical", "the one official, processed version the model uses", "something the app invents automatically for you"]], "compact")}
    </section>
    """

    glossary = simple_table(
        ["Term", "Plain-English meaning"],
        [
            ["activity_id", "A stable name for one activity, in one market."],
            ["model_input_measure", "The raw column the model is actually fitted on."],
            [
                "model_input_column",
                "The new column name the app creates after processing.",
            ],
            ["outcome_id", "A stable name for one outcome definition."],
            ["variable_id", "A stable name for one context variable."],
            ["native frequency", "How often the source data is really published."],
            [
                "pooling_group_id",
                "A label saying two activities are comparable — it does not force the model to combine them.",
            ],
            ["cap", "A spending or delivery limit, not money that was actually spent."],
            ["missing", "“We don't know,” never the same as a real zero."],
            [
                "maturity rule",
                "The rule for when an outcome's data is complete enough to trust.",
            ],
            [
                "RED / AMBER / GREEN",
                "How urgently a field matters: RED = always fill it in, AMBER = only for some uses, GREEN = optional.",
            ],
        ],
        "compact",
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Ancestry MMM Data Upload Guide</title>
<style>
:root{{--ink:#18212b;--muted:#5d6b78;--blue:#0b5cab;--navy:#12304a;--wash:#f3f7fb;--line:#d9e2ea;--red:#fce4e4;--amber:#fff1cc;--green:#e3f4e6;--grey:#edf0f2;--shadow:0 8px 24px rgba(19,48,74,.09)}}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth}} body{{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;color:var(--ink);line-height:1.55;background:#fff}} a{{color:var(--blue)}} a:visited{{color:#5b2a86}} code{{background:#eef3f7;color:#173b5e;border-radius:4px;padding:.1em .3em;font-size:.93em;overflow-wrap:anywhere}} footer a:visited{{color:#fff}} .skip{{position:absolute;left:-9999px}} .skip:focus{{left:1rem;top:1rem;background:#fff;padding:.5rem;z-index:10}}
.layout{{display:grid;grid-template-columns:260px minmax(0,1fr);min-height:100vh}} aside{{position:sticky;top:0;height:100vh;overflow:auto;background:var(--navy);color:#fff;padding:1.25rem}} aside h2{{font-size:1.1rem;color:#fff;margin:.2rem 0 1rem}} aside p{{font-size:.82rem;color:#c9d8e5}} nav a{{display:block;color:#e0edf7;text-decoration:none;padding:.32rem .2rem;font-size:.88rem}} nav a:hover,nav a:focus{{color:#fff;background:rgba(255,255,255,.1);border-radius:4px}} .search{{width:100%;padding:.55rem;border-radius:5px;border:1px solid #6e91aa;margin:.4rem 0 1rem}} main{{min-width:0}} .hero{{background:linear-gradient(135deg,#eaf4ff,#fff);padding:4rem clamp(1rem,5vw,5rem) 3.25rem;border-bottom:1px solid var(--line)}} .hero h1{{font-size:clamp(2rem,4vw,3.6rem);line-height:1.08;color:var(--navy);max-width:850px;margin:.2rem 0 1rem}} .hero p{{max-width:780px;font-size:1.08rem}} .badge{{display:inline-block;background:#dbeeff;color:#084d8d;padding:.25rem .55rem;border-radius:999px;font-weight:700;font-size:.78rem}} .section{{padding:3rem clamp(1rem,5vw,5rem);max-width:1500px}} .section:nth-of-type(even){{background:#fff}} .domain{{border-top:1px solid var(--line)}} h2{{font-size:2rem;color:var(--navy);margin:.15rem 0 1.1rem}} h3{{color:#234f72;margin-top:1.8rem}} .eyebrow{{text-transform:uppercase;letter-spacing:.12em;font-size:.76rem;color:var(--blue);font-weight:800;margin:0}} .callout{{border-left:5px solid var(--blue);background:var(--wash);padding:1rem 1.2rem;margin:1.2rem 0}} .warning{{border-left-color:#c67a00;background:#fff8e7}} .builder{{border-left-color:#1a7a4c;background:#f1faf5}} .builder h3{{margin-top:.2rem}} .builder ul{{margin:.3rem 0 .8rem;padding-left:1.2rem}} .builder li{{margin:.25rem 0}} .table-wrap{{overflow:auto;margin:1rem 0 1.25rem;border:1px solid var(--line);border-radius:7px}} table{{border-collapse:collapse;width:100%;background:#fff;font-size:.87rem}} th,td{{border-bottom:1px solid var(--line);padding:.55rem .65rem;text-align:left;vertical-align:top}} th{{background:#eaf1f6;color:var(--navy);font-weight:800;position:sticky;top:0;z-index:1}} tr:last-child td{{border-bottom:0}} .rag td:nth-child(2){{font-weight:800;min-width:150px}} .rag-red{{background:var(--red)}} .rag-amber{{background:var(--amber)}} .rag-green{{background:var(--green)}} .rag-grey{{background:var(--grey)}} .compact{{max-width:1100px}} .wide{{max-width:1400px}} pre{{overflow:auto;background:#f5f8fb;color:#17222d;border:1px solid #b8c7d3;padding:1rem;border-radius:6px;font-size:.86rem}} pre code{{background:transparent;color:#17222d;padding:0}} .mistakes{{padding-left:1.2rem}} .mistakes li{{margin:.35rem 0}} .steps{{counter-reset:step;list-style:none;padding:0;display:grid;gap:.7rem;max-width:850px}} .steps li{{counter-increment:step;display:flex;gap:.7rem;background:var(--wash);padding:.75rem;border-radius:6px}} .steps li::before{{content:counter(step);background:var(--blue);color:#fff;width:1.6rem;height:1.6rem;border-radius:50%;display:inline-grid;place-items:center;font-weight:800;flex:0 0 auto}} .diagram{{display:flex;align-items:center;gap:.7rem;flex-wrap:wrap;background:#fff;padding:1rem;border:1px solid var(--line);border-radius:9px;box-shadow:var(--shadow);margin:1rem 0 2rem}} .diagram-box{{border:2px solid var(--blue);border-radius:7px;padding:.75rem;min-width:180px;background:#f7fbff}} .diagram-box span{{display:block;font-size:.8rem;color:var(--muted);margin-top:.35rem}} .diagram-box.model{{border-color:#258b4d;background:#f5fff7}} .diagram-box.activity{{border-color:#8c5a00;background:#fffbf0}} .diagram-box.context{{border-color:#7846a7;background:#fbf7ff}} .arrow{{font-size:.77rem;color:var(--muted);text-align:center}} details{{border:1px solid var(--line);border-radius:6px;margin:.55rem 0;padding:.7rem 1rem;max-width:1400px}} summary{{cursor:pointer;font-weight:700;color:var(--navy)}} .back{{display:inline-block;margin-top:1.3rem;font-size:.85rem}} footer{{padding:2rem clamp(1rem,5vw,5rem);background:var(--navy);color:#d9e7f2;font-size:.85rem}} footer a{{color:#fff}}
@media(max-width:900px){{.layout{{display:block}} aside{{position:relative;height:auto}} nav{{columns:2}} .hero{{padding-top:2.5rem}} .section{{padding-top:2.3rem;padding-bottom:2.3rem}}}} @media print{{aside,.search,.skip,.back{{display:none!important}}.layout{{display:block}}.hero{{padding:1rem 0;border:0}}.section{{padding:1rem 0;break-inside:auto}}details{{break-inside:avoid}}pre{{white-space:pre-wrap}}a{{color:#000;text-decoration:none}}}}
</style></head><body><a class="skip" href="#main">Skip to content</a><div class="layout"><aside><h2>Ancestry MMM</h2><p>Data Upload Guide</p><input class="search" id="guideSearch" type="search" placeholder="Filter sections" aria-label="Filter guide sections"><nav id="toc"><a href="#top">Overview</a><a href="#workflow">What do I need?</a><a href="#outcomes">1. Outcomes</a><a href="#activity">2. Activity and Media</a><a href="#context">3. Context</a><a href="#ltr">FH LTR / DNA revenue</a><a href="#advanced">Add these later</a><a href="#faq">FAQ</a><a href="#glossary">Glossary</a><a href="#review">Source and review</a></nav></aside><main id="main"><header class="hero" id="top"><span class="badge">Version 2 · source-pack contract</span><h1>Ancestry MMM data upload guide</h1><p>This guide helps a first-time analyst prepare data the application can use. For every field, it tells you if you need it, what it means, what to type, and what happens if you skip it.</p><div class="callout"><b>Most important:</b> uploading a file successfully does not mean it's approved for reporting, planning, or optimisation. Those are separate, later steps.</div>{relationship}</header>{workflow}{outcomes}{activity}{context}{advanced}<section id="faq" class="section"><p class="eyebrow">Questions analysts ask</p><h2>FAQ</h2><p>If a question isn't answered here, check the “Fields you may need” table for that section, or the full technical reference at the end of each section.</p>{faq_html}</section><section id="glossary" class="section"><p class="eyebrow">Quick reference</p><h2>Glossary</h2>{glossary}</section><section id="review" class="section"><p class="eyebrow">Traceability</p><h2>Source and review</h2><p>This guide was built and checked against the current application code, not copied from an older version. The exact files, requirement IDs, and review results are recorded in <code>Ancestry_MMM_Data_Upload_Guide_REVIEW.md</code> and <code>Ancestry_MMM_Data_Upload_Guide_Simplification_Report.md</code>.</p><p>Primary implementation references include <code>ancestry_mmm/data/templates.py</code>, <code>template_downloads.py</code>, <code>loader.py</code>, <code>source_pack_adoption.py</code>, the Data Upload and Model Training pages, and the upload/template tests. Approved requirement IDs include REQ-DATAIN-001, REQ-COVERAGE-001, REQ-ACTIVITY-001, REQ-OUT-001/002/003, REQ-NBT-001/002/003/004, REQ-SEARCH-001/002/004/005, REQ-SEO-001, REQ-EVENT-001, REQ-EXPMODE-001, REQ-CALIB-001, REQ-ECON-002/003, REQ-FUTURE-001, and REQ-FX-001–006. The UK production NBT boundary is recorded in <code>docs/uk_production_onboarding_runbook.md</code>.</p><a class="back" href="#top">↑ Back to top</a></section></main></div><footer><p><b>Internal analyst guide.</b> No external libraries, fonts, images, or network calls are required. Print this page or open it locally in a browser.</p></footer><script>(function(){{const input=document.getElementById('guideSearch');const links=[...document.querySelectorAll('#toc a')];const sections=[...document.querySelectorAll('main .section, main .hero')];input.addEventListener('input',function(){{const q=input.value.toLowerCase().trim();sections.forEach(s=>{{s.hidden=!!q&&!s.innerText.toLowerCase().includes(q)}});links.forEach(a=>{{const id=a.getAttribute('href').slice(1),s=document.getElementById(id);a.hidden=!!q&&(!s||s.hidden)}})}})}})();</script></body></html>"""


def clean_token_formula(cell_ref: str) -> str:
    """Replace common separators using long-standing Excel functions."""
    raw = f"LOWER(TRIM({cell_ref}))"
    expression = raw
    replacements = [
        " ",
        "!",
        "#",
        "$",
        "%",
        "&",
        "'",
        "(",
        ")",
        "*",
        "+",
        ",",
        "-",
        ".",
        "/",
        ":",
        ";",
        "<",
        "=",
        ">",
        "?",
        "@",
        "[",
        "\\",
        "]",
        "^",
        "`",
        "{",
        "|",
        "}",
        "~",
    ]
    for character in replacements:
        expression = f'SUBSTITUTE({expression},"{character}","_")'
    for character in (chr(0x2013), chr(0x2014), chr(0x2019), chr(0x201C), chr(0x201D)):
        expression = f'SUBSTITUTE({expression},"{character}","_")'
    expression = f'SUBSTITUTE({expression},CHAR(9),"_")'
    expression = f'SUBSTITUTE({expression},CHAR(160),"_")'
    return f'IF(OR({raw}="",{raw}="nan",{raw}="none",{raw}="n/a"),"",{expression})'


def collapse_token_formula(clean_cell: str) -> str:
    expression = clean_cell
    for _ in range(8):
        expression = f'SUBSTITUTE({expression},"__","_")'
    return f'=IF({clean_cell}="","",{expression})'


def trim_token_formula(collapsed_cell: str) -> str:
    return (
        f'=IF(OR({collapsed_cell}="",{collapsed_cell}="_"),"",'
        f'IF(LEFT({collapsed_cell},1)="_",'
        f'IF(RIGHT({collapsed_cell},1)="_",MID({collapsed_cell},2,LEN({collapsed_cell})-2),RIGHT({collapsed_cell},LEN({collapsed_cell})-1)),'
        f'IF(RIGHT({collapsed_cell},1)="_",LEFT({collapsed_cell},LEN({collapsed_cell})-1),{collapsed_cell})))'
    )


def add_hidden_token_columns(
    ws, input_columns: list[str], rows: range, start_col: int = 12
) -> list[str]:
    """Add staged classic-function helper formulas outside the visible table."""
    token_columns = []
    for offset, input_col in enumerate(input_columns):
        clean_col = get_column_letter(start_col + offset * 3)
        collapsed_col = get_column_letter(start_col + offset * 3 + 1)
        token_col = get_column_letter(start_col + offset * 3 + 2)
        token_columns.append(token_col)
        ws.cell(7, start_col + offset * 3).value = f"_{input_col}_clean"
        ws.cell(7, start_col + offset * 3 + 1).value = f"_{input_col}_collapsed"
        ws.cell(7, start_col + offset * 3 + 2).value = f"_{input_col}_token"
        for row in rows:
            ws.cell(
                row, start_col + offset * 3
            ).value = f"={clean_token_formula(f'{input_col}{row}')}"
            ws.cell(row, start_col + offset * 3 + 1).value = collapse_token_formula(
                f"{clean_col}{row}"
            )
            ws.cell(row, start_col + offset * 3 + 2).value = trim_token_formula(
                f"{collapsed_col}{row}"
            )
        for helper_col in (clean_col, collapsed_col, token_col):
            ws.column_dimensions[helper_col].hidden = True
            ws.column_dimensions[helper_col].width = 2
    return token_columns


def join_token_columns(token_columns: list[str], row: int) -> str:
    terms = []
    for index, column in enumerate(token_columns):
        cell = f"{column}{row}"
        if index == 0:
            terms.append(f'IF({cell}<>"",{cell},"")')
        else:
            first = f"{token_columns[0]}{row}"
            terms.append(f'IF({cell}<>"",IF({first}<>"","_"&{cell},{cell}),"")')
    return "=" + "&".join(terms)


def style_sheet(ws, widths: dict[str, int]) -> None:
    navy = "12304A"
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A8"
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    ws["A1"].font = Font(size=18, bold=True, color=navy)
    ws["A2"].font = Font(italic=True, color="5D6B78")
    ws["A4"].font = Font(bold=True, color=navy)


def set_title(ws, title: str, subtitle: str, purpose: str) -> None:
    ws["A1"] = title
    ws["A2"] = subtitle
    ws["A4"] = purpose
    ws.merge_cells("A1:F1")
    ws.merge_cells("A2:F2")
    ws.merge_cells("A4:F4")


def add_candidate_table(
    ws, headers: list[str], rows: list[list[object]], tab_name: str = "Candidates"
) -> None:
    while ws.max_row < 6:
        ws.cell(ws.max_row + 1, 1).value = ""
    ws.append(headers)
    for row in rows:
        ws.append(row)
    end_col = get_column_letter(len(headers))
    ref = f"A7:{end_col}{ws.max_row}"
    tab = Table(displayName=tab_name, ref=ref)
    tab.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2", showRowStripes=True, showColumnStripes=False
    )
    ws.add_table(tab)
    for cell in ws[7]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="12304A")
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A8"


def add_dropdown(ws, cell_range: str, values: list[str], title: str) -> None:
    dv = DataValidation(
        type="list", formula1='"' + ",".join(values) + '"', allow_blank=True
    )
    dv.error = "Choose a value from the approved list or leave it blank when the field is optional."
    dv.errorTitle = title
    dv.prompt = "Select an approved value."
    dv.promptTitle = title
    ws.add_data_validation(dv)
    dv.add(cell_range)


def common_candidate_style(ws, widths: dict[str, int]) -> None:
    ws.sheet_view.showGridLines = False
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for cell in ws[7]:
        cell.fill = PatternFill("solid", fgColor="12304A")
        cell.font = Font(bold=True, color="FFFFFF")
    ws.freeze_panes = "A8"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1


def add_soft_dropdown(ws, cell_range: str, values: list[str], title: str) -> None:
    """A dropdown that offers suggestions without blocking free text -- for
    fields the app treats as an unenforced/suggested vocabulary, not a
    closed enum (e.g. marketing_objective)."""
    dv = DataValidation(
        type="list",
        formula1='"' + ",".join(values) + '"',
        allow_blank=True,
        showErrorMessage=False,
    )
    dv.prompt = "Choose a suggestion, or type your own text -- this field is not a closed list in the app."
    dv.promptTitle = title
    ws.add_data_validation(dv)
    dv.add(cell_range)


def color_header_range(ws, row: int, start_col: int, end_col: int, color: str) -> None:
    for c in range(start_col, end_col + 1):
        cell = ws.cell(row, c)
        cell.fill = PatternFill("solid", fgColor=color)
        cell.font = Font(bold=True, color="FFFFFF")


def add_status_conditional_formatting(ws, cell_range: str, first_cell: str) -> None:
    ws.conditional_formatting.add(
        cell_range,
        FormulaRule(
            formula=[f'ISNUMBER(SEARCH("Missing",{first_cell}))'],
            fill=PatternFill("solid", fgColor="FCE4E4"),
        ),
    )
    ws.conditional_formatting.add(
        cell_range,
        FormulaRule(
            formula=[
                f'OR(ISNUMBER(SEARCH("Duplicate",{first_cell})),ISNUMBER(SEARCH("differs",{first_cell})))'
            ],
            fill=PatternFill("solid", fgColor="FFF1CC"),
        ),
    )
    ws.conditional_formatting.add(
        cell_range,
        FormulaRule(
            formula=[f'{first_cell}="Ready"'],
            fill=PatternFill("solid", fgColor="E3F4E6"),
        ),
    )


def write_start_here(
    ws, title: str, subtitle: str, sections: list[tuple[str, list[str]]]
) -> None:
    ws["A1"] = title
    ws["A1"].font = Font(size=18, bold=True, color="12304A")
    ws["A2"] = subtitle
    ws["A2"].font = Font(italic=True, color="5D6B78")
    row = 4
    for heading, lines in sections:
        cell = ws.cell(row, 1, heading)
        cell.font = Font(bold=True, size=13, color="12304A")
        row += 1
        for line in lines:
            cell = ws.cell(row, 1, line)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            row += 1
        row += 1
    ws.column_dimensions["A"].width = 130
    ws.sheet_view.showGridLines = False


def write_allowed_values(wb: Workbook, rows: list[list[str]]):
    ws = wb.create_sheet("ALLOWED_VALUES")
    ws.append(["Field", "Accepted value", "Plain-English meaning", "When to use"])
    for row in rows:
        ws.append(row)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="12304A")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:D{ws.max_row}"
    for col, width in {"A": 28, "B": 26, "C": 55, "D": 48}.items():
        ws.column_dimensions[col].width = width
    for r in range(1, ws.max_row + 1):
        for c in range(1, 5):
            ws.cell(r, c).alignment = Alignment(wrap_text=True, vertical="top")
    ws.sheet_view.showGridLines = False
    return ws


def write_examples(wb: Workbook, headers: list[str], rows: list[list[str]]):
    ex = wb.create_sheet("EXAMPLES")
    ex.append(headers)
    for row in rows:
        ex.append(row)
    for c in ex[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="12304A")
    ex.sheet_view.showGridLines = False
    for idx in range(1, len(headers) + 1):
        ex.column_dimensions[get_column_letter(idx)].width = 46
    for r in range(1, ex.max_row + 1):
        for c in range(1, len(headers) + 1):
            ex.cell(r, c).alignment = Alignment(wrap_text=True, vertical="top")
    return ex


def builder_ref(col: str) -> str:
    """A DICTIONARY_OUTPUT formula template that copies one BUILDER column."""
    return "='BUILDER'!" + col + "{r}"


def builder_ref_or_default(col: str, default: str) -> str:
    """Like `builder_ref`, but falls back to a safe literal when BUILDER's
    cell is blank -- for columns the live parser requires to be non-blank
    even though the necessity review found nothing meaningful reads the
    value (confirmed by feeding builder output through the real parser)."""
    return (
        "=IF(TRIM('BUILDER'!" + col + '{r})<>"",'
        "'BUILDER'!" + col + '{r},"' + default + '")'
    )


def add_dictionary_output_sheet(
    wb: Workbook,
    output_columns: list[str],
    column_map: dict[str, str | None],
    data_rows: range,
):
    """Build the clean, upload-ready DICTIONARY_OUTPUT sheet.

    `column_map` maps an output column name to a formula template containing
    a literal ``{r}`` row placeholder (build one with `builder_ref`, or write
    a custom fallback formula by hand); a column absent from the map, or
    mapped to `None`, is written as a blank literal (used for fields the app
    derives automatically, such as unit/aggregation_type). Every non-blank
    cell is a live formula referencing BUILDER, so DICTIONARY_OUTPUT updates
    automatically as the analyst edits the BUILDER sheet.
    """
    ws = wb.create_sheet("DICTIONARY_OUTPUT")
    ws.append(list(output_columns))
    for r in data_rows:
        row_values = []
        for col in output_columns:
            template = column_map.get(col)
            row_values.append("" if template is None else template.format(r=r))
        ws.append(row_values)
    end_col = get_column_letter(len(output_columns))
    tab = Table(displayName="DictionaryOutput", ref=f"A1:{end_col}{ws.max_row}")
    tab.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2", showRowStripes=True, showColumnStripes=False
    )
    ws.add_table(tab)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="12304A")
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for idx in range(1, len(output_columns) + 1):
        ws.column_dimensions[get_column_letter(idx)].width = 24
    ws.freeze_panes = "A2"
    ws.sheet_view.showGridLines = False
    return ws


def build_outcome_dictionary_builder(path: Path) -> None:
    wb = Workbook()
    start_here = wb.active
    start_here.title = "START_HERE"
    write_start_here(
        start_here,
        "Outcome / KPI Dictionary Builder",
        "Formula-driven, no VBA -- builds a complete outcome_dictionary row and its outcome_id",
        [
            (
                "What this builder is for",
                [
                    "Use this workbook to define one row per KPI (outcome) you want the model to explain -- things like GSA, sign-ups, or Net Bill Through, split by segment.",
                    "It asks only for the choices you genuinely have to make, builds a stable outcome_id for you, and produces a clean row ready to paste into the outcome_dictionary sheet of the standard Outcomes upload workbook.",
                ],
            ),
            (
                "What you need to fill in",
                [
                    "Go to the BUILDER sheet. Fill in product, metric_key, segment, and metric for every KPI row -- these are the fields outcome_id is built from.",
                    "Only fill in the amber (Fields you may need) columns if they apply: outcome grouping, eligibility overrides, or value reporting. Leave them blank otherwise -- the app already has sensible defaults.",
                    "Only fill in the grey (official-approval) columns once you are ready to get this outcome approved for production reporting.",
                ],
            ),
            (
                "What is generated automatically",
                [
                    "Generated ID -- built from product + metric_key + segment.",
                    "Final ID -- the Generated ID, unless you type something in Manual override.",
                    "Row status -- plain-English text telling you if the row is Ready, missing something, or a duplicate.",
                    "The DICTIONARY_OUTPUT sheet -- every column the upload expects, in the right order, computed live from your BUILDER entries.",
                ],
            ),
            (
                "What is required, conditional, and optional",
                [
                    "Required (white columns): product, metric_key, segment, metric.",
                    "Conditional (amber columns, fill in only when it applies): segment_dimension, the four outcome-group fields, role and the five eligibility switches, value_weight/value_currency.",
                    "Optional / advanced (grey columns, official approval only): definition_version, event_definition, cohort_or_attribution_basis, completeness_or_maturity_policy, exclusions, reconciliation_source, business_owner, effective_from, effective_to.",
                    "Not asked at all: unit and aggregation_type. The app derives both automatically from metric_key for every registered metric -- DICTIONARY_OUTPUT leaves them blank on purpose, and that is correct.",
                    "Not included in this builder: date_basis and maturity_required. The schema-necessity review confirmed the app does not currently read either field for anything (see docs/Ancestry_MMM_Upload_Schema_Necessity_Review.md). If your project needs them recorded anyway, add the columns and values by hand after copying the output.",
                ],
            ),
            (
                "How dropdowns work",
                [
                    "product, metric_key, segment_dimension, group_aggregation, role, and the TRUE/FALSE eligibility switches are dropdowns built from the app's own governed lists. Click a cell in one of those columns and choose from the list, or see the ALLOWED_VALUES sheet for the full, current set with plain-English explanations.",
                ],
            ),
            (
                "How validation works",
                [
                    "The Row status column recalculates automatically as you type. It tells you in plain English whether a row is Ready, missing a required field, or a duplicate outcome_id -- fix the thing it names, then check again.",
                ],
            ),
            (
                "Where the final dictionary output goes",
                [
                    "Select every data row of the DICTIONARY_OUTPUT sheet, copy, and Paste Special > Values into the outcome_dictionary sheet of the standard Outcomes upload workbook.",
                ],
            ),
            (
                "Where the actual weekly KPI numbers go",
                [
                    "This builder never asks for your weekly numbers. Those go in the outcomes sheet of the same Outcomes upload workbook -- one column per outcome_id, one row per period_start x market.",
                ],
            ),
        ],
    )

    builder = wb.create_sheet("BUILDER")
    headers = [
        "product",
        "metric_key",
        "segment",
        "metric",
        "source_column",
        "outcome_id (existing)",
        "Manual override",
        "Generated ID",
        "Final ID",
        "Row status",
        "segment_dimension",
        "outcome_group_id",
        "outcome_group_label",
        "outcome_family_key",
        "group_aggregation",
        "role",
        "included_in_fit",
        "include_in_default_reporting",
        "include_in_official_total",
        "include_in_value",
        "include_in_optimisation",
        "value_weight",
        "value_currency",
        "definition_version",
        "event_definition",
        "cohort_or_attribution_basis",
        "completeness_or_maturity_policy",
        "exclusions",
        "reconciliation_source",
        "business_owner",
        "effective_from",
        "effective_to",
    ]
    example_rows = [
        ["Family History", "fh_gsa", "New", "GSA"],
        ["Family History", "fh_gsa", "DNA_CrossSell", "GSA"],
        ["Family History", "fh_gsa", "Winback", "GSA"],
        ["Family History", "fh_net_billthrough_count", "New", "Net bill-through count"],
        ["DNA", "dna_kit_sale", "New Customer", "Kit sale"],
    ]
    pad = len(headers) - 4
    example_rows = [row + [""] * pad for row in example_rows]
    rows = example_rows + [[""] * len(headers) for _ in range(20)]
    add_candidate_table(builder, headers, rows, "OutcomeCandidates")
    first_row, last_row = 8, 7 + len(rows)
    data_rows = range(first_row, last_row + 1)

    def col(name: str) -> str:
        return get_column_letter(headers.index(name) + 1)

    token_columns = add_hidden_token_columns(
        builder,
        [col("product"), col("metric_key"), col("segment")],
        data_rows,
        start_col=len(headers) + 3,
    )
    generated_col, final_col, status_col = (
        col("Generated ID"),
        col("Final ID"),
        col("Row status"),
    )
    existing_col, override_col = col("outcome_id (existing)"), col("Manual override")
    p, m, s, mt = col("product"), col("metric_key"), col("segment"), col("metric")
    for r in data_rows:
        builder[f"{generated_col}{r}"] = join_token_columns(token_columns, r)
        builder[f"{final_col}{r}"] = (
            f'=IF(TRIM({override_col}{r})<>"",TRIM({override_col}{r}),{generated_col}{r})'
        )
        builder[f"{status_col}{r}"] = (
            f'=IF(OR({p}{r}="",{m}{r}="",{s}{r}="",{mt}{r}=""),'
            '"Missing required field — fill in product, metric_key, segment, and metric before this row can be used.",'
            f'IF({generated_col}{r}="","Missing required field — product, metric_key, and segment must combine into an ID.",'
            f"IF(COUNTIF(${final_col}${first_row}:${final_col}${last_row},{final_col}{r})>1,"
            '"Duplicate outcome ID — two rows currently build the same outcome_id; add a distinguishing detail.",'
            f'IF(AND({existing_col}{r}<>"",{existing_col}{r}<>{final_col}{r}),'
            '"Existing outcome_id differs from the built ID — review before using.","Ready"))))'
        )

    widths = {get_column_letter(i): 20 for i in range(1, len(headers) + 1)}
    widths[status_col] = 48
    widths[col("metric")] = 26
    common_candidate_style(builder, widths)
    color_header_range(
        builder,
        7,
        headers.index("segment_dimension") + 1,
        headers.index("value_currency") + 1,
        "8C6A00",
    )
    color_header_range(
        builder,
        7,
        headers.index("definition_version") + 1,
        headers.index("effective_to") + 1,
        "5D6B78",
    )

    add_dropdown(
        builder, f"{p}{first_row}:{p}{last_row}", list(KNOWN_PRODUCTS), "Product"
    )
    add_dropdown(
        builder,
        f"{m}{first_row}:{m}{last_row}",
        OUTCOME_METRIC_KEY_CHOICES,
        "Metric key",
    )
    add_dropdown(
        builder,
        f"{col('segment_dimension')}{first_row}:{col('segment_dimension')}{last_row}",
        list(SEGMENT_DIMENSIONS),
        "Segment dimension",
    )
    add_dropdown(
        builder,
        f"{col('group_aggregation')}{first_row}:{col('group_aggregation')}{last_row}",
        list(OUTCOME_GROUP_AGGREGATIONS),
        "Group aggregation",
    )
    add_dropdown(
        builder,
        f"{col('role')}{first_row}:{col('role')}{last_row}",
        list(OUTCOME_ROLES),
        "Role",
    )
    for flag in (
        "included_in_fit",
        "include_in_default_reporting",
        "include_in_official_total",
        "include_in_value",
        "include_in_optimisation",
    ):
        add_dropdown(
            builder,
            f"{col(flag)}{first_row}:{col(flag)}{last_row}",
            TRUE_FALSE_BLANK,
            flag,
        )
    add_status_conditional_formatting(
        builder,
        f"{status_col}{first_row}:{status_col}{last_row}",
        f"{status_col}{first_row}",
    )

    source_column_col = col("source_column")
    column_map = {
        "outcome_id": builder_ref(final_col),
        "source_column": (
            "=IF(TRIM('BUILDER'!" + source_column_col + '{r})<>"",'
            "'BUILDER'!" + source_column_col + "{r},'BUILDER'!" + final_col + "{r})"
        ),
        "product": builder_ref(p),
        "metric_key": builder_ref(m),
        "metric": builder_ref(mt),
        "segment_dimension": builder_ref_or_default(
            col("segment_dimension"), "unspecified"
        ),
        "segment": builder_ref(s),
        "outcome_group_id": builder_ref(col("outcome_group_id")),
        "outcome_group_label": builder_ref(col("outcome_group_label")),
        "outcome_family_key": builder_ref(col("outcome_family_key")),
        "group_aggregation": builder_ref(col("group_aggregation")),
        "unit": None,
        "aggregation_type": None,
        "role": builder_ref(col("role")),
        "included_in_fit": builder_ref(col("included_in_fit")),
        "include_in_default_reporting": builder_ref(
            col("include_in_default_reporting")
        ),
        "include_in_official_total": builder_ref(col("include_in_official_total")),
        "include_in_value": builder_ref(col("include_in_value")),
        "include_in_optimisation": builder_ref(col("include_in_optimisation")),
        "definition_version": builder_ref(col("definition_version")),
        "event_definition": builder_ref(col("event_definition")),
        "cohort_or_attribution_basis": builder_ref(col("cohort_or_attribution_basis")),
        "completeness_or_maturity_policy": builder_ref(
            col("completeness_or_maturity_policy")
        ),
        "exclusions": builder_ref(col("exclusions")),
        "reconciliation_source": builder_ref(col("reconciliation_source")),
        "business_owner": builder_ref(col("business_owner")),
        "effective_from": builder_ref(col("effective_from")),
        "effective_to": builder_ref(col("effective_to")),
        "value_weight": builder_ref(col("value_weight")),
        "value_currency": builder_ref(col("value_currency")),
    }
    add_dictionary_output_sheet(
        wb, OUTCOME_DICTIONARY_OUTPUT_COLUMNS, column_map, data_rows
    )

    allowed_rows: list[list[str]] = []
    for value in KNOWN_PRODUCTS:
        allowed_rows.append(
            [
                "product",
                value,
                f"The {value} product line.",
                "Every outcome must belong to one product.",
            ]
        )
    for key, definition in METRIC_REGISTRY.items():
        allowed_rows.append(
            [
                "metric_key",
                key,
                f"{definition.display_name} ({definition.product or 'any product'}).",
                "Use the registered key whenever the metric already exists.",
            ]
        )
    allowed_rows.append(
        [
            "metric_key",
            METRIC_KEY_CUSTOM,
            "A genuinely new measure not yet in the registry.",
            "Only when no registered key matches.",
        ]
    )
    for value in SEGMENT_DIMENSIONS:
        allowed_rows.append(
            [
                "segment_dimension",
                value,
                "Which approved vocabulary the segment value comes from.",
                "Only if the same segment word could mean different things in different places.",
            ]
        )
    for value in OUTCOME_GROUP_AGGREGATIONS:
        allowed_rows.append(
            [
                "group_aggregation",
                value,
                "sum = components add to a governed total; none = descriptive grouping only.",
                "Only if this outcome is part of a governed semantic group.",
            ]
        )
    for value in OUTCOME_ROLES:
        allowed_rows.append(
            [
                "role",
                value,
                "Drives the default eligibility switches when they are left blank.",
                "Only if the primary default does not match this outcome.",
            ]
        )
    for flag in (
        "included_in_fit",
        "include_in_default_reporting",
        "include_in_official_total",
        "include_in_value",
        "include_in_optimisation",
    ):
        allowed_rows.append(
            [
                flag,
                "TRUE",
                "This outcome is included for this purpose.",
                "Only to override the role-based default.",
            ]
        )
        allowed_rows.append(
            [
                flag,
                "FALSE",
                "This outcome is excluded for this purpose.",
                "Only to override the role-based default.",
            ]
        )
    for field in (
        "segment",
        "metric",
        "source_column",
        "outcome_group_id",
        "outcome_group_label",
        "outcome_family_key",
        "value_weight",
        "value_currency",
        "definition_version",
        "event_definition",
        "cohort_or_attribution_basis",
        "completeness_or_maturity_policy",
        "exclusions",
        "reconciliation_source",
        "business_owner",
        "effective_from",
        "effective_to",
    ):
        allowed_rows.append(
            [
                field,
                "Free text — no fixed list",
                "Not a governed enum.",
                "Enter as plain text; there is no dropdown.",
            ]
        )
    write_allowed_values(wb, allowed_rows)

    write_examples(
        wb,
        ["Example", "Outcome identity", "Why"],
        [
            [
                "Good",
                "fh_gsa_new",
                "Stable product + metric_key + segment identity; meaning is still in the dictionary.",
            ],
            [
                "Good",
                "dna_kit_sale_new_customer",
                "DNA relationship partition is explicit when source supports it.",
            ],
            ["Invalid", "gsa", "Too little identity; product and segment collide."],
            [
                "Invalid",
                "fh_gsa_2026_01_05_uk",
                "Time and market are row/source scope, not a new outcome definition.",
            ],
            [
                "Review",
                "fh_gsa_dna_cross_sell",
                "Use the approved project spelling/lineage; do not infer from a friendly label.",
            ],
        ],
    )

    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    wb.save(path)


def build_activity_dictionary_builder(path: Path) -> None:
    wb = Workbook()
    start_here = wb.active
    start_here.title = "START_HERE"
    write_start_here(
        start_here,
        "Activity / Media Dictionary Builder",
        "Formula-driven, no VBA -- builds a complete activity_dictionary row and its activity_id",
        [
            (
                "What this builder is for",
                [
                    "Use this workbook to define one row per activity (a channel/platform/campaign-type combination such as Paid Search - Google - Brand) that you have spend, clicks, or impressions for.",
                    "It builds a stable activity_id for you from the fields that genuinely distinguish one activity from another, and produces a clean row ready to paste into the activity_dictionary sheet of the standard Activity and Media upload workbook.",
                ],
            ),
            (
                "What you need to fill in",
                [
                    "Go to the BUILDER sheet. Fill in channel, market, activity_ownership, intended_model_role, model_input_measure, economic_treatment, planning_eligibility, and source for every activity row.",
                    "For Paid Search activities you want split by Google/Bing and Brand/Non-Brand, also fill in platform and campaign_type -- the same two ordinary dictionary fields any other channel would use, not special Search-only inputs.",
                    "Only fill in the grey (optional/advanced) columns if you have the information handy -- they are reporting metadata, not fit or planning inputs.",
                ],
            ),
            (
                "What is generated automatically",
                [
                    "Generated ID -- built from channel plus whichever of platform and campaign_type you filled in.",
                    "Final ID -- the Generated ID, unless you type something in Manual override.",
                    "Row status -- plain-English text telling you if the row is Ready, missing something, or a duplicate.",
                    "The DICTIONARY_OUTPUT sheet -- every column the upload expects, in the right order, computed live from your BUILDER entries.",
                ],
            ),
            (
                "What is required, conditional, and optional",
                [
                    "Required (white columns): channel, market, activity_ownership, intended_model_role, model_input_measure, economic_treatment, planning_eligibility, source.",
                    "Conditional (amber columns): platform, campaign_type -- fill these in when they help distinguish one activity from another (Google vs Bing, Brand vs Non-Brand); the upload does currently reject a truly empty cell, so a blank one defaults to not specified in DICTIONARY_OUTPUT.",
                    "Optional / advanced (grey columns): pooling_group_id, funnel_stage, marketing_objective, product_advertised, message_type, currency, effective_from, effective_to. The schema-necessity review confirmed the model, canonicalisation, and optimiser never read these values -- only reporting rollups and the causal-graph display do. Leave the BUILDER cell blank if you don't have the information; DICTIONARY_OUTPUT automatically writes a harmless placeholder (unclassified for funnel_stage, not specified for the rest, pooling_group_id genuinely blank) instead of a truly empty cell, because the live upload currently rejects an empty value in those columns even though nothing meaningful reads it.",
                    "Not asked at all in this builder: model_input_unit, model_input_kind, spend_column, response_unit_column, response_unit. The necessity review confirmed these five v2 dictionary columns are currently write-only in the standard upload path -- filling them in does nothing today, and the real place to set units and cost mappings is inside the app, in Channel Media Units and Curve Generation, after your data is uploaded. Their column headers still appear (blank) in DICTIONARY_OUTPUT: once other v2 columns like currency are present, the current schema requires the full v2 column set to exist, so removing these headers entirely would make the whole row rejected. This builder never asks you to fill them in.",
                    "Also not asked at all: search_platform and search_intent_group_id. They are not activity_dictionary columns today -- activity_definitions_from_dictionary still doesn't map them from a standard workbook -- so this builder does not pretend they are ordinary fields. The governed Search-taxonomy mapping (Brand/Non-Brand, Google/Bing at the ActivityDefinition level) is configured separately, after upload, until that mapping gap is closed. Use platform and campaign_type above to keep your activity_id readable in the meantime.",
                ],
            ),
            (
                "How dropdowns work",
                [
                    "activity_ownership, intended_model_role, economic_treatment, planning_eligibility, and funnel_stage are dropdowns built from the app's own governed lists. campaign_type and marketing_objective offer suggestions but also accept free text, matching how the app actually treats them. See the ALLOWED_VALUES sheet for the full, current set with plain-English explanations.",
                ],
            ),
            (
                "How validation works",
                [
                    "The Row status column recalculates automatically as you type. It tells you in plain English whether a row is Ready, missing a required field, or a duplicate activity_id -- fix the thing it names, then check again.",
                ],
            ),
            (
                "Where the final dictionary output goes",
                [
                    "Select every data row of the DICTIONARY_OUTPUT sheet, copy, and Paste Special > Values into the activity_dictionary sheet of the standard Activity and Media upload workbook.",
                ],
            ),
            (
                "Where the actual weekly activity numbers go",
                [
                    "This builder never asks for your weekly spend, clicks, or impressions. Those go in the activity_data sheet of the same upload workbook, one row per period_start x market x activity_id.",
                ],
            ),
        ],
    )

    builder = wb.create_sheet("BUILDER")
    headers = [
        "channel",
        "market",
        "activity_ownership",
        "intended_model_role",
        "model_input_column",
        "model_input_measure",
        "economic_treatment",
        "planning_eligibility",
        "source",
        "activity_id (existing)",
        "Manual override",
        "Generated ID",
        "Final ID",
        "Row status",
        "platform",
        "campaign_type",
        "pooling_group_id",
        "funnel_stage",
        "marketing_objective",
        "product_advertised",
        "message_type",
        "currency",
        "effective_from",
        "effective_to",
    ]
    example_rows = [
        [
            "Paid Search",
            "UK",
            "paid",
            "intervention",
            "",
            "spend",
            "paid_media_cost",
            "optimisable",
            "Google Ads export",
        ],
        [
            "Paid Search",
            "UK",
            "paid",
            "intervention",
            "",
            "spend",
            "paid_media_cost",
            "optimisable",
            "Bing Ads export",
        ],
        [
            "TV",
            "UK",
            "paid",
            "intervention",
            "",
            "spend",
            "paid_media_cost",
            "optimisable",
            "Broadcaster invoice",
        ],
        [
            "SEO",
            "UK",
            "owned",
            "demand_capture",
            "",
            "clicks",
            "response_only",
            "scenario_only",
            "Google Search Console",
        ],
    ]
    pad = len(headers) - 9
    example_rows = [row + [""] * pad for row in example_rows]
    example_rows[0][headers.index("platform")] = "Google"
    example_rows[0][headers.index("campaign_type")] = "Brand"
    example_rows[1][headers.index("platform")] = "Bing"
    example_rows[1][headers.index("campaign_type")] = "Brand"
    rows = example_rows + [[""] * len(headers) for _ in range(20)]
    add_candidate_table(builder, headers, rows, "ActivityCandidates")
    first_row, last_row = 8, 7 + len(rows)
    data_rows = range(first_row, last_row + 1)

    def col(name: str) -> str:
        return get_column_letter(headers.index(name) + 1)

    id_inputs = [
        col("channel"),
        col("platform"),
        col("campaign_type"),
    ]
    token_columns = add_hidden_token_columns(
        builder, id_inputs, data_rows, start_col=len(headers) + 3
    )
    generated_col, final_col, status_col = (
        col("Generated ID"),
        col("Final ID"),
        col("Row status"),
    )
    existing_col, override_col = col("activity_id (existing)"), col("Manual override")
    ch, mk, own, role, mim, mms, econ, plan, src = (
        col("channel"),
        col("market"),
        col("activity_ownership"),
        col("intended_model_role"),
        col("model_input_column"),
        col("model_input_measure"),
        col("economic_treatment"),
        col("planning_eligibility"),
        col("source"),
    )
    for r in data_rows:
        builder[f"{generated_col}{r}"] = join_token_columns(token_columns, r)
        builder[f"{final_col}{r}"] = (
            f'=IF(TRIM({override_col}{r})<>"",TRIM({override_col}{r}),{generated_col}{r})'
        )
        builder[f"{status_col}{r}"] = (
            f'=IF(OR({ch}{r}="",{mk}{r}="",{own}{r}="",{role}{r}="",{mms}{r}="",{econ}{r}="",{plan}{r}="",{src}{r}=""),'
            '"Missing required field — fill in channel, market, activity_ownership, intended_model_role, model_input_measure, economic_treatment, planning_eligibility, and source.",'
            f'IF({generated_col}{r}="","Missing required field — channel must be filled in to build an ID.",'
            f"IF(COUNTIF(${final_col}${first_row}:${final_col}${last_row},{final_col}{r})>1,"
            '"Duplicate activity ID — two rows currently build the same activity_id; add the next meaningful field, not a random number.",'
            f'IF(AND({existing_col}{r}<>"",{existing_col}{r}<>{final_col}{r}),'
            '"Existing activity_id differs from the built ID — review before using.","Ready"))))'
        )

    widths = {get_column_letter(i): 20 for i in range(1, len(headers) + 1)}
    widths[status_col] = 48
    widths[col("channel")] = 16
    common_candidate_style(builder, widths)
    color_header_range(
        builder,
        7,
        headers.index("platform") + 1,
        headers.index("campaign_type") + 1,
        "8C6A00",
    )
    color_header_range(
        builder,
        7,
        headers.index("pooling_group_id") + 1,
        headers.index("effective_to") + 1,
        "5D6B78",
    )

    add_dropdown(
        builder,
        f"{own}{first_row}:{own}{last_row}",
        list(OWNERSHIP),
        "activity_ownership",
    )
    add_dropdown(
        builder,
        f"{role}{first_row}:{role}{last_row}",
        list(MODEL_ROLES),
        "intended_model_role",
    )
    add_dropdown(
        builder,
        f"{econ}{first_row}:{econ}{last_row}",
        list(ECONOMIC_TREATMENTS),
        "economic_treatment",
    )
    add_dropdown(
        builder,
        f"{plan}{first_row}:{plan}{last_row}",
        list(PLANNING_ELIGIBILITY),
        "planning_eligibility",
    )
    add_dropdown(
        builder,
        f"{col('funnel_stage')}{first_row}:{col('funnel_stage')}{last_row}",
        list(FUNNEL_STAGES),
        "funnel_stage",
    )
    add_soft_dropdown(
        builder,
        f"{col('platform')}{first_row}:{col('platform')}{last_row}",
        ["Google", "Bing"],
        "platform",
    )
    add_soft_dropdown(
        builder,
        f"{col('campaign_type')}{first_row}:{col('campaign_type')}{last_row}",
        ["Brand", "Non-Brand"],
        "campaign_type",
    )
    add_soft_dropdown(
        builder,
        f"{col('marketing_objective')}{first_row}:{col('marketing_objective')}{last_row}",
        list(MARKETING_OBJECTIVE_SUGGESTIONS),
        "marketing_objective",
    )
    add_status_conditional_formatting(
        builder,
        f"{status_col}{first_row}:{status_col}{last_row}",
        f"{status_col}{first_row}",
    )

    column_map = {
        "activity_id": builder_ref(final_col),
        "market": builder_ref(mk),
        "pooling_group_id": builder_ref(col("pooling_group_id")),
        "channel": builder_ref(ch),
        "platform": builder_ref_or_default(col("platform"), "not specified"),
        "campaign_type": builder_ref_or_default(col("campaign_type"), "not specified"),
        "marketing_objective": builder_ref_or_default(
            col("marketing_objective"), "not specified"
        ),
        "funnel_stage": builder_ref_or_default(col("funnel_stage"), "unclassified"),
        "product_advertised": builder_ref_or_default(
            col("product_advertised"), "not specified"
        ),
        "message_type": builder_ref_or_default(col("message_type"), "not specified"),
        "activity_ownership": builder_ref(own),
        "intended_model_role": builder_ref(role),
        "model_input_column": (
            "=IF(TRIM('BUILDER'!" + mim + '{r})<>"",'
            "'BUILDER'!" + mim + "{r},'BUILDER'!" + final_col + "{r})"
        ),
        "model_input_measure": builder_ref(mms),
        "economic_treatment": builder_ref(econ),
        "planning_eligibility": builder_ref(plan),
        "source": builder_ref(src),
        "currency": builder_ref(col("currency")),
        "effective_from": builder_ref(col("effective_from")),
        "effective_to": builder_ref(col("effective_to")),
    }
    add_dictionary_output_sheet(
        wb, ACTIVITY_DICTIONARY_OUTPUT_COLUMNS, column_map, data_rows
    )

    allowed_rows: list[list[str]] = (
        [
            [
                "activity_ownership",
                v,
                "Who controls or supplies the activity.",
                "Always -- keeps paid, owned, earned, and events distinct.",
            ]
            for v in OWNERSHIP
        ]
        + [
            [
                "intended_model_role",
                v,
                "Intended role in the model.",
                "Always -- separates treatments, controls, mediators, and demand capture.",
            ]
            for v in MODEL_ROLES
        ]
        + [
            [
                "economic_treatment",
                v,
                "How cost/value is treated.",
                "Always -- keeps economics separate from physical measurement.",
            ]
            for v in ECONOMIC_TREATMENTS
        ]
        + [
            [
                "planning_eligibility",
                v,
                "Whether planning or optimisation may use the activity.",
                "Always -- fit does not automatically grant planning rights.",
            ]
            for v in PLANNING_ELIGIBILITY
        ]
        + [
            [
                "funnel_stage",
                v,
                "Approved funnel position (reporting only).",
                "Only if you track funnel-stage reporting.",
            ]
            for v in FUNNEL_STAGES
        ]
        + [
            [
                "platform",
                "Google / Bing",
                "Suggested values only -- not a closed enum in the app.",
                "Free text is also accepted; use whatever platform actually applies, including non-Search channels like TV or a broadcaster name.",
            ],
            [
                "campaign_type",
                "Brand / Non-Brand",
                "Suggested values only -- not a closed enum in the app.",
                "Free text is also accepted; the app never rejects an unrecognised value.",
            ],
            [
                "marketing_objective",
                ", ".join(MARKETING_OBJECTIVE_SUGGESTIONS),
                "Suggested values only -- not a closed enum in the app.",
                "Free text is also accepted.",
            ],
            [
                "search_platform / search_intent_group_id",
                "Not offered by this builder",
                "Not activity_dictionary columns today -- the standard upload doesn't map them.",
                "Configured separately, after upload, in the governed Search-taxonomy admin mapping. Use platform and campaign_type above to keep your activity_id readable in the meantime.",
            ],
        ]
        + [
            [
                field,
                "Free text — no fixed list",
                "Not a governed enum.",
                "Enter as plain text; there is no dropdown.",
            ]
            for field in (
                "channel",
                "market",
                "source",
                "model_input_measure",
                "product_advertised",
                "message_type",
                "pooling_group_id",
                "currency",
                "effective_from",
                "effective_to",
            )
        ]
    )
    write_allowed_values(wb, allowed_rows)

    write_examples(
        wb,
        ["Check", "Good", "Invalid / risky", "Reason"],
        [
            [
                "Raw vs model-ready",
                "model_input_measure=spend; model_input_column=uk_paid_search_google_brand",
                "model_input_measure=uk_paid_search_google_brand",
                "The first is a raw source header; the second is a destination.",
            ],
            [
                "Search leaves",
                "Google Brand, Bing Brand, Google Non-Brand, Bing Non-Brand",
                "One generic Brand Search activity",
                "Parent totals are calculated from explicit leaves.",
            ],
            [
                "Identity",
                "paid_search_google_brand",
                "paid_search_2026_01_05_uk_12345",
                "Do not encode time or random numbers into stable identity.",
            ],
            [
                "Capacity",
                "paid_search_cap as separate governed cap",
                "cap copied into spend",
                "A cap is a constraint, not realised spend.",
            ],
            [
                "Measures",
                "spend + clicks + impressions retained; one selected input",
                "all measures silently summed",
                "Raw measures have different meanings and units.",
            ],
        ],
    )

    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    wb.save(path)


def build_context_dictionary_builder(path: Path) -> None:
    wb = Workbook()
    start_here = wb.active
    start_here.title = "START_HERE"
    write_start_here(
        start_here,
        "Context / External Factor Dictionary Builder",
        "Formula-driven, no VBA -- builds a complete variable_dictionary row and its variable_id",
        [
            (
                "What this builder is for",
                [
                    "Use this workbook to define one row per context variable -- things outside your control that might explain changes in an outcome, like CPI, seasonality, or a named event flag.",
                    "It builds a stable variable_id for you from the variable's class and concept, and produces a clean row ready to paste into the variable_dictionary sheet of the standard Context and External Factors upload workbook.",
                ],
            ),
            (
                "What you need to fill in",
                [
                    "Go to the BUILDER sheet. Fill in variable_class, concept, native_frequency, and role for every variable row.",
                    'Only fill in source and scope once this variable is reviewed for wider use ("adoption") -- not needed for a first upload.',
                ],
            ),
            (
                "What is generated automatically",
                [
                    "Generated ID -- built from variable_class and the concept name.",
                    "Final ID -- the Generated ID, unless you type something in Manual override.",
                    "Row status -- plain-English text telling you if the row is Ready, missing something, or a duplicate.",
                    "The DICTIONARY_OUTPUT sheet -- every column the upload expects, in the right order, computed live from your BUILDER entries.",
                ],
            ),
            (
                "What is required, conditional, and optional",
                [
                    "Required (white columns): variable_class, concept (used only to build the id -- not an upload column itself), native_frequency, role.",
                    "Conditional (amber columns): source, scope -- only needed once this variable is reviewed for wider use.",
                    "Optional (grey columns): effective_from, effective_to.",
                    "Not asked at all in this builder: unit. The schema-necessity review found it is stored and never read again, and is not even included in the app's own adoption completeness check. Its column header still appears (blank) in DICTIONARY_OUTPUT: once source/scope are present, the current schema requires the full v2 column set to exist, so removing this header entirely would make the whole row rejected. This builder never asks you to fill it in.",
                ],
            ),
            (
                "Read this before filling in variable_class, native_frequency, and role",
                [
                    "The schema-necessity review found that the app's real governance screen (Page 15, Data Coverage) does not read the uploaded variable_class or native_frequency at all -- it re-asks for both and defaults them itself regardless of what you upload here.",
                    "role has no enforced list anywhere in the code today, so this builder offers it as plain free text rather than inventing a dropdown.",
                    "Filling these in is still required for the upload to be accepted, but expect to confirm variable_class and native_frequency again on Page 15 after upload. This is a documented application limitation, not something this builder can fix -- see docs/Ancestry_MMM_Upload_Schema_Necessity_Review.md.",
                ],
            ),
            (
                "How dropdowns work",
                [
                    "variable_class is a dropdown built from the app's own governed list of five classes. native_frequency offers common suggestions but also accepts free text, since the app has no enforced frequency enum. role is plain free text. See the ALLOWED_VALUES sheet for the full list.",
                ],
            ),
            (
                "How validation works",
                [
                    "The Row status column recalculates automatically as you type. It tells you in plain English whether a row is Ready, missing a required field, or a duplicate variable_id -- fix the thing it names, then check again.",
                ],
            ),
            (
                "Where the final dictionary output goes",
                [
                    "Select every data row of the DICTIONARY_OUTPUT sheet, copy, and Paste Special > Values into the variable_dictionary sheet of the standard Context and External Factors upload workbook.",
                ],
            ),
            (
                "Where the actual observations go",
                [
                    "This builder never asks for your actual observed values. Those go in the context_data sheet of the same upload workbook, one row per period_start x market x variable_id, at whatever frequency the source actually publishes.",
                ],
            ),
        ],
    )

    builder = wb.create_sheet("BUILDER")
    headers = [
        "variable_class",
        "concept (not an upload column)",
        "native_frequency",
        "role",
        "variable_id (existing)",
        "Manual override",
        "Generated ID",
        "Final ID",
        "Row status",
        "source",
        "scope",
        "effective_from",
        "effective_to",
    ]
    example_rows = [
        ["rate_index", "UK CPI", "monthly", "exogenous_forecastable_control"],
        [
            "flow_count",
            "UK unemployment claims",
            "monthly",
            "exogenous_forecastable_control",
        ],
        [
            "stock_level",
            "UK active subscribers",
            "weekly",
            "exogenous_forecastable_control",
        ],
        [
            "survey_measurement",
            "Brand consideration",
            "monthly",
            "exogenous_forecastable_control",
        ],
        ["event_flag", "Black Friday", "weekly", "exogenous_forecastable_control"],
    ]
    pad = len(headers) - 4
    example_rows = [row + [""] * pad for row in example_rows]
    rows = example_rows + [[""] * len(headers) for _ in range(20)]
    add_candidate_table(builder, headers, rows, "ContextCandidates")
    first_row, last_row = 8, 7 + len(rows)
    data_rows = range(first_row, last_row + 1)

    def col(name: str) -> str:
        return get_column_letter(headers.index(name) + 1)

    vc, concept = col("variable_class"), col("concept (not an upload column)")
    nf, role = col("native_frequency"), col("role")
    token_columns = add_hidden_token_columns(
        builder, [vc, concept], data_rows, start_col=len(headers) + 3
    )
    generated_col, final_col, status_col = (
        col("Generated ID"),
        col("Final ID"),
        col("Row status"),
    )
    existing_col, override_col = col("variable_id (existing)"), col("Manual override")
    for r in data_rows:
        builder[f"{generated_col}{r}"] = join_token_columns(token_columns, r)
        builder[f"{final_col}{r}"] = (
            f'=IF(TRIM({override_col}{r})<>"",TRIM({override_col}{r}),{generated_col}{r})'
        )
        builder[f"{status_col}{r}"] = (
            f'=IF(OR({vc}{r}="",{concept}{r}="",{nf}{r}="",{role}{r}=""),'
            '"Missing required field — fill in variable_class, the concept name, native_frequency, and role.",'
            f'IF({generated_col}{r}="","Missing required field — variable_class and the concept name must combine into an ID.",'
            f"IF(COUNTIF(${final_col}${first_row}:${final_col}${last_row},{final_col}{r})>1,"
            '"Duplicate variable ID — two rows currently build the same variable_id; distinguish the actual variable, not its source frequency.",'
            f'IF(AND({existing_col}{r}<>"",{existing_col}{r}<>{final_col}{r}),'
            '"Existing variable_id differs from the built ID — review before using.","Ready"))))'
        )

    widths = {get_column_letter(i): 20 for i in range(1, len(headers) + 1)}
    widths[status_col] = 48
    widths[concept] = 30
    widths[role] = 32
    common_candidate_style(builder, widths)
    color_header_range(
        builder, 7, headers.index("source") + 1, headers.index("scope") + 1, "8C6A00"
    )
    color_header_range(
        builder,
        7,
        headers.index("effective_from") + 1,
        headers.index("effective_to") + 1,
        "5D6B78",
    )

    add_dropdown(
        builder,
        f"{vc}{first_row}:{vc}{last_row}",
        list(VARIABLE_CLASSES),
        "variable_class",
    )
    add_soft_dropdown(
        builder,
        f"{nf}{first_row}:{nf}{last_row}",
        ["daily", "weekly", "monthly", "quarterly", "yearly", "event"],
        "native_frequency",
    )
    add_status_conditional_formatting(
        builder,
        f"{status_col}{first_row}:{status_col}{last_row}",
        f"{status_col}{first_row}",
    )

    column_map = {
        "variable_id": builder_ref(final_col),
        "variable_class": builder_ref(vc),
        "native_frequency": builder_ref(nf),
        "role": builder_ref(role),
        "source": builder_ref(col("source")),
        "scope": builder_ref(col("scope")),
        "effective_from": builder_ref(col("effective_from")),
        "effective_to": builder_ref(col("effective_to")),
    }
    add_dictionary_output_sheet(
        wb, CONTEXT_DICTIONARY_OUTPUT_COLUMNS, column_map, data_rows
    )

    allowed_rows: list[list[str]] = (
        [
            [
                "variable_class",
                v,
                "One of the five approved classes.",
                "Always -- separates flows, stocks, rates, surveys, and event flags.",
            ]
            for v in VARIABLE_CLASSES
        ]
        + [
            [
                "native_frequency",
                v,
                "Common publishing frequency.",
                "Suggested only -- the app has no enforced enum for this field today.",
            ]
            for v in ("daily", "weekly", "monthly", "quarterly", "yearly", "event")
        ]
        + [
            [
                "role",
                "Free text — no fixed list",
                'The code has no enforced role enum today, despite being called "governed" in comments.',
                "Enter as plain text; example: exogenous_forecastable_control. Do not treat this as a closed list.",
            ],
            [
                "source",
                "Free text — no fixed list",
                "Provenance reference.",
                "Only needed once this variable is reviewed for wider use.",
            ],
            [
                "scope",
                "Free text — no fixed list",
                "Geographic or business scope.",
                "Only needed once this variable is reviewed for wider use.",
            ],
            [
                "effective_from",
                "ISO date",
                "When this dictionary mapping starts.",
                "Optional.",
            ],
            [
                "effective_to",
                "ISO date",
                "When this dictionary mapping ends.",
                "Optional.",
            ],
        ]
    )
    write_allowed_values(wb, allowed_rows)

    write_examples(
        wb,
        ["Check", "Good", "Invalid / risky", "Reason"],
        [
            [
                "Stable ID",
                "rate_index_uk_cpi",
                "rate_index_uk_cpi_monthly_gbp_2026",
                "Frequency, unit, and dates belong in the dictionary unless they change the variable itself.",
            ],
            [
                "Frequency",
                "native_frequency=monthly",
                "monthly value copied to weekly rows",
                "Preserve source frequency and align later by a governed method.",
            ],
            [
                "Missingness",
                "unavailable_source",
                "unavailable changed to 0",
                "Missingness is not observed zero.",
            ],
            [
                "Role",
                "CPI = exogenous_forecastable_control",
                "branded-search demand = exogenous control",
                "An endogenous mediator must be model-generated.",
            ],
            [
                "Event",
                "event_id + factual dates",
                "event flag inferred from a campaign name",
                "Named-event treatment is a separate governed path.",
            ],
        ],
    )

    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    wb.save(path)


def build_inventory() -> str:
    return """# Data-upload guide schema inventory

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
- Since the 2026-09-03 baseline, `core/search_intent_taxonomy.py` added a governed deeper Non-Brand Search child-group catalogue (`governed_search_intent_groups`, `validate_search_intent_group_catalogue`, `resolve_search_intent_model_grain`, `roll_up_paid_search_reporting_hierarchy`): only `brand_search`/`non_brand_search` are pre-approved; a child starts `approval_status="draft"`, cannot be fitted at the same model grain as its parent, and has no planning/cost-bearing treatment until child-level observed data and governed cost support exist. `activity_definitions_from_dictionary` (`templates.py:569-616`) still does not auto-map `search_intent_group_id`/`search_platform` from a standard workbook — unchanged, still an open documentation-boundary finding.

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

    - Implementation brief: `D:\\ORIGIAL D DRIVE\\008 Ancestry UK MMM - 2026\\LLM_Instructions_Build_Ancestry_MMM_Data_Upload_Guide_v2.md`.
- Approved requirements: REQ-DATAIN-001, REQ-COVERAGE-001, REQ-ACTIVITY-001, REQ-OUT-001/002/003, REQ-NBT-001/002/003/004, REQ-SEARCH-001/002/004/005, REQ-SEO-001, REQ-EVENT-001, REQ-EXPMODE-001, REQ-CALIB-001, REQ-ECON-002/003, REQ-FUTURE-001, and REQ-FX-001–006.
- Templates and parser: `ancestry_mmm/data/templates.py`, `template_downloads.py`, `loader.py`, `source_pack_adoption.py`, `source_inventory.py`.
- UI: `ancestry_mmm/pages/01_Data_Upload.py`, dedicated Search/SEO/valuation/evidence paths in application/core.
- UK production authority (pass 3): `docs/uk_production_onboarding_runbook.md`, `docs/approved_requirements/REQ-NBT-001.md` through `REQ-NBT-004.md`, `ancestry_mmm/core/net_billthrough.py`.
- Search/SEO governed-capability sources (pass 3): `ancestry_mmm/core/search_intent_taxonomy.py`, `ancestry_mmm/core/seo_visibility.py`, `ancestry_mmm/core/activities.py`.
- Tests inspected: `ancestry_mmm/tests/test_templates.py`, `test_outcome_source_pack_v2.py`, `test_source_pack_adoption_wp3.py`, and `test_template_downloads_wp8.py`.

## Known implementation/documentation gaps carried to review

1. Generated standard outcome examples use the display string `DNA cross-sell`, while the approved core constant is `DNA_CrossSell`; current parser validation accepts both because it requires a nonblank supplied segment rather than normalising it. The guide does not silently alter existing app behaviour; use the project-approved spelling consistently and review the template/parser mismatch. Confirmed still open at the pass-3 baseline (`template_downloads.py` unchanged since 2026-09-03).
2. Search taxonomy fields exist on the governed `ActivityDefinition` and admin UI, but the standard source dictionary parser currently maps the base dictionary fields and does not automatically map `search_intent_group_id` or `search_platform`. The guide labels these fields as a dedicated mapping/admin boundary and does not claim they are applied by the upload parser. Confirmed still open at the pass-3 baseline (`activity_definitions_from_dictionary` in `templates.py` unchanged since 2026-09-03, even though downstream Search-taxonomy machinery around it grew).
3. The generic downloadable sample outcome dictionary (`template_downloads.py`) still teaches GSA ids (`fh_gsa_new`, etc.) as its worked example, not the UK production NBT ids. This is accurate to disclose, not to silently fix — the sample is deliberately generic/cross-project, and UK production ids come from the approved UK source pack, not the generic sample. The guide now says this explicitly (see the UK production NBT note and its FAQ entry).
"""


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    (DOCS / "data_upload_guide_schema_inventory.md").write_text(
        build_inventory(), encoding="utf-8"
    )
    (DOCS / "Ancestry_MMM_Data_Upload_Guide.html").write_text(
        build_html(), encoding="utf-8"
    )
    build_outcome_dictionary_builder(
        DOCS / "Ancestry_MMM_Outcome_Dictionary_Builder.xlsx"
    )
    build_activity_dictionary_builder(
        DOCS / "Ancestry_MMM_Activity_Dictionary_Builder.xlsx"
    )
    build_context_dictionary_builder(
        DOCS / "Ancestry_MMM_Context_Dictionary_Builder.xlsx"
    )
    print("generated guide, inventory, and three Dictionary Builders")


if __name__ == "__main__":
    main()
