"""Link profile (generic; generator side): facts about how the distinct values of a source column fall into a lookup column and into the
other low-cardinality columns of the lookup table. Works on any relations of the connection; no names are built in.
Everything is computed on the given (in-memory, read-only use) connection with an interrupt; a failed or interrupted query gives None."""
import json, threading
from pathlib import Path

TIMEOUT_S, MAX_DISTINCT, TOP = 120, 30, 10

def _q(n): return '"' + n.replace('"', '""') + '"'

def run_limited(con, sql, timeout_s=TIMEOUT_S):
    cur = con.cursor(); timer = threading.Timer(timeout_s, cur.interrupt); timer.start()
    try: return cur.execute(sql).fetchall()
    except Exception: return None
    finally: timer.cancel()

def profile(con, rel, col, lookup, lcol, timeout_s=TIMEOUT_S, max_distinct=MAX_DISTINCT, top=TOP):
    """{'distinct', 'found', 'columns': {lookup column: [[value or 'empty', n], ...]}} or None."""
    s = f"SELECT DISTINCT CAST({_q(col)} AS VARCHAR) v FROM {_q(rel)} WHERE {_q(col)} IS NOT NULL"
    r = run_limited(con, f"WITH s AS ({s}) SELECT count(*), count(*) FILTER (WHERE v IN (SELECT CAST({_q(lcol)} AS VARCHAR) FROM {_q(lookup)} WHERE {_q(lcol)} IS NOT NULL)) FROM s", timeout_s)
    if r is None: return None
    out = {"distinct": r[0][0], "found": r[0][1], "columns": {}}
    names = run_limited(con, f"SELECT column_name FROM information_schema.columns WHERE table_name = '{lookup.replace(chr(39), chr(39) * 2)}' ORDER BY ordinal_position", timeout_s)
    if names is None: return None
    names = [n[0] for n in names if n[0] != lcol]
    if not names or not out["found"]: return out
    dc = run_limited(con, "SELECT " + ", ".join(f"count(DISTINCT {_q(n)})" for n in names) + f" FROM {_q(lookup)}", timeout_s)
    if dc is None: return None
    for n, k in zip(names, dc[0]):
        if k > max_distinct: continue
        rows = run_limited(con, f"WITH s AS ({s}), m AS (SELECT DISTINCT s.v, COALESCE(NULLIF(CAST(l.{_q(n)} AS VARCHAR), ''), 'empty') x FROM s JOIN {_q(lookup)} l "
                                f"ON CAST(l.{_q(lcol)} AS VARCHAR) = s.v) SELECT x, count(*) c FROM m GROUP BY x ORDER BY c DESC, x LIMIT {int(top)}", timeout_s)
        if rows is None: return None
        out["columns"][n] = [[x, c] for x, c in rows]
    return out

def _label(v): return "empty" if v == "empty" else json.dumps(" ".join(str(v).split())[:40], ensure_ascii=False)

def fact_line(lookup, lcol, p):
    parts = [f"found in {lookup}.{lcol}: {p['found']} of {p['distinct']} distinct values"]
    for n, items in p["columns"].items():
        if items: parts.append(f"{n}: " + ", ".join(f"{_label(v)} {c}" for v, c in items))
    return "; ".join(parts)

class LinkProfiles:
    """Cache in a JSON file: read when it exists, extended and written when a key is new."""
    def __init__(self, con, path, timeout_s=TIMEOUT_S):
        self.con, self.path, self.timeout_s, self.computed = con, Path(path), timeout_s, 0
        self.data = json.load(open(self.path, encoding="utf-8")) if self.path.exists() else {}

    def get(self, rel, col, lookup, lcol):
        key = f"{rel}.{col} -> {lookup}.{lcol}"
        if key not in self.data:
            p = profile(self.con, rel, col, lookup, lcol, self.timeout_s)
            if p is None: return None
            self.data[key] = p; self.computed += 1
            self.path.parent.mkdir(parents=True, exist_ok=True); json.dump(self.data, open(self.path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        return self.data[key]
