# Ancestry MMM upload-guide file-validation review

Status: complete for the supplied implementation brief.

## Scope and exact baseline

- Implementation brief: `D:\ORIGIAL D DRIVE\008 Ancestry UK MMM - 2026\LLM_Instructions_Fix_MMM_Excel_Builders_and_HTML_Contrast.md`
- Repository: `D:\App Projects\Media-Mix-Lab`
- Branch: `agent/uk-production-data-onboarding`
- Exact baseline SHA: `2bd8e9a8a197f121d1176e61566d6122313e44e9`
- This work is limited to the guide, its documentation/tooling generator, the contrast checker, and the generated builders. Parser, schema, ID contract, model, and governance behaviour were not changed.
- Existing unrelated worktree changes were preserved: `.mcp.json`, `ancestry_mmm/core/outcome_group_totals.py`, `ancestry_mmm/tests/test_official_lifecycle_browser.py`, `.playwright-mcp/`, `designs/`, and `tools/`.

## Corrected deliverables

- `Ancestry_MMM_Data_Upload_Guide.html`
- `Ancestry_MMM_Outcome_ID_Builder.xlsx`
- `Ancestry_MMM_Activity_ID_Builder.xlsx`
- `Ancestry_MMM_Context_Variable_ID_Builder.xlsx`
- `Ancestry_MMM_Data_Upload_Guide_File_Validation_REVIEW.md` (this report)
- Supporting generator/checker: `scripts/build_data_upload_guide_assets.py` and `scripts/check_data_upload_guide_contrast.py`.

All three builders retain the visible `ID Builder`, `Reference`, `Read me`, and `Examples` sheets. The visible candidate tables retain editable fields, dropdowns, RAG guidance, suggested IDs, manual overrides, final IDs, collision/completeness warnings, and dictionary previews. Activity identity continues to distinguish `activity_id`, `model_input_measure`, `model_input_column`, `source`, and `pooling_group_id` in the companion guidance. Outcome identity semantics remain product + metric + segment; `segment_dimension` remains explicit dictionary meaning and is not silently added to the stable ID.

## Excel corruption root cause and repair

The initial generated files were ZIP-valid, XML-parseable, and loadable by openpyxl, but Microsoft Excel 16.0 failed to open all three through COM with `0x800A03EC` (“Unable to get the Open property of the Workbooks class”). A known unrelated workbook opened successfully in the same Excel COM environment.

Controlled probes isolated two OOXML/formula causes:

1. The candidate sheet had both an Excel Table-owned AutoFilter and a worksheet-level AutoFilter over the same range. The feature probe showed that table + worksheet AutoFilter failed while table + data validation, table + conditional formatting, and table + calculation opened. The worksheet-level filter was removed; the Table retains its normal AutoFilter. The Reference filter range was also corrected from `A:G` to the complete `A:J` range.
2. The original Outcome and Activity formulas used a single-letter `LET` binding named `c`. Excel treats `c` as an invalid R1C1-style name in that context. Descriptive binding names removed that parse failure during diagnosis.

The final rebuild removes the fragile dependency altogether: staged hidden helper columns use broadly compatible `LOWER`, `TRIM`, `SUBSTITUTE`, `IF`, `OR`, `LEFT`, `RIGHT`, `MID`, and `LEN` functions. The visible ID formulas join those helper tokens with ordinary conditional concatenation. This keeps formulas below Excel's 8,192-character limit and avoids VBA, external links, and newer-function markers. The output contains one standard Excel Table per builder and no worksheet-level filter over that table.

## Microsoft Excel validation

Final validation used Microsoft Excel 16.0 through COM with `Visible = false`, `DisplayAlerts = false`, and read-only opens. Each workbook opened, recalculated, reported four worksheets, and closed cleanly:

| Workbook | Result | Calculated example |
|---|---|---|
| `Ancestry_MMM_Outcome_ID_Builder.xlsx` | Opened; 4 sheets; no recovery prompt/log | `family_history_fh_gsa_new` |
| `Ancestry_MMM_Activity_ID_Builder.xlsx` | Opened; 4 sheets; no recovery prompt/log | `paid_search_google_brand_google_brand_search` |
| `Ancestry_MMM_Context_Variable_ID_Builder.xlsx` | Opened; 4 sheets; no recovery prompt/log | `rate_index_uk_cpi` |

No automation Excel process remained after validation. The only remaining `EXCEL.EXE` process was the pre-existing user workbook `D:\db\Analysis FINAL - NEW 2.xlsm`; it was not touched.

### Repair-log review

The historical Excel recovery log `D:\Temp\error137800_01.xml` was inspected. It records the pre-fix Outcome workbook and exactly the removed AutoFilter, Table, and Formula features. No new Excel recovery log was produced by the final three-workbook validation. The separate `D:\Temp\claude\...\named_event_recovery.log` is a pytest scratchpad, not an Excel repair log.

## OOXML, workbook, and formula checks

For each final workbook:

- ZIP CRC test passed.
- Every XML and `.rels` part parsed successfully.
- Every internal relationship target resolved to an existing package part.
- Four expected sheets were present.
- One Table and one Table-owned AutoFilter were present.
- Formula error tokens `#REF!`, `#VALUE!`, `#NAME?`, `#N/A`, and `#DIV/0!` were absent from formula text.
- No formula exceeded 8,192 characters.
- Data validations were present: Outcome 3, Activity 2, Context 1.
- Hidden helper columns were outside the visible candidate tables.

The live Excel formula suite tested each builder with populated values, spaces, punctuation, mixed case, blank optional fields, `nan`/`none`/`n/a` sentinels, manual override, generated duplicates, and manual duplicates. Results were:

- Outcome: `family_history_gsa_uk_new_existing`; blank-field result `family_history_gsa_uk`; sentinel result blank; override trimmed to `manual.override / 1`; both duplicate warnings detected.
- Activity: `paid_search_google_ads_brand_test_brand_search`; blank-field result `paid_search_google_ads_brand_test`; sentinel result blank; override trimmed to `manual.override / 1`; both duplicate warnings detected.
- Context: `rate_index_uk_cpi`; blank-field result `rate_index`; sentinel result blank; override trimmed to `manual.override / 1`; both duplicate warnings detected.

## Parser and domain validation

The ID-builder workbooks are companion tools, not standard source-pack inputs, so they were not falsely passed to the source-pack parser as if their four helper sheets were domain tables. Instead, the repository's actual standard source templates were generated, parsed, and canonicalised for Outcomes, Activity and Media, and Context and External Factors:

| Domain | Parser | Canonicalisation |
|---|---|---|
| Outcomes | valid; expected tables recognised | valid; 10 outcome definitions |
| Activity and Media | valid; expected tables recognised | valid; model-input media shape `[2, 3]` |
| Context and External Factors | valid; expected tables and optional events recognised | valid; native context shape `[2, 3]` |

Focused regression tests passed:

```text
28 passed in 21.49s
```

Command:

```text
\.venv\Scripts\python.exe -m pytest --no-cov -q ancestry_mmm/tests/test_templates.py ancestry_mmm/tests/test_outcome_source_pack_v2.py ancestry_mmm/tests/test_source_pack_adoption_wp3.py ancestry_mmm/tests/test_template_downloads_wp8.py
```

## HTML contrast and browser review

The HTML repair changed the raw code/example blocks to a light background with dark text, made inline code readable, set the dark-sidebar title to white, and supplied visited-link colours for light and dark surfaces. The page remains self-contained with no external assets or network calls.

The automated checker is `scripts/check_data_upload_guide_contrast.py`. It computes effective backgrounds through transparent ancestors and applies WCAG AA thresholds of 4.5:1 for normal text and 3:1 for large text. Final result:

```json
{
  "audited": 1591,
  "contrast_failures": 0,
  "missing_anchors": 0,
  "duplicate_ids": 0,
  "console_errors": 0,
  "page_errors": 0,
  "faq_open": true,
  "search_works": true,
  "horizontal_overflow": {
    "1440x900": false,
    "1280x720": false,
    "390x844": false
  }
}
```

The guide was independently exercised in Chromium at the required desktop and mobile viewports. Navigation anchors, back-to-top, FAQ expansion, wide-table scrolling, search/filtering, and mobile layout were checked. Screenshots were captured and manually inspected at:

- `D:\Temp\mmm_guide_screenshots\01-top-navigation.png`
- `D:\Temp\mmm_guide_screenshots\02-outcomes.png`
- `D:\Temp\mmm_guide_screenshots\03-activity.png`
- `D:\Temp\mmm_guide_screenshots\04-context.png`
- `D:\Temp\mmm_guide_screenshots\05-advanced.png`
- `D:\Temp\mmm_guide_screenshots\06-faq.png`
- `D:\Temp\mmm_guide_screenshots\07-mobile.png`

The first contrast pass found one genuine failure: the sidebar `h2` rendered navy text on the navy sidebar at a 1:1 ratio. It was repaired to white and the independent pass returned zero failures. Wide RAG tables intentionally remain horizontally scrollable inside their table containers; they do not create page-level clipping or overflow.

## Review findings and status

Two repair/review passes were completed, with an additional live Excel calculation check after the first formula-compatible rebuild. The initial Excel open failure and the initial sidebar contrast failure were fixed and re-tested. No parser, source contract, ID semantic, model, or governance changes were needed.

The required Graphify refresh was attempted with `scripts\run_graphify_cli.ps1 update .`; the repository wrapper stopped it because the configured `UV_TOOL_BIN_DIR` (`D:\DevTools\uv\tool-bin`) is outside the configured `D:\Ancestry-MMM` root. This did not affect the source, workbook, parser, or browser validation results.

No Critical or High file-validity or readability issues remain.

The older guide review records two pre-existing Medium application-boundary follow-ups (DNA label spelling reconciliation and standard-upload Search taxonomy mapping). They are outside this file-validity/readability repair and were not silently changed here.
