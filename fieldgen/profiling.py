"""Column profiles of a source table computed from its CSV file (used when source/profiles/<table>.json is absent). Same structure as the profile files."""
import re
from collections import Counter

def _shape(v): return re.sub(r"[A-Za-z]", "A", re.sub(r"[0-9]", "9", str(v)))
def _cut(v): return v if not isinstance(v, str) else v[:40]
_NUM = ("INT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "REAL")

def profile_table(pkg, table):
    rows = pkg.source.rows(table["name"]); n = len(rows); out = {}
    for c in table["columns"]:
        name, ty = c["name"], c["type"].upper(); vals = [r[name] for r in rows if r.get(name) not in (None, "")]; cnt = Counter(vals)
        p = {"type": c["type"], "rows": n, "nulls": n - len(vals), "null_rate": round((n - len(vals)) / n, 6) if n else 0.0, "distinct": len(cnt),
             "top": [[_cut(v), k] for v, k in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[:10]]}
        if vals and any(x in ty for x in _NUM + ("DATE", "TIME")):
            try: key = float if any(x in ty for x in _NUM) else str; p["min"], p["max"] = str(min(vals, key=key)), str(max(vals, key=key))
            except ValueError: p["min"], p["max"] = min(vals), max(vals)
        else:
            lens = [len(v) for v in vals]; p["min_len"], p["max_len"] = (min(lens), max(lens)) if lens else (None, None)
        sh = Counter(_shape(v)[:40] for v in vals); p["shapes"] = sorted(sh.items(), key=lambda kv: (-kv[1], kv[0]))[:5]; out[name] = p
    return {"relation": table["name"], "rows": n, "columns": out}
