"""Regression guard for the data-upload guide/Excel-builder generator.

Checks that the controlled-value lists baked into
`scripts/build_data_upload_guide_assets.py` (the single source of truth for
the HTML guide, the three Excel ID builders, and the schema inventory) stay
in sync with the live governed vocabularies they are supposed to mirror.
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


def test_generator_produces_all_expected_outputs(tmp_path, monkeypatch, guide):
    monkeypatch.setattr(guide, "DOCS", tmp_path)
    guide.main()
    assert (tmp_path / "Ancestry_MMM_Data_Upload_Guide.html").exists()
    assert (tmp_path / "Ancestry_MMM_Outcome_ID_Builder.xlsx").exists()
    assert (tmp_path / "Ancestry_MMM_Activity_ID_Builder.xlsx").exists()
    assert (tmp_path / "Ancestry_MMM_Context_Variable_ID_Builder.xlsx").exists()
    assert (tmp_path / "data_upload_guide_schema_inventory.md").exists()
