"""Regression guard for the data-upload guide/Excel-builder generator.

Checks that the controlled-value lists baked into
`scripts/build_data_upload_guide_assets.py` (the single source of truth for
the HTML guide, the three Excel Dictionary Builders, and the schema
inventory) stay in sync with the live governed vocabularies they are
supposed to mirror.
This does not re-validate Excel/browser behaviour -- see the Excel-COM and
Playwright evidence recorded in `Ancestry_MMM_Data_Upload_Guide_REVIEW.md`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from ancestry_mmm.core.activities import FUNNEL_STAGES, OWNERSHIP, PLANNING_ELIGIBILITY
from ancestry_mmm.core.coverage import VARIABLE_CLASSES
from ancestry_mmm.core.search_intent_taxonomy import (
    SEARCH_INTENT_GROUP_ID_BRAND,
    SEARCH_INTENT_GROUP_ID_NON_BRAND,
    SEARCH_PLATFORMS,
)
from ancestry_mmm.core.seo_visibility import SEO_GROUP_BRAND, SEO_GROUP_NON_BRAND


def _guide_module():
    path = Path(__file__).parents[2] / "scripts" / "build_data_upload_guide_assets.py"
    spec = importlib.util.spec_from_file_location(
        "build_data_upload_guide_assets", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guide():
    return _guide_module()


def test_variable_class_dropdown_matches_governed_classes(guide):
    dropdown_values = {
        "flow_count",
        "stock_level",
        "rate_index",
        "survey_measurement",
        "event_flag",
    }
    assert dropdown_values == set(VARIABLE_CLASSES)


def test_activity_ownership_rag_lists_every_governed_value(guide):
    row = next(r for r in guide.ACTIVITY_RAG if r["Field name"] == "activity_ownership")
    for value in OWNERSHIP:
        assert value in row["Allowed values / format"]


def test_planning_eligibility_rag_lists_every_governed_value(guide):
    row = next(
        r for r in guide.ACTIVITY_RAG if r["Field name"] == "planning_eligibility"
    )
    for value in PLANNING_ELIGIBILITY:
        assert value in row["Allowed values / format"]


def test_funnel_stage_rag_lists_every_governed_value(guide):
    row = next(r for r in guide.ACTIVITY_RAG if r["Field name"] == "funnel_stage")
    for value in FUNNEL_STAGES:
        assert value in row["Allowed values / format"]


def test_search_taxonomy_baseline_ids_appear_in_guide_html(guide):
    html = guide.build_html()
    assert SEARCH_INTENT_GROUP_ID_BRAND in html
    assert SEARCH_INTENT_GROUP_ID_NON_BRAND in html
    for platform in SEARCH_PLATFORMS:
        assert platform in html


def test_seo_group_constants_appear_in_guide_html(guide):
    html = guide.build_html()
    assert SEO_GROUP_BRAND in html
    assert SEO_GROUP_NON_BRAND in html
    assert "seo_group_id" in html


def test_uk_nbt_production_outcomes_named_in_guide_html(guide):
    html = guide.build_html()
    for outcome_id in (
        "fh_net_billthrough_count_new",
        "fh_net_billthrough_count_dna_cross_sell",
        "fh_net_billthrough_count_winback",
    ):
        assert outcome_id in html


def test_guide_leads_with_minimum_for_first_fit(guide):
    html = guide.build_html()
    assert "Minimum for your first" in html
    assert "Fields you must fill in" in html
    assert "Fields you may need" in html
    # The minimum-checklist callout must appear before the first domain
    # section, not buried after the schema detail.
    assert html.index("Minimum for your first") < html.index('id="outcomes"')


def test_inert_activity_dictionary_fields_are_flagged_in_guide_html(guide):
    html = guide.build_html()
    for field in (
        "model_input_unit",
        "model_input_kind",
        "spend_column",
        "response_unit_column",
        "response_unit",
    ):
        assert field in html
    assert "currently have no effect" in html


def test_generator_produces_all_expected_outputs(tmp_path, monkeypatch, guide):
    monkeypatch.setattr(guide, "DOCS", tmp_path)
    guide.main()
    assert (tmp_path / "Ancestry_MMM_Data_Upload_Guide.html").exists()
    assert (tmp_path / "Ancestry_MMM_Outcome_Dictionary_Builder.xlsx").exists()
    assert (tmp_path / "Ancestry_MMM_Activity_Dictionary_Builder.xlsx").exists()
    assert (tmp_path / "Ancestry_MMM_Context_Dictionary_Builder.xlsx").exists()
    assert (tmp_path / "data_upload_guide_schema_inventory.md").exists()
    assert not (tmp_path / "Ancestry_MMM_Outcome_ID_Builder.xlsx").exists()
    assert not (tmp_path / "Ancestry_MMM_Activity_ID_Builder.xlsx").exists()
    assert not (tmp_path / "Ancestry_MMM_Context_Variable_ID_Builder.xlsx").exists()


def test_html_recommends_dictionary_builders_not_old_id_builders(guide):
    html = guide.build_html()
    assert "Dictionary_Builder.xlsx" in html
    assert "ID_Builder.xlsx" not in html
    assert "Dictionary Builder" in html


@pytest.mark.parametrize(
    ("builder_fn", "expected_columns"),
    [
        ("build_outcome_dictionary_builder", "OUTCOME_DICTIONARY_OUTPUT_COLUMNS"),
        ("build_activity_dictionary_builder", "ACTIVITY_DICTIONARY_OUTPUT_COLUMNS"),
        ("build_context_dictionary_builder", "CONTEXT_DICTIONARY_OUTPUT_COLUMNS"),
    ],
)
def test_dictionary_builder_output_sheet_matches_live_schema_columns(
    tmp_path, guide, builder_fn, expected_columns
):
    import openpyxl

    path = tmp_path / "builder.xlsx"
    getattr(guide, builder_fn)(path)
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == [
        "START_HERE",
        "BUILDER",
        "DICTIONARY_OUTPUT",
        "ALLOWED_VALUES",
        "EXAMPLES",
    ]
    output = wb["DICTIONARY_OUTPUT"]
    headers = [cell.value for cell in output[1]]
    assert headers == getattr(guide, expected_columns)


def test_outcome_dictionary_builder_omits_confirmed_inert_fields(tmp_path, guide):
    import openpyxl

    path = tmp_path / "outcome.xlsx"
    guide.build_outcome_dictionary_builder(path)
    wb = openpyxl.load_workbook(path)
    headers = {cell.value for cell in wb["DICTIONARY_OUTPUT"][1]}
    assert "date_basis" not in headers
    assert "maturity_required" not in headers


def test_activity_dictionary_builder_never_asks_for_write_only_fields(tmp_path, guide):
    import openpyxl

    path = tmp_path / "activity.xlsx"
    guide.build_activity_dictionary_builder(path)
    wb = openpyxl.load_workbook(path)
    # The live parser requires these columns' headers to exist once other v2
    # extras are present (confirmed via parser round-trip testing), so they
    # stay in DICTIONARY_OUTPUT -- but the BUILDER sheet must never offer
    # them as something the analyst fills in.
    output_headers = [cell.value for cell in wb["DICTIONARY_OUTPUT"][1]]
    builder_headers = {cell.value for cell in wb["BUILDER"][7]}
    for field in (
        "model_input_unit",
        "model_input_kind",
        "spend_column",
        "response_unit_column",
        "response_unit",
    ):
        assert field in output_headers
        assert field not in builder_headers


def test_context_dictionary_builder_role_is_free_text_not_a_dropdown(tmp_path, guide):
    import openpyxl

    path = tmp_path / "context.xlsx"
    guide.build_context_dictionary_builder(path)
    wb = openpyxl.load_workbook(path)
    builder = wb["BUILDER"]
    role_col = [c.value for c in builder[7]].index("role") + 1
    role_cell = f"{openpyxl.utils.get_column_letter(role_col)}13"
    assert not any(
        dv.sqref.__contains__(role_cell)
        for dv in builder.data_validations.dataValidation
    )


def test_context_dictionary_builder_never_asks_for_unused_unit_field(tmp_path, guide):
    import openpyxl

    path = tmp_path / "context.xlsx"
    guide.build_context_dictionary_builder(path)
    wb = openpyxl.load_workbook(path)
    # `unit`'s header must stay in DICTIONARY_OUTPUT: the live parser requires
    # the full v2 extra-column set once source/scope are present (confirmed
    # via parser round-trip testing), even though nothing reads its value.
    assert "unit" in [cell.value for cell in wb["DICTIONARY_OUTPUT"][1]]
    assert "unit" not in {cell.value for cell in wb["BUILDER"][7]}


def _write_workbook(tables):
    from io import BytesIO

    import pandas as pd

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, table in tables.items():
            table.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()


def test_outcome_dictionary_builder_output_is_accepted_by_the_real_parser():
    """Prove Dictionary Builder -> DICTIONARY_OUTPUT -> upload -> parser ->
    accepted, using literal values equal to what BUILDER's own formulas
    compute for its first pre-filled example row (verified separately via
    Excel COM: Generated ID = Final ID = family_history_fh_gsa_new)."""
    import pandas as pd

    from ancestry_mmm.core.coverage import DOMAIN_OUTCOMES
    from ancestry_mmm.data.templates import (
        canonicalize_standard_workbook,
        parse_standard_workbook,
    )

    outcome_id = "family_history_fh_gsa_new"
    outcome_dictionary = pd.DataFrame(
        [
            {
                "outcome_id": outcome_id,
                "source_column": outcome_id,
                "product": "Family History",
                "metric_key": "fh_gsa",
                "metric": "GSA",
                "segment_dimension": "unspecified",
                "segment": "New",
                "outcome_group_id": "",
                "outcome_group_label": "",
                "outcome_family_key": "",
                "group_aggregation": "",
            }
        ]
    )
    outcomes = pd.DataFrame(
        [{"period_start": "2026-01-05", "market": "UK", outcome_id: 120}]
    )
    raw = _write_workbook(
        {"outcomes": outcomes, "outcome_dictionary": outcome_dictionary}
    )
    workbook = parse_standard_workbook(
        raw, source_id="s1", filename="test.xlsx", logical_domain=DOMAIN_OUTCOMES
    )
    assert workbook.manifest.errors == ()
    assert workbook.manifest.valid_standard_template
    bundle = canonicalize_standard_workbook(workbook)
    assert [d.outcome_id for d in bundle.outcome_definitions] == [outcome_id]


def test_activity_dictionary_builder_output_is_accepted_by_the_real_parser():
    """Same proof for Activity, including the v2 extra columns the builder
    keeps (currency/effective_from/effective_to) alongside the blank
    write-only columns the schema still requires once those are present."""
    import pandas as pd

    from ancestry_mmm.core.coverage import DOMAIN_ACTIVITY_AND_MEDIA
    from ancestry_mmm.data.templates import (
        canonicalize_standard_workbook,
        parse_standard_workbook,
    )

    activity_id = "paid_search_google_brand"
    activity_dictionary = pd.DataFrame(
        [
            {
                "activity_id": activity_id,
                "market": "UK",
                "pooling_group_id": "",
                "channel": "Paid Search",
                "platform": "not specified",
                "campaign_type": "not specified",
                "marketing_objective": "not specified",
                "funnel_stage": "unclassified",
                "product_advertised": "not specified",
                "message_type": "not specified",
                "activity_ownership": "paid",
                "intended_model_role": "intervention",
                "model_input_column": activity_id,
                "model_input_measure": "spend",
                "economic_treatment": "paid_media_cost",
                "planning_eligibility": "optimisable",
                "source": "Google Ads export",
                "model_input_unit": "",
                "model_input_kind": "",
                "spend_column": "",
                "response_unit_column": "",
                "response_unit": "",
                "currency": "",
                "effective_from": "",
                "effective_to": "",
            }
        ]
    )
    activity_data = pd.DataFrame(
        [
            {
                "period_start": "2026-01-05",
                "market": "UK",
                "activity_id": activity_id,
                "spend": 1200,
            }
        ]
    )
    raw = _write_workbook(
        {"activity_data": activity_data, "activity_dictionary": activity_dictionary}
    )
    workbook = parse_standard_workbook(
        raw,
        source_id="s2",
        filename="test.xlsx",
        logical_domain=DOMAIN_ACTIVITY_AND_MEDIA,
    )
    assert workbook.manifest.errors == ()
    assert workbook.manifest.valid_standard_template
    bundle = canonicalize_standard_workbook(workbook)
    assert [d.activity_id for d in bundle.activity_definitions] == [activity_id]


def test_context_dictionary_builder_output_is_accepted_by_the_real_parser():
    """Same proof for Context, including the blank `unit` column the schema
    still requires once source/scope (kept per the necessity review) are
    present."""
    import pandas as pd

    from ancestry_mmm.core.coverage import DOMAIN_CONTEXT_AND_EXTERNAL_FACTORS
    from ancestry_mmm.data.templates import (
        canonicalize_standard_workbook,
        parse_standard_workbook,
    )

    variable_id = "rate_index_uk_cpi"
    variable_dictionary = pd.DataFrame(
        [
            {
                "variable_id": variable_id,
                "variable_class": "rate_index",
                "native_frequency": "monthly",
                "role": "exogenous_forecastable_control",
                "source": "",
                "scope": "",
                "effective_from": "",
                "effective_to": "",
                "unit": "",
            }
        ]
    )
    context_data = pd.DataFrame(
        [
            {
                "period_start": "2026-01-01",
                "market": "UK",
                "variable_id": variable_id,
                "value": 132.4,
                "native_frequency": "monthly",
            }
        ]
    )
    raw = _write_workbook(
        {"context_data": context_data, "variable_dictionary": variable_dictionary}
    )
    workbook = parse_standard_workbook(
        raw,
        source_id="s3",
        filename="test.xlsx",
        logical_domain=DOMAIN_CONTEXT_AND_EXTERNAL_FACTORS,
    )
    assert workbook.manifest.errors == ()
    assert workbook.manifest.valid_standard_template
    bundle = canonicalize_standard_workbook(workbook)
    assert bundle.context_variable_metadata[0]["variable_id"] == variable_id


def test_outcome_rag_marks_date_basis_and_maturity_required_as_unused(guide):
    """Guards against the technical reference re-implying these fields do
    something: both are confirmed inert by the necessity review and are not
    offered by the Outcome Dictionary Builder."""
    for field in ("date_basis", "maturity_required"):
        row = next(r for r in guide.OUTCOME_RAG if r["Field name"] == field)
        assert row["Status"].startswith("GREY")
        assert "not used by any current transformation" in row["Used by"].lower()


def test_activity_rag_marks_write_only_fields_as_currently_inert(guide):
    """Guards against the technical reference implying these fields govern
    media-unit, economics, cost-mapping, or response behaviour through the
    standard upload path -- they are confirmed write-only today."""
    for field in (
        "model_input_unit",
        "model_input_kind",
        "spend_column",
        "response_unit_column",
        "response_unit",
    ):
        row = next(r for r in guide.ACTIVITY_RAG if r["Field name"] == field)
        assert row["Status"] == "GREY — Currently write-only"
        assert "not applied by the standard upload path" in row["Plain-English meaning"]


def test_activity_rag_marks_reporting_only_fields_accurately(guide):
    """Guards against the technical reference describing reporting/graph
    metadata as fit- or planning-critical."""
    for field in (
        "pooling_group_id",
        "platform",
        "marketing_objective",
        "funnel_stage",
        "product_advertised",
        "message_type",
    ):
        row = next(r for r in guide.ACTIVITY_RAG if r["Field name"] == field)
        used_by = row["Used by"].lower()
        assert "reporting" in used_by
        assert "only" in used_by


def test_context_rag_discloses_variable_class_and_native_frequency_override(guide):
    """Guards against the technical reference describing these as fully
    governed settings when Page 15 (Data Coverage) currently re-defaults
    them regardless of what is uploaded."""
    for field in ("variable_class", "native_frequency"):
        row = next(r for r in guide.CONTEXT_RAG if r["Field name"] == field)
        assert "Page 15" in row["Why the tool needs it"]


def test_context_rag_discloses_role_is_not_enforced(guide):
    """Guards against the technical reference describing role as a governed
    enum when no enforcement exists anywhere in the code today."""
    row = next(r for r in guide.CONTEXT_RAG if r["Field name"] == "role")
    assert "not currently enforced" in row["Status"]


def test_activity_dictionary_builder_never_asks_for_search_taxonomy_pseudo_fields(
    tmp_path, guide
):
    """search_platform/search_intent_group_id are not activity_dictionary
    columns today, so the builder must not ask for them as if they were
    ordinary fields -- platform/campaign_type (real columns) build the id
    instead."""
    import openpyxl

    path = tmp_path / "activity.xlsx"
    guide.build_activity_dictionary_builder(path)
    wb = openpyxl.load_workbook(path)
    builder_headers = {cell.value for cell in wb["BUILDER"][7]}
    assert "search_platform" not in builder_headers
    assert "search_intent_group_id" not in builder_headers
    assert "platform" in builder_headers
    assert "campaign_type" in builder_headers


def test_activity_dictionary_builder_id_has_exactly_three_identity_inputs(
    tmp_path, guide
):
    """channel, platform, campaign_type are the only fields the Generated ID
    formula draws on -- not the retired 5-input (incl. search_platform /
    search_intent_group_id) design. Each identity input gets exactly 3
    hidden helper columns (clean/collapsed/token); this count changing back
    to 15 would mean the 5-input design silently returned."""
    import openpyxl

    path = tmp_path / "activity.xlsx"
    guide.build_activity_dictionary_builder(path)
    wb = openpyxl.load_workbook(path)
    builder = wb["BUILDER"]
    hidden_helper_columns = [
        letter
        for letter, dim in builder.column_dimensions.items()
        if dim.hidden and dim.width == 2
    ]
    assert len(hidden_helper_columns) == 9  # 3 identity inputs x 3 helper columns
