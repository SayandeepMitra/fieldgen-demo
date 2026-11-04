"""Link profile with a NULL label (generic; generator side). null_label false: identical to src/link_profile_v4.py.
null_label true: SQL NULL and the empty string are two different values (labels NULL and "")."""
import json
from fieldgen.link_facts import (profile as profile_v4, fact_line as fact_line_v4, run_limited, LinkProfiles, TIMEOUT_S, MAX_DISTINCT, TOP, _q)

def profile(con, rel, col, lookup, lcol, timeout_s=TIMEOUT_S, max_distinct=MAX_DISTINCT, top=TOP, null_label=False):
    if not null_label: return profile_v4(con, rel, col, lookup, lcol, timeout_s, max_distinct, top)
    base = profile_v4(con, rel, col, lookup, lcol, timeout_s, max_distinct, top)
    if base is None or not base["columns"]: return base
    s = f"SELECT DISTINCT CAST({_q(col)} AS VARCHAR) v FROM {_q(rel)} WHERE {_q(col)} IS NOT NULL"
    for n in list(base["columns"]):
        rows = run_limited(con, f"WITH s AS ({s}), m AS (SELECT DISTINCT s.v, CAST(l.{_q(n)} AS VARCHAR) x FROM s JOIN {_q(lookup)} l ON CAST(l.{_q(lcol)} AS VARCHAR) = s.v) "
                                f"SELECT x, count(*) c FROM m GROUP BY x ORDER BY c DESC, x NULLS LAST LIMIT {int(top)}", timeout_s)
        if rows is None: return None
        base["columns"][n] = [[x, c] for x, c in rows]
    return base

def _label(v): return "NULL" if v is None else json.dumps(" ".join(str(v).split())[:40], ensure_ascii=False)

def fact_line(lookup, lcol, p, null_label=False):
    if not null_label: return fact_line_v4(lookup, lcol, p)
    parts = [f"found in {lookup}.{lcol}: {p['found']} of {p['distinct']} distinct values"]
    for n, items in p["columns"].items():
        if items: parts.append(f"{n}: " + ", ".join(f"{_label(v)} {c}" for v, c in items))
    return "; ".join(parts)

class LinkProfilesV5(LinkProfiles):
    def __init__(self, con, path, timeout_s=TIMEOUT_S, null_label=False):
        super().__init__(con, path, timeout_s); self.null_label = null_label

    def get(self, rel, col, lookup, lcol):
        if not self.null_label: return super().get(rel, col, lookup, lcol)
        key = f"{rel}.{col} -> {lookup}.{lcol}"
        if key not in self.data:
            p = profile(self.con, rel, col, lookup, lcol, self.timeout_s, null_label=True)
            if p is None: return None
            self.data[key] = p; self.computed += 1
            self.path.parent.mkdir(parents=True, exist_ok=True); json.dump(self.data, open(self.path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        return self.data[key]
