"""Harness side: evaluator fixes for the perturbation level (L4). Subclass of Harness; the original classes are untouched.
 a. class e (upper-cased ids): existing rows are kept; copies of rows whose id/link/alignment columns change under upper() are added, so joins stay
    consistent in the upper-cased copy and in the original rows. A class whose reference returns no rows on the variant (while it has rows on the real
    data) is invalid for that table: skipped, recorded in self.invalid, never a failure.
 b. an empty candidate result and an empty reference result are equal.
 c. every failing class is stored per field in res["L4_failed"]. Classes are checked in the order of l4_v2.CLASSES (a, b, c, d, e); the original code
    checked all of them but stored only the first failing one."""
from collections import Counter
import fieldgen.compare as ev
from fieldgen import l4 as l4_v2
from fieldgen.db import package_connection
from fieldgen.harness import Harness, mismatches

def build_class_e_copy(pkg, align_cols):
    con = package_connection(pkg); pk, link, child = l4_v2._roles(pkg, align_cols)
    for t in pkg.source.tables:
        name = t["name"]; keyc = {c["name"] for c in t["columns"] if c["type"].upper().startswith("VARCHAR") and (c["name"] in pk[name] or c["name"] in link[name] or (name, c["name"]) in align_cols)}
        if not keyc: continue
        sel = ", ".join(f'upper("{c["name"]}")' if c["name"] in keyc else f'"{c["name"]}"' for c in t["columns"])
        cond = " OR ".join(f'"{c}" IS DISTINCT FROM upper("{c}")' for c in sorted(keyc))
        con.execute(f'INSERT INTO "{name}" SELECT {sel} FROM "{name}" WHERE {cond}')
    return con

class HarnessFix(Harness):
    def __init__(self, *a, **k):
        super().__init__(*a, **k); self.invalid = set(); self._last_bad = []
        l4_v2._CACHE[("e", tuple(sorted(self.align_cols)))] = build_class_e_copy(self.pkg, self.align_cols)

    def ref_l4(self, g):
        tid = g["task_id"]
        if tid in self._ref4: return self._ref4[tid]
        if not self.recipes: self._ref4[tid] = (False, {}); return self._ref4[tid]     # minimum reference format: no reference expressions, no L4
        rtype = self.ttypes[g["table"]][g["column"]]; rows = {}; ok = True
        if g["kind"] == "value":
            grecipe, gsql = self.ref_sql(g)
            try: base = self.run_on(self.con, gsql, grecipe, rtype)
            except Exception: base = []
            for c in l4_v2.CLASSES:
                try:
                    con = l4_v2.class_connection(self.pkg, c, self.align_cols).cursor()
                    rows[c] = self.run_on(con, gsql, grecipe, rtype)
                    if Counter(rows[c]) != Counter(self.run_on(con, gsql, grecipe, rtype)): ok = False; break
                    if not rows[c] and base: rows[c] = None; self.invalid.add((c, g["table"]))
                except Exception: ok = False; break
        self._ref4[tid] = (ok, rows); return self._ref4[tid]

    def _l4(self, g, recipe, cand_sql, rtype, task, gold, align):
        bad = []; n = align["arity"]
        okref, refrows = self.ref_l4(g)
        if not okref: self._last_bad = []; return None, []
        for c in l4_v2.CLASSES:
            if g["kind"] == "value" and refrows.get(c, 0) is None: continue          # invalid variant for this table
            con = l4_v2.class_connection(self.pkg, c, self.align_cols).cursor(); ex = []
            try:
                cand = self.run_on(con, cand_sql, recipe, rtype)
                if g["kind"] == "keygen": ok, _ = ev.keygen_property(task, align, cand)
                elif g["kind"] == "placeholder": ok = all(r[-1] is None for r in cand)
                else:
                    ref = refrows[c]
                    if not cand and not ref: ok = True
                    else:
                        cmp = ev.compare(task, gold, align, cand, ref); ok = cmp["L1"] and (cmp["L2"] or cmp["wrong"] == 0)
                        if not ok: ex = mismatches(cand, ref, n)
            except Exception as e: ok = False; ex = [["error", str(e)[:100], ""]]
            if not ok: bad.append({"class": c, "name": l4_v2.CLASSES[c], "rows": ex})
        self._last_bad = bad
        return not bad, bad

    def score_field(self, recipe, final, tid, robust=True):
        self._last_bad = []
        res = super().score_field(recipe, final, tid, robust)
        res["L4_failed"] = [b["class"] for b in self._last_bad]
        return res
