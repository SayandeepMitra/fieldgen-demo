"""Which gold every grader uses. Set TPCDI_GOLD=v1 (R1's ETL as ported, 72/89 audit) or v2 (repaired, 89/89 audit).

All graders (grade_swap, l2_grade, l2_run, gold_audit, build_prompt, build_clean_subset ...) import their paths from here,
so one environment variable switches the whole stack and every number can be reproduced against either gold.
Default is v2 (cut over 2026-11-06); TPCDI_GOLD=v1 reproduces the earlier numbers. The v2 files are never mixed with v1 files.
"""
import os

BENCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(BENCH, "deliverables")
VERSION = os.environ.get("TPCDI_GOLD", "v2")      # default flipped to v2 on 2026-11-06; TPCDI_GOLD=v1 reproduces the old numbers
if VERSION not in ("v1", "v2"):
    raise SystemExit(f"TPCDI_GOLD must be v1 or v2, got {VERSION!r}")
_s = "" if VERSION == "v1" else "_v2"

GOLD_SQL = os.path.join(D, f"ported_historical_load{_s}.sql")
GOLD_DB = os.path.join(D, f"tpcdi_populated{_s}.duckdb")
TARGET_DDL = os.path.join(D, f"tpcdi_target_schema{_s}.sql")
AUDIT_CSV = os.path.join(D, f"gold_audit_results{_s}.csv")
CLEAN_SUBSET_CSV = os.path.join(D, f"tpcdi_clean_subset{_s}.csv")
RUNS_SUBDIR = "runs" if VERSION == "v1" else os.path.join("runs", "v2")   # graded outputs against v2 live apart from v1's
SUFFIX = _s                      # "" for v1, "_v2" for v2: appended to result files keyed to a gold (null_control_results, graded, ...)
MAPPING_CSV = os.path.join(D, f"tpcdi_column_mapping{_s}.csv")
