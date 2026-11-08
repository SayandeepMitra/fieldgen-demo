"""Null-control over every gold column: swap NULL in, record the score. High score = the grader
cannot tell a wrong answer from the right one on that column (constant/NULL/low-variance column)."""
import json, duckdb
import grade_swap as g
con = duckdb.connect(g.DB_PATH, read_only=True)
gold = g.load_gold()
out = {}
for table, spec in gold.items():
    for col in spec["cols"]:
        r = g.null_control(con, gold, table, col)
        out[f"{table}.{col}"] = r
        print(table, col, r.get("match_pct"), r.get("status"), flush=True)
json.dump(out, open("null_control_results" + __import__("gold_version").SUFFIX + ".json", "w"), indent=1)
print("DONE")
