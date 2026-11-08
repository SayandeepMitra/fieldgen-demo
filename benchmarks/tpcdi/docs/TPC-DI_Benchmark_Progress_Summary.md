# TPC-DI Benchmark — Progress Summary

Sep 23, 2026 · @Kaustubh

## What TPC-DI Is

TPC-DI is TPC's benchmark for data-integration (ETL) workloads: source data in flat files transforms into a 20-table warehouse, under rules TPC publishes only as English prose, never code. For this project it supplies one concrete, fully-verified `(S, D, T, transformation)` example — source schema, source data, target schema, and ground-truth queries — to build and test an automatic schema-transformation query generator against.

## Key Numbers

| Metric | Value |
| --- | --- |
| Target schema (`T`) | 20 tables, 30 foreign keys, 241 columns |
| Source schema (`S`) | 31 tables (extracted from `schema.sql`) |
| Generated data (`D`), scale factor 3 | 4,579,717 rows, 267.1 MiB, 3 batches, generated in 6.5s |
| Columns classified (Task A3 sample) | 58 total — DimCustomer 33, DimAccount 11, FactMarketHistory 14 |
| Plain-copy rate on that sample | 10.3% (37.9% including rename) vs. doc's whole-schema \~60% estimate |
| DuckDB load result | 51 tables total (20 `T` + 31 `S`), zero errors |
| Bonus `D`→`S` load test | 1,689,746 rows (Trade, HR, DailyMarket) loaded with zero cast errors |

## Existing Files & Repos

| Item | Role |
| --- | --- |
| `Course_Projects-23-33.pdf` | Research problem statement + 4-stage pipeline |
| `benchmark_evaluation.pdf`/`.tex` | Task doc driving Tasks A1–A5 (TPC-DI) / B1–B5 (MIMIC) |
| `tpcdi_target_schema.sql` | `T`, pre-supplied, 20 tables |
| R1 `TPC-DI-MS-SQL-Benchmark` (cloned) | Source of `S` (`schema.sql`) and the transformation (`historical_load.sql`) |
| R2 `tpcdi-kit` (cloned) | Source of `D` — bundles the real `DIGen.jar` generator |
| R3 `dbtpcdi` (cloned) | Cloud-only dbt implementation; has a reference `FactMarketHistory` |

## Files Created

| File | Contents |
| --- | --- |
| `benchmark/FINDINGS.md` | Full task-by-task log |
| `benchmark/deliverables/tpcdi_source_schema.sql` | `S`, 31 tables, portable SQL |
| `benchmark/deliverables/tpcdi_target_schema.sql` | `T`, 20 tables |
| `benchmark/deliverables/tpcdi_transformations.csv` | 58 columns classified by transformation category |
| `benchmark/deliverables/load_schemas.py` | Reusable DuckDB loader script |
| `benchmark/deliverables/tpcdi.duckdb` | Schema-only DB, 51 tables, 1.5 MB |
| `benchmark/tpcdi/tpcdi-kit/staging/3/` | Full generated `D`, 267.1 MiB |
| `benchmark/sample_data/tpcdi_sf3/` | 108 KB representative sample of `D` |
| `project_plan.md` | Living status tracker |

## Work Completed (Tasks A1–A5)

1. **A1 — Clone & survey (R1).** Cloned `TPC-DI-MS-SQL-Benchmark`. Confirmed `historical_load.sql` (911 lines) and `CreateDBTableSchema.sql` (310 lines) exist as expected.
2. **A2 — Locate `S`.** `CreateDBTableSchema.sql` turned out to be a second copy of `T`, not `S`. Real `S` found in `schema.sql` (684 lines): `CREATE SCHEMA Source` + 31 `Source.*` staging tables.
3. **A3 — Classify transformations.** Classified 58 columns across `DimCustomer` (33), `DimAccount` (11), `FactMarketHistory` (14) into copy/rename/lookup join/SCD history/etc. Found `FactMarketHistory`'s INSERT is fully commented out and abandoned in R1. Plain-copy rate: 10.3% — lower than the doc's \~60% whole-schema estimate because this sample was deliberately the hardest 3 tables.
4. **A4 — Generate `D`.** Cloned R2/R3. R2's `Tools.zip` bundles the real `DIGen.jar` v1.1.0 (no tpc.org registration needed). Fixed 4 runtime hurdles: jar-in-jar classloader failure, PDGF needing a genuine Java 8 runtime (user installed via Homebrew), Apple Silicon incompatibility (fixed via Rosetta 2), and a separate PDGF/bankmark UG end-user license (reviewed and approved by the user). Generated SF=3: 4,579,717 rows, 267.1 MiB, in 6.5 seconds.
5. **A5 — Load & validate.** Extracted `tpcdi_source_schema.sql`, loaded both schemas into DuckDB (51 tables, zero errors). Loaded 3 real generated files (Trade, HR, DailyMarket — 1.69M rows) directly into the extracted `S` tables with zero casting errors, confirming `S` and `D` are a genuinely matched pair.

## Usability For Next Stages

All four pieces (`S`, `D`, `T`, transformation) are in hand, portable (DuckDB), and cross-validated end to end. This unblocks:

- **Stage 2, Query Synthesis** — ready now: feed the generator `D`, `S`, `T` and produce candidate queries `{Q}`.
- **Stage 3, Equivalence Check** — ready: the SF=3 dataset is small enough to execute `{Q}` vs. `{Q̂}` and compare quickly.
- **Stage 4, Reverse Execution** — feasible: a real `D` exists to measure reconstruction distance against.
- **Stage 1, Ground Truth Generation** — largely bypassed: `historical_load.sql` is a real, human-written ground truth, not something that needs synthesizing.

## Known Gaps

- `FactMarketHistory` has no working transformation in R1 (abandoned mid-write); R3 (`dbtpcdi`) has a working BigQuery/Jinja version, not yet ported.
- Task A3's classification sampled only 3 of 20 target tables, deliberately the hardest ones — not yet representative of the whole schema.
- MIMIC-IV → OMOP (Tasks B1–B5) not started — no second benchmark yet to compare TPC-DI against.
