"""Harness side: scorer fixes for the recipe layer (E1-R). Subclass of HarnessFix; the earlier classes are untouched.
 a. alignment keys of a tool recipe are cast to the type of the reference key (a timestamp key against a date key is compared as a date);
 b. a gold alignment key that names a column of a relation the recipe lacks is resolved through a many-to-one (or one-to-one) link to a column of
    a relation the recipe has; every substitution is logged in self.substitutions;
 c. the recipe layer counts rows as the table build does: full branch rows, a multiset of keys, de-duplicated only for union_distinct."""
import re
from collections import Counter
import sqlglot
from sqlglot import exp
from fieldgen.harness_fix import HarnessFix
from fieldgen.harness import Harness
from fieldgen.parse import recipe_info, branch_tables
from fieldgen.assemble import _keys, _tail, assemble_table, combine_sql
import fieldgen.harness as _ev2

def assemble_table_e1(recipe, columns, exprs, types, key_exprs=None):
    """assemble_table with generated keys numbered one after the other, so a key may be ordered by an earlier generated key (no nested windows)."""
    gen = {k["column"]: k for k in recipe.get("keys") or [] if k["column"] in columns}
    if len(gen) < 2: return assemble_table(recipe, columns, exprs, types, key_exprs)
    first = next(iter(gen)); one = dict(recipe); one["keys"] = [k for k in recipe["keys"] if k["column"] == first]
    q = assemble_table(one, columns, exprs, types, key_exprs)
    for c, k in list(gen.items())[1:]:
        q = f'SELECT *, CAST(ROW_NUMBER() OVER (ORDER BY {", ".join(k["order_by"])}) AS {types[c]}) AS "{c}" FROM ({q})'
    return q

class HarnessE1(HarnessFix):
    def __init__(self, *a, **k):
        super().__init__(*a, **k); self.substitutions = []; self._ktypes = {}
        self._links = sorted((l for l in self.pkg.source.links if l["cardinality"] in ("many_to_one", "one_to_one") and not l.get("weak")), key=lambda l: (l["child"], l["parent"], l["child_columns"]))

    # ---- a. key types
    def key_types(self, g):
        k = g["task_id"]
        if k not in self._ktypes:
            ts = []
            for e in g["alignment"]["reference"]:
                try: ts.append(self.con.execute(f'SELECT typeof(({e})) FROM ref."{g["table"]}" r LIMIT 1').fetchone()[0])
                except Exception: ts.append(None)
            self._ktypes[k] = ts
        return self._ktypes[k]

    def _cast(self, g, keys):
        if all(e.endswith("@const") for e in g["alignment"]["source"]): return keys
        ts = self.key_types(g)
        return {b: [f"TRY_CAST(({x}) AS {t})" if t else x for x, t in zip(ks, ts)] for b, ks in keys.items()}

    # ---- b. link substitution
    def _via_links(self, g, recipe, err):
        info = recipe_info(recipe); groups = {}
        for e in g["alignment"]["source"]:
            bid, tc = e.split(":", 1); groups.setdefault(bid, []).append(tuple(tc.split(".", 1)))
        uniq = []
        for gr in groups.values():
            if gr not in uniq: uniq.append(gr)
        out = {}
        for bid, i in info.items():
            tables = list(i["tables"]); cands = []
            for gr in uniq:
                new, why = [], []
                for t, c in gr:
                    if t in tables: new.append((t, c)); continue
                    hit = next(((l["child"], l["child_columns"][l["parent_columns"].index(c)], l) for l in self._links if l["parent"] == t and len(l["child_columns"]) == 1 and c in l["parent_columns"] and l["child"] in tables), None) \
                        or next(((l["parent"], l["parent_columns"][l["child_columns"].index(c)], l) for l in self._links if l["child"] == t and len(l["child_columns"]) == 1 and c in l["child_columns"] and l["parent"] in tables), None)
                    if not hit: new = None; break
                    new.append((hit[0], hit[1])); why.append({"from": f"{t}.{c}", "to": f"{hit[0]}.{hit[1]}", "link": f"{hit[2]['child']}.{','.join(hit[2]['child_columns'])} -> {hit[2]['parent']}.{','.join(hit[2]['parent_columns'])} ({hit[2]['cardinality']})"})
                if new: cands.append((new, why))
            if not cands: return None, err
            new, why = cands[0]; ks = []
            for t, c in new:
                al = [a for a, tt in i["aliases"].items() if tt == t]
                if len(al) != 1: return None, f"key unavailable in {bid} (table {t} appears under {len(al)} aliases)"
                ks.append(f"{al[0]}.{c}")
            out[bid] = ks
            for w in why: self.substitutions.append({"field": g["task_id"], "branch": bid, **w})
        return out, None

    def resolve_keys(self, g, recipe):
        keys, err = Harness.resolve_keys(self, g, recipe); gold = self._is_gold(g, recipe)
        if err and "(absent)" in err and not gold: keys, err = self._via_links(g, recipe, err)
        if keys is not None and not gold: keys = self._cast(g, keys)
        return keys, err

    # ---- c. one row logic
    def recipe_rows(self, recipe, keys):
        """Full rows of every branch (keys first); de-duplicated when the recipe says union_distinct; returns the list of key tuples."""
        out = []; n = len(next(iter(keys.values()))); seen = set()
        for b in recipe["branches"]:
            ks = _keys(keys[b["id"]], recipe.get("group_by"))
            q = f"SELECT {ks}, * {b['from']}{_tail(recipe)}" if not recipe.get("group_by") else f"SELECT {ks} {b['from']}{_tail(recipe)}"
            for r in self.con.execute(q).fetchall():
                r = tuple(None if v is None else str(v) for v in r)
                if recipe["combine"] == "union_distinct":
                    if r in seen: continue
                    seen.add(r)
                out.append(r[:n])
        return out

    def recipe_layer(self, table, recipe):
        gr = self.recipes.get(table) or {"branches": [], "combine": None, "group_by": None}; anchor = next(g for k, g in self.fields.items() if g["table"] == table); diag = {}
        if recipe is None: return {"pass": False, "reason": "no valid recipe", "diag": diag}
        info = recipe_info(recipe); src_t = {t["name"] for t in self.pkg.source.tables}
        used = [t for t in dict.fromkeys(t for i in info.values() for t in i["tables"]) if t in src_t]
        gold_tabs = [t for t in dict.fromkeys(t for b in gr["branches"] for t in branch_tables(b["from"])[1]) if t in src_t]
        diag = {"tables_used": used, "gold_tables": gold_tabs, "extra_tables": [t for t in used if t not in gold_tabs], "missing_tables": [t for t in gold_tabs if t not in used],
                "combine": recipe["combine"], "gold_combine": gr["combine"], "grouped": bool(recipe.get("group_by")), "gold_grouped": bool(gr["group_by"]),
                "joins": sum(len(list(sqlglot.parse_one("SELECT 1 " + b["from"], read="duckdb").find_all(exp.Join))) for b in recipe["branches"])}
        n0 = len(self.substitutions); keys, err = self.resolve_keys(anchor, recipe)
        diag["key_substitutions"] = self.substitutions[n0:]
        if err: return {"pass": False, "reason": err, "diag": diag}
        try: cand = self.recipe_rows(recipe, keys)
        except Exception as e: return {"pass": False, "reason": "does not run: " + str(e)[:120], "diag": diag}
        ref = self._ref_keys(anchor); C, R = Counter(cand), Counter(ref); ok = C == R and len(cand) == len(ref)
        return {"pass": ok, "rows": len(cand), "ref_rows": len(ref), "diag": diag,
                "reason": None if ok else f"key multiset differs (missing {sum((R - C).values())}, extra {sum((C - R).values())}; rows {len(cand)} vs {len(ref)})"}

    # a formula with a window function nests badly under a generated-key window: count it as NULL for the table build (as a formula that does not run)
    def table_level(self, table, recipe, exprs):
        old = _ev2.assemble_table; _ev2.assemble_table = assemble_table_e1
        try: out = super().table_level(table, recipe, exprs)
        finally: _ev2.assemble_table = old
        if not out.get("ran") and "nested" in str(out.get("error", "")).lower():
            ex2 = {c: e for c, e in exprs.items() if not any(re.search(r"\bover\s*\(", s, re.I) for s in e.values())}
            out = super().table_level(table, recipe, ex2); out["dropped_window_formulas"] = sorted(set(exprs) - set(ex2))
        return out
