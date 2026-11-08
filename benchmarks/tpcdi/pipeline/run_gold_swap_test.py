"""Per-column gold self-swap: for every gold column, swap its OWN defining expression back in via
the same descent/requalify/cast path a model candidate takes. Must score 100% everywhere; any
miss is a bug in the grader (or non-determinism), not a model result."""
import json, duckdb
from sqlglot import exp
import grade_swap as g
con = duckdb.connect(g.DB_PATH, read_only=True)
gold = g.load_gold()
out = {}
for table, spec in gold.items():
    for col in spec["cols"]:
        ins = spec["insert"].copy()
        found = g.defining_select(ins, col)
        if found is None:
            out[f'{table}.{col}'] = {'status': 'NO_DEFINING_SELECT'}; print(table, col, 'NO_DEFINING_SELECT'); continue
        cur, i, name = found
        item = cur.expressions[i]
        ge = g._strip_alias(item).sql(dialect="duckdb")
        r = g.grade_candidate(con, gold, table, col, ge)
        out[f"{table}.{col}"] = r
        print(table, col, r.get("match_pct"), r["status"], (r.get("error") or "")[:100].replace("\n", " "), flush=True)
json.dump(out, open("gold_swap_results" + __import__("gold_version").SUFFIX + ".json", "w"), indent=1)
print("DONE")
