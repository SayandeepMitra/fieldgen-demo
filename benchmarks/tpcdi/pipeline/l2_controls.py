"""Validation controls for the L2 grader (run these before trusting an L2 number).
  C1 gold-as-pipeline        : the gold's own per-table SQL, run from scratch in the sandbox, must score 100% on every column
                                 and reproduce the official audit (done by l2_run.py on runs/l2/_subs/gold_pipeline; see FINDINGS).
  C2 empty pipeline          : no SQL at all -> every table MISSING, every column 0 (floor).
  C3 L1 <-> L2 consistency   : take an LLM expression graded at L1 (swap-in), put it into the gold's table query, run that
                                 table through the L2 pipeline path, and compare L2 strict column score with the L1 match_pct.
                                 They must agree for ordinary columns (L1 and L2 see the same wrong cells). They are expected to
                                 DIFFER for foreign-SK columns (L1 compares the number, L2 the entity it points to) - reported apart.
usage: python l2_controls.py [--n 18]
"""
import argparse, json, os, shutil, sys
import duckdb
import grade_swap as g, l2_grade, l2_run

HERE = os.path.dirname(os.path.abspath(__file__))


def c2_empty():
    d = os.path.join(l2_run.RUNS, "_subs", "empty"); os.makedirs(d, exist_ok=True)
    rd, db, ex = l2_run.run_submission(d, "ctrl_empty")
    res = l2_grade.grade(db)
    s = l2_grade.summarise(res)
    ok = all(v["status"] == "MISSING" or v["cand_rows"] == 0 for v in res["tables"].values()) and s["columns_exact_all"].startswith("0/")
    return {"summary": s, "pass": bool(ok)}


def pick(n):
    graded = json.load(open(os.path.join(HERE, __import__("gold_version").RUNS_SUBDIR, "ab_v5a", "graded.json")))
    gold = g.load_gold()
    rows = []
    for r in graded:
        t, c = r["key"].split(".", 1)
        if t not in gold or t in ("DimTrade",) and False:
            continue
        idc = l2_grade.IDENTITY.get(t, [])
        if c in idc or l2_grade.is_self_sk(t, c):
            continue
        fk = bool(l2_grade.fk_dim(t, c))
        if r["status"] == "EXECUTED" and 0 < (r["match_pct"] or 0) < 99.995:
            rows.append((fk, r))
    plain = [r for fk, r in rows if not fk]; fks = [r for fk, r in rows if fk]
    seen, out = set(), []
    for r in plain[: 400]:
        if r["key"] in seen: continue
        seen.add(r["key"]); out.append(("plain", r))
        if len([1 for k, _ in out if k == "plain"]) >= n - 4: break
    for r in fks:
        if r["key"] in seen: continue
        seen.add(r["key"]); out.append(("fk", r))
        if len([1 for k, _ in out if k == "fk"]) >= 4: break
    return out


def c3(n):
    gold = g.load_gold(); con = duckdb.connect(g.DB_PATH, read_only=True)
    res = []
    for kind, r in pick(n):
        t, c = r["key"].split(".", 1)
        types = g.column_types(con, t)
        sub = os.path.join(l2_run.RUNS, "_subs", f"swap_{t}_{c}"); os.makedirs(sub, exist_ok=True)
        cols = gold[t]["cols"]
        sql = g.probe_query(gold, t, c, r["expr"], types)
        open(os.path.join(sub, f"{t}.sql"), "w").write(f"INSERT INTO {t} ({', '.join(cols)}) {sql};\n")
        rd, db, ex = l2_run.run_submission(sub, f"ctrl_swap_{t}_{c}", keep_gold_except=[t])
        out = l2_grade.grade(db, only=[t])
        l2 = out["tables"][t]["columns"][c]["pct_ref"]
        res.append({"key": r["key"], "kind": kind, "model": r["model"], "L1_match_pct": r["match_pct"], "L2_pct_ref": l2,
                    "agree": abs((r["match_pct"] or 0) - (l2 or 0)) < 0.01})
        print(res[-1], flush=True)
        shutil.rmtree(rd, ignore_errors=True)               # sandbox copies are ~0.5 GB each
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=18); a = ap.parse_args()
    out = {"C2_empty": c2_empty()}
    print("C2", out["C2_empty"], flush=True)
    out["C3_swap_consistency"] = c3(a.n)
    plain = [x for x in out["C3_swap_consistency"] if x["kind"] == "plain"]
    out["C3_plain_agree"] = f"{sum(x['agree'] for x in plain)}/{len(plain)}"
    json.dump(out, open(os.path.join(l2_run.RUNS, "ctrl_results.json"), "w"), indent=1)
    print(out["C3_plain_agree"])
