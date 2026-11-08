# fieldgen run on TPC-DI (one replicate)

What this folder is: the `fieldgen` CLI (this repository's tool) run unchanged on our TPC-DI benchmark, graded by our L2 grader.
Results and discussion: `../BENCHMARKS_synthea_omop_vs_tpcdi.md` §C–D. Numbers (gold v2, strict L2): 9/16 tables with correct rows, 88/210 columns exact
(core 85/196, hard 5/70), official audit 34/78; tables fieldgen built itself: 10/16, 103/210.

Files kept: `build_package.py` (fills the fieldgen package), `run_fieldgen.py` (CLI wrapper), `run_gen.sh`, `compare_to_compose.py`,
`rep1/run/` (calls.jsonl, recipes, formulas, **sql/** = the generated SQL per table, report.md, summary.json).
Not kept in git (size / reproducible): `base_pkg/`, `rep1/pkg/`, `rep1/run/built_parquet`, `source_only.duckdb`, the virtualenv.

Package choices (see `build_package.py`): all 31 `Source.*` tables, the target DDL, the **given matching** (`tpcdi_column_mapping.csv` value columns only;
`rule_sql` is never read), spec Clause 3.2 descriptions as target guidance, spec Clause 4.4.1/4.4.2 conventions as domain knowledge (same text as frozen prompt v5a).
The gold SQL and target data were never read. Model: Nemotron-3.5-super-120B via the NVIDIA free endpoint, 4 requests/min, 1 worker.
Two mechanical overrides in `run_fieldgen.py`: raise the 20 MB source-file cap, and read memory size via `sysctl` on macOS.

Run cost: 383 calls (33 failed), 1.42 M tokens in / 0.76 M out, ~2 h 20 min.
Replicate 2 was started and stopped at 54/205 formulas after a network stall (its folder is not kept): fieldgen's run-to-run noise on TPC-DI is **not measured**.
Grade: `python ../pipeline/fieldgen_to_l2.py convert rep1/run OUT_DIR` then `python ../pipeline/l2_run.py OUT_DIR --name NAME --audit`
(or `fieldgen_to_l2.py built ...` for the tables fieldgen built itself).
