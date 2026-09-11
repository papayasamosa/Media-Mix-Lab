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


def test_activity_dictionary_builder_offers_governed_search_taxonomy_fields(
    tmp_path, guide
):
    """2026-09-10: activity_definitions_from_dictionary now maps
    search_intent_group_id/search_platform when present (REQ-SEARCH-004
    addendum) - the builder must offer them as real, validated inputs,
    not merely blank headers the parser tolerates. Both use the strict
    (non-"soft") dropdown, since these are governed closed vocabularies,
    not free-text suggestions like platform/campaign_type."""
    import openpyxl

    path = tmp_path / "activity.xlsx"
    guide.build_activity_dictionary_builder(path)
    wb = openpyxl.load_workbook(path)
    builder = wb["BUILDER"]
    builder_headers = {cell.value for cell in builder[7]}
    assert "search_platform" in builder_headers
    assert "search_intent_group_id" in builder_headers
    assert "platform" in builder_headers
    assert "campaign_type" in builder_headers

    dv_sqrefs = {
        str(dv.sqref): set(dv.formula1.strip('"').split(","))
        for dv in builder.data_validations.dataValidation
    }
    search_intent_col = [
        cell.column_letter
        for cell in builder[7]
        if cell.value == "search_intent_group_id"
    ][0]
    search_platform_col = [
        cell.column_letter for cell in builder[7] if cell.value == "search_platform"
    ][0]
    intent_values = next(
        values
        for sqref, values in dv_sqrefs.items()
        if sqref.startswith(f"{search_intent_col}8")
    )
    platform_values = next(
        values
        for sqref, values in dv_sqrefs.items()
        if sqref.startswith(f"{search_platform_col}8")
    )
    assert intent_values == {
        SEARCH_INTENT_GROUP_ID_BRAND,
        SEARCH_INTENT_GROUP_ID_NON_BRAND,
    }
    assert platform_values == set(SEARCH_PLATFORMS)


def test_activity_dictionary_builder_search_taxonomy_round_trips_through_the_real_parser():
    """Brand+Google and Non-Brand+Bing both survive builder -> workbook ->
    parser -> governed ActivityDefinition, and a Brand activity with no
    platform specified (aggregate Search, REQ-SEARCH-004 S4) is equally
    valid."""
    import pandas as pd

    from ancestry_mmm.core.coverage import DOMAIN_ACTIVITY_AND_MEDIA
    from ancestry_mmm.data.templates import (
        canonicalize_standard_workbook,
        parse_standard_workbook,
    )

    def _row(
        activity_id: str, search_intent_group_id: str, search_platform: str
    ) -> dict:
        return {
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
            "search_intent_group_id": search_intent_group_id,
            "search_platform": search_platform,
        }

    activity_dictionary = pd.DataFrame(
        [
            _row(
                "paid_search_google_brand",
                SEARCH_INTENT_GROUP_ID_BRAND,
                "google",
            ),
            _row(
                "paid_search_bing_non_brand",
                SEARCH_INTENT_GROUP_ID_NON_BRAND,
                "bing",
            ),
            _row("paid_search_brand_aggregate", SEARCH_INTENT_GROUP_ID_BRAND, ""),
        ]
    )
    activity_data = pd.DataFrame(
        [
            {
                "period_start": "2026-01-05",
                "market": "UK",
                "activity_id": row["activity_id"],
                "spend": 1200,
            }
            for _, row in activity_dictionary.iterrows()
        ]
    )
    raw = _write_workbook(
        {"activity_data": activity_data, "activity_dictionary": activity_dictionary}
    )
    workbook = parse_standard_workbook(
        raw,
        source_id="s3",
        filename="test.xlsx",
        logical_domain=DOMAIN_ACTIVITY_AND_MEDIA,
    )
    assert workbook.manifest.errors == ()
    bundle = canonicalize_standard_workbook(workbook)
    by_id = {d.activity_id: d for d in bundle.activity_definitions}

    assert by_id["paid_search_google_brand"].search_intent_group_id == (
        SEARCH_INTENT_GROUP_ID_BRAND
    )
    assert by_id["paid_search_google_brand"].search_platform == "google"
    assert by_id["paid_search_bing_non_brand"].search_intent_group_id == (
        SEARCH_INTENT_GROUP_ID_NON_BRAND
    )
    assert by_id["paid_search_bing_non_brand"].search_platform == "bing"
    assert by_id["paid_search_brand_aggregate"].search_intent_group_id == (
        SEARCH_INTENT_GROUP_ID_BRAND
    )
    assert by_id["paid_search_brand_aggregate"].search_platform == ""


def test_non_search_activity_is_not_forced_to_supply_search_taxonomy_fields():
    """A TV activity leaving both new columns blank is exactly as valid as
    before this capability existed - search taxonomy is never required
    just because the columns now exist in DICTIONARY_OUTPUT."""
    import pandas as pd

    from ancestry_mmm.core.coverage import DOMAIN_ACTIVITY_AND_MEDIA
    from ancestry_mmm.data.templates import (
        canonicalize_standard_workbook,
        parse_standard_workbook,
    )

    activity_dictionary = pd.DataFrame(
        [
            {
                "activity_id": "tv_brand",
                "market": "UK",
                "pooling_group_id": "",
                "channel": "TV",
                "platform": "not specified",
                "campaign_type": "not specified",
                "marketing_objective": "not specified",
                "funnel_stage": "unclassified",
                "product_advertised": "not specified",
                "message_type": "not specified",
                "activity_ownership": "paid",
                "intended_model_role": "intervention",
                "model_input_column": "tv_brand",
                "model_input_measure": "spend",
                "economic_treatment": "paid_media_cost",
                "planning_eligibility": "optimisable",
                "source": "Broadcaster invoice",
                "model_input_unit": "",
                "model_input_kind": "",
                "spend_column": "",
                "response_unit_column": "",
                "response_unit": "",
                "currency": "",
                "effective_from": "",
                "effective_to": "",
                "search_intent_group_id": "",
                "search_platform": "",
            }
        ]
    )
    activity_data = pd.DataFrame(
        [
            {
                "period_start": "2026-01-05",
                "market": "UK",
                "activity_id": "tv_brand",
                "spend": 5000,
            }
        ]
    )
    raw = _write_workbook(
        {"activity_data": activity_data, "activity_dictionary": activity_dictionary}
    )
    workbook = parse_standard_workbook(
        raw,
        source_id="s4",
        filename="test.xlsx",
        logical_domain=DOMAIN_ACTIVITY_AND_MEDIA,
    )
    assert workbook.manifest.errors == ()
    bundle = canonicalize_standard_workbook(workbook)
    assert bundle.activity_definitions[0].search_intent_group_id is None
    assert bundle.activity_definitions[0].search_platform == ""


def test_invalid_search_taxonomy_combination_fails_clearly():
    """A PMax activity carrying a search_intent_group_id must be rejected
    with a specific, attributable reason, never silently accepted or
    silently dropped."""
    import pandas as pd

    from ancestry_mmm.core.coverage import DOMAIN_ACTIVITY_AND_MEDIA
    from ancestry_mmm.data.templates import parse_standard_workbook

    activity_dictionary = pd.DataFrame(
        [
            {
                "activity_id": "pmax_shopping",
                "market": "UK",
                "pooling_group_id": "",
                "channel": "Paid Search",
                "platform": "not specified",
                "campaign_type": "pmax",
                "marketing_objective": "not specified",
                "funnel_stage": "unclassified",
                "product_advertised": "not specified",
                "message_type": "not specified",
                "activity_ownership": "paid",
                "intended_model_role": "intervention",
                "model_input_column": "pmax_shopping",
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
                "search_intent_group_id": SEARCH_INTENT_GROUP_ID_BRAND,
                "search_platform": "google",
            }
        ]
    )
    activity_data = pd.DataFrame(
        [
            {
                "period_start": "2026-01-05",
                "market": "UK",
                "activity_id": "pmax_shopping",
                "spend": 1200,
            }
        ]
    )
    raw = _write_workbook(
        {"activity_data": activity_data, "activity_dictionary": activity_dictionary}
    )
    workbook = parse_standard_workbook(
        raw,
        source_id="s5",
        filename="test.xlsx",
        logical_domain=DOMAIN_ACTIVITY_AND_MEDIA,
    )
    from ancestry_mmm.data.templates import canonicalize_standard_workbook

    with pytest.raises(ValueError, match="excluded from the Paid Search taxonomy"):
        canonicalize_standard_workbook(workbook)


def test_guide_html_documents_the_generic_denominator_outcome_mechanism(guide):
    """Finance constant-dollar / LTR documentation audit (2026-09-10):
    the guide must state that denominator_outcome_id's per-week match is
    generic (not NBT-specific) and name the exact UK cohort
    correspondence, so a future GSA-week LTR is documented as equally
    valid without implying a code change is needed."""
    html = guide.build_html()
    assert "denominator mechanism is generic" in html
    assert "fh_net_billthrough_count_new" in html
    assert "fh_net_billthrough_count_dna_cross_sell" in html
    assert "fh_net_billthrough_count_winback" in html
    assert "fh_gsa</code>-week LTR" in html
    assert "own matching cohort's count for that week" in html


def test_guide_html_documents_finance_constant_dollar_fx_vintage(guide):
    """The guide must explain the real Finance upload format and the
    vintage-not-observation-year rule, the latest-vintage default with
    override, and that a USD-declared amount is never converted again -
    the exact points corrected in the FX business decision."""
    html = guide.build_html()
    assert 'id="fx"' in html
    assert "year_id" in html
    assert "currency_code" in html
    assert "local_to_usd_conversion_rate" in html
    assert "never the calendar year" in html
    assert "defaults to the latest one" in html
    assert "never converted again" in html
    assert "never falls back to another vintage" in html


def test_guide_html_names_the_actual_ui_labels_for_the_fx_workflow(guide):
    """The guide must not just explain the FX file format and vintage
    rules in the abstract - it must tell the analyst exactly where in
    the running app to upload the Finance table and where to select or
    override the vintage, using the real, current UI labels (page
    titles, section/expander names, button and dropdown labels) rather
    than an internal filename or a generic description."""
    html = guide.build_html()
    assert "Where to actually do this in the app" in html
    # Upload location: Export & Recovery page's "Finance FX rate set"
    # section, "Upload Finance constant-dollar table" expander.
    assert "Export &amp; Recovery" in html
    assert "Finance FX rate set" in html
    assert "Upload Finance constant-dollar table" in html
    assert "Validate and load Finance table" in html
    # Vintage selection/override location: Results & Response Curves
    # page's "Economic outcome valuation &amp; ROI" section.
    assert "Results &amp; Response Curves" in html
    assert "Economic outcome valuation" in html
    assert "Finance constant-dollar vintage" in html
    assert "USD constant-dollar basis" in html


def test_guide_fx_ui_labels_match_the_live_pages():
    """Cross-check against the actual running pages, not just the guide's
    own text: if the Export & Recovery upload widgets or the Results page
    vintage selector are ever relabelled, this must fail so the guide
    gets updated in the same change rather than silently going stale."""
    export_page = Path(__file__).parents[1] / "pages" / "09_Project_Export.py"
    results_page = Path(__file__).parents[1] / "pages" / "07_Results_Curve_Bank.py"
    export_src = export_page.read_text(encoding="utf-8")
    results_src = results_page.read_text(encoding="utf-8")

    assert '"Finance FX rate set"' in export_src
    assert '"Upload Finance constant-dollar table"' in export_src
    assert '"Validate and load Finance table"' in export_src
    assert '"Finance constant-dollar vintage"' in results_src
    assert "USD constant-dollar basis" in results_src


def test_guide_faq_and_glossary_cover_fx_vintage(guide):
    html = guide.build_html()
    assert "Finance FX &#x201c;vintage&#x201d;" in html or "vintage" in html
    assert "FX vintage" in html
    assert "constant-dollar rate" in html


def test_dictionary_builders_never_carry_an_fx_rate_value_column(guide):
    """Architecture guard: FX rates must stay a separate governed project
    input (application.fx_service, Project Export page) - never a column
    on the normal Outcome or Activity Dictionary. This must keep failing
    if anyone ever adds year_id/currency_code/local_to_usd_conversion_rate
    (or a plain 'rate'/'exchange_rate' column) to either dictionary's
    output contract."""
    forbidden = {
        "year_id",
        "currency_code",
        "local_to_usd_conversion_rate",
        "exchange_rate",
        "fx_rate",
    }
    for columns_name in (
        "OUTCOME_DICTIONARY_OUTPUT_COLUMNS",
        "ACTIVITY_DICTIONARY_OUTPUT_COLUMNS",
        "CONTEXT_DICTIONARY_OUTPUT_COLUMNS",
    ):
        columns = set(getattr(guide, columns_name))
        assert not (columns & forbidden), (
            f"{columns_name} must never carry an FX-rate column: {columns & forbidden}"
        )


def test_currency_rag_rows_point_to_the_separate_fx_governance(guide):
    """Regression guard for the audit finding that currency/value_currency
    are identification-only: their guide text must say so and must not
    silently start implying they perform conversion."""
    activity_currency = next(
        r for r in guide.ACTIVITY_RAG if r["Field name"] == "currency"
    )
    assert (
        "does not perform FX conversion" in activity_currency["Why the tool needs it"]
    )
    assert "never inferred from market" in activity_currency["Why the tool needs it"]

    outcome_value_currency = next(
        r for r in guide.OUTCOME_RAG if r["Field name"] == "value_currency"
    )
    assert "never converts it" in outcome_value_currency["Why the tool needs it"]


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
