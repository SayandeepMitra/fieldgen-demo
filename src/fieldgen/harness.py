"""Harness side: recipe layer, formula layer (L0-L4), mode comparison for the package. Reads gold; never imported by generator code."""
import os, glob, json, os, re
from collections import Counter
import duckdb, sqlglot
from sqlglot import exp
from fieldgen import compare as ev
from fieldgen.package import load_package
from fieldgen.db import package_connection
from fieldgen.parse import branch_tables, recipe_info
from fieldgen.assemble import assemble_expr, assemble_keys, combine_sql, assemble_table
from fieldgen.final_expr import final_expressions
from fieldgen import l4 as l4_v2

def _fmt(v): return "NULL" if v is None else str(v)

def mismatches(cand, ref, n, limit=3):
    """first rows (key, got, expected) where candidate and reference differ; rows are (key.., value) tuples."""
    from collections import defaultdict
    C, R = defaultdict(Counter), defaultdict(Counter)
    for r in cand: C[r[:n]][r[n]] += 1
    for r in ref: R[r[:n]][r[n]] += 1
    out = []
    for k in R:
        if k not in C: out.append([[_fmt(x) for x in k], "<row missing>", _fmt(next(iter(R[k])))])
        elif C[k] != R[k]: out.append([[_fmt(x) for x in k], _fmt(next(iter(C[k] - R[k]), None)), _fmt(next(iter(R[k] - C[k]), None))])
        if len(out) >= limit: return out
    for k in C:
        if k not in R and len(out) < limit: out.append([[_fmt(x) for x in k], _fmt(next(iter(C[k]))), "<extra row>"])
    return out[:limit]

class Harness:
    def __init__(self, pkg_root, reference_dir):
        pkg_root = str(pkg_root).rstrip("/") + "/"; reference_dir = str(reference_dir).rstrip("/") + "/"
        self.root = pkg_root; self.reference_dir = reference_dir; self.pkg = load_package(pkg_root)
        self.con = package_connection(self.pkg)
        self.con.execute("CREATE SCHEMA ref")
        self.ttypes = {t["name"]: {c["name"]: c["type"] for c in t["columns"]} for t in self.pkg.target.tables}
        self.recipes, self.fields = {}, {}; self._ref4 = {}
        for f in glob.glob(reference_dir + "recipes/*.json"):
            r = json.load(open(f)); self.recipes[r["table"]] = r
        for f in glob.glob(reference_dir + "fields/*.json"):
            g = json.load(open(f)); self.fields[g["task_id"]] = g
        for f in sorted(glob.glob(reference_dir + "reference_data/*.csv")):
            t = os.path.basename(f)[:-4]
            if t not in self.ttypes: continue
            cols = ", ".join(f'"{c}" {ty}' for c, ty in self.ttypes[t].items())
            self.con.execute(f'CREATE TABLE ref."{t}" ({cols})'); self.con.execute(f"COPY ref.\"{t}\" FROM '{f}' (HEADER true)")
        al = reference_dir + "alignment.json"
        if os.path.exists(al):      # minimum reference format: reference tables + the source columns that identify each row (docs/reference_format.md)
            for t, a_ in json.load(open(al)).items():
                if t not in self.ttypes: continue
                alts = a_["source"] if a_["source"] and isinstance(a_["source"][0], list) else [a_["source"]]
                src = [f"b{i + 1}:{x}" for i, alt in enumerate(alts) for x in alt]; ref = [x if x.startswith("r.") else f"r.{x}" for x in a_["reference"]]
                for c in self.ttypes[t]:
                    tid = f"{t}.{c}"
                    if tid in self.fields: continue
                    self.fields[tid] = {"task_id": tid, "table": t, "column": c, "kind": "excluded" if c in a_.get("exclude", []) else "value", "reference": {"table": t, "column": c}, "expressions": [],
                                        "alignment": {"source": src, "reference": ref}, "alignment_quality": "strong", "ambiguity": {"ambiguous": False, "reason": "minimum format", "source": "pending"}, "exclusion_reason": None}
        self.con.execute("SET search_path='main,ref'")
        self.align_cols = set()
        for g in self.fields.values():
            for e in g["alignment"]["source"]:
                tc = e.split(":", 1)[-1]
                if tc != "@const": self.align_cols.add(tuple(tc.split(".", 1)))

    # ---------- keys
    def _is_gold(self, g, recipe):
        return g["table"] in self.recipes and recipe.get("branches") == self.recipes[g["table"]]["branches"]

    def resolve_keys(self, g, recipe):
        """gold alignment key -> {tool branch: [key exprs]} (one expression per key column, two or more allowed), or (None, reason).
        For the gold recipe itself the key fields' own gold expressions are used; for a tool recipe the key columns are traced source
        columns, resolved through the tool's table aliases."""
        info = recipe_info(recipe); refs = g["alignment"]["reference"]
        if all(e.endswith("@const") for e in g["alignment"]["source"]): return {bid: ["1"] for bid in info}, None      # keyless: compare rows as a multiset
        if self._is_gold(g, recipe) and all(re.fullmatch(r"r\.(\w+)", x) for x in refs):
            cols = [re.fullmatch(r"r\.(\w+)", x).group(1) for x in refs]
            fs = [self.fields.get(f'{g["table"]}.{c}') for c in cols]
            if all(f and f["kind"] == "value" for f in fs):
                ex = {bid: [next((e["expr"] for e in f["expressions"] if e["branch"] == bid), None) for f in fs] for bid in info}
                if all(all(v) for v in ex.values()): return ex, None
        groups = {}
        for e in g["alignment"]["source"]:
            bid, tc = e.split(":", 1); groups.setdefault(bid, []).append(tuple(tc.split(".", 1)))
        uniq = []
        for gr in groups.values():
            if gr not in uniq: uniq.append(gr)
        out = {}
        for bid, i in info.items():
            ok = []
            for gr in uniq:
                if all(t in i["tables"] for t, _ in gr): ok.append(gr)
            if not ok: return None, f"key unavailable in {bid} (absent)"
            if len(ok) > 1: return None, f"key unavailable in {bid} (ambiguous)"
            ks = []
            for t, c in ok[0]:
                al = [a for a, tt in i["aliases"].items() if tt == t]
                if len(al) != 1: return None, f"key unavailable in {bid} (table {t} appears under {len(al)} aliases)"
                ks.append(f"{al[0]}.{c}")
            out[bid] = ks
        return out, None

    def _ref_keys(self, g):
        ks = ", ".join(f"CAST(({e}) AS VARCHAR)" for e in g["alignment"]["reference"])
        return [tuple(r) for r in self.con.execute(f'SELECT {ks} FROM ref."{g["table"]}" r').fetchall()]

    # ---------- recipe layer
    def recipe_layer(self, table, recipe):
        gr = self.recipes.get(table) or {"branches": [], "combine": None, "group_by": None}; anchor = next(g for k, g in self.fields.items() if g["table"] == table)
        diag = {}
        if recipe is None: return {"pass": False, "reason": "no valid recipe", "diag": diag}
        info = recipe_info(recipe); used = [t for t in dict.fromkeys(t for i in info.values() for t in i["tables"]) if t in {x["name"] for x in self.pkg.source.tables}]
        src_t = {t["name"] for t in self.pkg.source.tables}
        gold_tabs = [t for t in dict.fromkeys(t for b in gr["branches"] for t in branch_tables(b["from"])[1]) if t in src_t]
        diag = {"tables_used": used, "gold_tables": gold_tabs, "extra_tables": [t for t in used if t not in gold_tabs], "missing_tables": [t for t in gold_tabs if t not in used],
                "combine": recipe["combine"], "gold_combine": gr["combine"], "grouped": bool(recipe.get("group_by")), "gold_grouped": bool(gr["group_by"]),
                "joins": sum(len(list(sqlglot.parse_one("SELECT 1 " + b["from"], read="duckdb").find_all(exp.Join))) for b in recipe["branches"])}
        keys, err = self.resolve_keys(anchor, recipe)
        if err: return {"pass": False, "reason": err, "diag": diag}
        try:
            q = combine_sql(recipe, [assemble_keys(recipe, b["id"], keys[b["id"]]) for b in recipe["branches"]])
            cand = [tuple(None if v is None else str(v) for v in r) for r in self.con.execute(f"select * from ({q})").fetchall()]
        except Exception as e: return {"pass": False, "reason": "does not run: " + str(e)[:120], "diag": diag}
        ref = self._ref_keys(anchor)
        C, R = Counter(cand), Counter(ref)
        ok = C == R and len(cand) == len(ref)
        return {"pass": ok, "reason": None if ok else f"key multiset differs (missing {sum((R - C).values())}, extra {sum((C - R).values())}; rows {len(cand)} vs {len(ref)})",
                "diag": diag}

    # ---------- formula layer
    def _legacy(self, g, recipe):
        task = {"row_source": {"branches": [{"id": b["id"]} for b in recipe["branches"]], "combine": recipe["combine"]}}
        gold = {"reference": {"schema": "ref", "table": g["table"], "column": g["column"]}, "alignment_quality": g["alignment_quality"], "kind": g["kind"]}
        align = {"ref_exprs": g["alignment"]["reference"], "arity": len(g["alignment"]["reference"])}
        return task, gold, align

    def ref_sql(self, g, con_recipe=None):
        gr = self.recipes[g["table"]]; recipe = {"branches": gr["branches"], "combine": gr["combine"], "group_by": gr["group_by"]}
        keys, _ = self.resolve_keys(g, recipe)
        return recipe, {e["branch"]: assemble_expr(recipe, e["branch"], keys[e["branch"]], e["expr"]) for e in g["expressions"]}

    def run_on(self, con, sqls, recipe, rtype):
        rows = []
        for b in recipe["branches"]:
            q = f"SELECT * EXCLUDE (value), TRY_CAST(value AS {rtype}) AS value FROM ({sqls[b['id']]})"
            rows += [tuple(round(x, 6) if isinstance(x, float) else x for x in r) for r in con.execute(q).fetchall()]
        return rows

    def _ex(self, res, level, detail): res.setdefault("explain", {})[level] = detail

    def score_field(self, recipe, final, tid, robust=True):
        g = self.fields[tid]; rtype = self.ttypes[g["table"]][g["column"]]
        res = {"task_id": tid, "kind": g["kind"], "L0": False, "L1": False, "L2": False, "L3": False, "L4": False, "error": None}
        exprs = final_expressions(final)
        if recipe is None or not exprs:
            res["error"] = "no recipe" if recipe is None else "no valid expressions"; self._ex(res, "L0", {"why": res["error"]}); return res
        info = recipe_info(recipe)
        if {e["branch"] for e in exprs} != set(info):
            res["error"] = "branches do not match the recipe"; self._ex(res, "L0", {"why": res["error"]}); return res
        res["tool_expr"] = {e["branch"]: e["sql"] for e in exprs}
        try:
            for e in exprs: self.con.execute(assemble_expr(recipe, e["branch"], [], e["sql"])).fetchall()
            res["L0"] = True
        except Exception as ex: res["error"] = str(ex)[:150]; self._ex(res, "L0", {"why": res["error"]}); return res
        keys, err = self.resolve_keys(g, recipe)
        if err: res["error"] = err; self._ex(res, "L1", {"why": err}); return res
        by = {e["branch"]: assemble_expr(recipe, e["branch"], keys[e["branch"]], e["sql"]) for e in exprs}
        task, gold, align = self._legacy(g, recipe); n = align["arity"]
        try: cand = self.run_on(self.con, by, recipe, rtype)
        except Exception as ex:
            res["error"] = "key expression failed: " + str(ex)[:120]; self._ex(res, "L1", {"why": res["error"]}); return res
        ref = None
        if g["kind"] == "placeholder":
            res["L1"] = res["L2"] = res["L3"] = all(r[-1] is None for r in cand) and bool(cand)
            if not res["L1"]: self._ex(res, "L1", {"rows": [[[_fmt(x) for x in r[:n]], _fmt(r[n]), "NULL"] for r in cand if r[n] is not None][:3]})
        else:
            r = ev.score_sql(self.con, task, gold, align, by, robust=False)
            res.update({k: r[k] for k in ("L1", "L2", "L3")}); res["wrong_fraction"] = r["wrong_fraction"]
            if not res["L3"]: res["L3"] = self._type_ok(by, recipe, rtype)
            if not r["L0"]: res["L0"] = False; res["error"] = r["error"]; self._ex(res, "L0", {"why": r["error"]}); return res
            if not (res["L1"] and res["L2"]):
                if g["kind"] == "keygen":
                    self._ex(res, "L2", {"why": "generated key violates the property (null, duplicate, or several values per key)"})
                else:
                    ref = ev.ref_rows(self.con, gold, align); self._ex(res, "L1" if not res["L1"] else "L2", {"rows": mismatches(cand, ref, n)})
        if not res["L3"]: self._ex(res, "L3", {"types": sorted(self._types(by, recipe)), "expected": rtype})
        if robust and res["L1"] and res["L2"]:
            res["L4"], bad = self._l4(g, recipe, by, rtype, task, gold, align)
            if bad: self._ex(res, "L4", bad[0])
        return res

    FAM = {"INTEGER": "INT", "BIGINT": "INT", "SMALLINT": "INT", "HUGEINT": "INT", "INT": "INT", "TINYINT": "INT", "FLOAT": "NUM", "DOUBLE": "NUM", "REAL": "NUM", "DECIMAL": "NUM", "NUMERIC": "NUM"}
    def _types(self, by, recipe):
        types = set()
        for b in recipe["branches"]: types |= {r[0] for r in self.con.execute(f"select distinct typeof(value) from ({by[b['id']]})").fetchall()}
        return types
    def _type_ok(self, by, recipe, rtype):
        """L3 with integer widths treated as one family (a generated key is BIGINT, the column INTEGER)."""
        fam = lambda t: self.FAM.get(ev.tnorm(t), ev.tnorm(t)); types = self._types(by, recipe)
        return len(types) == 1 and fam(next(iter(types))) == fam(rtype)

    def ref_l4(self, g):
        """reference expression on the perturbed data: (eligible, {class: rows}). A field whose reference expression itself fails on a
        perturbed copy is not eligible for L4."""
        tid = g["task_id"]
        if tid in self._ref4: return self._ref4[tid]
        rtype = self.ttypes[g["table"]][g["column"]]; rows = {}; ok = True
        if g["kind"] == "value":
            grecipe, gsql = self.ref_sql(g)
            for c in l4_v2.CLASSES:
                try:
                    con = l4_v2.class_connection(self.pkg, c, self.align_cols).cursor()
                    rows[c] = self.run_on(con, gsql, grecipe, rtype)
                    if Counter(rows[c]) != Counter(self.run_on(con, gsql, grecipe, rtype)): ok = False; break      # reference not deterministic on this copy
                except Exception: ok = False; break
        self._ref4[tid] = (ok, rows); return self._ref4[tid]

    def _l4(self, g, recipe, cand_sql, rtype, task, gold, align):
        """(passed or None when the reference is not eligible, [{class, rows}]); rows are example mismatches (key, got, expected)."""
        bad = []; n = align["arity"]
        okref, refrows = self.ref_l4(g)
        if not okref: return None, []
        for c in l4_v2.CLASSES:
            con = l4_v2.class_connection(self.pkg, c, self.align_cols).cursor(); ex = []
            try:
                cand = self.run_on(con, cand_sql, recipe, rtype)
                if g["kind"] == "keygen": ok, _ = ev.keygen_property(task, align, cand)
                elif g["kind"] == "placeholder": ok = all(r[-1] is None for r in cand)
                else:
                    ref = refrows[c]; cmp = ev.compare(task, gold, align, cand, ref)
                    ok = cmp["L1"] and (cmp["L2"] or cmp["wrong"] == 0)
                    if not ok: ex = mismatches(cand, ref, n)
            except Exception as e: ok = False; ex = [["error", str(e)[:100], ""]]
            if not ok: bad.append({"class": c, "name": l4_v2.CLASSES[c], "rows": ex})
        return not bad, bad

    # ---------- table level
    def gold_exprs(self, table, skip=()):
        return {g["column"]: {e["branch"]: e["expr"] for e in g["expressions"]} for g in self.fields.values()
                if g["table"] == table and g["kind"] != "excluded" and g["column"] not in skip and not any(e["branch"] == "over_union" for e in g["expressions"])}

    def table_level(self, table, recipe, exprs):
        """Assemble one query for the table from the recipe and the formulas, run it on the package source, compare with the reference.
        exprs: {column: {branch: sql}}. Generated keys (recipe `keys`) are checked by property only."""
        cols = list(self.ttypes[table]); types = self.ttypes[table]
        anchor = next(g for g in self.fields.values() if g["table"] == table)
        out = {"table": table, "ran": False, "rows": None, "ref_rows": None, "row_count_equal": False, "keys_equal": False}
        if recipe is None: out["error"] = "no valid recipe"; return out
        keys, err = self.resolve_keys(anchor, recipe)
        if err: out["error"] = err; return out
        gen = [k["column"] for k in recipe.get("keys") or []]
        scored = [c for c, g in ((g["column"], g) for g in self.fields.values() if g["table"] == table) if g["kind"] != "excluded" and c not in gen and g["kind"] != "keygen"]
        try:
            cur = self.con.execute(assemble_table(recipe, cols, exprs, types, keys)); names = [d[0] for d in cur.description]; rows = cur.fetchall()
        except Exception as e: out["error"] = str(e)[:200]; return out
        out["ran"] = True; out["rows"] = len(rows); idx = {n: i for i, n in enumerate(names)}
        sel = ", ".join(f'CAST("{c}" AS VARCHAR)' for c in scored)
        nk = len(anchor["alignment"]["reference"]); rk = ", ".join(f"CAST(({e}) AS VARCHAR)" for e in anchor["alignment"]["reference"])
        ref = self.con.execute(f'SELECT {rk}, {sel} FROM ref."{table}" r').fetchall() if scored else self.con.execute(f'SELECT {rk} FROM ref."{table}" r').fetchall()
        out["ref_rows"] = len(ref); out["row_count_equal"] = len(rows) == len(ref)
        toS = lambda v: None if v is None else str(v)
        cand = {}
        for r in rows: cand.setdefault(tuple(toS(r[idx[f"_k{i}"]]) for i in range(nk)), []).append([toS(r[idx[c]]) for c in scored])
        refd = {}
        for r in ref: refd.setdefault(tuple(r[:nk]), []).append(list(r[nk:]))
        out["keys_equal"] = Counter({k: len(v) for k, v in cand.items()}) == Counter({k: len(v) for k, v in refd.items()})
        right = {c: 0 for c in scored}; rows_ok = 0; samples = {}
        for k, rv in refd.items():
            cv = sorted(cand.get(k, []), key=str)
            for j, rrow in enumerate(sorted(rv, key=str)):
                crow = cv[j] if j < len(cv) else None
                ok_all = crow is not None
                for ci, c in enumerate(scored):
                    good = crow is not None and crow[ci] == rrow[ci]
                    right[c] += good; ok_all &= good
                    if not good and len(samples.setdefault(c, [])) < 3: samples[c].append([list(k), None if crow is None else crow[ci], rrow[ci]])
                rows_ok += ok_all
        nref = max(len(ref), 1)
        out.update({"scored_fields": len(scored), "fields_all_correct": sum(v == len(ref) for v in right.values()),
                    "field_correct_share": round(sum(v == len(ref) for v in right.values()) / max(len(scored), 1), 4),
                    "cell_accuracy": round(sum(right.values()) / (nref * max(len(scored), 1)), 4), "rows_all_correct_share": round(rows_ok / nref, 4),
                    "wrong_fields": {c: {"correct": v, "of": len(ref), "examples": samples.get(c, [])} for c, v in right.items() if v != len(ref)}})
        out["ids"] = {}
        for c in gen + [g["column"] for g in self.fields.values() if g["table"] == table and g["kind"] == "keygen" and g["column"] not in gen]:
            vals = [r[idx[c]] for r in rows]
            out["ids"][c] = {"non_null": all(v is not None for v in vals), "unique": len(set(vals)) == len(vals), "ok": bool(vals) and all(v is not None for v in vals) and len(set(vals)) == len(vals)}
        return out

    # ---------- a whole cell
    def evaluate_cell(self, cell_dir, attempt="final"):
        recs = [json.loads(l) for l in open(cell_dir + "recipes.jsonl")]
        flds = [json.loads(l) for l in open(cell_dir + "fields.jsonl")]
        pick = lambda r: (r.get("first") if attempt == "first" and r.get("first") else r)
        out = {"recipes": {}, "fields": {}, "tables": {}, "tokens": {"in": 0, "out": 0}, "retry_tokens": {"in": 0, "out": 0}, "retries": 0, "attempt": attempt}
        for r in recs:
            lay = self.recipe_layer(r["table"], pick(r)["recipe"]); lay["errors"] = pick(r)["errors"]; out["recipes"][r["table"]] = lay
        rec_final = {r["table"]: r["recipe"] for r in recs}
        for r in recs + flds:
            for k in ("in", "out"):
                out["tokens"][k] += r["tokens"][k]; out["retry_tokens"][k] += (r.get("retry_tokens") or {}).get(k, 0)
            out["retries"] += 1 if r.get("retry") else 0
        by_table = {}
        for f in flds:
            p = pick(f); recipe = rec_final.get(f["table"])
            res = self.score_field(recipe, p.get("final"), f["task_id"]); res["errors"] = p.get("errors", []); res["assumptions"] = (p.get("final") or {}).get("assumptions") or []
            out["fields"][f["task_id"]] = res; by_table.setdefault(f["table"], {})[f["task_id"].split(".", 1)[1]] = {e["branch"]: e["sql"] for e in (final_expressions(p.get("final")) or [])}
        for r in recs:
            t = r["table"]; recipe = rec_final.get(t)
            ex_t = {c: e for c, e in by_table.get(t, {}).items() if out["fields"].get(f"{t}.{c}", {}).get("L0")}      # a formula that does not run counts as NULL, not as a failed table
            tl = self.table_level(t, recipe, ex_t)
            out["tables"][t] = tl
            for c, idr in [(k["column"], (tl.get("ids") or {}).get(k["column"])) for k in (recipe or {}).get("keys") or [] if (tl.get("ids") or {}).get(k["column"])]:   # generated keys: property check stands for L0-L4
                tid = f"{t}.{c}"
                if tid in self.fields: out["fields"][tid] = {"task_id": tid, "kind": "keygen", "generated_by_recipe": True, **{k: idr["ok"] for k in ("L0", "L1", "L2", "L3", "L4")}, "error": None if idr["ok"] else "generated key violates the property"}
            for c in [k["column"] for k in (recipe or {}).get("keys") or []]:
                tid = f"{t}.{c}"
                if tid in self.fields and tid not in out["fields"]: out["fields"][tid] = {"task_id": tid, "kind": "keygen", "generated_by_recipe": True, **{k: False for k in ("L0", "L1", "L2", "L3", "L4")}, "error": tl.get("error") or "table query did not run"}
        return out

    def score_expressions(self, recipe, table, col, exprs):
        """self-test helper: score a given expression set"""
        return self.score_field(recipe, {"status": "answer", "expressions": exprs}, f"{table}.{col}")

    # ---------- failures.csv
    def failures_rows(self, cell, ev_cell):
        rows = []
        for tid, f in sorted(ev_cell["fields"].items()):
            if all(f.get(k) for k in ("L0", "L1", "L2", "L3", "L4")): continue
            g = self.fields[tid]; ref_e = "; ".join(f"{e['branch']}: {e['expr']}" for e in g["expressions"])
            tool_e = "; ".join(f"{b}: {s}" for b, s in (f.get("tool_expr") or {}).items()) or ("(generated by recipe key entry)" if f.get("generated_by_recipe") else "(none)")
            ex = f.get("explain") or {}
            levels = [k for k in ("L0", "L1", "L2", "L3", "L4") if not f.get(k) and (k in ex or f.get("generated_by_recipe") or f.get("error"))] or [k for k in ("L0", "L1", "L2", "L3", "L4") if not f.get(k)][:1]
            for lv in levels:
                d = ex.get(lv, {}); rows.append({"cell": cell, "field": tid, "level": lv, "reference_expr": ref_e, "tool_expr": tool_e,
                    "mismatches": json.dumps(d.get("rows") or ([d["why"]] if d.get("why") else []) or ([d] if d.get("types") else [])) if d else (f.get("error") or ""),
                    "l4_class": d.get("class", "") if lv == "L4" else "", "l4_example": json.dumps(d.get("rows", [])[:1]) if lv == "L4" else "",
                    "assumptions": " | ".join(f.get("assumptions") or []), "parse_errors": " | ".join(f.get("errors") or [])})
        return rows
