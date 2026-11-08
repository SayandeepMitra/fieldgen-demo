"""
End-to-end demo of the Phase C harness for ONE target column: Level 1 (table skeleton) + Level 2
(column prompt, with profiling) -> call all 3 models (or dry-run without an API key) -> show the
held-out ground truth from tpcdi_column_mapping.csv for comparison (this is what Phase D would
grade the model outputs against -- never shown to the models themselves).
"""
import csv
import duckdb

from build_prompt import build_column_prompt, DB_PATH
from call_llm import run_all_models, MODELS
import os

MAPPING_CSV = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))), "deliverables/tpcdi_column_mapping.csv")


def get_ground_truth(target_table, target_column):
    with open(MAPPING_CSV, newline="") as f:
        for r in csv.DictReader(f):
            if r["target_table"] == target_table and r["target_column"] == target_column:
                return r
    return None


def run(target_table, target_column):
    con = duckdb.connect(DB_PATH, read_only=True)

    print(f"\n{'='*100}\nDEMO: {target_table}.{target_column}\n{'='*100}")

    prompt = build_column_prompt(target_table, target_column, con)
    print("--- PROMPT SENT TO EACH MODEL ---")
    print(prompt)

    print("--- MODEL OUTPUTS ---")
    if os.environ.get("OPENROUTER_API_KEY"):
        responses = run_all_models(prompt)
        for key, resp in responses.items():
            print(f"[{key} / {MODELS[key]}]\n{resp}\n")
    else:
        print("(OPENROUTER_API_KEY not set -- no live calls made this run. Would call:", list(MODELS.values()), ")")

    print("--- HELD-OUT GROUND TRUTH (never shown to the models -- for Phase D grading) ---")
    gt = get_ground_truth(target_table, target_column)
    if gt:
        print(f"  rule_sql:       {gt['rule_sql']}")
        print(f"  column_kind:    {gt['column_kind']}")
        print(f"  rule_reliable:  {gt['rule_reliable']}")
        print(f"  notes:          {gt['notes']}")
    else:
        print("  (not found in mapping CSV)")


if __name__ == "__main__":
    run("DimCompany", "Industry")
    run("DimCompany", "FoundingDate")
