"""Build the analyst-facing Ancestry MMM data-upload guide and ID builders.

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


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


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
    return dict(zip(RAG_HEAD, [field, status, exists, filled, meaning, good, why, missing, used, fmt, blank]))


OUTCOME_RAG = [
    rag_row("period_start", "RED — Must provide", "Yes", "Yes", "Start date for the source period.", "2026-01-05", "Aligns rows to the source time grain.", "The table cannot be keyed or checked.", "outcomes", "ISO date; one source period", "Never for an outcomes row."),
    rag_row("market", "RED — Must provide", "Yes", "Yes", "The market belonging to this row.", "UK", "Market is a row-level key; it is never inferred from the file name.", "The row is rejected or cannot be assigned safely.", "outcomes; all domains", "Stable market code or label", "Never for a usable row."),
    rag_row("outcome_id", "RED — Must provide", "Yes", "Yes", "Stable identity of the outcome definition.", "fh_gsa_new", "Joins the source column to its approved meaning.", "The outcome cannot be defined or fitted.", "outcome_dictionary; completeness", "Stable lowercase ID; no duplicates", "Never."),
    rag_row("source_column", "RED — Must provide", "Yes", "Yes", "Exact column in outcomes that holds the values.", "fh_gsa_new", "Connects the dictionary to the wide source table.", "The definition cannot be mapped to data.", "outcome_dictionary; parser", "Exact header spelling", "Never."),
    rag_row("product", "RED — Must provide", "Yes", "Yes", "Product family represented by the outcome.", "Family History", "Keeps Family History and DNA outcomes distinct.", "The definition is invalid.", "outcome registry; reporting", "Family History or DNA, or an approved product", "Never."),
    rag_row("metric_key", "RED — Must provide", "Yes", "Yes", "Stable registry key for the metric.", "fh_gsa", "Prevents meaning being guessed from a friendly label.", "The metric may be rejected or treated as custom.", "outcome registry; fit", "Approved key or explicit custom", "Never."),
    rag_row("metric", "RED — Must provide", "Yes", "Yes", "Human-readable metric name.", "GSA", "Makes the definition readable while the key stays stable.", "The definition is incomplete.", "dictionary; reports", "Do not use aliases as a substitute for a definition", "Never."),
    rag_row("segment_dimension", "RED — Must provide", "Yes", "Yes", "What the segment label means.", "fh_customer_segment", "Stops the same label meaning different things.", "The segment cannot be interpreted safely.", "outcome registry; groups", "Approved dimension vocabulary", "Never."),
    rag_row("segment", "RED — Must provide", "Yes", "Yes", "The supplied segment value.", "New", "Fits New, Winback, and DNA cross-sell separately where supported.", "The outcome cannot be assigned to a segment.", "fit; reporting", "Use source-approved labels; do not silently add DNA partitions", "Never."),
    rag_row("outcome_group_id", "AMBER — Needed for some uses", "Yes", "No", "Optional semantic group identity.", "fh_gsa_family", "Describes components or a supplied total without choosing fit treatment.", "Group reconciliation or group views are unavailable.", "groups; reconciliation", "Stable ID; leave the complete group block blank if unused", "When no governed group exists."),
    rag_row("outcome_group_label", "AMBER — Needed for some uses", "Yes", "No", "Readable group name.", "Family History GSA", "Explains the group to reviewers.", "The group is incomplete.", "groups; review", "Text", "When outcome_group_id is blank."),
    rag_row("outcome_family_key", "AMBER — Needed for some uses", "Yes", "No", "Family key used for group semantics.", "fh_gsa", "Keeps group members in one outcome family.", "The group is incomplete.", "groups; reconciliation", "Stable registry/custom key", "When no group is used."),
    rag_row("group_aggregation", "AMBER — Needed for some uses", "Yes", "No", "Whether the group is a sum or descriptive only.", "sum", "Controls reconciliation semantics; it does not automatically fit a total.", "The group cannot be used for governed reconciliation.", "groups; totals", "sum or none", "When outcome_group_id is blank."),
    rag_row("unit", "AMBER — Needed for some uses", "Yes", "No", "Unit of the outcome value.", "GSA", "Separates counts, rates, currency, and indexes.", "The registry may supply a default; do not guess for custom metrics.", "definition; economics", "Approved unit text", "Only when the registry has an approved default."),
    rag_row("aggregation_type", "AMBER — Needed for some uses", "Yes", "No", "How values aggregate.", "count", "A rate is not added like a count.", "Economic/reporting use is blocked or ambiguous.", "definition; reporting", "count, rate, currency, index", "When the registry supplies it."),
    rag_row("date_basis", "AMBER — Needed for some uses", "Yes", "No", "Date meaning for the outcome.", "signup_date", "Avoids silently mixing event and billing dates.", "The definition may be unapproved for official use.", "approval; completeness", "Approved date-basis vocabulary", "Only while the definition is draft and the registry supplies no value."),
    rag_row("maturity_required", "AMBER — Needed for some uses", "Yes", "No", "Whether the outcome needs a maturity rule.", "TRUE", "Makes incomplete periods visible.", "Maturity cannot be governed.", "outcome completeness", "TRUE/FALSE", "For outcomes that are not maturity-sensitive."),
    rag_row("role", "AMBER — Needed for some uses", "Yes", "No", "Use role for this outcome.", "primary", "Separates fit, secondary, funnel, and diagnostic uses.", "Eligibility defaults may not match the intended use.", "eligibility; reporting", "primary, secondary, funnel_intermediate, diagnostic", "When using the project default only."),
    rag_row("included_in_fit", "AMBER — Needed for some uses", "Yes", "No", "Whether this outcome is included in fitting.", "TRUE", "Keeps definition and use decisions separate.", "The intended fit treatment is unclear.", "fit governance", "TRUE/FALSE", "When approval is not yet decided."),
    rag_row("include_in_default_reporting", "AMBER — Needed for some uses", "Yes", "No", "Whether it appears in default reports.", "TRUE", "Prevents a fitted outcome becoming headline output by accident.", "Reporting eligibility is unclear.", "reporting governance", "TRUE/FALSE", "When it is diagnostic-only."),
    rag_row("include_in_official_total", "AMBER — Needed for some uses", "Yes", "No", "Whether it can enter an official total.", "FALSE", "Official totals require explicit approval.", "Official total construction is blocked.", "official reporting", "TRUE/FALSE", "For non-total outcomes."),
    rag_row("include_in_value", "AMBER — Needed for some uses", "Yes", "No", "Whether economic value may use it.", "TRUE", "Count, value, and rate layers stay distinct.", "CPA/ROI use is blocked for that outcome.", "valuation; economics", "TRUE/FALSE", "For count-only or diagnostic outcomes."),
    rag_row("include_in_optimisation", "AMBER — Needed for some uses", "Yes", "No", "Whether optimisation may target it.", "FALSE", "Fit and optimisation eligibility are separate approvals.", "Optimisation is blocked for that outcome.", "optimisation governance", "TRUE/FALSE", "For diagnostic or unapproved outcomes."),
    rag_row("definition_version", "AMBER — Needed for some uses", "Yes", "Yes for approval", "Version of the business definition.", "1.0", "Makes reports reproducible when definitions change.", "Official approval is incomplete.", "approval; persistence", "Version text or number", "During early draft only."),
    rag_row("event_definition", "AMBER — Needed for some uses", "Yes", "Yes for approval", "What event is counted.", "Approved weekly GSA event", "Finance/Product can reconcile the definition.", "The outcome cannot be approved.", "approval; reconciliation", "Plain text with source reference", "During early draft only."),
    rag_row("cohort_or_attribution_basis", "AMBER — Needed for some uses", "Yes", "Yes for approval", "How people are assigned to the period and segment.", "signup_date_attributed", "Prevents cohort and event bases being mixed.", "Official use is blocked.", "approval; value join", "Plain text or approved vocabulary", "During early draft only."),
    rag_row("completeness_or_maturity_policy", "AMBER — Needed for some uses", "Yes", "Yes for approval", "Rule for when a period is complete.", "14-day source horizon (illustrative/historical-test example)", "Stops immature outcome periods being treated as final.", "Official reporting is blocked.", "completeness; approval", "Plain text; versioned; official UK production NBT uses its own approved production maturity rule, evidence, and exclusions — not this illustrative 14-day historical-test example", "Only for exploratory drafts."),
    rag_row("exclusions", "AMBER — Needed for some uses", "Yes", "Yes for approval", "Rows or cases excluded from the definition.", "Test accounts excluded", "Keeps source reconciliation auditable.", "Approval is incomplete.", "approval; reconciliation", "Plain text", "When there are no exclusions, write none."),
    rag_row("reconciliation_source", "AMBER — Needed for some uses", "Yes", "Yes for approval", "Source used to reconcile the measure.", "Finance weekly ledger v3", "Names the authority for the measure.", "Official use is blocked.", "approval; audit", "Plain text with version", "Only for exploratory drafts."),
    rag_row("business_owner", "AMBER — Needed for some uses", "Yes", "Yes for approval", "Owner who approves the definition.", "Finance", "Makes decision ownership visible.", "The definition cannot be approved.", "approval; audit", "Text", "During early draft only."),
    rag_row("effective_from", "GREEN — Optional", "Yes", "No", "Date the definition becomes active.", "2026-01-01", "Supports versioned definition history.", "No effective window is recorded.", "persistence; audit", "ISO date", "For a definition with no time-limited version."),
    rag_row("effective_to", "GREEN — Optional", "Yes", "No", "Date the definition stops being active.", "2026-12-31", "Supports versioned definition history.", "No end window is recorded.", "persistence; audit", "ISO date", "For a current/open-ended definition."),
    rag_row("value_weight", "AMBER — Needed for some uses", "Yes", "No", "Approved value per outcome, if supplied in the definition.", "42.50", "Only a governed mapping may turn counts into value.", "Value reporting is blocked; do not invent a value.", "economics; planning", "Number; not a rate unless explicitly defined", "For count-only models or separate valuation uploads."),
    rag_row("value_currency", "AMBER — Needed for some uses", "Yes", "No", "Currency of an approved value weight.", "GBP", "Prevents mixing monetary units.", "Monetary output is blocked pending currency governance.", "economics; FX", "Uppercase ISO 4217 code", "When no monetary value is supplied."),
]


COMPLETENESS_RAG = [
    rag_row("outcome_id", "RED — Must provide", "Yes", "Yes", "Outcome definition covered by this completeness record.", "fh_net_billthrough_count_new", "Joins completeness metadata to one approved outcome.", "The metadata cannot be bound.", "outcome_completeness", "Existing outcome_id", "Never."),
    rag_row("data_as_of_date", "RED — Must provide", "Yes", "Yes", "Date through which the source is known.", "2026-02-14", "Shows how current the extract is.", "Freshness cannot be reviewed.", "completeness; audit", "ISO date", "Never."),
    rag_row("model_start_week", "RED — Must provide", "Yes", "Yes", "First model week covered by the source.", "2026-01-05", "Checks the intended model window.", "Coverage cannot be checked.", "completeness", "ISO date", "Never."),
    rag_row("model_end_week", "RED — Must provide", "Yes", "Yes", "Last model week covered by the source.", "2026-02-09", "Checks the intended model window.", "Coverage cannot be checked.", "completeness", "ISO date", "Never."),
    rag_row("latest_complete_net_billthrough_week", "RED — Must provide for NBT", "Yes", "Yes for NBT", "Latest week that is complete under the maturity rule.", "2026-01-26", "Stops immature NBT periods being treated as final.", "Official NBT use is blocked.", "NBT completeness; official reporting", "ISO date", "For non-NBT outcomes only if the project contract says not applicable."),
    rag_row("maturity_rule_description", "RED — Must provide for maturity-sensitive outcomes", "Yes", "Yes", "Plain-English maturity/completeness rule.", "14-day horizon after week end (exploratory/historical-test example only)", "Explains why a period is complete.", "Official use is blocked.", "approval; audit", "Versioned text; for official UK production NBT this must be the approved production maturity rule, not the bounded historical-test 14-day rule", "For outcomes with no maturity requirement."),
    rag_row("source_owner", "RED — Must provide", "Yes", "Yes", "Owner of the completeness metadata/source.", "Finance Analytics", "Provides accountability for the extract.", "Completeness cannot be approved.", "audit; approval", "Text", "Never for governed metadata."),
]


ACTIVITY_RAG = [
    rag_row("period_start", "RED — Must provide", "Yes", "Yes", "Start date for the source period.", "2026-01-05", "Preserves the activity source grain.", "Rows cannot be aligned.", "activity_data", "ISO date", "Never."),
    rag_row("market", "RED — Must provide", "Yes", "Yes", "Market for this activity row or dictionary record.", "UK", "Market is explicit and row-level.", "The row cannot be assigned safely.", "activity_data; activity_dictionary", "Stable market code/label", "Never."),
    rag_row("activity_id", "RED — Must provide", "Yes", "Yes", "Stable identity of the activity at market × activity grain.", "paid_search_google_brand", "Joins raw observations to the dictionary.", "The activity cannot be mapped.", "activity_data; activity_dictionary", "Stable ID; unique within market", "Never."),
    rag_row("pooling_group_id", "AMBER — Needed for some uses", "Yes", "No", "Optional cross-market identity for similar activity.", "paid_search_brand", "Supports lineage and comparison; it does not force statistical pooling.", "Cross-market identity is not recorded.", "hierarchy; review", "Stable ID", "When the activity has no governed cross-market peer."),
    rag_row("channel", "RED — Must provide", "Yes", "Yes", "Channel label used by the model and reports.", "Paid Search", "Separates activity identity from descriptive detail.", "The dictionary is rejected.", "activity dictionary; model input", "Text; do not use a generic Brand Search label", "Never."),
    rag_row("platform", "AMBER — Needed for some uses", "Yes", "Yes for differentiated platform", "Buying or delivery platform.", "Google", "Helps distinguish Google and Bing when that matters.", "Platform-level identity may collide.", "activity identity; reports", "Text", "If platform is genuinely not applicable."),
    rag_row("campaign_type", "AMBER — Needed for some uses", "Yes", "No", "Campaign or placement type.", "Brand", "Adds meaningful identity when platform/channel alone is not enough.", "Similar activities may collide.", "activity identity; reports", "Text", "When source has no campaign type."),
    rag_row("marketing_objective", "AMBER — Needed for some uses", "Yes", "No", "Why the activity was run.", "acquisition/performance", "Supports reporting; it is not silently inferred.", "Objective reporting is incomplete.", "reports; governance", "Suggested vocabulary or documented custom", "When not supplied."),
    rag_row("funnel_stage", "AMBER — Needed for some uses", "Yes", "Yes for governed classification", "Approved funnel position.", "performance_lower", "Supports pathway governance without guessing.", "Classification is incomplete.", "pathways; reports", "brand_upper, mid_funnel, performance_lower, cross_funnel, not_applicable, unclassified", "Only while unclassified is explicitly accepted."),
    rag_row("product_advertised", "AMBER — Needed for some uses", "Yes", "No", "Product in the creative or offer.", "Family History", "Separates FH, DNA, and cross-product activity.", "Product reporting is incomplete.", "reports; pathways", "Text; approved product names where known", "When activity is product-neutral."),
    rag_row("message_type", "AMBER — Needed for some uses", "Yes", "No", "Message or offer type.", "brand", "Descriptive taxonomy for analysis.", "Message reporting is incomplete.", "reports", "Text", "When not available."),
    rag_row("activity_ownership", "RED — Must provide", "Yes", "Yes", "Who controls or supplies the activity.", "paid", "Keeps paid, owned, earned, and events distinct.", "The activity is invalid.", "model role; economics", "paid, owned, earned, external_event", "Never."),
    rag_row("intended_model_role", "RED — Must provide", "Yes", "Yes", "Intended role in the model.", "intervention", "Separates treatments, controls, mediators, and demand capture.", "The activity is invalid or misclassified.", "model governance", "intervention, mediator, demand_capture, control, event", "Never."),
    rag_row("model_input_column", "RED — Must provide", "Yes", "Yes", "Destination column after tidy data is pivoted to model-ready form.", "uk_paid_search_google_brand", "Tells canonicalisation where the selected measure belongs.", "The model input cannot be created.", "canonicalisation; model frame", "Stable wide-column name", "Never."),
    rag_row("model_input_measure", "RED — Must provide", "Yes", "Yes", "Exact raw column selected as the model input.", "spend", "The parser selects this raw measure explicitly.", "The activity cannot be canonicalised.", "canonicalisation", "Exact raw header such as spend, clicks, impressions, GRPs", "Never."),
    rag_row("economic_treatment", "RED — Must provide", "Yes", "Yes", "How cost/value is treated.", "paid_media_cost", "Keeps economics separate from physical measurement.", "The dictionary is invalid.", "economics; planning", "paid_media_cost, fully_loaded_cost, campaign_cost, response_only, not_applicable", "Never."),
    rag_row("planning_eligibility", "RED — Must provide", "Yes", "Yes", "Whether planning or optimisation may use the activity.", "optimisable", "Fit does not automatically grant planning rights.", "Planning treatment is unclear.", "planning; optimisation", "optimisable, scenario_only, fixed, excluded", "Never."),
    rag_row("source", "RED — Must provide", "Yes", "Yes", "Source system, file, or owner reference.", "Google Ads export 2026-08", "Preserves provenance and reviewability.", "The dictionary is invalid.", "audit; persistence", "Text with version/date preferred", "Never."),
    rag_row("model_input_unit", "AMBER — Needed for some uses", "Yes", "Yes for model input", "Unit of the selected model input.", "GBP", "Prevents treating all model inputs as spend.", "Unit review is required; economics may be blocked.", "model input; media units", "GBP, impressions, clicks, GRP, TVR, etc.", "When the source unit is recorded elsewhere in a governed mapping."),
    rag_row("model_input_kind", "AMBER — Needed for some uses", "Yes", "Yes for model input", "Whether input is monetary spend or exposure.", "monetary_spend", "Connects the input to the correct cost contract.", "Physical-to-monetary translation is unresolved.", "media units; economics", "monetary_spend or exposure", "When a governed mapping supplies it."),
    rag_row("spend_column", "AMBER — Needed for some uses", "Yes", "No", "Raw monetary spend column, if one exists.", "spend", "Allows a later cost mapping without pretending it is the model input.", "Spend mapping needs review.", "economics; cost mapping", "Exact raw header", "For response-only or non-monetary activity."),
    rag_row("response_unit_column", "AMBER — Needed for some uses", "Yes", "No", "Raw delivery/response column, if one exists.", "clicks", "Records a separate physical response measure.", "Response mapping needs review.", "media units; diagnostics", "Exact raw header", "When no physical response is supplied."),
    rag_row("response_unit", "AMBER — Needed for some uses", "Yes", "No", "Unit in the response column.", "clicks", "Prevents clicks, impressions, conversions, and visits being conflated.", "Response mapping needs review.", "media units", "Text", "When response_unit_column is blank."),
    rag_row("currency", "AMBER — Needed for some uses", "Yes", "No", "Currency of monetary spend.", "GBP", "Identifies the monetary unit; it does not perform FX conversion.", "Monetary economics is blocked pending mapping.", "economics; FX", "Uppercase ISO 4217", "For non-monetary activity."),
    rag_row("effective_from", "GREEN — Optional", "Yes", "No", "Date this mapping becomes active.", "2026-01-01", "Supports versioned source mappings.", "No start window is recorded.", "audit; persistence", "ISO date", "For a stable mapping with no time window."),
    rag_row("effective_to", "GREEN — Optional", "Yes", "No", "Date this mapping stops being active.", "2026-12-31", "Supports source mapping history.", "No end window is recorded.", "audit; persistence", "ISO date", "For a current/open-ended mapping."),
    rag_row("search_intent_group_id", "AMBER — Needed for some uses", "Yes in the governed Search mapping", "Yes for Search taxonomy", "Search intent axis such as Brand or Non-Brand.", "brand_search", "Keeps Search leaves explicit instead of one generic Brand Search variable.", "Search taxonomy remains unclassified.", "Search mapping; reports", "brand_search or non_brand_search; a governed deeper Non-Brand child ID is also accepted once explicitly approved (starts draft)", "For non-Search activities."),
    rag_row("search_platform", "AMBER — Needed for some uses", "Yes in the governed Search mapping", "Yes for Search taxonomy", "Search platform axis.", "google", "Keeps Google and Bing leaves distinct.", "Platform-level Search identity remains unclassified.", "Search mapping; reports", "google or bing", "For non-Search activities."),
]


CONTEXT_RAG = [
    rag_row("period_start", "RED — Must provide", "Yes", "Yes", "Start date of the native-frequency observation.", "2026-01-05", "Preserves the source frequency and row grain.", "The observation cannot be aligned.", "context_data", "ISO date", "Never."),
    rag_row("market", "RED — Must provide", "Yes", "Yes", "Market for the observation.", "UK", "Market is explicit, not inferred from file name.", "The observation cannot be assigned.", "context_data", "Stable market code/label", "Never."),
    rag_row("variable_id", "RED — Must provide", "Yes", "Yes", "Stable identity of the context variable.", "uk_cpi", "Joins observations to meaning and role.", "The variable cannot be used.", "context_data; variable_dictionary", "Stable ID; unique in dictionary", "Never."),
    rag_row("value", "RED — Must provide", "Yes", "Yes unless state says unavailable", "Observed value at native frequency.", "132.4", "Carries the actual source observation without fake rows.", "The observation is missing; do not silently fill it.", "context_data", "Finite numeric value or governed missing state", "Only when an explicit missingness state is provided by the governed path."),
    rag_row("native_frequency", "RED — Must provide", "Yes", "Yes", "Frequency at which the source was observed.", "weekly", "Stops monthly or quarterly data being presented as weekly.", "The source frequency is unknown.", "context_data; variable_dictionary", "weekly, monthly, quarterly, yearly, daily, event", "Never."),
    rag_row("variable_class", "RED — Must provide", "Yes", "Yes", "Type of variable.", "rate_index", "Separates flows, stocks, rates, surveys, and event flags.", "The variable meaning is incomplete.", "variable_dictionary", "flow_count, stock_level, rate_index, survey_measurement, event_flag", "Never for governed variables."),
    rag_row("role", "RED — Must provide", "Yes", "Yes", "Approved operational future/model role.", "exogenous_forecastable_control", "Prevents an endogenous mediator being independently forecast.", "The variable role is unsafe or blocked.", "variable_dictionary; planning", "Approved role text; see guide", "Never for governed variables."),
    rag_row("source", "AMBER — Needed for some uses", "Yes", "Yes for adoption", "Source system or owner reference.", "ONS CPI release", "Makes provenance visible.", "Context adoption remains under review.", "variable_dictionary; audit", "Text with version/date", "For an early draft only."),
    rag_row("scope", "AMBER — Needed for some uses", "Yes", "Yes for adoption", "Geographic or business scope of the variable.", "UK", "Prevents a national series being mistaken for a market series.", "Adoption remains under review.", "variable_dictionary; alignment", "Text", "For an exploratory upload not yet adopted."),
    rag_row("effective_from", "GREEN — Optional", "Yes", "No", "Date the dictionary mapping starts.", "2026-01-01", "Supports versioned context meaning.", "No mapping start is recorded.", "audit; persistence", "ISO date", "For an always-active mapping."),
    rag_row("effective_to", "GREEN — Optional", "Yes", "No", "Date the dictionary mapping ends.", "2026-12-31", "Supports versioned context meaning.", "No mapping end is recorded.", "audit; persistence", "ISO date", "For an open-ended mapping."),
    rag_row("unit", "AMBER — Needed for some uses", "Yes", "Yes for adoption", "Unit of the observed value.", "index", "Prevents rates, counts, and currency being mixed.", "Context adoption remains under review.", "variable_dictionary; economics", "Text", "For a variable whose unit is explicitly not applicable."),
]


EVENT_RAG = [
    rag_row("event_id", "RED — Must provide", "Yes", "Yes", "Stable event identity.", "black_friday_2026", "Keeps occurrences traceable.", "The event row is invalid.", "events", "Stable ID", "Never."),
    rag_row("event_name", "RED — Must provide", "Yes", "Yes", "Readable event name.", "Black Friday", "Makes the event understandable.", "The event row is invalid.", "events", "Text", "Never."),
    rag_row("start_date", "RED — Must provide", "Yes", "Yes", "First date of the event window.", "2026-11-27", "Preserves the factual event window.", "The event cannot be used.", "events", "ISO date", "Never."),
    rag_row("end_date", "RED — Must provide", "Yes", "Yes", "Last date of the event window.", "2026-11-30", "Preserves the factual event window.", "The event cannot be used.", "events", "ISO date; on/after start", "Never."),
]


EXPERIMENT_RAG = [
    rag_row("experiment_id", "RED — Must provide", "Yes", "Yes", "Stable experiment identity.", "geo_lift_uk_01", "Links evidence to one experiment.", "The evidence cannot be reviewed.", "experiment_evidence", "Stable ID", "Never."),
    rag_row("activity_id", "RED — Must provide", "Yes", "Yes", "Activity affected by the experiment.", "paid_search_google_brand", "Links evidence to a governed activity.", "Evidence cannot be mapped.", "experiment_evidence", "Existing activity ID", "Never."),
    rag_row("market", "RED — Must provide", "Yes", "Yes", "Market in the experiment.", "UK", "Keeps experiment scope explicit.", "Evidence cannot be scoped.", "experiment_evidence", "Stable market code/label", "Never."),
    rag_row("start_date", "RED — Must provide", "Yes", "Yes", "Experiment start date.", "2026-03-01", "Defines the test window.", "Evidence cannot be checked.", "experiment_evidence", "ISO date", "Never."),
    rag_row("end_date", "RED — Must provide", "Yes", "Yes", "Experiment end date.", "2026-03-28", "Defines the test window.", "Evidence cannot be checked.", "experiment_evidence", "ISO date; on/after start", "Never."),
]


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def html_table(rows: list[dict[str, str]], extra_class: str = "") -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in RAG_HEAD)
    body = []
    for row in rows:
        status = row["Status"]
        cls = "red" if status.startswith("RED") else "amber" if status.startswith("AMBER") else "green" if status.startswith("GREEN") else "grey"
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
    return "<ul class=\"mistakes\">" + "".join(f"<li>{esc(item)}</li>" for item in items) + "</ul>"


def domain_section(
    anchor: str,
    number: str,
    title: str,
    purpose: str,
    structure: str,
    raw_example: str,
    dictionary_schema: str,
    rag: list[dict[str, str]],
    connection: str,
    checklist: list[str],
    add: list[str],
    common_mistakes: list[str],
    valid_invalid: list[list[str]],
    extra_html: str = "",
) -> str:
    return f"""
    <section id="{anchor}" class="domain section">
      <p class="eyebrow">Domain {number}</p><h2>{esc(title)}</h2>
      <h3>Purpose</h3><p>{purpose}</p>
      <h3>Workbook structure</h3><p>{structure}</p>
      <h3>Raw table example</h3>{code_block(raw_example)}
      <h3>Dictionary schema</h3><p>{dictionary_schema}</p>
      {html_table(rag, "wide")}
      <h3>Worked connection</h3><p>{connection}</p>
      <h3>Minimum checklist</h3>{mistakes(checklist)}
      <h3>Add these when available</h3>{mistakes(add)}
      <h3>Common mistakes</h3>{mistakes(common_mistakes)}
      <h3>Valid and invalid examples</h3>{simple_table(["Valid", "Invalid", "Why"], valid_invalid)}
      {extra_html}
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
    faq = [
        ("What is the safest first upload?", "Upload the three standard domain workbooks using the current templates, with dictionaries completed and source metadata attached. See <a href=\"#workflow\">the workflow</a>."),
        ("Can one domain use more than one physical file?", "Yes. A logical domain may contain many uploaded files or workbooks. The app merges them only when keys and shared values are compatible."),
        ("Can one workbook contain several domains?", "Yes, but select the domain explicitly when the workbook contains more than one recognised domain."),
        ("Is market read from the filename?", "No. Market must be a row-level column in every relevant table."),
        ("Should I make all data weekly?", "No. Upload the source at its native frequency. A later alignment step needs its own approved method."),
        ("Are missing values the same as zero?", "No. Missing means unavailable or not observed; zero is a measured zero. Never fill one with the other silently."),
        ("What does outcomes wide mean?", "Each row is one period and market. Each outcome has its own source column."),
        ("What does activity tidy-long mean?", "Each row identifies one period, market, and activity, with one or more raw measures in columns."),
        ("What is source_column?", "It is the exact header in the raw outcomes table that contains the outcome values."),
        ("Can an ID explain the whole outcome?", "No. The dictionary carries meaning. IDs must be stable and useful, but meaning must never be guessed from an ID."),
        ("Which Family History segments are in scope?", "New, Winback, and DNA cross-sell. Do not add a fourth FH segment without an approved decision."),
        ("Can I add DNA self-activated and gifted segments?", "Only when the source and an approved use support them. Do not add them silently."),
        ("Are GSA and Net Bill Through the same metric?", "No. They are distinct definitions with different date, cohort, maturity, and reconciliation needs."),
        ("Can I upload weekly Net Bill Through?", "Yes, when it is a supplied governed outcome with an approved definition and completeness metadata. The app does not reconstruct it from raw billing events."),
        ("What is the completeness sheet for?", "It records the data-as-of date, model window, maturity rule, and owner for an outcome. It is especially important for official NBT use."),
        ("What are the official UK production NBT outcomes?", "Three separate Family History outcomes: fh_net_billthrough_count_new, fh_net_billthrough_count_dna_cross_sell, and fh_net_billthrough_count_winback. See <a href=\"#uk-nbt-production\">the UK production NBT note</a>."),
        ("Does production NBT use the same 14-day maturity example shown elsewhere in this guide?", "No. That 14-day example is an illustrative historical-test rule. Official UK production NBT uses its own approved production definition, maturity rule, and evidence bundle supplied with the source pack."),
        ("Does the downloadable generic sample outcome workbook already use the NBT ids?", "No. The generic sample teaches the pattern using GSA ids. UK production NBT ids and definitions come from the approved UK source pack, not the generic sample."),
        ("What is model_input_measure?", "The exact raw activity measure selected for modelling, such as spend, clicks, impressions, GRPs, or TVRs."),
        ("What is model_input_column?", "The model-ready destination column created after tidy activity data is pivoted. It is not the raw measurement column."),
        ("Does the activity ID need every metadata field?", "No. Use the smallest stable identity that avoids collisions. Keep descriptive fields in the dictionary."),
        ("Should the same activity ID be reused across markets?", "It may be reused for the same cross-market activity concept, with market remaining part of the row key. Use pooling_group_id for an optional cross-market identity."),
        ("Does pooling_group_id pool the model?", "No. It records comparable identity only. Pooling is a separate model choice."),
        ("Do spend and clicks mean the same thing?", "No. Record the model input, spend, and response unit separately. A later governed mapping is required for monetary economics."),
        ("Should all raw activity measures be modelled?", "No. Keep useful raw measures, but select one model_input_measure per activity for the model input."),
        ("Do owned and earned activity belong in another domain?", "No. They are activity/media records too. Their ownership, role, and economics must be explicit."),
        ("How are Brand and Non-Brand Search represented?", "Use separate activity identities and the approved Search taxonomy: Google/Bing × Brand/Non-Brand. Parent totals are calculated from leaves."),
        ("Can I add a deeper Non-Brand Search child group?", "Only through the governed taxonomy catalogue, starting as draft. A child cannot be fitted at the same model grain as its parent, and it has no planning eligibility or cost-bearing treatment until child-level observed data and governed cost support exist."),
        ("Can SEO visibility be split by Brand and Non-Brand?", "Yes, using seo_group_id/seo_group_name per market/week. A row with no group supplied stays in one generic seo_visibility group."),
        ("Are PMax, Demand Gen, and YouTube Paid Search?", "No. They are not automatically classified as Paid Search by platform name."),
        ("What is a Search cap?", "A budget or delivery ceiling. It is a constraint, not realised spend or delivery, and expected unused cap must remain possible."),
        ("What is residual Paid Search incrementality?", "A model output from the approved treatment path. It is not a raw source metric or a new upload object."),
        ("Can Google Trends be generic context?", "Only as an explicitly governed context variable. For Candidate A Brand Demand, use the dedicated anchor upload with its query metadata."),
        ("Can GSC organic traffic stand in for SEO visibility?", "No. The governed SEO visibility metric is separate from organic Search capture and uses its dedicated observation path."),
        ("Can monthly context be manually expanded to weeks?", "No. Do not duplicate or invent weekly rows. Use a governed frequency-alignment method when one is approved."),
        ("What are the context variable classes?", "flow_count, stock_level, rate_index, survey_measurement, and event_flag."),
        ("How do I upload named events?", "Use the optional events sheet with event_id, event_name, start_date, and end_date. Factual dates stay unchanged; classification is not inferred."),
        ("Does experiment evidence calibrate the model automatically?", "No. It remains source evidence until a separate reviewed calibration record and method are approved."),
        ("Is outcome valuation part of the three core workbooks?", "No. FH LTR and DNA revenue valuation are separate governed uploads and are not needed for a count first fit."),
        ("Can I use an average LTR for future ROI?", "Only as an explicit scenario assumption approved for the project. Do not extrapolate historical values automatically."),
        ("Does a currency column perform FX conversion?", "No. It identifies the monetary unit. FX translation needs a governed rate set and approved method."),
        ("What happens when two rows have the same key?", "The standard merge and canonicalisation paths fail closed and ask you to resolve the source grain; they do not silently aggregate."),
        ("What does a RED field mean?", "The column must exist and the value is required for the stated use. A GREEN field may be optional, but its absence can still limit a feature."),
        ("Why does the builder show a collision warning?", "Because two candidate rows would produce the same stable ID. Add the next meaningful identity field; do not add a random number."),
        ("Can I override a suggested ID?", "Yes. The final ID uses the manual override when present, but you remain responsible for uniqueness, stability, and dictionary consistency."),
        ("Where can I find the exact parser contract?", "See the source files and tests listed in the <a href=\"#review\">review note</a>. This guide explains the analyst-facing boundary."),
    ]
    faq_html = "".join(f"<details><summary>{esc(q)}</summary><p>{a}</p></details>" for q, a in faq)

    outcomes = domain_section(
        "outcomes", "1", "Outcomes", "Outcomes are the measures the model explains. Keep Family History New, DNA cross-sell, and Winback separate. Keep DNA customer-relationship partitions separate from purchase-recipient partitions unless an approved definition says otherwise.",
        "Required sheets: <code>outcomes</code> and <code>outcome_dictionary</code>. Optional sheet: <code>outcome_completeness</code>. The source table is wide: one row per <code>period_start × market</code>, with one source column per outcome. The dictionary is the meaning layer.",
        "period_start | market | fh_gsa_new | fh_gsa_dna_cross_sell | fh_gsa_winback\n2026-01-05   | UK     | 120        | 18                    | 9",
        "The current v2 dictionary requires: outcome_id, source_column, product, metric_key, metric, segment_dimension, segment, outcome_group_id, outcome_group_label, outcome_family_key, group_aggregation. The code also accepts optional canonical definition fields such as unit, aggregation_type, date_basis, maturity_required, role, eligibility flags, definition_version, event_definition, cohort_or_attribution_basis, completeness_or_maturity_policy, exclusions, reconciliation_source, business_owner, effective_from, effective_to, value_weight, and value_currency.",
        OUTCOME_RAG,
        "The dictionary row with <code>outcome_id=fh_gsa_new</code> points to <code>source_column=fh_gsa_new</code>. The parser checks that this exact column exists in <code>outcomes</code>; it does not infer that “GSA” or “NBT” in an ID means anything. If a group is supplied, its rows describe semantic membership and optional sum reconciliation. Group membership does not automatically make a total fit or become an official report.",
        ["The two required sheets exist and have exact required headers.", "Every outcomes row has a period_start and market.", "Every dictionary source_column exists in outcomes.", "Outcome IDs are unique and stable.", "Product, metric, segment dimension, and segment are explicit.", "Use the completeness sheet for official/maturity-sensitive outcomes, especially supplied NBT."],
        ["Add versioned definition, owner, date basis, cohort basis, exclusions, and reconciliation source.", "Add outcome_group fields when a component/total relationship is governed.", "Add outcome_completeness for data-as-of and maturity review.", "Add a separate valuation upload for FH LTR or DNA revenue; do not put rate calculations in the count table."],
        ["Using NBT as a friendly name for GSA or treating sign-up → NBT → GSA as a universal sequence.", "Putting outcomes in long format when the current standard outcomes contract expects wide rows.", "Using an outcome ID to carry meaning while leaving dictionary fields blank.", "Guessing product or segment from a source-column name.", "Adding self-activated/gifted/unactivated DNA splits without source support and approval.", "Fitting a supplied total and its components together without an explicit treatment.", "Reconstructing weekly NBT from event-level billing data at upload time.", "Using a rate as if it were a count or adding rates across weeks.", "Applying the illustrative 14-day historical-test maturity example as the production NBT default instead of the approved production maturity rule and evidence."],
        [["fh_gsa_new + product Family History + segment New + metric_key fh_gsa", "metric_key fh_net_billthrough_count but metric says GSA", "The key, label, and definition disagree."], ["DNA New Customer and DNA Existing FH Customer in separate rows", "A DNA combined row silently copied into both segments", "A copied value double-counts and invents support."], ["outcome_group_id blank for an independent outcome", "group_aggregation=sum with no group ID", "The group block must be complete or blank."], ["outcome_completeness row names the exact NBT outcome_id", "Completeness row uses a friendly label not in the dictionary", "Completeness is keyed to the governed definition."], ["GSA and NBT supplied as distinct columns", "One column labelled GSA/NBT", "These are different measures and approvals."]],
        extra_html="<h3>Optional outcome_completeness schema</h3><p>Use this sheet for freshness, model-window, maturity, and ownership metadata. Official NBT requires it under the approved completeness contract.</p>" + html_table(COMPLETENESS_RAG, "wide") + """
      <h3 id="uk-nbt-production">UK production Net Bill Through (NBT)</h3>
      <div class="callout warning"><b>Production-specific example, not a universal rule.</b> This section describes the approved UK production boundary. It does not change the generic outcome contract above, and it must not be read as a default for every market or project.</div>
      <p>Official UK production configures three separate Family History NBT outcomes — <code>fh_net_billthrough_count_new</code>, <code>fh_net_billthrough_count_dna_cross_sell</code>, and <code>fh_net_billthrough_count_winback</code> — as distinct <code>outcome_id</code>/<code>source_column</code> rows sharing <code>metric_key=fh_net_billthrough_count</code> with New, DNA cross-sell, and Winback as separate <code>segment</code> values, the same New/DNA-cross-sell/Winback pattern already shown for GSA above. GSA remains a distinct secondary/context measure: it is never reconstructed into NBT, and NBT is never reconstructed from GSA or from raw billing events.</p>
      <p>Production NBT requires its own completeness/maturity evidence supplied with the source pack, not invented at upload time: the approved production definition, maturity/completeness evidence, exclusions, reconciliation source, <code>data_as_of_date</code>, and a source fingerprint. This production evidence bundle is a separate, stricter requirement than the bounded historical-test 14-day maturity rule used for exploratory/historical work — do not apply the historical-test rule to production NBT, and do not treat the illustrative 14-day example elsewhere in this guide as the production default.</p>
      <p>This boundary is recorded in <code>docs/uk_production_onboarding_runbook.md</code> and the approved <code>REQ-NBT-001</code> through <code>REQ-NBT-004</code> requirement records, which are the authority for the exact production definition, maturity rule, and evidence requirements — this guide summarises them for an analyst preparing an upload; it does not restate them as new rules.</p>""",
    )
    activity = domain_section(
        "activity", "2", "Activity and Media", "Activity data describes what was delivered, spent, or observed. The tidy source is kept separate from the wide model frame so the selected physical measure is visible and reproducible.",
        "Required sheets: <code>activity_data</code> and <code>activity_dictionary</code>. Raw activity data is tidy/long with at least <code>period_start</code>, <code>market</code>, and <code>activity_id</code>. The dictionary contains base fields plus optional v2 physical-unit and effective-date fields. A single workbook may carry multiple raw measure columns.",
        "period_start | market | activity_id                 | spend | impressions | clicks\n2026-01-05   | UK     | paid_search_google_brand   | 1200  | 180000      | 8200",
        "Base dictionary fields: activity_id, market, pooling_group_id, channel, platform, campaign_type, marketing_objective, funnel_stage, product_advertised, message_type, activity_ownership, intended_model_role, model_input_column, model_input_measure, economic_treatment, planning_eligibility, source. v2 adds model_input_unit, model_input_kind, spend_column, response_unit_column, response_unit, currency, effective_from, and effective_to. Search intent/platform fields exist in the governed activity model, but the current standard source dictionary parser does not map them automatically; use the dedicated mapping/admin boundary and treat this as a review item.",
        ACTIVITY_RAG,
        "For <code>activity_id=paid_search_google_brand</code>, <code>model_input_measure=spend</code> selects the raw <code>spend</code> column. After canonicalisation, the value is written to the wide destination <code>model_input_column=uk_paid_search_google_brand</code>. This is why <b>model_input_measure</b> and <b>model_input_column</b> are different. Spend, delivery, and response-unit fields remain separate. Missing activity rows stay missing; they are not filled as zero.",
        ["The two required sheets and exact identity columns exist.", "Every raw row has period_start, market, and activity_id.", "Every dictionary key is unique at market × activity_id.", "model_input_measure names a real raw measure column.", "model_input_column is stable and unique in the model frame.", "Ownership, role, economics, planning, and source are explicit."],
        ["Keep spend, impressions, clicks, GRPs, spots, visits, and other observed measures when useful.", "Record physical units and currency separately.", "Record Search taxonomy only where the dedicated governed mapping supports it.", "Add governed media cost mappings before monetary CPA/ROI."],
        ["Making a wide activity table when the standard source expects tidy-long rows.", "Putting every metadata field into the ID and creating brittle IDs.", "Using <code>model_input_column</code> as if it were the raw source measure.", "Treating spend as clicks, or clicks as conversions, without an explicit mapping.", "Forcing paid, owned, and earned activity into different logical domains.", "Filling missing delivery with zero.", "Assuming every activity is optimisable because it was fitted.", "Calling PMax, Demand Gen, or YouTube Paid Search merely because the platform is Google.", "Using Brand Search as one generic variable without classification."],
        [["spend is selected as model_input_measure and unit is GBP", "model_input_measure is uk_paid_search_google_brand", "The raw source column and model-ready destination are different."], ["Google Brand and Bing Brand have separate activity IDs", "Google/Bing stored only in a free-text file name", "Platform identity must be explicit."], ["pooling_group_id shared by comparable markets", "assuming shared pooling_group_id means pooled estimation", "Pooling is a model choice, not an ID effect."], ["paid_search_cap recorded as a constraint object", "cap copied into realised spend", "A cap is not guaranteed spend."], ["owned SEO activity marked earned/demand_capture", "SEO visibility relabelled as paid delivery", "SEO visibility and organic capture are distinct."], ["missing row left absent", "missing row filled with 0", "Absence is not an observed zero."]],
    )
    context = domain_section(
        "context", "3", "Context and External Factors", "Context data records controls, signals, and events at their native source frequency. Its role is explicit because future planning treats exogenous controls, endogenous mediators, latent baseline states, cost assumptions, and decisions differently.",
        "Required sheets: <code>context_data</code> and <code>variable_dictionary</code>. Optional sheet: <code>events</code>. Context data is tidy/long with <code>period_start</code>, <code>market</code>, <code>variable_id</code>, <code>value</code>, and <code>native_frequency</code>. Monthly or quarterly data may remain monthly or quarterly. Do not manually make fake weekly rows.",
        "period_start | market | variable_id | value | native_frequency\n2026-01-01   | UK     | uk_cpi      | 132.4 | monthly",
        "The current variable dictionary requires variable_id, variable_class, native_frequency, and role. v2 adds source, scope, effective_from, effective_to, and unit. Events use event_id, event_name, start_date, and end_date. The current closed variable classes are flow_count, stock_level, rate_index, survey_measurement, and event_flag.",
        CONTEXT_RAG,
        "The row with <code>variable_id=uk_cpi</code> joins to a dictionary row with <code>variable_class=rate_index</code>, <code>native_frequency=monthly</code>, and an approved role such as <code>exogenous_forecastable_control</code>. The parser preserves native frequency and pivots observations; it does not invent a weekly value. A later alignment method must be approved and documented.",
        ["The two required sheets exist and use exact headers.", "Every context observation has period_start, market, variable_id, value, and native_frequency.", "Every variable has class, native frequency, and role.", "Mixed frequency is disclosed rather than silently converted.", "Missingness and observed zero are distinguishable.", "Events use factual dates and are kept separate from continuous variables."],
        ["Add source, scope, unit, and effective dates.", "Add a named events sheet for campaigns, holidays, or other governed occurrences.", "Add dedicated Google Trends Candidate A metadata when using a Brand Demand anchor.", "Add dedicated SEO visibility observations for GSC-derived ranking visibility."],
        ["Copying monthly data into each week.", "Treating unavailable as zero.", "Using one variable ID for measures with different units or meanings.", "Forecasting an endogenous mediator as an independent future control.", "Using an ordinary external forecast for the latent baseline.", "Assuming the current app has a default monthly-to-weekly conversion.", "Putting a named event into a continuous value column with no event identity.", "Treating Google Trends 0 as confirmed zero demand."],
        [["uk_cpi is monthly and stays monthly", "uk_cpi repeated into four weekly rows", "The source frequency must remain truthful."], ["variable_class=rate_index", "variable_class=consumer_signal without an approved class", "Use the closed vocabulary for governed context."], ["role=exogenous_forecastable_control for CPI", "role=exogenous_forecastable_control for branded-search demand", "An endogenous mediator must be generated by the scenario model."], ["event_id and factual start/end dates", "event flag silently inferred from a promotion name", "Event treatment is separately governed."], ["suppressed value state recorded", "suppressed converted to 0", "Suppressed is not observed zero."]],
        extra_html="<h3>Optional events schema</h3><p>Events are a separate optional table. Keep factual dates and event identity; do not infer event family or response treatment.</p>" + html_table(EVENT_RAG, "wide"),
    )
    search_table = simple_table(
        ["Object", "Unit", "Role / treatment", "Upload or source boundary"],
        [["search_demand", "index or count", "demand_capture context; not paid", "Candidate A Google Trends anchor or another governed demand source"], ["paid_search_spend", "currency", "intervention / paid cost", "activity data + cost mapping"], ["paid_search_delivery", "clicks or impressions", "descriptive delivery; not a second fitted spend", "activity data + physical mapping"], ["paid_search_cap", "currency or delivery unit", "constraint/context; not realised spend", "separate governed cap object / Candidate A inputs"], ["organic_search_capture", "response count", "demand_capture; earned", "activity or dedicated source"], ["direct_navigation_capture", "response count", "demand_capture; owned", "activity or dedicated source"], ["residual Paid Search incrementality", "model output", "treatment result", "never a raw upload column"]],
        "compact",
    )
    advanced = f"""
    <section id="advanced" class="section">
      <p class="eyebrow">Optional and advanced boundaries</p><h2>Use separate paths when the feature is different</h2>
      <p>These inputs are not required for a first count model. Uploading evidence does not grant reporting, planning, or optimisation approval.</p>
      <h3>Search object model</h3><p>Never collapse these objects into one <code>Brand Search</code> column:</p>{search_table}
      <p>Minimum Search taxonomy leaves are Google Brand, Bing Brand, Google Non-Brand, and Bing Non-Brand. Keep <code>search_intent_group_id</code> and <code>search_platform</code> as separate axes. PMax, Demand Gen, and YouTube are not automatically Paid Search. A cap is not guaranteed spend, and a higher non-binding cap must not create artificial value.</p>
      <p>A deeper Non-Brand Search child group (for example a specific Non-Brand sub-category) is supported through a separate governed taxonomy catalogue, not by inventing a new free-text value. A new child starts in draft status until explicitly approved, stays subordinate to its approved Brand/Non-Brand parent, and cannot be fitted at the same model grain as that parent — a project chooses either the parent or its governed children for fitting, not both at once. Google/Bing remains a separate platform axis from the intent group. A draft or newly approved child has no planning eligibility and no cost-bearing economic treatment until child-level observed data and governed cost support exist; reporting can still roll a child up into its parent total.</p>
      <h3>Candidate A Search mediation/capacity observations</h3>
      <p>Use the dedicated Candidate A observation boundary when supplying <code>paid_search_delivery</code>, <code>paid_search_cap</code>, <code>organic_search_capture</code>, and <code>direct_navigation_capture</code>. It requires exact period/market rows, a complete weekly grid, finite non-negative values, and delivery not exceeding cap under the governed scale. It does not infer source IDs, cap provenance, demand channels, or a calibration prior.</p>
      <h3>Google Trends Candidate A Brand Demand anchor</h3>
      <p>Use the dedicated upload with <code>week</code> and <code>raw_index</code>, plus query_set_id, geography, approved branded terms, category, search property, extraction date, and sigma. The raw index is 0–100 relative interest. A raw zero is <b>suppressed</b>, not confirmed zero. One query set is used for the series; there is no silent stitching. This is exploratory/directional and planning-disabled by default.</p>
      <h3>SEO / Google Search Console</h3>
      <p>Use the dedicated SEO visibility path: market, week, dimension_label, position, impressions, and optional clicks. The metric is an impression-weighted inverse position index. It is not organic Search capture, it is not a paid activity, and it is outside spend-based CPA/ROI and optimisation until separately approved.</p>
      <p>SEO visibility supports more than one named group per market/week — select Brand and Non-Brand (or an explicitly governed deeper child) individually via <code>seo_group_id</code>/<code>seo_group_name</code> rather than blending them into one series; a row with no group supplied defaults to a single generic <code>seo_visibility</code> group. Rows may be raw GSC observations or already-aggregated market/week/group rows. A missing week stays inactive — it is never zero-filled — and SEO carries no spend-based CPA or ROI regardless of grouping.</p>
      <h3>Outcome valuation</h3>
      <p>FH LTR and DNA revenue are a separate governed artifact, not an outcome dictionary shortcut. The current upload columns are <code>valuation_kind</code>, <code>market</code>, <code>week</code>, <code>segment</code>, <code>denominator_outcome_id</code>, <code>quality_status</code>, <code>segment_dimension</code>, <code>aggregate_value</code>, <code>currency</code>, <code>source</code>, <code>source_version</code>, <code>schema_version</code>, and <code>horizon_months</code>. Count-first fitting can omit it. Historical rates are derived at weekly segment grain; future values require an explicit scenario assumption, not automatic extrapolation. FX conversion is a separate Finance-governed decision.</p>
      <h3>Experiment evidence</h3>
      <p>Optional <code>experiment_evidence</code> rows need experiment_id, activity_id, market, start_date, and end_date. Adoption later needs design, estimand, estimate, uncertainty, method, source, and evidence status. Uploading evidence never auto-calibrates the model or changes a fit.</p>{html_table(EXPERIMENT_RAG, "wide")}
      <h3>Future-variable roles</h3>
      {simple_table(["Role", "Meaning", "Example", "Do not do"], [["planned decision variable", "User sets spend, delivery, promotion, price, or cap", "Paid Search spend", "Call a cap realised spend"], ["exogenous forecastable control", "External series suitable for a forecast", "CPI or unemployment", "Forecast an endogenous mediator independently"], ["cost/translation assumption", "CPM, CPC, GRP cost, FX, or similar", "GBP per click", "Treat model input units as automatically monetary"], ["endogenous funnel state", "Generated by the causal model from the plan", "Branded-search demand", "Also configure as an independent future control"], ["latent baseline state", "Projected from its own fitted process", "Time-varying intercept", "Send it to Chronos as an ordinary target"], ["fixed business assumption / diagnostic", "Held fixed or historical-only", "Approved business rule", "Optimise it without approval"]], "compact")}
      <h3>RAG for advanced uploads</h3>
      {simple_table(["Input", "First fit needed?", "Standard sheet or separate?", "Absent consequence", "RAG"], [["Outcome completeness", "No for exploratory counts; yes for official/maturity-sensitive outcomes", "Optional standard sheet", "Official use blocks", "AMBER / RED by use"], ["Named events", "No", "Optional standard sheet", "Event response unavailable", "AMBER"], ["Experiment evidence", "No", "Optional standard sheet", "No calibration evidence", "AMBER"], ["SEO/GSC", "No", "Dedicated SEO path", "No SEO visibility pathway", "AMBER"], ["Trends Candidate A", "No", "Dedicated anchor path", "No Candidate A demand anchor", "AMBER"], ["FH LTR/DNA revenue", "No for count fit", "Separate valuation upload", "Economic output blocked", "AMBER / RED for economics"], ["FX/cost mappings", "No", "Separate governed mapping", "CPA/ROI translation blocked", "AMBER / RED for economics"], ["Future assumptions/caps", "No", "Scenario/config boundary", "Scenario value or capacity output blocked", "AMBER / RED for planning"]], "compact")}
    </section>
    """
    workflow = f"""
    <section id="workflow" class="section">
      <p class="eyebrow">Start here</p><h2>Upload workflow</h2>
      <div class="callout"><b>Logical domain is not one physical file.</b> You may upload any number of files or workbooks to a domain, and a workbook may contain several tables. The app keeps source versions and table lineage visible.</div>
      <div class="callout warning"><b>RAG key:</b> RED means provide it for the stated use; AMBER means some uses need it; GREEN means optional. The words and consequences are authoritative — colour is only a visual aid.</div>
      <ol class="steps"><li>Download the current standard templates.</li><li>Complete dictionary fields before loading large raw files.</li><li>Keep each source at its native frequency and keep market in the rows.</li><li>Upload Outcomes, Activity and Media, and Context and External Factors as their logical categories. Add Experiment Evidence only when it is useful.</li><li>Review warnings, provenance, source versions, missingness, duplicate keys, and model-input mappings.</li><li>Only then continue to transformation, fit, reporting, planning, or optimisation. A successful upload is not an approval.</li></ol>
      <h3>What the current parser does</h3>
      <ul><li>Reads every sheet in a standard workbook and retains unknown sheets with a warning.</li><li>Requires explicit domain selection when a workbook contains multiple recognised domains.</li><li>Rejects empty sheets and missing required columns.</li><li>Canonicalises activity only at the explicit model-input boundary, pivoting to period × market.</li><li>Preserves missing rows; it does not silently fill missing activity or context values with zero.</li><li>Rejects duplicate source grain during canonicalisation or incompatible duplicate rows when merging multiple files.</li><li>Accepts legacy v1 shapes but marks them incomplete; use v2 for new work.</li></ul>
      <h3>Three words that prevent most mistakes</h3>
      {simple_table(["Word", "Means", "Does not mean"], [["raw", "what the source supplied", "a model-ready wide frame"], ["dictionary", "what a field means and how it is governed", "a licence to infer missing values"], ["canonical", "the explicit transformation boundary", "a silent fill, frequency conversion, or approval"]], "compact")}
    </section>
    """
    glossary = simple_table(["Term", "Plain-English meaning"], [["activity_id", "Stable identity at market × activity grain."], ["model_input_measure", "Raw column selected for the model."], ["model_input_column", "Destination column after activity pivot."], ["outcome_id", "Stable outcome-definition identity."], ["variable_id", "Stable context-variable identity."], ["native frequency", "Frequency the source actually uses."], ["pooling_group_id", "Optional comparison identity, not a pooling instruction."], ["cap", "A budget/delivery ceiling, not realised spend."], ["missing", "No usable observed value; not the same as zero."], ["maturity rule", "When an outcome period is complete enough to use."], ["RAG", "Red/amber/green status with written consequences."], ["source version", "Version of the file or upstream source used."], ["residual incrementality", "A model output after the governed pathway treatment."], ["evidence status", "Strength/readiness of evidence; not reporting approval."]], "compact")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Ancestry MMM Data Upload Guide</title>
<style>
:root{{--ink:#18212b;--muted:#5d6b78;--blue:#0b5cab;--navy:#12304a;--wash:#f3f7fb;--line:#d9e2ea;--red:#fce4e4;--amber:#fff1cc;--green:#e3f4e6;--grey:#edf0f2;--shadow:0 8px 24px rgba(19,48,74,.09)}}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth}} body{{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;color:var(--ink);line-height:1.55;background:#fff}} a{{color:var(--blue)}} a:visited{{color:#5b2a86}} code{{background:#eef3f7;color:#173b5e;border-radius:4px;padding:.1em .3em;font-size:.93em}} footer a:visited{{color:#fff}} .skip{{position:absolute;left:-9999px}} .skip:focus{{left:1rem;top:1rem;background:#fff;padding:.5rem;z-index:10}}
.layout{{display:grid;grid-template-columns:260px minmax(0,1fr);min-height:100vh}} aside{{position:sticky;top:0;height:100vh;overflow:auto;background:var(--navy);color:#fff;padding:1.25rem}} aside h2{{font-size:1.1rem;color:#fff;margin:.2rem 0 1rem}} aside p{{font-size:.82rem;color:#c9d8e5}} nav a{{display:block;color:#e0edf7;text-decoration:none;padding:.32rem .2rem;font-size:.88rem}} nav a:hover,nav a:focus{{color:#fff;background:rgba(255,255,255,.1);border-radius:4px}} .search{{width:100%;padding:.55rem;border-radius:5px;border:1px solid #6e91aa;margin:.4rem 0 1rem}} main{{min-width:0}} .hero{{background:linear-gradient(135deg,#eaf4ff,#fff);padding:4rem clamp(1rem,5vw,5rem) 3.25rem;border-bottom:1px solid var(--line)}} .hero h1{{font-size:clamp(2rem,4vw,3.6rem);line-height:1.08;color:var(--navy);max-width:850px;margin:.2rem 0 1rem}} .hero p{{max-width:780px;font-size:1.08rem}} .badge{{display:inline-block;background:#dbeeff;color:#084d8d;padding:.25rem .55rem;border-radius:999px;font-weight:700;font-size:.78rem}} .section{{padding:3rem clamp(1rem,5vw,5rem);max-width:1500px}} .section:nth-of-type(even){{background:#fff}} .domain{{border-top:1px solid var(--line)}} h2{{font-size:2rem;color:var(--navy);margin:.15rem 0 1.1rem}} h3{{color:#234f72;margin-top:1.8rem}} .eyebrow{{text-transform:uppercase;letter-spacing:.12em;font-size:.76rem;color:var(--blue);font-weight:800;margin:0}} .callout{{border-left:5px solid var(--blue);background:var(--wash);padding:1rem 1.2rem;margin:1.2rem 0}} .warning{{border-left-color:#c67a00;background:#fff8e7}} .table-wrap{{overflow:auto;margin:1rem 0 1.25rem;border:1px solid var(--line);border-radius:7px}} table{{border-collapse:collapse;width:100%;background:#fff;font-size:.87rem}} th,td{{border-bottom:1px solid var(--line);padding:.55rem .65rem;text-align:left;vertical-align:top}} th{{background:#eaf1f6;color:var(--navy);font-weight:800;position:sticky;top:0;z-index:1}} tr:last-child td{{border-bottom:0}} .rag td:nth-child(2){{font-weight:800;min-width:150px}} .rag-red{{background:var(--red)}} .rag-amber{{background:var(--amber)}} .rag-green{{background:var(--green)}} .rag-grey{{background:var(--grey)}} .compact{{max-width:1100px}} pre{{overflow:auto;background:#f5f8fb;color:#17222d;border:1px solid #b8c7d3;padding:1rem;border-radius:6px;font-size:.86rem}} pre code{{background:transparent;color:#17222d;padding:0}} .mistakes{{padding-left:1.2rem}} .mistakes li{{margin:.35rem 0}} .steps{{counter-reset:step;list-style:none;padding:0;display:grid;gap:.7rem;max-width:850px}} .steps li{{counter-increment:step;display:flex;gap:.7rem;background:var(--wash);padding:.75rem;border-radius:6px}} .steps li::before{{content:counter(step);background:var(--blue);color:#fff;width:1.6rem;height:1.6rem;border-radius:50%;display:inline-grid;place-items:center;font-weight:800;flex:0 0 auto}} .diagram{{display:flex;align-items:center;gap:.7rem;flex-wrap:wrap;background:#fff;padding:1rem;border:1px solid var(--line);border-radius:9px;box-shadow:var(--shadow);margin:1rem 0 2rem}} .diagram-box{{border:2px solid var(--blue);border-radius:7px;padding:.75rem;min-width:180px;background:#f7fbff}} .diagram-box span{{display:block;font-size:.8rem;color:var(--muted);margin-top:.35rem}} .diagram-box.model{{border-color:#258b4d;background:#f5fff7}} .diagram-box.activity{{border-color:#8c5a00;background:#fffbf0}} .diagram-box.context{{border-color:#7846a7;background:#fbf7ff}} .arrow{{font-size:.77rem;color:var(--muted);text-align:center}} details{{border:1px solid var(--line);border-radius:6px;margin:.55rem 0;padding:.7rem 1rem;max-width:1000px}} summary{{cursor:pointer;font-weight:700;color:var(--navy)}} .back{{display:inline-block;margin-top:1.3rem;font-size:.85rem}} footer{{padding:2rem clamp(1rem,5vw,5rem);background:var(--navy);color:#d9e7f2;font-size:.85rem}} footer a{{color:#fff}}
@media(max-width:900px){{.layout{{display:block}} aside{{position:relative;height:auto}} nav{{columns:2}} .hero{{padding-top:2.5rem}} .section{{padding-top:2.3rem;padding-bottom:2.3rem}}}} @media print{{aside,.search,.skip,.back{{display:none!important}}.layout{{display:block}}.hero{{padding:1rem 0;border:0}}.section{{padding:1rem 0;break-inside:auto}}details{{break-inside:avoid}}pre{{white-space:pre-wrap}}a{{color:#000;text-decoration:none}}}}
</style></head><body><a class="skip" href="#main">Skip to content</a><div class="layout"><aside><h2>Ancestry MMM</h2><p>Data Upload Guide</p><input class="search" id="guideSearch" type="search" placeholder="Filter sections" aria-label="Filter guide sections"><nav id="toc"><a href="#top">Overview</a><a href="#workflow">Upload workflow</a><a href="#outcomes">1. Outcomes</a><a href="#activity">2. Activity and Media</a><a href="#context">3. Context</a><a href="#advanced">Advanced boundaries</a><a href="#faq">FAQ</a><a href="#glossary">Glossary</a><a href="#review">Source and review</a></nav></aside><main id="main"><header class="hero" id="top"><span class="badge">Version 2 · source-pack contract</span><h1>Ancestry MMM data upload guide</h1><p>This guide helps a first-time analyst prepare data that the application can understand and review. It explains what each table means, how dictionaries connect to raw data, and what the tool does when information is missing.</p><div class="callout"><b>Most important:</b> upload the meaning with the data. A successful file upload does not mean the measure is approved for modelling, reporting, planning, or optimisation.</div>{relationship}</header>{workflow}{outcomes}{activity}{context}{advanced}<section id="faq" class="section"><p class="eyebrow">Questions analysts ask</p><h2>FAQ</h2><p>Use the links in the answers to jump to the longer explanation. If a business definition is not approved, stop and raise it rather than guessing.</p>{faq_html}</section><section id="glossary" class="section"><p class="eyebrow">Quick reference</p><h2>Glossary</h2>{glossary}</section><section id="review" class="section"><p class="eyebrow">Traceability</p><h2>Source and review</h2><p>This guide was built from the current repository contracts, not from an old guide. The exact files, requirement IDs, parser checks, and review results are recorded in <code>Ancestry_MMM_Data_Upload_Guide_REVIEW.md</code>.</p><p>Primary implementation references include <code>ancestry_mmm/data/templates.py</code>, <code>loader.py</code>, <code>source_pack_adoption.py</code>, <code>source_inventory.py</code>, the Data Upload page, and the upload/template tests. Approved requirement IDs include REQ-DATAIN-001, REQ-COVERAGE-001, REQ-ACTIVITY-001, REQ-OUT-001/002/003, REQ-NBT-001/002/003/004, REQ-SEARCH-001/002/004/005, REQ-SEO-001, REQ-EVENT-001, REQ-EXPMODE-001, REQ-CALIB-001, REQ-ECON-002/003, REQ-FUTURE-001, and REQ-FX-001–006. The UK production NBT boundary is recorded in <code>docs/uk_production_onboarding_runbook.md</code>.</p><a class="back" href="#top">↑ Back to top</a></section></main></div><footer><p><b>Internal analyst guide.</b> No external libraries, fonts, images, or network calls are required. Print this page or open it locally in a browser.</p></footer><script>(function(){{const input=document.getElementById('guideSearch');const links=[...document.querySelectorAll('#toc a')];const sections=[...document.querySelectorAll('main .section, main .hero')];input.addEventListener('input',function(){{const q=input.value.toLowerCase().trim();sections.forEach(s=>{{s.hidden=!!q&&!s.innerText.toLowerCase().includes(q)}});links.forEach(a=>{{const id=a.getAttribute('href').slice(1),s=document.getElementById(id);a.hidden=!!q&&(!s||s.hidden)}})}})}})();</script></body></html>"""


def clean_token_formula(cell_ref: str) -> str:
    """Replace common separators using long-standing Excel functions."""
    raw = f"LOWER(TRIM({cell_ref}))"
    expression = raw
    replacements = [
        " ", "!", "#", "$", "%", "&", "'", "(", ")", "*", "+", ",",
        "-", ".", "/", ":", ";", "<", "=", ">", "?", "@", "[", "\\",
        "]", "^", "`", "{", "|", "}", "~",
    ]
    for character in replacements:
        expression = f'SUBSTITUTE({expression},"{character}","_")'
    for character in (chr(0x2013), chr(0x2014), chr(0x2019), chr(0x201c), chr(0x201d)):
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


def add_hidden_token_columns(ws, input_columns: list[str], rows: range, start_col: int = 12) -> list[str]:
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
            ws.cell(row, start_col + offset * 3).value = f'={clean_token_formula(f"{input_col}{row}")}'
            ws.cell(row, start_col + offset * 3 + 1).value = collapse_token_formula(f"{clean_col}{row}")
            ws.cell(row, start_col + offset * 3 + 2).value = trim_token_formula(f"{collapsed_col}{row}")
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


def add_rag_reference(wb: Workbook, rows: list[dict[str, str]], id_fields: dict[str, str]) -> None:
    ws = wb.create_sheet("Reference")
    ws.append(["Dictionary field", "Meaning", "RAG status", "Enter/select value", "Used in suggested ID?", "Why or not part of ID", "Column must exist?", "Value must be filled in?", "Allowed values / format", "Can be blank when..."])
    for row in rows:
        field = row["Field name"]
        use = id_fields.get(field, "no")
        why = id_fields.get(f"{field}__why", "Dictionary meaning, not stable identity")
        ws.append([field, row["Plain-English meaning"], row["Status"], "", use, why, row["Column must exist?"], row["Value must be filled in?"], row["Allowed values / format"], row["Can be blank when..."]])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:J{ws.max_row}"
    ws.sheet_view.showGridLines = False
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="12304A")
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for col, width in {"A":28,"B":42,"C":25,"D":28,"E":23,"F":48,"G":18,"H":25,"I":48,"J":40}.items():
        ws.column_dimensions[col].width = width
    for i in range(2, ws.max_row + 1):
        status = str(ws.cell(i, 3).value)
        ws.cell(i, 3).fill = PatternFill("solid", fgColor="FCE4E4" if status.startswith("RED") else "FFF1CC" if status.startswith("AMBER") else "E3F4E6")
        for c in range(1, 11):
            ws.cell(i, c).alignment = Alignment(wrap_text=True, vertical="top")
    notes = wb.create_sheet("Read me")
    notes["A1"] = "How to use this builder"
    notes["A1"].font = Font(size=16, bold=True, color="12304A")
    notes["A3"] = "1. Complete the editable cells in the Candidate rows sheet."
    notes["A4"] = "2. Use the suggested ID first. It is based on meaningful identity fields, not every dictionary field."
    notes["A5"] = "3. If the warning says collision, add the next meaningful AMBER identity field. Do not add a random number."
    notes["A6"] = "4. Use Manual override ID only when the governed ID already exists. Final ID uses the override when present."
    notes["A7"] = "5. Excel calculates formulas when the file opens. No VBA is used. The formulas use broadly compatible Excel text and conditional functions."
    notes["A9"] = "Important: an ID is not a business definition. Keep the dictionary fields complete even when a field is not part of the ID."
    notes.column_dimensions["A"].width = 120
    for row in range(3, 10):
        notes[f"A{row}"].alignment = Alignment(wrap_text=True, vertical="top")
    notes.sheet_view.showGridLines = False


def add_candidate_table(ws, headers: list[str], rows: list[list[object]], tab_name: str = "Candidates") -> None:
    while ws.max_row < 6:
        ws.cell(ws.max_row + 1, 1).value = ""
    ws.append(headers)
    for row in rows:
        ws.append(row)
    end_col = chr(64 + len(headers))
    ref = f"A7:{end_col}{ws.max_row}"
    tab = Table(displayName=tab_name, ref=ref)
    tab.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True, showColumnStripes=False)
    ws.add_table(tab)
    for cell in ws[7]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="12304A")
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A8"


def add_dropdown(ws, cell_range: str, values: list[str], title: str) -> None:
    dv = DataValidation(type="list", formula1='"' + ",".join(values) + '"', allow_blank=True)
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


def build_outcome_workbook(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "ID Builder"
    set_title(ws, "Outcome ID Builder", "Formula-driven, no VBA · v2 outcome dictionary companion", "Enter one candidate definition per row. The ID is an identity aid; the dictionary remains the source of meaning.")
    headers = ["product", "metric_key", "segment_dimension", "segment", "outcome_id (existing)", "Manual override ID", "Suggested ID", "Final ID", "Collision / completeness warning", "Dictionary row preview"]
    rows = [
        ["Family History", "fh_gsa", "fh_customer_segment", "New", "", "", "", "", "", ""],
        ["Family History", "fh_gsa", "fh_customer_segment", "DNA_CrossSell", "", "", "", "", "", ""],
        ["Family History", "fh_gsa", "fh_customer_segment", "Winback", "", "", "", "", "", ""],
        ["DNA", "dna_kit_sale", "dna_customer_relationship", "New Customer", "", "", "", "", "", ""],
        ["DNA", "dna_kit_sale", "dna_customer_relationship", "Existing FH Customer", "", "", "", "", ""],
        ["", "", "", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", "", "", ""],
    ]
    add_candidate_table(ws, headers, rows, "OutcomeCandidates")
    token_columns = add_hidden_token_columns(ws, ["A", "B", "D"], range(8, 8 + len(rows)))
    for r in range(8, 8 + len(rows)):
        ws.cell(r, 7).value = join_token_columns(token_columns, r)
        ws.cell(r, 8).value = f'=IF(TRIM(F{r})<>F{r},TRIM(F{r}),IF(TRIM(F{r})<>"",F{r},G{r}))'
        ws.cell(r, 9).value = f'=IF(H{r}="","RED: complete product, metric_key, and segment before finalising",IF(COUNTIF($H$8:$H$25,H{r})>1,"AMBER: duplicate final ID — add a meaningful identity distinction",IF(E{r}<>"",IF(E{r}<>H{r},"AMBER: existing ID differs from built ID — review dictionary lineage","OK: existing ID matches"),"OK: unique in this builder")))'
        ws.cell(r, 10).value = f'=IF(H{r}="","", "outcome_id="&H{r}&" | product="&A{r}&" | metric_key="&B{r}&" | segment_dimension="&C{r}&" | segment="&D{r})'
    common_candidate_style(ws, {"A":20,"B":22,"C":26,"D":24,"E":25,"F":24,"G":30,"H":30,"I":55,"J":105})
    add_dropdown(ws, "A8:A25", ["Family History", "DNA"], "Product")
    add_dropdown(ws, "B8:B25", ["fh_gsa", "fh_signup", "fh_net_billthrough_count", "fh_net_billthrough_rate", "dna_kit_sale", "custom"], "Metric key")
    add_dropdown(ws, "C8:C25", ["fh_customer_segment", "dna_customer_relationship", "dna_purchase_recipient", "combined", "custom", "unspecified"], "Segment dimension")
    for cell in ws["I"][7:]:
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.conditional_formatting.add("I8:I25", FormulaRule(formula=['ISNUMBER(SEARCH("RED",I8))'], fill=PatternFill("solid", fgColor="FCE4E4")))
    ws.conditional_formatting.add("I8:I25", FormulaRule(formula=['ISNUMBER(SEARCH("AMBER",I8))'], fill=PatternFill("solid", fgColor="FFF1CC")))
    ws.conditional_formatting.add("I8:I25", FormulaRule(formula=['LEFT(I8,2)="OK"'], fill=PatternFill("solid", fgColor="E3F4E6")))
    add_rag_reference(wb, OUTCOME_RAG, {"product": "yes", "metric_key": "yes", "segment_dimension": "only if needed", "segment": "yes", "product__why": "Defines a stable product axis.", "metric_key__why": "Defines the metric identity.", "segment_dimension__why": "Use when the same segment value can mean different things.", "segment__why": "Defines the segment identity."})
    ex = wb.create_sheet("Examples")
    ex.append(["Example", "Outcome identity", "Why"])
    ex.append(["Good", "fh_gsa_new", "Stable product + metric + segment identity; meaning is still in the dictionary."])
    ex.append(["Good", "dna_kit_sale_new_customer", "DNA relationship partition is explicit when source supports it."])
    ex.append(["Invalid", "gsa", "Too little identity; product and segment collide."])
    ex.append(["Invalid", "fh_gsa_2026_01_05_uk", "Time and market are row/source scope, not a new outcome definition."])
    ex.append(["Review", "fh_gsa_dna_cross_sell", "Use the approved project spelling/lineage; do not infer from a friendly label."])
    ex.column_dimensions["A"].width = 16
    ex.column_dimensions["B"].width = 38
    ex.column_dimensions["C"].width = 95
    for c in ex[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="12304A")
    ex.sheet_view.showGridLines = False
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    wb.save(path)


def build_activity_workbook(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "ID Builder"
    set_title(ws, "Activity ID Builder", "Formula-driven, no VBA · progressive collision checks", "Use the smallest stable identity that distinguishes an activity. Keep measures, units, and descriptive fields in the dictionary.")
    headers = ["channel", "platform", "campaign_type", "search_platform", "search_intent_group_id", "activity_id (existing)", "Manual override ID", "Suggested ID", "Final ID", "Collision / completeness warning", "Dictionary row preview"]
    rows = [
        ["Paid Search", "Google", "Brand", "google", "brand_search", "", "", "", "", "", ""],
        ["Paid Search", "Bing", "Brand", "bing", "brand_search", "", "", "", "", "", ""],
        ["Paid Search", "Google", "Non-Brand", "google", "non_brand_search", "", "", "", "", "", ""],
        ["Paid Search", "Bing", "Non-Brand", "bing", "non_brand_search", "", "", "", "", "", ""],
        ["TV", "Example broadcaster", "Brand", "", "", "", "", "", "", "", ""],
        ["SEO", "Google Search Console", "Visibility", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", "", "", "", ""],
    ]
    add_candidate_table(ws, headers, rows, "ActivityCandidates")
    token_columns = add_hidden_token_columns(ws, ["A", "B", "C", "D", "E"], range(8, 8 + len(rows)))
    for r in range(8, 8 + len(rows)):
        ws.cell(r, 8).value = join_token_columns(token_columns, r)
        ws.cell(r, 9).value = f'=IF(TRIM(G{r})<>G{r},TRIM(G{r}),IF(TRIM(G{r})<>"",G{r},H{r}))'
        ws.cell(r, 10).value = f'=IF(I{r}="","RED: complete channel and a meaningful activity distinction",IF(COUNTIF($I$8:$I$25,I{r})>1,"AMBER: duplicate final ID — add the next meaningful field; do not add a random number",IF(F{r}<>"",IF(F{r}<>I{r},"AMBER: existing ID differs from built ID — review lineage","OK: existing ID matches"),"OK: unique in this builder")))'
        ws.cell(r, 11).value = f'=IF(I{r}="","", "activity_id="&I{r}&" | channel="&A{r}&" | platform="&B{r}&" | campaign_type="&C{r}&" | search_platform="&D{r}&" | search_intent_group_id="&E{r})'
    common_candidate_style(ws, {"A":20,"B":25,"C":20,"D":20,"E":26,"F":29,"G":24,"H":32,"I":32,"J":65,"K":125})
    add_dropdown(ws, "D8:D25", ["google", "bing"], "Search platform")
    add_dropdown(ws, "E8:E25", ["brand_search", "non_brand_search"], "Search intent group")
    ws.conditional_formatting.add("J8:J25", FormulaRule(formula=['ISNUMBER(SEARCH("RED",J8))'], fill=PatternFill("solid", fgColor="FCE4E4")))
    ws.conditional_formatting.add("J8:J25", FormulaRule(formula=['ISNUMBER(SEARCH("AMBER",J8))'], fill=PatternFill("solid", fgColor="FFF1CC")))
    ws.conditional_formatting.add("J8:J25", FormulaRule(formula=['LEFT(J8,2)="OK"'], fill=PatternFill("solid", fgColor="E3F4E6")))
    add_rag_reference(wb, ACTIVITY_RAG, {"channel": "yes", "platform": "only if needed", "campaign_type": "only if needed", "search_platform": "only if needed", "search_intent_group_id": "only if needed", "channel__why": "Starts the stable activity identity.", "platform__why": "Distinguishes platforms when channel alone collides.", "campaign_type__why": "Adds the next meaningful distinction when needed.", "search_platform__why": "Separates Google and Bing Search leaves.", "search_intent_group_id__why": "Separates Brand and Non-Brand Search leaves."})
    ex = wb.create_sheet("Examples")
    ex.append(["Check", "Good", "Invalid / risky", "Reason"])
    ex.append(["Raw vs model-ready", "model_input_measure=spend; model_input_column=uk_paid_search_google_brand", "model_input_measure=uk_paid_search_google_brand", "The first is a raw source header; the second is a destination."])
    ex.append(["Search leaves", "Google Brand, Bing Brand, Google Non-Brand, Bing Non-Brand", "One generic Brand Search activity", "Parent totals are calculated from explicit leaves."])
    ex.append(["Identity", "paid_search_google_brand", "paid_search_2026_01_05_uk_12345", "Do not encode time or random numbers into stable identity."])
    ex.append(["Capacity", "paid_search_cap as separate governed cap", "cap copied into spend", "A cap is a constraint, not realised spend."])
    ex.append(["Measures", "spend + clicks + impressions retained; one selected input", "all measures silently summed", "Raw measures have different meanings and units."])
    ex.column_dimensions["A"].width = 22
    ex.column_dimensions["B"].width = 52
    ex.column_dimensions["C"].width = 52
    ex.column_dimensions["D"].width = 72
    for c in ex[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="12304A")
    ex.sheet_view.showGridLines = False
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    wb.save(path)


def build_context_workbook(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "ID Builder"
    set_title(ws, "Context Variable ID Builder", "Formula-driven, no VBA · stable variable identity", "Build a stable variable ID from meaning. Do not encode source, frequency, unit, or effective dates unless they represent a genuinely different variable.")
    headers = ["variable_class", "variable name / concept", "variable_id (existing)", "Manual override ID", "Suggested ID", "Final ID", "Collision / completeness warning", "Dictionary row preview"]
    rows = [["rate_index", "UK CPI", "", "", "", "", "", ""], ["flow_count", "UK unemployment claims", "", "", "", "", ""], ["stock_level", "UK active subscribers", "", "", "", "", ""], ["survey_measurement", "Brand consideration", "", "", "", "", ""], ["event_flag", "Black Friday", "", "", "", "", ""], ["", "", "", "", "", "", ""], ["", "", "", "", "", "", ""], ["", "", "", "", "", "", ""]]
    add_candidate_table(ws, headers, rows, "ContextCandidates")
    token_columns = add_hidden_token_columns(ws, ["A", "B"], range(8, 8 + len(rows)))
    for r in range(8, 8 + len(rows)):
        ws.cell(r, 5).value = join_token_columns(token_columns, r)
        ws.cell(r, 6).value = f'=IF(TRIM(D{r})<>D{r},TRIM(D{r}),IF(TRIM(D{r})<>"",D{r},E{r}))'
        ws.cell(r, 7).value = f'=IF(F{r}="","RED: complete variable class and concept",IF(COUNTIF($F$8:$F$25,F{r})>1,"AMBER: duplicate final ID — distinguish the actual variable, not its source frequency",IF(C{r}<>"",IF(C{r}<>F{r},"AMBER: existing ID differs from built ID — review lineage","OK: existing ID matches"),"OK: unique in this builder")))'
        ws.cell(r, 8).value = f'=IF(F{r}="","", "variable_id="&F{r}&" | variable_class="&A{r}&" | concept="&B{r})'
    common_candidate_style(ws, {"A":24,"B":34,"C":27,"D":24,"E":32,"F":32,"G":70,"H":110})
    add_dropdown(ws, "A8:A25", ["flow_count", "stock_level", "rate_index", "survey_measurement", "event_flag"], "Variable class")
    ws.conditional_formatting.add("G8:G25", FormulaRule(formula=['ISNUMBER(SEARCH("RED",G8))'], fill=PatternFill("solid", fgColor="FCE4E4")))
    ws.conditional_formatting.add("G8:G25", FormulaRule(formula=['ISNUMBER(SEARCH("AMBER",G8))'], fill=PatternFill("solid", fgColor="FFF1CC")))
    ws.conditional_formatting.add("G8:G25", FormulaRule(formula=['LEFT(G8,2)="OK"'], fill=PatternFill("solid", fgColor="E3F4E6")))
    add_rag_reference(wb, CONTEXT_RAG, {"variable_class": "yes", "variable_id": "yes", "variable_class__why": "Keeps different kinds of variable separate.", "variable_id__why": "Stable identity used by the source dictionary and observations."})
    ex = wb.create_sheet("Examples")
    ex.append(["Check", "Good", "Invalid / risky", "Reason"])
    ex.append(["Stable ID", "rate_index_uk_cpi", "rate_index_uk_cpi_monthly_gbp_2026", "Frequency, unit, and dates belong in the dictionary unless they change the variable itself."])
    ex.append(["Frequency", "native_frequency=monthly", "monthly value copied to weekly rows", "Preserve source frequency and align later by a governed method."])
    ex.append(["Missingness", "unavailable_source", "unavailable changed to 0", "Missingness is not observed zero."])
    ex.append(["Role", "CPI = exogenous_forecastable_control", "branded-search demand = exogenous control", "An endogenous mediator must be model-generated."])
    ex.append(["Event", "event_id + factual dates", "event flag inferred from a campaign name", "Named-event treatment is a separate governed path."])
    ex.column_dimensions["A"].width = 22
    ex.column_dimensions["B"].width = 52
    ex.column_dimensions["C"].width = 52
    ex.column_dimensions["D"].width = 80
    for c in ex[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="12304A")
    ex.sheet_view.showGridLines = False
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
    (DOCS / "data_upload_guide_schema_inventory.md").write_text(build_inventory(), encoding="utf-8")
    (DOCS / "Ancestry_MMM_Data_Upload_Guide.html").write_text(build_html(), encoding="utf-8")
    build_outcome_workbook(DOCS / "Ancestry_MMM_Outcome_ID_Builder.xlsx")
    build_activity_workbook(DOCS / "Ancestry_MMM_Activity_ID_Builder.xlsx")
    build_context_workbook(DOCS / "Ancestry_MMM_Context_Variable_ID_Builder.xlsx")
    print("generated guide, inventory, and three ID builders")


if __name__ == "__main__":
    main()
