"""Tests for `application.fx_service`'s Finance constant-dollar
ingestion and vintage resolution (Finance constant-dollar correction,
2026-09-10). No actual exchange rate appears anywhere in this file -
every rate used is a clearly synthetic test value. The real Finance
file (`.local-data/Constant Dollar Conversion Rate by Year.xlsx`) is
never read here - it is used only for one-off, manual format
verification outside the automated test suite, and is never committed."""

from decimal import Decimal

import pandas as pd
import pytest

from ancestry_mmm.application.fx_service import (
    FXUploadValidationError,
    build_finance_constant_dollar_rate_set,
    default_fx_vintage_year_id,
    resolve_constant_dollar_vintage_rate,
)
from ancestry_mmm.core.fx_rates import available_vintage_year_ids


def _finance_frame(**overrides) -> pd.DataFrame:
    rows = overrides.pop(
        "rows",
        [
            {"year_id": 2025, "currency_code": "GBP", "local_to_usd_conversion_rate": 1.25},
            {"year_id": 2025, "currency_code": "EUR", "local_to_usd_conversion_rate": 1.05},
            {"year_id": 2025, "currency_code": "USD", "local_to_usd_conversion_rate": 1.0},
            {"year_id": 2026, "currency_code": "GBP", "local_to_usd_conversion_rate": 1.30},
            {"year_id": 2026, "currency_code": "EUR", "local_to_usd_conversion_rate": 1.08},
            {"year_id": 2026, "currency_code": "USD", "local_to_usd_conversion_rate": 1.0},
        ],
    )
    return pd.DataFrame(rows)


def _build(**overrides):
    frame = overrides.pop("frame", _finance_frame())
    defaults = dict(
        rate_set_id="finance-constant-dollar-test",
        rate_set_version=1,
        name="Finance constant-dollar table",
        provider="Finance",
    )
    defaults.update(overrides)
    return build_finance_constant_dollar_rate_set(frame, **defaults)


def _build_approved(**overrides):
    defaults = dict(
        approval_status="approved",
        approved_by="finance-reviewer",
        approved_at="2026-01-01T00:00:00Z",
    )
    defaults.update(overrides)
    return _build(**defaults)


class TestFinanceConstantDollarIngestion:
    """`build_finance_constant_dollar_rate_set` ingests Finance's actual
    three-column published format directly."""

    def test_ingests_two_vintages(self):
        rate_set, records = _build()
        assert available_vintage_year_ids(records) == ("2025", "2026")
        # 2 currencies (GBP, EUR) x 2 vintages - the USD identity rows
        # are dropped, never built into an FXRateRecord.
        assert len(records) == 4

    def test_conversion_direction_is_usd_equals_local_times_rate(self):
        _rate_set, records = _build()
        gbp_2026 = next(
            r
            for r in records
            if r.source_currency == "GBP" and r.financial_year == "2026"
        )
        assert gbp_2026.target_currency == "USD"
        assert gbp_2026.rate == Decimal("1.30")

    def test_usd_identity_rows_are_never_built_into_a_record(self):
        _rate_set, records = _build()
        assert not any(r.source_currency == "USD" for r in records)

    def test_all_usd_rows_with_no_other_currency_is_rejected(self):
        frame = pd.DataFrame(
            [{"year_id": 2026, "currency_code": "USD", "local_to_usd_conversion_rate": 1.0}]
        )
        with pytest.raises(FXUploadValidationError, match="USD identity"):
            _build(frame=frame)

    def test_missing_required_column_is_rejected(self):
        frame = pd.DataFrame([{"year_id": 2026, "currency_code": "GBP"}])
        with pytest.raises(FXUploadValidationError, match="missing required column"):
            _build(frame=frame)

    def test_empty_upload_is_rejected(self):
        frame = pd.DataFrame(columns=["year_id", "currency_code", "local_to_usd_conversion_rate"])
        with pytest.raises(FXUploadValidationError, match="no rows"):
            _build(frame=frame)

    def test_non_integer_year_id_is_rejected(self):
        frame = pd.DataFrame(
            [
                {
                    "year_id": "not-a-year",
                    "currency_code": "GBP",
                    "local_to_usd_conversion_rate": 1.3,
                }
            ]
        )
        with pytest.raises(FXUploadValidationError, match="non-integer year_id"):
            _build(frame=frame)

    def test_default_vintage_is_the_latest_ingested(self):
        _rate_set, records = _build()
        assert default_fx_vintage_year_id(records) == "2026"


class TestConstantDollarVintageResolution:
    """`resolve_constant_dollar_vintage_rate` resolves the *selected
    vintage's* rate for a currency pair - never the observation's own
    calendar year, never a fallback to another vintage."""

    def test_resolves_the_selected_vintage(self):
        rate_set, records = _build_approved()
        rate = resolve_constant_dollar_vintage_rate(
            rate_set,
            records,
            source_currency="GBP",
            target_currency="USD",
            vintage_year_id="2026",
        )
        assert rate == Decimal("1.30")

    def test_different_vintages_yield_different_rates(self):
        rate_set, records = _build_approved()
        rate_2025 = resolve_constant_dollar_vintage_rate(
            rate_set,
            records,
            source_currency="GBP",
            target_currency="USD",
            vintage_year_id="2025",
        )
        rate_2026 = resolve_constant_dollar_vintage_rate(
            rate_set,
            records,
            source_currency="GBP",
            target_currency="USD",
            vintage_year_id="2026",
        )
        assert rate_2025 == Decimal("1.25")
        assert rate_2026 == Decimal("1.30")
        assert rate_2025 != rate_2026

    def test_currency_absent_from_the_selected_vintage_returns_none(self):
        """AUD has no rate in either vintage of this synthetic set -
        must return None (block), never fabricate or infer a rate."""
        rate_set, records = _build_approved()
        rate = resolve_constant_dollar_vintage_rate(
            rate_set,
            records,
            source_currency="AUD",
            target_currency="USD",
            vintage_year_id="2026",
        )
        assert rate is None

    def test_never_falls_back_to_a_different_vintage(self):
        """Regression: GBP exists in 2025 but the request is for a
        vintage_year_id that has no matching record at all - must return
        None, never silently substitute the 2025 rate."""
        rate_set, records = _build_approved()
        rate = resolve_constant_dollar_vintage_rate(
            rate_set,
            records,
            source_currency="GBP",
            target_currency="USD",
            vintage_year_id="2099",
        )
        assert rate is None

    def test_pending_rate_set_returns_none(self):
        rate_set, records = _build(approval_status="pending")
        rate = resolve_constant_dollar_vintage_rate(
            rate_set,
            records,
            source_currency="GBP",
            target_currency="USD",
            vintage_year_id="2026",
        )
        assert rate is None

    def test_approved_rate_set_resolves(self):
        rate_set, records = _build(
            approval_status="approved",
            approved_by="finance-reviewer",
            approved_at="2026-01-01T00:00:00Z",
        )
        rate = resolve_constant_dollar_vintage_rate(
            rate_set,
            records,
            source_currency="GBP",
            target_currency="USD",
            vintage_year_id="2026",
        )
        assert rate == Decimal("1.30")

    def test_fingerprint_mismatch_raises(self):
        rate_set, records = _build_approved()
        tampered_records = records[:-1]  # drop a record without updating the set
        with pytest.raises(FXUploadValidationError, match="fingerprint"):
            resolve_constant_dollar_vintage_rate(
                rate_set,
                tampered_records,
                source_currency="GBP",
                target_currency="USD",
                vintage_year_id="2026",
            )
