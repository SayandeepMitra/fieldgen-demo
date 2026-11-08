# deliverables: which file belongs to which gold

Gold **v2** (repaired, default since 2026-11-06) is the benchmark's reference. Gold **v1** (R1's `historical_load.sql` ported to DuckDB, defects preserved) is kept only to
reproduce earlier numbers. `TPCDI_GOLD=v1|v2` (see `pipeline/gold_version.py`) switches every grader; v2 is the default.

| artefact | v1 | v2 |
|---|---|---|
| gold SQL | `ported_historical_load.sql` | `ported_historical_load_v2.sql` |
| target DDL | `tpcdi_target_schema.sql` | `tpcdi_target_schema_v2.sql` (CurrentPrice, Dividend now NUMERIC) |
| populated target DB (not in git, rebuilt) | `tpcdi_populated.duckdb` | `tpcdi_populated_v2.duckdb` (`pipeline/build_gold_v2.py`) |
| official audit | `gold_audit_results.csv` (72/89) | `gold_audit_results_v2.csv` (89/89) |
| audit findings | `gold_audit_findings.csv` | `gold_audit_findings_v2.csv` |
| own checks | `gold_v1_checks.csv` | `gold_v2_checks.csv` (30/30) |
| clean subset | `tpcdi_clean_subset.csv` (171 core, 37 hard) | `tpcdi_clean_subset_v2.csv` (196 core, 70 hard) |
| column mapping | `tpcdi_column_mapping.csv` | `tpcdi_column_mapping_v2.csv` |

Shared by both: `tpcdi_source_schema.sql`, `tpcdi_split.csv` (dev/test), `tpcdi_spec_target_descriptions.json`, `tpcdi_transformations.csv`, `FROZEN_PROMPT.json`, `load_schemas.py`.
`GOLD_V2_CHANGES.md` lists every repaired defect. The `tpcdi.duckdb` (source + empty targets) is also rebuilt by `tpcdi/work/rebuild_all.sh`.
