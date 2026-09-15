"""WP8 regression tests for downloadable standard source templates."""

from __future__ import annotations

from ancestry_mmm.core.coverage import (
    DOMAIN_ACTIVITY_AND_MEDIA,
    DOMAIN_CONTEXT_AND_EXTERNAL_FACTORS,
    DOMAIN_EXPERIMENT_EVIDENCE,
    DOMAIN_OUTCOMES,
)
from ancestry_mmm.data.template_downloads import (
    build_standard_template,
    standard_template_filename,
)
from ancestry_mmm.data.templates import (
    EVENT_UPLOAD_COLUMNS,
    OUTCOMES_TEMPLATE_SCHEMA_VERSION,
    canonicalize_standard_workbook,
    parse_standard_workbook,
)


def test_downloadable_templates_are_valid_domain_workbooks():
    domains = (
        DOMAIN_OUTCOMES,
        DOMAIN_ACTIVITY_AND_MEDIA,
        DOMAIN_CONTEXT_AND_EXTERNAL_FACTORS,
        DOMAIN_EXPERIMENT_EVIDENCE,
    )
    for domain in domains:
        workbook = parse_standard_workbook(
            build_standard_template(domain),
            source_id=f"template-{domain}",
            filename=standard_template_filename(domain),
            logical_domain=domain,
        )
        assert workbook.manifest.valid_standard_template
        assert workbook.manifest.logical_domain == domain
        assert all(not table.empty for table in workbook.tables.values())
        canonicalize_standard_workbook(workbook)


def test_downloadable_context_template_events_sheet_has_all_preferred_columns():
    """The downloadable Context template's `events` sheet must carry the
    full seven-column preferred contract (`EVENT_UPLOAD_COLUMNS`), not
    only the legacy four columns - the legacy structure remains supported
    only as a compatibility path for older uploads, never the shipped
    template itself."""
    workbook = parse_standard_workbook(
        build_standard_template(DOMAIN_CONTEXT_AND_EXTERNAL_FACTORS),
        source_id="template-context",
        filename=standard_template_filename(DOMAIN_CONTEXT_AND_EXTERNAL_FACTORS),
        logical_domain=DOMAIN_CONTEXT_AND_EXTERNAL_FACTORS,
    )
    events_table = workbook.tables["events"]
    assert set(EVENT_UPLOAD_COLUMNS).issubset(set(events_table.columns))
    assert not events_table.empty


def test_outcomes_download_is_v2_and_contains_explicit_dna_partitions():
    workbook = parse_standard_workbook(
        build_standard_template(DOMAIN_OUTCOMES),
        source_id="outcomes-template",
        filename=standard_template_filename(DOMAIN_OUTCOMES),
        logical_domain=DOMAIN_OUTCOMES,
    )
    assert workbook.manifest.template_schema_version == OUTCOMES_TEMPLATE_SCHEMA_VERSION
    assert "outcome_completeness" not in workbook.tables
    dictionary = workbook.tables["outcome_dictionary"]
    assert set(dictionary["segment_dimension"]) >= {
        "fh_customer_segment",
        "dna_customer_relationship",
        "dna_purchase_recipient",
    }
    assert "cohort_basis" not in dictionary.columns
    assert "maturity_rule" not in dictionary.columns
    assert "owner" not in dictionary.columns
    assert "version" not in dictionary.columns
