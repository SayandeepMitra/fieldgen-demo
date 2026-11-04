"""Harness side: scorer that handles one table under several aliases in a branch (generic). Subclass of HarnessE1; the earlier classes are untouched.
The key columns of the reference are source columns (table.column); a recipe may reach such a table under several aliases. The old scorer stops there
("appears under N aliases"). Here every assignment of the reference's table references to the aliases of that table is tried (at most MAX_ASSIGN; more is
"too many" and counts as unavailable). Levels per table-repeat: PASS (rows and keys match with at least one assignment), ROWS-ONLY (row count matches, keys are
not reproduced or not available), FAIL (row count differs, no recipe, or the recipe does not run). With one alias per table the pass/fail result equals the old scorer."""
import itertools, re
from collections import Counter
from fieldgen.harness_keys import HarnessE1
from fieldgen.harness import Harness
from fieldgen.parse import recipe_info

MAX_ASSIGN = 8

class HarnessV4(HarnessE1):
    _mode = "strict"; _points = None; _choice = None

    def _alias(self, bid, t, c, al):
        if len(al) == 1: return al[0], None
        if self._mode == "record" and len(al) > 1:
            self._points.setdefault((bid, t, c), tuple(al)); return al[0], None
        if self._mode == "apply" and (bid, t, c) in self._choice: return self._choice[(bid, t, c)], None
        return None, f"key unavailable in {bid} (table {t} appears under {len(al)} aliases)"

    def _base_keys(self, g, recipe):
        """src.evaluate_v2.Harness.resolve_keys with the alias choice made by _alias."""
        info = recipe_info(recipe); refs = g["alignment"]["reference"]
        if all(e.endswith("@const") for e in g["alignment"]["source"]): return {bid: ["1"] for bid in info}, None
        if self._is_gold(g, recipe) and all(re.fullmatch(r"r\.(\w+)", x) for x in refs):
            cols = [re.fullmatch(r"r\.(\w+)", x).group(1) for x in refs]; fs = [self.fields.get(f'{g["table"]}.{c}') for c in cols]
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
            ok = [gr for gr in uniq if all(t in i["tables"] for t, _ in gr)]
            if not ok: return None, f"key unavailable in {bid} (absent)"
            if len(ok) > 1: return None, f"key unavailable in {bid} (ambiguous)"
            ks = []
            for t, c in ok[0]:
                a, err = self._alias(bid, t, c, [x for x, tt in i["aliases"].items() if tt == t])
                if err: return None, err
                ks.append(f"{a}.{c}")
            out[bid] = ks
        return out, None

    def _via_links(self, g, recipe, err):
        """HarnessE1._via_links with the alias choice made by _alias."""
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
                a, e2 = self._alias(bid, t, c, [x for x, tt in i["aliases"].items() if tt == t])
                if e2: return None, e2
                ks.append(f"{a}.{c}")
            out[bid] = ks
            for w in why: self.substitutions.append({"field": g["task_id"], "branch": bid, **w})
        return out, None

    def resolve_keys(self, g, recipe):
        keys, err = self._base_keys(g, recipe); gold = self._is_gold(g, recipe)
        if err and "(absent)" in err and not gold: keys, err = self._via_links(g, recipe, err)
        if keys is not None and not gold: keys = self._cast(g, keys)
        return keys, err

    def _set(self, mode, choice=None):
        self._mode, self._choice = mode, choice
        if mode == "record": self._points = {}

    def row_count(self, recipe):
        """Rows the recipe builds, without any key (constant key)."""
        return len(self.recipe_rows(recipe, {b["id"]: ["1"] for b in recipe["branches"]}))

    def level(self, table, recipe):
        """{level, pass, reason, rows, ref_rows, tried: [{assignment, pass, reason}], passed: [...]}; the old result is in 'old'."""
        self._set("strict"); old = self.recipe_layer(table, recipe)
        res = {"old_pass": bool(old["pass"]), "old_reason": old.get("reason"), "rows": old.get("rows"), "ref_rows": old.get("ref_rows"), "tried": [], "passed": []}
        if old["pass"]: res.update(level="PASS", **{"pass": True}); return res
        reason = old.get("reason") or ""
        if recipe is None or reason.startswith(("no valid recipe", "does not run")): res.update(level="FAIL", **{"pass": False}); return res
        anchor = next(g for g in self.fields.values() if g["table"] == table); ref_n = len(self._ref_keys(anchor)); res["ref_rows"] = ref_n
        if "appears under" in reason:
            self._set("record"); self.recipe_layer(table, recipe); pts = dict(self._points or {}); self._set("strict")
            combos = list(itertools.product(*[pts[k] for k in pts])) if pts else []
            if len(combos) > MAX_ASSIGN:
                res["too_many"] = len(combos); res["reason"] = f"too many assignments ({len(combos)})"
            else:
                for combo in combos:
                    choice = dict(zip(pts, combo)); self._set("apply", choice)
                    try: r = self.recipe_layer(table, recipe)
                    finally: self._set("strict")
                    lab = "; ".join(f"{b}:{t}.{c}={a}" for (b, t, c), a in choice.items())
                    res["tried"].append({"assignment": lab, "pass": bool(r["pass"]), "reason": r.get("reason")})
                    if r["pass"]: res["passed"].append(lab)
                if res["passed"]: res.update(level="PASS", **{"pass": True}); res["reason"] = None; return res
                res["reason"] = "no assignment reproduces the keys" if res["tried"] else reason
        else: res["reason"] = reason
        try: n = self.row_count(recipe)
        except Exception as e: res.update(level="FAIL", **{"pass": False}); res["reason"] = "does not run: " + str(e)[:100]; return res
        res["rows"] = n; res["pass"] = False; res["level"] = "ROWS-ONLY" if n == ref_n else "FAIL"; return res


Scorer = HarnessV4      # recipe layer and column scoring with alias assignment
