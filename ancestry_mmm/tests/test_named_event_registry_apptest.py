"""REQ-EVENT-001 (Work Package 1): AppTest coverage for the governed
named-event registry workflow wired into pages/01_Data_Upload.py -
uploaded Context events rows wait for explicit analyst adoption, the
registry is immutable, factual dates are never rewritten, and the page
never derives classification or treatment from an event name."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

from ancestry_mmm.core.coverage import (
    DOMAIN_CONTEXT_AND_EXTERNAL_FACTORS,
    SourceDefinition,
)
from ancestry_mmm.core.named_events import NamedEventOccurrence

st.page_link = lambda *a, **k: None

ROOT = Path(__file__).parent.parent
PAGE = ROOT / "pages" / "01_Data_Upload.py"


def _events_row() -> dict:
    return {
        "event_id": "md-2026",
        "event_name": "Mother's Day 2026",
        "start_date": "2026-03-22",
        "end_date": "2026-03-22",
    }


def _run_at(**extra_state):
    at = AppTest.from_file(str(PAGE), default_timeout=60)
    at.session_state["raw_sources"] = {"events": _events_frame()}
    at.session_state["source_definitions"] = [
        SourceDefinition(
            source_id="events",
            name="events",
            logical_domain=DOMAIN_CONTEXT_AND_EXTERNAL_FACTORS,
        ).to_dict()
    ]
    at.session_state["data_loaded"] = True
    for key, value in extra_state.items():
        at.session_state[key] = value
    at.run()
    return at


def _events_frame():
    import pandas as pd

    return pd.DataFrame([_events_row()])


def _all_text(at: AppTest) -> str:
    parts = [(m.value or "") for m in at.markdown]
    parts += [(c.value or "") for c in at.caption]
    parts += [(i.value or "") for i in at.info]
    parts += [(s.value or "") for s in at.success]
    parts += [(e.value or "") for e in at.error]
    parts += [(w.value or "") for w in at.warning]
    return "\n".join(parts)


def test_named_event_section_shows_with_source_rows():
    at = _run_at()
    assert not at.exception, f"page raised: {at.exception}"
    text = _all_text(at)
    assert "Named events" in text
    assert "Source rows awaiting adoption" in text


def test_source_rows_are_listed_but_never_auto_adopted():
    at = _run_at()
    assert not at.exception, f"page raised: {at.exception}"
    # The row renders in the awaiting-adoption table, but the registry
    # stays empty until the analyst explicitly adopts it. (Dataframe cell
    # values are widgets, not markdown - assert the section heading and
    # the empty registry, and that the adopt selector offers the row.)
    assert at.session_state["named_event_occurrences"] == []
    assert "Source rows awaiting adoption" in _all_text(at)
    selector = next(s for s in at.selectbox if s.key == "ne_adopt_row_select")
    assert "md-2026" in str(selector.options)


def test_adopting_a_row_registers_version_1_with_factual_dates():
    at = _run_at()
    assert not at.exception, f"page raised: {at.exception}"

    at.text_input(key="ne_adopt_market").set_value("UK")
    at.run()

    submit = next(b for b in at.button if b.label == "Adopt occurrence")
    submit.click().run()
    assert not at.exception, f"page raised after adopting: {at.exception}"
    occurrences = at.session_state["named_event_occurrences"]
    assert len(occurrences) == 1
    record = NamedEventOccurrence.from_dict(occurrences[0])
    assert record.event_id == "md-2026"
    assert record.event_version == 1
    assert record.start_date == "2026-03-22"
    assert record.end_date == "2026-03-22"
    assert record.market_scope == ("UK",)
    assert record.family_id is None
    assert not hasattr(record, "classification")
    assert not hasattr(record, "treatment")


def test_adopting_without_required_fields_fails_closed():
    at = _run_at()
    assert not at.exception, f"page raised: {at.exception}"

    # No market scope supplied - adoption must fail closed with the
    # missing fields named, and the registry must stay empty.
    submit = next(b for b in at.button if b.label == "Adopt occurrence")
    submit.click().run()
    assert not at.exception, f"page raised after adopting: {at.exception}"
    assert at.session_state["named_event_occurrences"] == []
    assert any("missing required field" in (e.value or "") for e in at.error)


def test_registering_a_family_requires_explicit_classification():
    at = _run_at()
    assert not at.exception, f"page raised: {at.exception}"

    at.text_input(key="ne_family_id").set_value("mothers_day")
    at.text_input(key="ne_family_name").set_value("Mother's Day")
    at.text_input(key="ne_family_classification").set_value("gifting")
    at.run()

    submit = next(b for b in at.button if b.label == "Register family")
    submit.click().run()
    assert not at.exception, f"page raised after registering family: {at.exception}"
    families = at.session_state["named_event_families"]
    assert len(families) == 1
    assert families[0]["family_id"] == "mothers_day"
    assert families[0]["classification"] == "gifting"


def test_family_without_classification_fails_closed():
    at = _run_at()
    assert not at.exception, f"page raised: {at.exception}"

    at.text_input(key="ne_family_id").set_value("mothers_day")
    at.text_input(key="ne_family_name").set_value("Mother's Day")
    at.run()

    submit = next(b for b in at.button if b.label == "Register family")
    submit.click().run()
    assert not at.exception, f"page raised after registering family: {at.exception}"
    assert at.session_state["named_event_families"] == []
    assert any("required" in (e.value or "") for e in at.error)


def test_registered_occurrences_render_with_factual_dates():
    occurrence = NamedEventOccurrence(
        event_id="md-2026",
        event_version=1,
        display_name="Mother's Day 2026",
        start_date="2026-03-22",
        end_date="2026-03-22",
        market_scope=("UK",),
        source_id="events",
    ).to_dict()
    at = _run_at(named_event_occurrences=[occurrence])
    assert not at.exception, f"page raised: {at.exception}"
    # Dataframe cells are widgets, not markdown - the factual-date section
    # heading is the testable rendering surface; the record itself was
    # already asserted in the adoption tests above.
    assert "Registered occurrences (factual dates)" in _all_text(at)


def _preferred_events_frame():
    import pandas as pd

    return pd.DataFrame(
        [
            {
                "event_id": "mothers_day_2025_uk",
                "event_name": "Mother's Day",
                "event_family_id": "mothers_day",
                "event_type": "gifting",
                "market": "UK",
                "start_date": "2025-03-30",
                "end_date": "2025-03-30",
            },
            {
                "event_id": "mothers_day_2025_de",
                "event_name": "Mother's Day",
                "event_family_id": "mothers_day",
                "event_type": "gifting",
                "market": "DE",
                "start_date": "2025-05-11",
                "end_date": "2025-05-11",
            },
        ]
    )


def _run_preferred_at(**extra_state):
    at = AppTest.from_file(str(PAGE), default_timeout=60)
    at.session_state["raw_sources"] = {"events": _preferred_events_frame()}
    at.session_state["source_definitions"] = [
        SourceDefinition(
            source_id="events",
            name="events",
            logical_domain=DOMAIN_CONTEXT_AND_EXTERNAL_FACTORS,
        ).to_dict()
    ]
    at.session_state["data_loaded"] = True
    for key, value in extra_state.items():
        at.session_state[key] = value
    at.run()
    return at


def test_preferred_rows_show_bulk_adopt_section():
    at = _run_preferred_at()
    assert not at.exception, f"page raised: {at.exception}"
    text = _all_text(at)
    assert "Bulk adopt (preferred seven-column rows)" in text


def test_bulk_adopt_button_registers_family_occurrences_and_definition():
    at = _run_preferred_at()
    assert not at.exception, f"page raised: {at.exception}"

    submit = next(b for b in at.button if b.key == "ne_bulk_adopt_button")
    submit.click().run()
    assert not at.exception, f"page raised after bulk adopt: {at.exception}"

    families = at.session_state["named_event_families"]
    occurrences = at.session_state["named_event_occurrences"]
    definitions = at.session_state["named_event_response_definitions"]
    assert len(families) == 1
    assert families[0]["family_id"] == "mothers_day"
    assert families[0]["classification"] == "gifting"
    assert len(occurrences) == 2
    assert {tuple(o["market_scope"]) for o in occurrences} == {("UK",), ("DE",)}
    assert len(definitions) == 1
    assert definitions[0]["response_definition_id"] == "mothers_day_default_response"
    assert definitions[0]["treatment"] == "anticipatory"


def _promotion_events_frame():
    import pandas as pd

    return pd.DataFrame(
        [
            {
                "event_id": "black_friday_2025_uk",
                "event_name": "Black Friday",
                "event_family_id": "black_friday",
                "event_type": "promotion",
                "market": "UK",
                "start_date": "2025-11-28",
                "end_date": "2025-12-01",
            }
        ]
    )


def _run_promotion_at(**extra_state):
    at = AppTest.from_file(str(PAGE), default_timeout=60)
    at.session_state["raw_sources"] = {"events": _promotion_events_frame()}
    at.session_state["source_definitions"] = [
        SourceDefinition(
            source_id="events",
            name="events",
            logical_domain=DOMAIN_CONTEXT_AND_EXTERNAL_FACTORS,
        ).to_dict()
    ]
    at.session_state["data_loaded"] = True
    for key, value in extra_state.items():
        at.session_state[key] = value
    at.run()
    return at


def test_promotion_row_adopts_as_governed_data_with_no_response_definition():
    at = _run_promotion_at()
    assert not at.exception, f"page raised: {at.exception}"

    submit = next(b for b in at.button if b.key == "ne_bulk_adopt_button")
    submit.click().run()
    assert not at.exception, f"page raised after bulk adopt: {at.exception}"

    families = at.session_state["named_event_families"]
    occurrences = at.session_state["named_event_occurrences"]
    definitions = at.session_state["named_event_response_definitions"]
    assert len(families) == 1
    assert families[0]["family_id"] == "black_friday"
    assert families[0]["classification"] == "promotional"
    assert families[0]["classification_status"] == "promotional_window_unresolved"
    assert len(occurrences) == 1
    assert occurrences[0]["start_date"] == "2025-11-28"
    assert occurrences[0]["end_date"] == "2025-12-01"
    # Never auto-fitted - the bounded per-occurrence response mechanism is
    # a disclosed, decision-required gap.
    assert definitions == []

    text = _all_text(at)
    assert "NOT currently included in the fitted named-event response" in text
    assert "decision-required" in text


def test_registered_families_enable_definition_form():
    from ancestry_mmm.core.named_events import NamedEventFamily

    family = NamedEventFamily(
        family_id="mothers_day",
        family_version=1,
        display_name="Mother's Day",
        classification="gifting",
    ).to_dict()
    at = _run_at(named_event_families=[family])
    assert not at.exception, f"page raised: {at.exception}"
    assert "Event response definitions" in _all_text(at)

    at.text_input(key="ne_definition_id").set_value("md-def")
    at.text_input(key="ne_definition_method").set_value("governed-ref")
    at.run()

    submit = next(b for b in at.button if b.label == "Register response definition")
    submit.click().run()
    assert not at.exception, f"page raised after definition: {at.exception}"
    definitions = at.session_state["named_event_response_definitions"]
    assert len(definitions) == 1
    assert definitions[0]["treatment"] == "contemporaneous"
    assert definitions[0]["family_id"] == "mothers_day"
