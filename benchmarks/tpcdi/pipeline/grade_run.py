"""Grade a runs/NAME/results.jsonl with the swap-in grader (same scope as the v4 prompt).
Writes runs/NAME/graded.json: one record per (column, model, repeat) with status/match_pct and the
NULL-control baseline, so scores on weakly-discriminating columns can be read as lift over baseline."""
import argparse, json, os, collections
import duckdb
import grade_swap as g
from grade_subset import clean_sql

HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser(); ap.add_argument("--run", required=True); a = ap.parse_args()
import gold_version as _gv
rd = os.path.join(HERE, _gv.RUNS_SUBDIR, a.run)
con = duckdb.connect(g.DB_PATH, read_only=True)
gold = g.load_gold()
null = json.load(open(os.path.join(HERE, "null_control_results" + __import__("gold_version").SUFFIX + ".json")))
cache = {}
latest = {}
for line in open(os.path.join(rd, "results.jsonl")):
    r = json.loads(line)
    k = (r["key"], r["model"], r["repeat"])
    if not r.get("error") or k not in latest:
        latest[k] = r
out = []
for (key, model, rep), r in sorted(latest.items()):
    table, col = key.split(".", 1)
    rec = {"key": key, "model": model, "repeat": rep, "null_baseline": (null.get(key) or {}).get("match_pct")}
    if r.get("error") or not r.get("sql"):
        rec.update(status="NO_ANSWER", error=r.get("error"))
    else:
        expr = clean_sql(r["sql"])
        ck = (key, expr)
        if ck not in cache:
            cache[ck] = g.grade_candidate(con, gold, table, col, expr)
        rec.update(cache[ck]); rec["expr"] = expr
    out.append(rec)
    print(f"{key:34s} {model:14s} #{rep} {rec['status']:17s} {str(rec.get('match_pct')):>7s} (null {rec['null_baseline']}) {(rec.get('error') or '')[:70]}".replace("\n", " "), flush=True)
json.dump(out, open(os.path.join(rd, "graded.json"), "w"), indent=1)
c = collections.defaultdict(collections.Counter)
for r in out:
    s = r["status"]
    c[r["model"]]["exact" if s == "EXECUTED" and r.get("match_pct") == 100 else ("partial" if s == "EXECUTED" and (r.get("match_pct") or 0) > 0 else ("wrong0" if s == "EXECUTED" else s.lower()))] += 1
for m, cc in c.items():
    print(m, dict(cc))
