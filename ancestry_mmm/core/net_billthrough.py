"""Validation for authoritative, uploaded Family History net bill-through.

Net bill-through is an input KPI, not a transformation performed by the MMM.
This module deliberately contains no signup, billing, cancellation, refund,
offer or maturity-estimation logic.

G2A.7 (REQ-NBT-001): NBT completeness validation remains a data-integrity
gate; business-definition approval is separate (see core.outcome_approval).
Both are required for official NBT use.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Dict, List, Sequence

import numpy as np
import pandas as pd

NBT_METRIC_KEY = "fh_net_billthrough_count"
NBT_DATE_BASIS = "signup_date_attributed"
NBT_DATE_BASES = ("signup_date", NBT_DATE_BASIS)
NBT_UNIT = "bill-through subscriber"


@dataclass(frozen=True)
class NetBillthroughCompletenessMetadata:
    data_as_of_date: str
    model_start_week: str
    model_end_week: str
    latest_complete_net_billthrough_week: str
    maturity_rule_description: str
    source_owner: str
    metric_key: str = NBT_METRIC_KEY
    aggregation_type: str = "count"
    date_basis: str = NBT_DATE_BASIS
    unit: str = NBT_UNIT
    # G2A.7 (REQ-NBT-001): bind completeness metadata to the specific
    # outcome definition this data belongs to — completeness is about
    # data integrity for a particular outcome, not a global property.
    outcome_id: str = ""
    definition_version: str = ""
    definition_fingerprint: str = ""
    # REQ-NBT-005: an explicit, per-source-pack production readiness window
    # (e.g. 30 days for the current UK Family History production pack),
    # distinct from REQ-NBT-002's 14-day *historical-test* completeness
    # horizon. `None` means "not configured" - assess_official_maturity_
    # readiness never assumes a default in its absence (REQ-NBT-004: no
    # historical-test rule may be silently applied as a production
    # assumption).
    maturity_window_days: int | None = None

    def completeness_fingerprint(self) -> str:
        """Stable SHA-256 fingerprint of this completeness record, covering
        the data-integrity fields that define the record's identity:
        source_owner, data_as_of_date, latest_complete_net_billthrough_week,
        maturity_rule_description, and maturity_window_days. This is NOT the
        same as the outcome-definition fingerprint (``definition_fingerprint``)
        — a completeness record can be updated (newer as-of date, later
        complete week) without changing the outcome definition, and vice
        versa."""
        payload: Dict[str, object] = {
            "source_owner": self.source_owner,
            "data_as_of_date": self.data_as_of_date,
            "latest_complete_net_billthrough_week": self.latest_complete_net_billthrough_week,
            "maturity_rule_description": self.maturity_rule_description,
            "maturity_window_days": self.maturity_window_days,
            "outcome_id": self.outcome_id,
            "definition_version": self.definition_version,
            "definition_fingerprint": self.definition_fingerprint,
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "NetBillthroughCompletenessMetadata":
        known = cls.__dataclass_fields__
        return cls(**{key: item for key, item in value.items() if key in known})


def _outcome_value(outcome: object, key: str, default=None):
    if isinstance(outcome, dict):
        return outcome.get(key, default)
    return getattr(outcome, key, default)


def validate_supplied_net_billthrough(
    data: pd.DataFrame,
    metadata: NetBillthroughCompletenessMetadata | None,
    *,
    configured_markets: Sequence[str] | None = None,
    configured_segments: Sequence[str] | None = None,
    configured_outcomes: Sequence[object] | None = None,
    value_column: str = NBT_METRIC_KEY,
    week_column: str = "week_start",
    market_column: str = "market",
    segment_column: str = "segment",
) -> List[str]:
    """Validate canonical long or wide weekly net bill-through data."""
    if metadata is None:
        return [
            "Model training blocked: net bill-through completeness metadata is required."
        ]
    if isinstance(metadata, dict):
        metadata = NetBillthroughCompletenessMetadata.from_dict(metadata)

    errors: List[str] = []
    required = {week_column, market_column}
    missing_columns = sorted(required - set(data.columns))
    if missing_columns:
        return [
            f"Supplied net bill-through data is missing columns: {missing_columns}."
        ]

    if (
        metadata.metric_key != NBT_METRIC_KEY
        or metadata.date_basis not in NBT_DATE_BASES
    ):
        errors.append(
            "Net bill-through must use metric_key 'fh_net_billthrough_count' "
            "and a signup-date basis, not finance-date GSA."
        )
    if metadata.aggregation_type != "count" or metadata.unit != NBT_UNIT:
        errors.append(
            "Net bill-through must be a count measured in bill-through subscribers."
        )

    try:
        start = pd.Timestamp(metadata.model_start_week).normalize()
        end = pd.Timestamp(metadata.model_end_week).normalize()
        latest = pd.Timestamp(metadata.latest_complete_net_billthrough_week).normalize()
        as_of = pd.Timestamp(metadata.data_as_of_date).normalize()
    except (TypeError, ValueError):
        return errors + [
            "Net bill-through completeness metadata contains invalid dates."
        ]
    if start > end:
        errors.append("model_start_week must not be after model_end_week.")
        return errors
    if latest < end:
        errors.append(
            f"Model training blocked: latest complete net bill-through week "
            f"{latest.date()} is earlier than model end week {end.date()}."
        )
    if latest > as_of:
        errors.append(
            "latest_complete_net_billthrough_week cannot be after data_as_of_date."
        )
    if (
        not metadata.maturity_rule_description.strip()
        or not metadata.source_owner.strip()
    ):
        errors.append(
            "Net bill-through metadata requires a maturity rule and source owner."
        )

    frame = data.copy()
    frame[week_column] = pd.to_datetime(
        frame[week_column], errors="coerce"
    ).dt.normalize()
    if frame[week_column].isna().any():
        errors.append("Net bill-through contains invalid week values.")
    before_start = frame[week_column] < start
    after_end = frame[week_column] > end
    if before_start.any() or after_end.any():
        errors.append(
            "Net bill-through coverage must exactly match the configured model window; "
            f"found {int(before_start.sum())} row(s) before and {int(after_end.sum())} row(s) after it."
        )

    within = frame[frame[week_column].between(start, end, inclusive="both")].copy()
    expected_weeks = set(pd.date_range(start, end, freq="7D"))
    unexpected_weeks = sorted(set(within[week_column].dropna()) - expected_weeks)
    if unexpected_weeks:
        errors.append(
            "Net bill-through uses an incorrect weekly anchor; every date must be "
            f"7 days from {start.date()}."
        )

    configured_outcomes = list(configured_outcomes or [])
    if configured_outcomes:
        configured_outcomes = [
            outcome
            for outcome in configured_outcomes
            if _outcome_value(outcome, "metric_key") == NBT_METRIC_KEY
        ]
    markets_default = [str(m) for m in (configured_markets or [])]

    def validate_values(values: pd.Series, label: str) -> None:
        numeric = pd.to_numeric(values, errors="coerce")
        if numeric.isna().any():
            errors.append(
                f"Net bill-through counts for {label} contain missing or non-numeric values."
            )
        valid = numeric.dropna()
        if (valid < 0).any():
            errors.append(f"Net bill-through counts for {label} must be non-negative.")
        if not np.allclose(valid, np.round(valid), atol=1e-8):
            errors.append(f"Net bill-through counts for {label} must be integer-like.")

    # Canonical wide form: one row per market/week, one source column per
    # configured outcome. This is the shape consumed by the model preprocessor.
    if configured_outcomes:
        duplicate_count = int(
            within.duplicated([market_column, week_column], keep=False).sum()
        )
        if duplicate_count:
            errors.append(
                f"Net bill-through contains {duplicate_count} duplicate market × week row(s)."
            )
        for outcome in configured_outcomes:
            source_column = _outcome_value(outcome, "source_column", value_column)
            segment = str(_outcome_value(outcome, "segment", "unknown"))
            outcome_markets = (
                _outcome_value(outcome, "markets", None) or markets_default
            )
            if source_column not in within.columns:
                errors.append(
                    f"Supplied net bill-through data is missing outcome column '{source_column}'."
                )
                continue
            for market in [str(m) for m in outcome_markets]:
                rows = within[within[market_column].astype(str) == market]
                missing_weeks = sorted(expected_weeks - set(rows[week_column].dropna()))
                if missing_weeks:
                    errors.append(
                        f"Net bill-through is missing {len(missing_weeks)} week(s) for "
                        f"market '{market}', segment '{segment}', outcome '{source_column}'."
                    )
                validate_values(
                    rows[source_column], f"market '{market}', segment '{segment}'"
                )
        return errors

    # Canonical long form: one row per market/segment/week with a shared
    # fh_net_billthrough_count value column.
    required_long = {segment_column, value_column}
    missing_long = sorted(required_long - set(within.columns))
    if missing_long:
        return errors + [
            f"Supplied net bill-through data is missing columns: {missing_long}."
        ]
    duplicate_count = int(
        within.duplicated(
            [market_column, segment_column, week_column], keep=False
        ).sum()
    )
    if duplicate_count:
        errors.append(
            f"Net bill-through contains {duplicate_count} duplicate market × segment × week row(s)."
        )
    validate_values(within[value_column], "the prepared long frame")
    markets = markets_default or sorted(
        within[market_column].dropna().astype(str).unique()
    )
    segments = [str(s) for s in (configured_segments or [])] or sorted(
        within[segment_column].dropna().astype(str).unique()
    )
    configured_pairs = {(market, segment) for market in markets for segment in segments}
    actual_pairs = set(
        zip(within[market_column].astype(str), within[segment_column].astype(str))
    )
    absent_pairs = sorted(configured_pairs - actual_pairs)
    if absent_pairs:
        errors.append(
            f"Net bill-through is missing configured market × segment combinations: {absent_pairs}."
        )
    for market, segment in sorted(configured_pairs & actual_pairs):
        rows = within[
            (within[market_column].astype(str) == market)
            & (within[segment_column].astype(str) == segment)
        ]
        missing_weeks = sorted(expected_weeks - set(rows[week_column].dropna()))
        if missing_weeks:
            errors.append(
                f"Net bill-through is missing {len(missing_weeks)} week(s) for "
                f"market '{market}', segment '{segment}'."
            )
    return errors


def validate_nbt_completeness_metadata_for_outcome(
    outcome: object,
    metadata: "NetBillthroughCompletenessMetadata | dict | None",
) -> List[str]:
    """G2A.7a.1 (REQ-NBT-001, section 10): planning-time NBT completeness
        gate. Confirms the supplied completeness metadata still references
        *this* outcome definition and passes its own internal-consistency
        checks - it does not re-validate the full historical dataframe (that is
        `validate_supplied_net_billthrough`, enforced at model-training time via
        `assert_model_frame_net_billthrough_complete`). An approved outcome
        definition alone is not sufficient for official NBT use; both an
    G2A.7a.2: the three binding fields — ``outcome_id``,
        ``definition_version``, and ``definition_fingerprint`` — are mandatory.
        Missing, blank, or mismatched values block official NBT use. An empty
        fingerprint no longer passes."""
    issues: List[str] = []
    if metadata is None:
        return [
            "Net bill-through completeness metadata is required for "
            "official NBT use - an approved definition alone is not "
            "sufficient."
        ]
    if isinstance(metadata, dict):
        metadata = NetBillthroughCompletenessMetadata.from_dict(metadata)

    outcome_id = _outcome_value(outcome, "outcome_id")
    # G2A.7a.2: outcome_id binding is mandatory — blank or mismatched blocks
    if not metadata.outcome_id:
        issues.append(
            "Net bill-through completeness metadata is missing the required "
            "outcome_id binding field."
        )
    elif outcome_id and metadata.outcome_id != outcome_id:
        issues.append(
            f"Net bill-through completeness metadata references outcome "
            f"'{metadata.outcome_id}', not the requested outcome '{outcome_id}'."
        )

    # G2A.7a.2, G2A.7a.3: definition_version binding is mandatory for both
    # object and dict outcomes
    if not metadata.definition_version:
        issues.append(
            "Net bill-through completeness metadata is missing the required "
            "definition_version binding field."
        )
    else:
        outcome_version = _outcome_value(outcome, "definition_version")
        if outcome_version and metadata.definition_version != outcome_version:
            issues.append(
                f"Net bill-through completeness metadata references definition "
                f"version '{metadata.definition_version}', not the current "
                f"version '{outcome_version}'."
            )

    # G2A.7a.2, G2A.7a.3: definition_fingerprint binding is mandatory —
    # validated for both object and dict outcomes. An empty fingerprint
    # no longer passes.
    if not metadata.definition_fingerprint:
        issues.append(
            "Net bill-through completeness metadata is missing the required "
            "definition_fingerprint binding field."
        )
    else:
        # Handle both OutcomeDefinition objects and dicts
        if isinstance(outcome, dict):
            from .outcome_approval import fingerprint_outcome_definition
            from .outcomes import OutcomeDefinition

            try:
                outcome_def = OutcomeDefinition.from_dict(outcome)
                current_fingerprint = fingerprint_outcome_definition(outcome_def)
            except (TypeError, ValueError, KeyError):
                current_fingerprint = ""
        else:
            from .outcome_approval import fingerprint_outcome_definition

            current_fingerprint = fingerprint_outcome_definition(outcome)
        if (
            current_fingerprint
            and metadata.definition_fingerprint != current_fingerprint
        ):
            issues.append(
                "Net bill-through completeness metadata was recorded "
                "against a different outcome-definition fingerprint; it is "
                "stale for the current definition."
            )

    try:
        start = pd.Timestamp(metadata.model_start_week).normalize()
        end = pd.Timestamp(metadata.model_end_week).normalize()
        latest = pd.Timestamp(metadata.latest_complete_net_billthrough_week).normalize()
        as_of = pd.Timestamp(metadata.data_as_of_date).normalize()
    except (TypeError, ValueError):
        return issues + [
            "Net bill-through completeness metadata contains invalid dates."
        ]
    if start > end:
        issues.append("model_start_week must not be after model_end_week.")
    if latest < end:
        issues.append(
            f"latest complete net bill-through week {latest.date()} is "
            f"earlier than model end week {end.date()}."
        )
    if latest > as_of:
        issues.append(
            "latest_complete_net_billthrough_week cannot be after data_as_of_date."
        )
    if (
        not metadata.maturity_rule_description.strip()
        or not metadata.source_owner.strip()
    ):
        issues.append(
            "Net bill-through metadata requires a maturity rule and source owner."
        )
    return issues


def assess_official_maturity_readiness(
    metadata: "NetBillthroughCompletenessMetadata | dict | None",
) -> dict:
    """REQ-NBT-005: assess whether the latest complete NBT week is old enough
    to be treated as mature for *official* reporting/planning use.

    This is a surfaced readiness signal, not a new blocking gate on
    ``validate_supplied_net_billthrough``/``assert_supplied_net_billthrough_complete``
    - those existing functions keep validating structural completeness
    (coverage, non-negativity, week alignment) exactly as before. This
    function answers a different question: given the supplied
    ``maturity_window_days`` (a per-source-pack governed value - e.g. 30 days
    for the current UK Family History production pack per the UK FH MMM
    implementation brief, 2026-09-10 - never a value this function invents),
    has enough time passed since the latest complete week for its cohorts to
    be considered read for official use?

    Deliberately does not default ``maturity_window_days`` to 14 (REQ-NBT-002's
    historical-*test*-only completeness horizon) or to any other number:
    REQ-NBT-004 requires production maturity to come from the supplied source
    metadata, not a silently-applied historical-test assumption. When
    ``maturity_window_days`` is not configured, this returns
    ``is_mature=None`` ("not assessed"), never ``True`` or ``False``.
    """
    if metadata is None:
        return {
            "is_mature": None,
            "maturity_window_days": None,
            "days_since_latest_complete_week": None,
            "reason": "No net bill-through completeness metadata supplied.",
        }
    if isinstance(metadata, dict):
        metadata = NetBillthroughCompletenessMetadata.from_dict(metadata)

    try:
        latest = pd.Timestamp(
            metadata.latest_complete_net_billthrough_week
        ).normalize()
        as_of = pd.Timestamp(metadata.data_as_of_date).normalize()
    except (TypeError, ValueError):
        return {
            "is_mature": None,
            "maturity_window_days": metadata.maturity_window_days,
            "days_since_latest_complete_week": None,
            "reason": "Completeness metadata contains invalid dates.",
        }

    days_since = int((as_of - latest).days)
    if metadata.maturity_window_days is None:
        return {
            "is_mature": None,
            "maturity_window_days": None,
            "days_since_latest_complete_week": days_since,
            "reason": (
                "No maturity_window_days is configured for this source pack; "
                "official readiness cannot be assessed against a threshold "
                "that was never supplied."
            ),
        }

    is_mature = days_since >= metadata.maturity_window_days
    return {
        "is_mature": is_mature,
        "maturity_window_days": metadata.maturity_window_days,
        "days_since_latest_complete_week": days_since,
        "reason": (
            f"{days_since} day(s) have elapsed since the latest complete week "
            f"against a {metadata.maturity_window_days}-day maturity window."
            if is_mature
            else (
                f"Only {days_since} day(s) have elapsed since the latest "
                f"complete week; {metadata.maturity_window_days} day(s) are "
                "required before treating it as mature for official use."
            )
        ),
    }


def assert_supplied_net_billthrough_complete(*args, **kwargs) -> None:
    """Raise before model construction when the authoritative KPI is invalid."""
    errors = validate_supplied_net_billthrough(*args, **kwargs)
    if errors:
        raise ValueError(
            "Model training blocked by net bill-through validation:\n"
            + "\n".join(errors)
        )


def assert_model_frame_net_billthrough_complete(frame: dict) -> None:
    """Defensive training gate for frames that bypassed the preprocessor."""
    outcomes = list(frame.get("outcomes") or [])
    nbt = [o for o in outcomes if _outcome_value(o, "metric_key") == NBT_METRIC_KEY]
    if not nbt:
        return
    y = np.asarray(frame.get("Y"))
    market_idx = np.asarray(frame.get("market_idx"))
    markets = list(frame.get("markets") or [])
    validation = pd.DataFrame(
        {
            "week_start": pd.to_datetime(frame.get("dates")),
            "market": [markets[int(index)] for index in market_idx],
        }
    )
    configured = []
    outcome_ids = list(frame.get("outcome_ids") or [])
    for outcome in nbt:
        outcome_id = _outcome_value(outcome, "outcome_id")
        position = outcome_ids.index(outcome_id)
        source_column = f"__nbt_validation_{position}"
        validation[source_column] = y[:, position]
        configured.append(
            {
                "metric_key": NBT_METRIC_KEY,
                "source_column": source_column,
                "segment": _outcome_value(outcome, "segment", "unknown"),
                "markets": markets,
            }
        )
    assert_supplied_net_billthrough_complete(
        validation,
        frame.get("net_billthrough_metadata"),
        configured_outcomes=configured,
    )
