"""L4 robustness for the package (harness side). Perturbed copies of the package source, one per class, seed 2026.
Classes: a random NULLs, b unseen/empty/mixed-case strings, c boundary values, d lookup misses, e uppercase ids.
Generic: perturbs every table; key columns (pk, link columns, alignment keys) are kept consistent."""
import random
from fieldgen.db import package_connection
SEED = 2026
CLASSES = {"a": "random NULLs", "b": "unseen/empty/mixed-case strings", "c": "boundary values", "d": "lookup misses", "e": "uppercase ids"}
_CACHE = {}

def _roles(pkg, align_cols):
    pk = {t["name"]: set(t["pk"]) for t in pkg.source.tables}
    link = {t["name"]: set() for t in pkg.source.tables}; child = {t["name"]: set() for t in pkg.source.tables}
    for l in pkg.source.links:
        link[l["child"]] |= set(l["child_columns"]); link[l["parent"]] |= set(l["parent_columns"]); child[l["child"]] |= set(l["child_columns"])
    return pk, link, child

def build_class(pkg, cls, align_cols):
    rng = random.Random(f"{SEED}:{cls}")
    con = package_connection(pkg); pk, link, child = _roles(pkg, align_cols); n = 0
    for t in pkg.source.tables:
        name, cols = t["name"], t["columns"]; protected = pk[name] | link[name] | {c for (tt, c) in align_cols if tt == name}
        rows = [r[0] for r in con.execute(f'select rowid from "{name}" order by rowid').fetchall()]
        if not rows: continue
        free = [c for c in cols if c["name"] not in protected]
        def clone(rid, over):
            nonlocal n; n += 1
            sel = []
            for c in cols:
                q = f'"{c["name"]}"'
                if c["name"] in over: sel.append(over[c["name"]])
                elif c["name"] in pk[name] | {x for (tt, x) in align_cols if tt == name} and c["type"].upper().startswith("VARCHAR"): sel.append(f"{q} || '~{n}'")
                else: sel.append(q)
            con.execute(f'INSERT INTO "{name}" SELECT {", ".join(sel)} FROM "{name}" WHERE rowid = {rid}')
        isv = lambda c: c["type"].upper().startswith("VARCHAR")
        if cls == "a":
            for c in free:
                pick = rng.sample(rows, max(1, len(rows) // 5))
                con.execute(f'UPDATE "{name}" SET "{c["name"]}" = NULL WHERE rowid IN ({",".join(map(str, pick))})')
        elif cls == "b":
            for v in ("'zzz'", "''", "CASE WHEN {q} = upper({q}) THEN lower({q}) ELSE upper({q}) END", "' ' || {q}"):
                for rid in rng.sample(rows, min(3, len(rows))):
                    clone(rid, {c["name"]: v.format(q=f'"{c["name"]}"') for c in free if isv(c)})
        elif cls == "c":
            dates = ["DATE '1900-01-01'", "DATE '2000-02-29'", "DATE '2262-04-11'"]; tss = ["TIMESTAMPTZ '1900-01-01 00:00:00+00'", "TIMESTAMPTZ '2000-12-31 23:59:59+00'", "TIMESTAMPTZ '2000-12-31 23:59:59+05'"]
            for i in range(3):
                over = {}
                for c in free:
                    ty = c["type"].upper()
                    if ty == "DATE": over[c["name"]] = dates[i]
                    elif ty.startswith("TIMESTAMP"): over[c["name"]] = tss[i]
                    elif ty in ("INTEGER", "BIGINT"): over[c["name"]] = ["0", "-1", "2147483647"][i]
                    elif ty in ("DOUBLE", "FLOAT", "DECIMAL"): over[c["name"]] = ["0", "-1", "1e9"][i]
                clone(rng.choice(rows), over)
        elif cls == "d":
            cc = [c for c in cols if c["name"] in child[name] and isv(c) and c["name"] not in pk[name]]
            if cc:
                for rid in rng.sample(rows, min(3, len(rows))): clone(rid, {c["name"]: "'zz_missing'" for c in cc})
        elif cls == "e":
            for c in cols:
                if isv(c) and (c["name"] in pk[name] or c["name"] in link[name]): con.execute(f'UPDATE "{name}" SET "{c["name"]}" = upper("{c["name"]}")')
    return con

class _UTCConn:
    """A DuckDB cursor does not inherit the session time zone of its connection; the perturbed-data connections are used through .cursor(), so the cursor is set to UTC (as the base connection is)."""
    def __init__(self, con): self._c = con
    def cursor(self):
        cur = self._c.cursor(); cur.execute("SET TimeZone='UTC'"); return cur
    def __getattr__(self, name): return getattr(self._c, name)

def class_connection(pkg, cls, align_cols):
    key = (cls, tuple(sorted(align_cols)))
    if key not in _CACHE: _CACHE[key] = build_class(pkg, cls, align_cols)
    return _UTCConn(_CACHE[key])
