# TPC-DI benchmark for fieldgen

**fieldgen** (this repository) writes SQL that converts a source database into a target data model. **TPC-DI is a benchmark for it**, next to the Synthea → OMOP example
(`../../examples/synthea_omop`). The benchmark was built for CS5663 "Database Transformation for a Target Schema" (course project, IIT Hyderabad).

Source S = the 31 `Source.*` tables parsed from TPC-DI data (DIGen, SF=3, Batch 1, 4.6 M rows). Target T = the TPC-DI warehouse (20 tables, 16 populated, 210 columns).
Reference ("gold") = SQL that loads T from S. fieldgen's SQL (or any pipeline's) is run on S alone and the tables it builds are compared with the gold's.

**Read first:** `PROGRESS.md` (status, numbers, TODO), `BENCHMARKS_synthea_omop_vs_tpcdi.md` (the two benchmarks compared, and fieldgen's first TPC-DI result),
`deliverables/GOLD_V2_CHANGES.md` (defects repaired in the gold), `deliverables/README.md` (which file is v1 vs v2), `pipeline/L2_README.md` (table-level grader),
`fieldgen_run/README_RESULT.md` (how fieldgen was run on it), `FINDINGS.md` (long log of what was done and why), `docs/project_plan.md`.

## Status against the course roadmap (4 stages)
1. **Ground truth: done for TPC-DI.** Source, target and gold (v2: official audit 89/89, independent dbt cross-check in `gold_crosscheck/`). The target is TPC-DI's real warehouse, not a model-generated schema. Second benchmark: Synthea → OMOP (existing).
2. **Query synthesis: fieldgen is the system.** First run on TPC-DI, unchanged and untuned, one replicate: 88/210 columns exact (core 85/196, hard 5/70), 9/16 tables with correct rows. Our per-column prompt arms (L1, frozen prompt v5a: 158/196 core, 33/70 hard for Nemotron) are **baselines** that are handed the gold's table skeleton.
3. **Equivalence check: done on our side** (L1 swap-in grader, L2 table grader, official audit, controls). Not yet connected to fieldgen's own scorer: the gold has not been exported in fieldgen's reference format, so `fieldgen test`, L4 and the leak test do not run on TPC-DI yet.
4. **Reverse execution: not started.**
Limits: `PROGRESS.md` and `deliverables/GOLD_V2_CHANGES.md` ("Verification and its limits").

## Reproduce
Not in the repository (size and licences): the TPC-DI kit and generated data (`tpcdi/tpcdi-kit/`, TPC and bankmark licences), the DuckDB databases, graded sandboxes. See `../../LICENSES.md`.
Run the commands from `benchmarks/tpcdi`; scripts import siblings, so run them from `pipeline/` without `-I`.

```bash
# 0. environment (Python 3.13 was used); fieldgen itself: pip install -e ../..  (from this folder)
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && pip install -e ../..

# 1. data: obtain the TPC-DI kit from tpc.org, generate SF=3 into tpcdi/tpcdi-kit/staging/3/ (needs Java 8; on Apple Silicon x86 Java 8 + Rosetta).
#    The problems met and the commands that worked: FINDINGS.md ("Hurdle 1-3").

# 2. load Source.* into tpcdi/work/tpcdi.duckdb and run R1's ported load (v1 gold)
bash tpcdi/work/rebuild_all.sh
cp tpcdi/work/tpcdi.duckdb deliverables/tpcdi_populated.duckdb
#    v2 only uses the Source.* tables of this file. The v1 target tables may differ slightly from the v1 numbers in the logs: the original deliverable
#    database was patched once later (backup `tpcdi_populated.duckdb.bak_before_cashflag_fix`); this rebuild path has not been re-run since the move into fieldgen.

# 3. build the repaired gold (7 s), audit it, run its checks
cd pipeline
python build_gold_v2.py
python gold_audit.py            # TPCDI_GOLD=v2 is the default; =v1 reproduces the earlier numbers
python gold_checks_v2.py

# 4. grade a pipeline: SUBMISSION_DIR holds one <Table>.sql per target table
python l2_run.py SUBMISSION_DIR --name NAME --audit

# 5. fieldgen on TPC-DI: see fieldgen_run/README_RESULT.md (build_package.py, run_fieldgen.py), then
python fieldgen_to_l2.py convert ../fieldgen_run/rep1/run OUT_DIR && python l2_run.py OUT_DIR --name NAME --audit

# 6. per-column baselines need a free NVIDIA key (export NVIDIA_API_KEY=...; never commit a .env). Example:
python run_v4.py --run ab_v5a --prompt v5a --models nemotron,mistral_large && python grade_run.py --run ab_v5a && python score_clean.py ab_v5a
```
All paths in the scripts are relative to their own location. `pipeline/.env.example` lists `OPENROUTER_API_KEY` (old runs); the NVIDIA-hosted runs read `NVIDIA_API_KEY`.
`fieldgen_run/run_gen.sh` expects `../pipeline/.env`; the virtualenv it used (`fieldgen_run/venv`) is not kept: recreate it with `pip install -e ../..`.
