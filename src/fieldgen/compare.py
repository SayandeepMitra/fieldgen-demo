"""Comparison helpers of the scorer (reference side; never used by the generator): normalisation, reference rows, row comparison, key property."""
import csv, json, os, re, decimal, datetime
from collections import Counter, defaultdict
from fieldgen.assemble_v1 import assemble

def norm(v):
    if isinstance(v, (float, decimal.Decimal)): return round(float(v), 6)
    return v

def tnorm(t):
    t = re.sub(r"\(.*?\)", "", str(t)).upper().strip()
    return {"INT": "INTEGER", "INT4": "INTEGER", "STRING": "VARCHAR", "TEXT": "VARCHAR", "REAL": "FLOAT", "INT8": "BIGINT"}.get(t, t)

def ref_type(con, gold):
    r = gold["reference"]
    return con.execute("select data_type from information_schema.columns where table_schema=? and table_name=? and column_name=?", [r["schema"], r["table"], r["column"]]).fetchone()[0]

def ref_rows(con, gold, align, schema=None):
    r = gold["reference"]; sch = schema or r["schema"]
    ks = ", ".join(f"({e})" for e in align["ref_exprs"])
    sel = f"SELECT {ks}, r.{r['column']} FROM {sch}.{r['table']} r"
    return [tuple(norm(x) for x in row) for row in con.execute(sel).fetchall()]

def run_branches(con, task, gold, sql_by_branch, rtype):
    """returns (ok, error, rows[(key..., value)], types)"""
    rows, types = [], set()
    for b in task["row_source"]["branches"]:
        sql = sql_by_branch.get(b["id"])
        if sql is None: return False, f"branch {b['id']} missing", [], types
        try:
            q = f"SELECT * EXCLUDE (value), TRY_CAST(value AS {rtype}) AS value, typeof(value) AS _t FROM ({sql})"
            res = con.execute(q).fetchall()
        except Exception as e:
            return False, str(e)[:300], [], types
        for r in res:
            rows.append(tuple(norm(x) for x in r[:-1])); types.add(r[-1])
    return True, None, rows, types

def compare(task, gold, align, cand, ref):
    combine = task["row_source"]["combine"]; n = align["arity"]
    out = {}
    if combine == "union_distinct":
        cs, rs = set(cand), set(ref); ck, rk = Counter(r[:n] for r in cs), Counter(r[:n] for r in rs)
        ck, rk = Counter(set(r[:n] for r in cs)), Counter(set(r[:n] for r in rs))
        cvals = defaultdict(Counter); rvals = defaultdict(Counter)
        for r in cs: cvals[r[:n]][r[n]] += 1
        for r in rs: rvals[r[:n]][r[n]] += 1
    else:
        ck, rk = Counter(r[:n] for r in cand), Counter(r[:n] for r in ref)
        cvals = defaultdict(Counter); rvals = defaultdict(Counter)
        for r in cand: cvals[r[:n]][r[n]] += 1
        for r in ref: rvals[r[:n]][r[n]] += 1
    out["missing"] = sum((rk - ck).values()); out["extra"] = sum((ck - rk).values())
    out["L1"] = out["missing"] == 0 and out["extra"] == 0
    if gold["alignment_quality"] == "weak":
        C = Counter(cand) if combine != "union_distinct" else Counter(set(cand)); R = Counter(ref) if combine != "union_distinct" else Counter(set(ref))
        tot = max(sum(C.values()), sum(R.values()), 1); good = sum((C & R).values())
        out["aligned"] = tot; out["wrong"] = tot - good
    else:
        aligned = wrong = 0
        for k in set(cvals) & set(rvals):
            a = sum(min(cvals[k][v], rvals[k][v]) for v in set(cvals[k]) | set(rvals[k]))
            m = min(sum(cvals[k].values()), sum(rvals[k].values()))
            aligned += m; wrong += m - a
        out["aligned"] = aligned; out["wrong"] = wrong
    out["L2"] = out["aligned"] > 0 and out["wrong"] == 0
    out["wrong_fraction"] = round(out["wrong"] / out["aligned"], 6) if out["aligned"] else 1.0
    return out

def keygen_property(task, align, cand):
    n = align["arity"]; vals = [r[n] for r in cand]
    nonnull = all(v is not None for v in vals)
    unique = len(set(vals)) == len(vals)
    per_key = defaultdict(set)
    for r in cand: per_key[r[:n]].add(r[n])
    one = all(len(s) == 1 for s in per_key.values())
    viol = sum(v is None for v in vals) + (len(vals) - len(set(vals))) + sum(len(s) - 1 for s in per_key.values())
    return nonnull and unique and one, round(viol / max(len(vals), 1), 6)

def score_sql(con, task, gold, align, sql_by_branch, robust=False, ref_sql=None):
    """Score assembled SQL (one query per branch). Returns dict with L0..L3, wrong_fraction, missing, extra."""
    rtype = ref_type(con, gold)
    ok, err, cand, types = run_branches(con, task, gold, sql_by_branch, rtype)
    res = {"L0": ok, "error": err, "L1": False, "L2": False, "L3": False, "wrong_fraction": 1.0, "missing": None, "extra": None}
    if not ok: return res
    res["L3"] = len(types) == 1 and tnorm(next(iter(types))) == tnorm(rtype)
    ref = ref_rows(con, gold, align)
    c = compare(task, gold, align, cand, ref)
    res.update(L1=c["L1"], missing=c["missing"], extra=c["extra"])
    if gold["kind"] == "keygen":
        okp, frac = keygen_property(task, align, cand)
        res["L2"], res["wrong_fraction"] = okp, frac
    else:
        res["L2"], res["wrong_fraction"] = c["L2"], c["wrong_fraction"]
    res["robust"], res["robust_bad"] = None, []
    return res

def final_expressions(final):
    if not final: return None
    if final.get("status") == "answer": return final.get("expressions")
    if final.get("status") == "ambiguous":
        c = final.get("candidates") or []
        d = final.get("default", 0)
        return c[d]["expressions"] if c and 0 <= d < len(c) else None
    return None

