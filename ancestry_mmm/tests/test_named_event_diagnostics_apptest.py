"""AppTest coverage for the Diagnostics page's "Named-event diagnostics"
expander (implementation brief: close the remaining named-event
diagnostics gap). Diagnostic only - proves the section renders the
governed per-`event_family_id x market` table against a real fitted
model's frame, using the same fixture pattern as
`test_diagnostics_rail_apptest.py`."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import arviz as az
import streamlit as st
from streamlit.testing.v1 import AppTest

from ancestry_mmm.core.activities import ActivityDefinition
from ancestry_mmm.core.hierarchical_model import FHModelMeta
from ancestry_mmm.core.named_event_fit_inputs import build_named_event_fit_inputs
from ancestry_mmm.core.named_event_response import NAMED_EVENT_RESPONSE_STRUCTURE
from ancestry_mmm.core.named_event_type_policy import (
    CLASSIFICATION_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED,
)
from ancestry_mmm.core.named_events import (
    DEFAULT_EVENT_EVIDENCE_STATUS,
    EventResponseDefinition,
    NamedEventFamily,
    NamedEventOccurrence,
)
from ancestry_mmm.core.pathways import resolve_pathway_masks
from ancestry_mmm.core.schema import ModelSpec

st.page_link = lambda *a, **k: None

ROOT = Path(__file__).parent.parent
PAGE = ROOT / "pages" / "06_Diagnostics.py"


def _trace_frame_meta(*, dates_start="2024-01-01", n_obs=40):
    """A minimal, single-outcome, single-market real trace/frame/meta
    triple, wide enough in `dates` to actually contain the Mother's Day
    occurrences these tests register (mirrors
    `test_diagnostics_rail_apptest.py`'s own fixture, widened)."""
    rng = np.random.default_rng(11)
    n_chain, n_draw = 2, 20
    oids = ["fh_new_gsa"]
    chs = ["TV"]

    Y = rng.uniform(5, 30, size=(n_obs, 1))
    trace = az.from_dict(
        posterior={
            "mu": np.maximum(
                Y[None, None, :, 0] + rng.normal(0, 0.5, size=(n_chain, n_draw, n_obs)),
                0.1,
            )[..., None],
            "alpha": np.full((n_chain, n_draw, 1), 8.0),
            "decay_rate": np.full((n_chain, n_draw, 1), 0.5),
            "hill_K": np.ones((n_chain, n_draw, 1)),
            "hill_S": np.full((n_chain, n_draw, 1), 4.0),
            "beta": np.ones((n_chain, n_draw, 1, 1)),
            "intercept": np.zeros((n_chain, n_draw, 1)),
            "trend_coef": np.zeros((n_chain, n_draw, 1)),
            "promo_coef": np.zeros((n_chain, n_draw, 1)),
            "market_offset": np.zeros((n_chain, n_draw, 1, 1)),
            "gamma_fourier": np.zeros((n_chain, n_draw, 4, 1)),
        },
        coords={
            "obs": list(range(n_obs)),
            "outcome": oids,
            "channel": chs,
            "market": ["UK"],
            "fourier": list(range(4)),
        },
        dims={
            "mu": ["obs", "outcome"],
            "alpha": ["outcome"],
            "decay_rate": ["channel"],
            "hill_K": ["channel"],
            "hill_S": ["channel"],
            "beta": ["outcome", "channel"],
            "intercept": ["outcome"],
            "trend_coef": ["outcome"],
            "promo_coef": ["outcome"],
            "market_offset": ["market", "outcome"],
            "gamma_fourier": ["fourier", "outcome"],
        },
        sample_stats={"diverging": np.zeros((n_chain, n_draw), dtype=bool)},
    )

    meta = FHModelMeta(
        markets=["UK"],
        outcome_ids=oids,
        channels=chs,
        dna_channels=[],
        dna_channel_idx=[],
        non_dna_idx=[0],
        dna_outcome_id=oids[0],
        dna_lag_weeks=1,
        unpooled_markets=[],
        control_names=[],
        pathway_masks=resolve_pathway_masks(
            oids,
            chs,
            [],
            dna_channel_idx=[],
            dna_outcome_id=oids[0],
            direct_dna_outcome_ids=[],
            dna_lag_weeks=1,
        ),
    )

    dates = pd.date_range(dates_start, periods=n_obs, freq="7D")
    x_media = rng.uniform(0, 100, size=(n_obs, 1))
    frame = {
        "Y": Y,
        "X_media": x_media,
        "markets": ["UK"],
        "market_bounds": [(0, n_obs)],
        "market_idx": np.zeros(n_obs, dtype=int),
        "promo": np.zeros((n_obs, 1)),
        "trend": np.arange(n_obs, dtype=float),
        "fourier": np.zeros((n_obs, 4)),
        "outcome_ids": oids,
        "dates": dates.to_numpy(),
        "df": pd.DataFrame(
            {"date": dates, "market": "UK", "TV": x_media[:, 0], "fh_new_gsa": Y[:, 0]}
        ),
    }
    return trace, frame, meta


def _seed_fully_identified_model(
    at: AppTest, *, named_event_fit_inputs=None, **frame_kwargs
) -> None:
    """`named_event_fit_inputs`, if supplied, mutates `meta`'s named-event
    provenance fields exactly as `build_fh_hierarchical_model` would at
    fit time (mirrors `test_named_event_hierarchical_model_wiring.py`'s
    `_meta_from_fit` helper) BEFORE it is ever assigned into `at.
    session_state` - never read back and mutated after assignment, since
    AppTest's `session_state` is not guaranteed to expose the exact same
    object for in-place mutation before the first `.run()`."""
    trace, frame, meta = _trace_frame_meta(**frame_kwargs)
    if named_event_fit_inputs is not None:
        meta.named_event_fit_blocks = [
            (b.family_id, b.market) for b in named_event_fit_inputs.blocks
        ]
        meta.named_event_fit_block_provenance = [
            {
                "family_id": b.family_id,
                "market": b.market,
                "response_definition_id": b.response_definition_id,
                "response_definition_version": b.response_definition_version,
                "classification": b.classification,
                "fitted_support_weeks": int(np.any(b.design != 0.0, axis=1).sum()),
            }
            for b in named_event_fit_inputs.blocks
        ]
        meta.named_event_fit_fingerprint = named_event_fit_inputs.fingerprint()
        meta.named_event_response_definitions_at_fit = list(
            named_event_fit_inputs.consumed_response_definitions()
        )
    at.session_state["trace"] = trace
    at.session_state["frame"] = frame
    at.session_state["model_meta"] = meta
    at.session_state["model_spec"] = ModelSpec(
        date_col="date",
        market_col="market",
        markets=["UK"],
        segment_outcomes={"New": "fh_new_gsa"},
        channels=["TV"],
    ).to_dict()
    at.session_state["posterior_params"] = {"beta": [[1.0]]}
    at.session_state["model_run_id"] = "run-test-named-event-diag-1"
    at.session_state["activity_definitions"] = [
        ActivityDefinition(
            activity_id="a1",
            channel="TV",
            activity_ownership="paid",
            model_role="intervention",
            economic_treatment="paid_media_cost",
            planning_eligibility="optimisable",
            source="test",
            approval_status="approved",
            approved_by="Test Reviewer",
            approved_at="2026-07-29T00:00:00+00:00",
        ).to_dict()
    ]


def _all_text(at: AppTest) -> str:
    parts = [(m.value or "") for m in at.markdown]
    parts += [(c.value or "") for c in at.caption]
    parts += [(i.value or "") for i in at.info]
    parts += [(s.value or "") for s in at.success]
    parts += [(w.value or "") for w in at.warning]
    return "\n".join(parts)


def test_no_registered_events_shows_info_message():
    at = AppTest.from_file(str(PAGE), default_timeout=60)
    _seed_fully_identified_model(at)
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    assert any(exp.label == "Named-event diagnostics" for exp in at.expander)
    text = _all_text(at)
    assert "No named-event occurrences are registered" in text


def test_fitted_gifting_family_shows_included_in_fit():
    at = AppTest.from_file(str(PAGE), default_timeout=60)
    _seed_fully_identified_model(at, dates_start="2026-01-05", n_obs=20)
    family = NamedEventFamily(
        family_id="mothers_day",
        family_version=1,
        display_name="Mother's Day",
        classification="gifting",
        classification_status=DEFAULT_EVENT_EVIDENCE_STATUS,
    )
    occurrence = NamedEventOccurrence(
        event_id="md-2026",
        event_version=1,
        display_name="Mother's Day 2026",
        start_date="2026-03-16",
        end_date="2026-03-16",
        market_scope=("UK",),
        source_id="events",
        family_id="mothers_day",
    )
    definition = EventResponseDefinition(
        response_definition_id="mothers_day_default_response",
        response_definition_version=1,
        family_id="mothers_day",
        treatment="anticipatory",
        max_lead=3,
        max_lag=0,
        transformation_method_reference=NAMED_EVENT_RESPONSE_STRUCTURE,
    )
    at.session_state["named_event_families"] = [family.to_dict()]
    at.session_state["named_event_occurrences"] = [occurrence.to_dict()]
    at.session_state["named_event_response_definitions"] = [definition.to_dict()]
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    text = _all_text(at)
    assert "fit_status counts" in text
    assert "included_in_fit" in text


def test_promotional_family_shows_promotional_window_unresolved():
    at = AppTest.from_file(str(PAGE), default_timeout=60)
    _seed_fully_identified_model(at, dates_start="2025-11-03", n_obs=20)
    family = NamedEventFamily(
        family_id="black_friday",
        family_version=1,
        display_name="Black Friday",
        classification="promotional",
        classification_status=CLASSIFICATION_STATUS_PROMOTIONAL_WINDOW_UNRESOLVED,
    )
    occurrence = NamedEventOccurrence(
        event_id="black_friday_2025_uk",
        event_version=1,
        display_name="Black Friday",
        start_date="2025-11-28",
        end_date="2025-12-01",
        market_scope=("UK",),
        source_id="events",
        family_id="black_friday",
    )
    at.session_state["named_event_families"] = [family.to_dict()]
    at.session_state["named_event_occurrences"] = [occurrence.to_dict()]
    at.session_state["named_event_response_definitions"] = []
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    text = _all_text(at)
    assert "promotional_window_unresolved" in text
    assert "never the same thing as a fitted zero effect" in text


def _mothers_day_registry():
    family = NamedEventFamily(
        family_id="mothers_day",
        family_version=1,
        display_name="Mother's Day",
        classification="gifting",
        classification_status=DEFAULT_EVENT_EVIDENCE_STATUS,
    )
    occurrence = NamedEventOccurrence(
        event_id="md-2026",
        event_version=1,
        display_name="Mother's Day 2026",
        start_date="2026-03-16",
        end_date="2026-03-16",
        market_scope=("UK",),
        source_id="events",
        family_id="mothers_day",
    )
    definition = EventResponseDefinition(
        response_definition_id="mothers_day_default_response",
        response_definition_version=1,
        family_id="mothers_day",
        treatment="anticipatory",
        max_lead=3,
        max_lag=0,
        transformation_method_reference=NAMED_EVENT_RESPONSE_STRUCTURE,
    )
    return family, occurrence, definition


def _headings(at: AppTest) -> list[str]:
    return [(m.value or "") for m in at.markdown]


def test_fitted_model_view_shows_current_when_registry_matches_fit():
    at = AppTest.from_file(str(PAGE), default_timeout=60)
    family, occurrence, definition = _mothers_day_registry()
    probe_frame = _trace_frame_meta(dates_start="2026-01-05", n_obs=20)[1]
    fit_inputs = build_named_event_fit_inputs(
        probe_frame,
        families=[family],
        occurrences=[occurrence],
        response_definitions=[definition],
    )
    _seed_fully_identified_model(
        at, dates_start="2026-01-05", n_obs=20, named_event_fit_inputs=fit_inputs
    )
    at.session_state["named_event_families"] = [family.to_dict()]
    at.session_state["named_event_occurrences"] = [occurrence.to_dict()]
    at.session_state["named_event_response_definitions"] = [definition.to_dict()]
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    headings = _headings(at)
    assert any(h.strip("#* ") == "This fitted model" for h in headings)
    assert any("Current registry / next-fit readiness" in h for h in headings)
    text = _all_text(at)
    assert "Current - the governed registry" in text


def test_fitted_model_view_shows_drift_when_occurrence_date_changed():
    at = AppTest.from_file(str(PAGE), default_timeout=60)
    family, occurrence, definition = _mothers_day_registry()
    probe_frame = _trace_frame_meta(dates_start="2026-01-05", n_obs=20)[1]
    fit_inputs = build_named_event_fit_inputs(
        probe_frame,
        families=[family],
        occurrences=[occurrence],
        response_definitions=[definition],
    )
    fitted_blocks_before = [(b.family_id, b.market) for b in fit_inputs.blocks]
    _seed_fully_identified_model(
        at, dates_start="2026-01-05", n_obs=20, named_event_fit_inputs=fit_inputs
    )

    changed_occurrence = NamedEventOccurrence(
        event_id="md-2026",
        event_version=2,
        display_name="Mother's Day 2026",
        start_date="2026-03-23",  # a week later than what was fitted
        end_date="2026-03-23",
        market_scope=("UK",),
        source_id="events",
        family_id="mothers_day",
    )
    at.session_state["named_event_families"] = [family.to_dict()]
    at.session_state["named_event_occurrences"] = [changed_occurrence.to_dict()]
    at.session_state["named_event_response_definitions"] = [definition.to_dict()]
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    text = _all_text(at)
    assert "Changed since fit" in text
    assert "event occurrence set or timing changed" in text
    # The fitted-model table itself must not have been rewritten by the
    # occurrence edit.
    assert (
        list(at.session_state["model_meta"].named_event_fit_blocks)
        == fitted_blocks_before
    )


def test_no_named_event_consumed_at_fit_shows_readiness_only():
    at = AppTest.from_file(str(PAGE), default_timeout=60)
    _seed_fully_identified_model(at, dates_start="2026-01-05", n_obs=20)
    family, occurrence, definition = _mothers_day_registry()
    # Registry has an event, but the fitted model never consumed one -
    # meta's named-event fields stay at their empty defaults.
    at.session_state["named_event_families"] = [family.to_dict()]
    at.session_state["named_event_occurrences"] = [occurrence.to_dict()]
    at.session_state["named_event_response_definitions"] = [definition.to_dict()]
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    text = _all_text(at)
    assert "did not consume any named event at fit time" in text
    assert "Current registry / next-fit readiness" in text
    # No fake/empty "This fitted model" table heading.
    headings = _headings(at)
    assert not any(h.strip("#* ") == "This fitted model" for h in headings)
