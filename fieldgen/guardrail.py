"""Guardrail (generator side): checks a candidate field expression against the target field card, on the source data and on probes.
Version 1 (D2): every rule is a hard check, the NULL probe checks not-null. Version 2 (D3, spec["version"] == 2, the default):
 hard checks (trigger a retry): the query runs; type cast; declared max length; allowed values (complete lists only; special values allowed);
 case invariance (a string column compared with a string literal: the result for a sample value and its upper-case and lower-case variant must agree).
 advisory (warnings, never a retry): pattern, lengths and range rules from documentation, not-null on the real data.
 a NULL input that gives NULL is logged as "input fault: NULL source" and never triggers a retry.
Own probes, no evaluator import. A probe is a view that replaces one matched source column by a probe value; the recipe branch is
run on it (search path puts the probe view before the base table). Deterministic."""
import re, threading
from fieldgen.assemble import assemble_expr

UNSEEN = "zz_unseen_value_q9"
MAX_PROBED_COLUMNS = 4
TIMEOUT_S, RETRY_TIMEOUT_S = 900, 1800
_W = {}

def _q(x): return '"' + x.replace('"', '""') + '"'
def _lit(v): return "'" + v.replace("'", "''") + "'"

# ---------------------------------------------------------------- spec building (parent side)
def target_spec(card):
    """The part of a target field card the guardrail needs."""
    av = card["allowed_values"]; allowed = None
    if av["kind"] != "none" and av["entries"]:
        allowed = sorted({str(e["value"]) for e in av["entries"]} | {str(e["value"]) for e in card["special_values"]})
    return {"type": card["type"]["declared"], "base": card["type"]["base"], "nullable": card["nullable"], "allowed": allowed, "rules": card["rules"],
            "declared_max": card["type"]["max_length"], "allowed_complete": bool(allowed) and av["omitted_count"] == 0}

def probe_list(dumpview, matched, tables, max_length=None):
    """matched: [{relation, column}]; tables: set of base relation names. Returns probes {kind, relation, column, value, type}."""
    out = []; seen = set()
    for m in matched:
        key = (m["relation"], m["column"])
        if key in seen or m["relation"] not in tables or len(seen) >= MAX_PROBED_COLUMNS: continue
        card = dumpview.sf.get(key)
        if not card: continue
        seen.add(key); typ = card["type"]; isstr = typ.upper().startswith(("VARCHAR", "TEXT"))
        out.append({"kind": "null", "relation": key[0], "column": key[1], "value": None, "type": typ})
        if not isstr: continue
        by = {}
        for s in card["samples"]:
            if s["value"] is not None: by.setdefault(s["kind"], []).append(s["value"])
        observed = {v["value"] for v in card["value_domain"].get("values", [])}
        unseen = UNSEEN if not max_length else UNSEEN[:max(1, max_length)]
        while unseen in observed: unseen = (unseen + "x")[-(max_length or 99):] if max_length else unseen + "x"
        if unseen in observed: unseen = None
        if unseen: out.append({"kind": "unseen", "relation": key[0], "column": key[1], "value": unseen, "type": typ})
        for kind in ("longest", "shortest"):
            if kind in by: out.append({"kind": kind, "relation": key[0], "column": key[1], "value": by[kind][0], "type": typ})
        base = (by.get("random") or by.get("rarest") or [None])[0]
        if base and base.swapcase() != base: out.append({"kind": "mixed_case", "relation": key[0], "column": key[1], "value": base.swapcase(), "type": typ})
    return out

def make_spec(recipe, exprs, card, probes, tables_sql=None, case_probes=(), version=2):
    return {"version": version, "case_probes": list(case_probes), **{"recipe": {"branches": [{"id": b["id"], "from": b["from"]} for b in recipe["branches"]], "group_by": recipe.get("group_by"), "combine": recipe.get("combine"), **({"history": recipe["history"]} if recipe.get("history") else {})},
            "exprs": exprs, "target": target_spec(card), "probes": probes}}

# ---------------------------------------------------------------- checks (worker side)
def _run(con, sql, timeout):
    t = threading.Timer(timeout, con.interrupt); t.start()
    try: return con.execute(sql).fetchall()
    finally: t.cancel()

def _rule_text(t):
    ru = t["rules"]; p = []
    if ru.get("max_length") is not None: p.append(f"max length {ru['max_length']}")
    if ru.get("pattern"): p.append("digits only" if ru["pattern"] == "^[0-9]+$" else f"pattern {ru['pattern']}")
    if ru.get("lengths"): p.append("length in " + ",".join(map(str, ru["lengths"])))
    if ru.get("range"): p.append(f"range {ru['range']}")
    return "; ".join(p)

def _judge(rows, t, probe, branch):
    """rows: [(text_value, cast_failed, count)] -> violations."""
    v = []; ru = t["rules"]
    def add(check, rule, bad):
        if bad: v.append({"check": check, "probe": probe, "branch": branch, "offending": sorted(bad)[:3], "rule": rule})
    add("not_null", "target field is NOT NULL", ["NULL"] if (not t["nullable"] and any(r[0] is None and not r[1] for r in rows)) else [])
    add("type_cast", f"value must cast to {t['type']}", [str(r[3])[:40] for r in rows if r[1]])
    vals = [r[0] for r in rows if r[0] is not None and not r[1]]
    if t["allowed"] is not None: add("allowed_values", "value must be one of the allowed or special values", [x for x in vals if x not in set(t["allowed"])])
    if t["base"] == "string":
        if ru.get("max_length") is not None: add("max_length", f"length at most {ru['max_length']}", [x for x in vals if len(x) > ru["max_length"]])
        if ru.get("pattern"): add("pattern", "digits only" if ru["pattern"] == "^[0-9]+$" else f"pattern {ru['pattern']}", [x for x in vals if not re.fullmatch(ru["pattern"], x)])
        if ru.get("lengths"): add("lengths", "length in " + ",".join(map(str, ru["lengths"])), [x for x in vals if len(x) not in ru["lengths"]])
    if ru.get("range") and t["base"] in ("integer", "numeric"):
        lo, hi = ru["range"]; add("range", f"value in [{lo}, {hi}]", [x for x in vals if not (lo <= float(x) <= hi)])
    return v

def _judge2(rows, t, probe, branch):
    """Version 2: (violations, warnings, faults) for one run."""
    viol, warn, fault = [], [], []; ru = t["rules"]; data = probe == "data"
    def add(lst, check, rule, bad):
        if bad: lst.append({"check": check, "probe": probe, "branch": branch, "offending": sorted(bad)[:3], "rule": rule})
    if any(r[0] is None and not r[1] for r in rows):
        if probe.startswith("null:"): fault.append({"check": "input fault: NULL source", "probe": probe, "branch": branch, "offending": ["NULL"], "rule": "a NULL source value gives a NULL result", "target_nullable": t["nullable"]})
        elif data and not t["nullable"]: warn.append({"check": "not_null", "probe": probe, "branch": branch, "offending": ["NULL"], "rule": "target field is NOT NULL (real source data)"})
    add(viol, "type_cast", f"value must cast to {t['type']}", [str(r[3])[:40] for r in rows if r[1]])
    vals = [r[0] for r in rows if r[0] is not None and not r[1]]
    if t.get("allowed_complete") and t["allowed"] is not None: add(viol, "allowed_values", "value must be one of the allowed or special values", [x for x in vals if x not in set(t["allowed"])])
    if t["base"] == "string" and t.get("declared_max") is not None: add(viol, "max_length", f"declared length at most {t['declared_max']}", [x for x in vals if len(x) > t["declared_max"]])
    if data and t["base"] == "string":
        if ru.get("pattern"): add(warn, "pattern", "digits only" if ru["pattern"] == "^[0-9]+$" else f"pattern {ru['pattern']}", [x for x in vals if not re.fullmatch(ru["pattern"], x)])
        if ru.get("lengths"): add(warn, "lengths", "length in " + ",".join(map(str, ru["lengths"])), [x for x in vals if len(x) not in ru["lengths"]])
    if data and ru.get("range") and t["base"] in ("integer", "numeric"):
        lo, hi = ru["range"]; add(warn, "range", f"value in [{lo}, {hi}]", [x for x in vals if not (lo <= float(x) <= hi)])
    return viol, warn, fault

def _branch_query(spec, e):
    return assemble_expr(spec["recipe"], e["branch"], [], e["sql"])

def _from_text(spec, branch): return next(b["from"] for b in spec["recipe"]["branches"] if b["id"] == branch)
def _uses(spec, branch, relation): return bool(re.search(rf"(?<![A-Za-z0-9_]){re.escape(relation)}(?![A-Za-z0-9_])", _from_text(spec, branch), re.I))

def _probe_view(con, sch, relation, column, value, typ):
    lit = "CAST(NULL AS %s)" % typ if value is None else _lit(value)
    con.execute(f"DROP SCHEMA IF EXISTS {sch} CASCADE"); con.execute(f"CREATE SCHEMA {sch}")
    con.execute(f"CREATE VIEW {sch}.{_q(relation)} AS SELECT * REPLACE ({lit} AS {_q(column)}) FROM main.{_q(relation)}")

def _case_results(con, spec, cp, value, timeout):
    """Case-folded result distribution of every branch that reads the relation, with the column set to one constant."""
    sch = "probe_case"; _probe_view(con, sch, cp["relation"], cp["column"], value, cp["type"]); out = {}
    try:
        con.execute(f"SET search_path = '{sch},main'")
        for e in spec["exprs"]:
            if not _uses(spec, e["branch"], cp["relation"]): continue
            rows = _run(con, f"SELECT lower(CAST(value AS VARCHAR)), count(*) FROM ({_branch_query(spec, e)}) GROUP BY 1 ORDER BY 1 NULLS FIRST", timeout)
            out[e["branch"]] = [(r[0], r[1]) for r in rows]
    finally:
        con.execute("SET search_path = 'main'"); con.execute(f"DROP SCHEMA IF EXISTS {sch} CASCADE")
    return out

def _show(res):
    return ", ".join(f"{'NULL' if v is None else v} x{n}" for v, n in res[:4]) + (", ..." if len(res) > 4 else "")

def case_checks(con, spec, timeout=TIMEOUT_S):
    """Hard check, version 2: for each sample value of a compared string column, the result for the sample, its upper-case and its lower-case
    variant must agree (text case ignored, so a copied column is allowed)."""
    viol = []; skipped = []
    for cp in spec.get("case_probes", []):
        bad = 0
        for smp in cp["samples"]:
            variants = list(dict.fromkeys([smp, smp.upper(), smp.lower()]))
            if len(variants) < 2: continue
            try: res = {v: _case_results(con, spec, cp, v, timeout) for v in variants}
            except Exception as ex:
                if "INTERRUPT" in str(ex).upper(): skipped.append(f"case:{cp['relation']}.{cp['column']}"); continue
                viol.append({"check": "runs", "probe": f"case:{cp['relation']}.{cp['column']}", "branch": "-", "offending": [str(ex).split("\n")[0][:160]], "rule": "the query must run"}); continue
            for br in res[variants[0]]:
                other = next((v for v in variants[1:] if res[v].get(br) != res[variants[0]][br]), None)
                if other is not None and bad < 2:
                    bad += 1; viol.append({"check": "case_invariance", "probe": f"case:{cp['relation']}.{cp['column']}", "branch": br, "column": f"{cp['relation']}.{cp['column']}",
                                           "offending": [f"{variants[0]!r} -> {_show(res[variants[0]][br])}", f"{other!r} -> {_show(res[other][br])}"],
                                           "rule": "the result must not depend on the case of the column's text"})
                    break
    return viol, skipped

def check_with(con, spec, timeout=TIMEOUT_S):
    """Run all checks on one connection. Returns {"ok", "violations", "warnings", "faults", "skipped"}."""
    t = spec["target"]; v2 = spec.get("version", 2) == 2; viol = []; warns = []; faults = []; pending = []
    def one(e, probe, search, tmo):
        q = _branch_query(spec, e)
        sql = (f"SELECT CAST(TRY_CAST(value AS {t['type']}) AS VARCHAR) AS tv, (value IS NOT NULL AND TRY_CAST(value AS {t['type']}) IS NULL) AS bad, count(*), "
               f"CAST(any_value(value) AS VARCHAR) FROM ({q}) GROUP BY 1, 2")
        try:
            con.execute(f"SET search_path = '{search}'")
            rows = _run(con, sql, tmo)
        except Exception as ex:
            msg = str(ex)
            if "INTERRUPT" in msg.upper(): return "timeout"
            viol.append({"check": "runs", "probe": probe, "branch": e["branch"], "offending": [msg.split("\n")[0][:160]], "rule": "the query must run"}); return None
        finally:
            try: con.execute("SET search_path = 'main'")
            except Exception: pass
        rr = [(r[0], r[1], r[2], r[3]) for r in rows]
        if v2:
            a, b, c = _judge2(rr, t, probe, e["branch"]); viol.extend(a); warns.extend(b); faults.extend(c)
        else: viol.extend(_judge(rr, t, probe, e["branch"]))
        return None
    def pass_(tmo, units):
        for e, probe, search in units:
            if one(e, probe, search, tmo) == "timeout": pending.append((e, probe, search))
    units = [(e, "data", "main") for e in spec["exprs"]]
    for i, p in enumerate(spec["probes"]):
        sch = f"probe_{i}"; label = f"{p['kind']}:{p['relation']}.{p['column']}"
        rel_units = [(e, label, sch) for e in spec["exprs"] if _uses(spec, e["branch"], p["relation"])]
        if not rel_units: continue
        _probe_view(con, sch, p["relation"], p["column"], p["value"], p["type"])
        try: pass_(timeout, [(e, l, f"{sch},main") for e, l, s in rel_units])
        finally: con.execute(f"DROP SCHEMA IF EXISTS {sch} CASCADE")
    pass_(timeout, units)
    again = list(pending); pending.clear()
    if again: pass_(RETRY_TIMEOUT_S, again)
    skipped = [f"{p[1]}@{p[0]['branch']}" for p in pending]
    if v2:
        cv, cs = case_checks(con, spec, timeout); viol.extend(cv); skipped += cs
    def dedupe(lst):
        seen, out = set(), []
        for x in sorted(lst, key=lambda x: (x["probe"] != "data",) + tuple(map(str, (x["check"], x["probe"], x["branch"], x["offending"])))):
            k = (x["check"], x["probe"], x["branch"], tuple(x["offending"]))
            if k not in seen: seen.add(k); out.append(x)
        return out
    out = dedupe(viol)
    return {"ok": not out, "violations": out, "warnings": dedupe(warns), "faults": dedupe(faults), "skipped": skipped}

# ---------------------------------------------------------------- case probes (parent side)
def _comparison_columns(sql):
    """Columns (qualifier, name) that appear in a comparison with a string literal."""
    import sqlglot
    from sqlglot import exp
    try: tree = sqlglot.parse_one(sql, read="duckdb")
    except Exception: return []
    found = []
    for node in tree.find_all(exp.EQ, exp.NEQ, exp.In, exp.Like, exp.ILike, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between, exp.Case):
        if isinstance(node, exp.Case):
            if node.args.get("this") is None: continue
            lits = any(isinstance(i.args.get("this"), exp.Literal) and i.args["this"].is_string for i in node.args.get("ifs", []))
            cols = list(node.args["this"].find_all(exp.Column)) if lits else []
        else:
            lits = any(l.is_string for l in node.find_all(exp.Literal)); cols = list(node.find_all(exp.Column)) if lits else []
        found += [(c.table or None, c.name) for c in cols]
    return list(dict.fromkeys(found))

def case_probe_list(ft, exprs, dumpview, tables, max_columns=3, max_samples=3):
    """Base string columns that the expressions compare with a string literal, resolved through the branch aliases and the column lineage."""
    out = []; seen = set(); rels = ft.get("relations", {}); low = lambda d: {k.lower(): k for k in d}
    for e in exprs:
        al = ft["aliases"].get(e["branch"], {})
        for q, name in _comparison_columns(e["sql"]):
            cands = []
            for alias in ([q] if q else list(al)):
                table = al.get(alias, alias)
                if table in tables:
                    card = next((c for (r, c) in dumpview.sf if r == table and c.lower() == name.lower()), None)
                    if card: cands.append((table, card))
                elif table in rels:
                    col = low(rels[table]["columns"]).get(name.lower())
                    for o in (rels[table]["columns"].get(col) or {}).get("origin") or []:
                        rt, _, rc = o.partition(".")
                        if rt in tables and (rt, rc) in dumpview.sf: cands.append((rt, rc))
            for key in cands:
                card = dumpview.sf.get(key)
                if key in seen or len(seen) >= max_columns or not card or not card["type"].upper().startswith(("VARCHAR", "TEXT")): continue
                smp = [s["value"] for s in card["samples"] if s["kind"] == "random" and s["value"] and s["value"].upper() != s["value"].lower()][:max_samples]
                if smp: seen.add(key); out.append({"relation": key[0], "column": key[1], "samples": smp, "type": card["type"]})
    return out

# ---------------------------------------------------------------- process pool
def init_worker(pkg_root, mem_mb, threads):
    from fieldgen.db import package_connection
    con = package_connection(pkg_root); con.execute(f"SET memory_limit='{mem_mb}MB'"); con.execute(f"SET threads={threads}"); _W["con"] = con

def check_in_worker(spec):
    return check_with(_W["con"], spec)

def make_pool(pkg_root, workers=None):
    import os, multiprocessing as mp, concurrent.futures as cf
    n = workers or max(1, (os.cpu_count() or 2) // 2); ram = [int(l.split()[1]) for l in open("/proc/meminfo") if l.startswith("MemTotal")][0] * 1024
    mem = int(0.7 * ram / n) // 2 ** 20; thr = max(1, (os.cpu_count() or 2) // n)
    return cf.ProcessPoolExecutor(max_workers=n, mp_context=mp.get_context("spawn"), initializer=init_worker, initargs=(str(pkg_root), mem, thr))

def format_violations(viol, limit=8):
    lines = [f"- case invariance: the result depends on the case of the text in {v['column']}: " + " but ".join(v["offending"]) if v["check"] == "case_invariance" else
             f"- check {v['check']} on {v['probe']} (branch {v['branch']}): rule: {v['rule']}; offending: " + ", ".join(repr(x) for x in v["offending"]) for v in viol[:limit]]
    return "\n".join(lines) + (f"\n- ... and {len(viol) - limit} more" if len(viol) > limit else "")
