"""The structure page must communicate supplied, not reconstructed, NBT."""

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from ancestry_mmm.core.net_billthrough import NBT_METRIC_KEY
from ancestry_mmm.core.outcomes import FAMILY_HISTORY

st.page_link = lambda *a, **k: None

ROOT = Path(__file__).parent.parent
PAGE = ROOT / "pages" / "03_Structure_Segments_Markets.py"


def test_structure_page_uses_authoritative_uploaded_nbt():
    source = Path("ancestry_mmm/pages/03_Structure_Segments_Markets.py").read_text()
    assert "authoritative weekly count" in source
    assert "NetBillthroughOfferRule" not in source


def _transformed_data() -> pd.DataFrame:
    n = 20
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-06", periods=n, freq="W"),
            "market": ["UK"] * n,
            "New": rng.poisson(50, n).astype(float),
        }
    )


def _seed_nbt_session_state(at: AppTest, **net_billthrough_overrides) -> None:
    at.session_state["transformed_data"] = _transformed_data()
    at.session_state["date_col"] = "date"
    at.session_state["market_col"] = "market"
    at.session_state["outcome_definitions"] = [
        {
            "outcome_id": "fh_net_billthrough_count_new",
            "product": FAMILY_HISTORY,
            "segment": "New",
            "metric": "Net bill-through count",
            "metric_key": NBT_METRIC_KEY,
            "source_column": "New",
            "unit": "bill-through subscriber",
        },
    ]
    if net_billthrough_overrides:
        at.session_state["net_billthrough_metadata"] = net_billthrough_overrides


class TestNBTMaturityWindowUI:
    """UK FH MMM brief (2026-09-10) follow-up: `maturity_window_days`
    (REQ-NBT-005) existed on `NetBillthroughCompletenessMetadata` with no
    UI control to actually set it - closing that gap end to end through
    the real page."""

    def test_nbt_section_renders_with_maturity_window_field(self):
        at = AppTest.from_file(str(PAGE), default_timeout=60)
        _seed_nbt_session_state(at)
        at.run()
        assert not at.exception

        labels = [n.label for n in at.number_input]
        assert any("Official maturity readiness window" in label for label in labels)

    def test_setting_the_maturity_window_updates_the_live_readiness_readout(self):
        """Interacts with the real widget (rather than requiring the
        unrelated "at least one media channel" save-validation gate to
        pass first) - proves the number_input's value actually drives
        assess_official_maturity_readiness's live readout, not just that
        the widget renders."""
        at = AppTest.from_file(str(PAGE), default_timeout=60)
        _seed_nbt_session_state(
            at,
            data_as_of_date="2026-08-20",
            latest_complete_net_billthrough_week="2026-07-13",
            model_start_week="2026-01-05",
            model_end_week="2026-07-13",
            maturity_rule_description="Mature after 30 days",
            source_owner="Finance",
        )
        at.run()
        assert not at.exception
        # No maturity_window_days configured yet - "not assessed", not mature/not-mature.
        assert any(
            "Official readiness" in c.value and "is configured" in c.value
            for c in at.caption
        )

        maturity_input = [
            n
            for n in at.number_input
            if "Official maturity readiness window" in n.label
        ][0]
        maturity_input.set_value(60).run()
        assert not at.exception
        # Only 38 days have elapsed (2026-07-13 -> 2026-08-20); a 60-day
        # window is not yet met - the readout must say so, not "mature".
        warnings = [w.value for w in at.warning]
        assert any("38 day(s)" in w and "60 day(s)" in w for w in warnings)

    def test_configured_maturity_window_shows_readiness_readout(self):
        at = AppTest.from_file(str(PAGE), default_timeout=60)
        _seed_nbt_session_state(
            at,
            data_as_of_date="2026-08-20",
            latest_complete_net_billthrough_week="2026-07-13",
            model_start_week="2026-01-05",
            model_end_week="2026-07-13",
            maturity_rule_description="Mature after 30 days",
            source_owner="Finance",
            maturity_window_days=30,
        )
        at.run()
        assert not at.exception

        maturity_inputs = [
            n
            for n in at.number_input
            if "Official maturity readiness window" in n.label
        ]
        assert maturity_inputs and maturity_inputs[0].value == 30

        captions = [c.value for c in at.caption] + [s.value for s in at.success]
        assert any("Official readiness" in c for c in captions)
