"""Paired comparison of two graded runs (same columns, same models): totals, wins, regressions.
usage: compare_runs.py OLD_RUN NEW_RUN"""
import csv, json, sys, collections
old_run, new_run = sys.argv[1], sys.argv[2]
HERE = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))
m = {f"{r['target_table']}.{r['target_column']}": r for r in csv.DictReader(open(f"{HERE}/deliverables/tpcdi_column_mapping.csv"))}
load = lambda n: {(r["key"], r["model"]): r for r in json.load(open(f"{HERE}/pipeline/runs/{n}/graded.json")) if r["repeat"] == 0}
A, B = load(old_run), load(new_run)
def cls(r):
    if r is None or r["status"] != "EXECUTED": return "fail"
    p = r["match_pct"]; return "exact" if p >= 99.995 else ("partial" if p >= 50 else "wrong")
models = sorted({k[1] for k in B}); keys = sorted({k[0] for k in B})
rel = [k for k in keys if m[k]["rule_reliable"] != "no"]
for label, ks in (("RELIABLE-GOLD", rel), ("ALL 210", keys)):
    print(f"\n{label} ({len(ks)} cols): exact  {old_run} -> {new_run}")
    for mo in models:
        a = sum(cls(A.get((k, mo))) == "exact" for k in ks); b = sum(cls(B.get((k, mo))) == "exact" for k in ks)
        fa = sum(cls(A.get((k, mo))) == "fail" for k in ks); fb = sum(cls(B.get((k, mo))) == "fail" for k in ks)
        print(f"  {mo:14s} {a:4d} -> {b:4d}  ({b-a:+d})   fail-to-run {fa} -> {fb}")
for mo in models:
    win = [k for k in rel if cls(A.get((k, mo))) != "exact" and cls(B.get((k, mo))) == "exact"]
    reg = [k for k in rel if cls(A.get((k, mo))) == "exact" and cls(B.get((k, mo))) != "exact"]
    print(f"\n{mo}: {len(win)} columns became exact, {len(reg)} regressed (reliable gold)")
    print("  WINS:", ", ".join(f"{k}[{m[k]['column_kind']}]" for k in win))
    print("  REGRESSIONS:", ", ".join(f"{k}[{m[k]['column_kind']}] {A[(k,mo)].get('match_pct')}->{B.get((k,mo),{}).get('match_pct')}" for k in reg))
