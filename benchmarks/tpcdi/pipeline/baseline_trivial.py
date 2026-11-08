"""Non-LLM baselines on the SAME swap-in task and the SAME given matching as the LLM runs.
  trivial_name : of the matched source fields in scope, pick the one whose name is closest to the target column
                 (exact after case/underscore folding, else difflib ratio, else the first); emit it unchanged. NULL if none.
  trivial_mode : emit the most frequent value of the target column in T as a constant (the best constant guess).
Writes runs/baseline_trivial/graded.json in grade_run.py's format so score_clean.py reads it like any model."""
import difflib, json, os, re
import duckdb
import grade_swap as g
import scope_prompt as sp

HERE = os.path.dirname(os.path.abspath(__file__))
fold = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
gold = g.load_gold()
con = duckdb.connect(g.DB_PATH, read_only=True)
null = json.load(open(os.path.join(HERE, "null_control_results" + __import__("gold_version").SUFFIX + ".json")))
out = []
for table, s in gold.items():
    for col in s["cols"]:
        key = f"{table}.{col}"
        base = (null.get(key) or {}).get("match_pct")
        try:
            sc = sp.derive_scope(gold, con, table, col)
            refs = sc["refs"] if sc else []
        except Exception:
            refs = []
        if refs:
            tgt = fold(col)
            best = max(refs, key=lambda r: (fold(r["col"]) == tgt, difflib.SequenceMatcher(None, tgt, fold(r["col"])).ratio()))
            expr_name = f'{best["alias"]}.{best["col"]}'
        else:
            expr_name = "NULL"
        r = con.execute(f'select "{col}", count(*) c from {table} group by 1 order by c desc limit 1').fetchone()
        v = r[0]
        expr_mode = "NULL" if v is None else ("'" + str(v).replace("'", "''") + "'")
        for model, expr in (("trivial_name", expr_name), ("trivial_mode", expr_mode)):
            res = g.grade_candidate(con, gold, table, col, expr)
            out.append({"key": key, "model": model, "repeat": 0, "null_baseline": base, **res, "expr": expr})
        print(key, out[-2]["status"], out[-2].get("match_pct"), "|", out[-1].get("match_pct"), flush=True)
rd = os.path.join(HERE, __import__("gold_version").RUNS_SUBDIR, "baseline_trivial"); os.makedirs(rd, exist_ok=True)
json.dump(out, open(os.path.join(rd, "graded.json"), "w"), indent=1)
