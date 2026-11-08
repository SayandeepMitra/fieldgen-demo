"""
Generic "swap-in" grader. Replaces the hand-written per-column GRADABLE specs in grade_subset.py.

Idea: the executable gold for every target table is one INSERT ... SELECT in
deliverables/ported_historical_load.sql, whose select items line up one-to-one with the
target column list. To grade a candidate expression for column c of table T:
  1. keep the gold query exactly as it is (same CTEs, FROM, JOINs, WHERE, GROUP BY),
  2. replace only select item c with the candidate expression,
  3. run it, and compare the result with the already-populated T.

Row alignment needs no hand-picked key: every OTHER output column is left identical to gold,
so a row's identity is the tuple of its other columns. Probe and T are compared as multisets of
(other-columns tuple, value of c). Nothing in the gold query or the candidate is edited beyond
that one swap, and the comparator is the same for every column (see _norm).

Self-test (gold_self_test): swap in each gold expression for itself -- must reproduce T exactly.
Control test (null_control): swap in NULL -- must score ~0, otherwise the column is not
discriminating (e.g. it is constant/all-NULL in T) and a high score on it means nothing.

Limits: the candidate is evaluated in the scope of the gold final SELECT. For tables whose
final SELECT reads from CTEs (DimCustomer, DimAccount, DimSecurity, DimTrade) the model's raw
Source.* references are not visible there; those tables are reported as scope-limited.
"""
import re
import datetime
import decimal
from collections import Counter

import duckdb
import sqlglot
from sqlglot import exp

BASE = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import gold_version as _gv                                   # TPCDI_GOLD=v1|v2 picks the gold SQL + populated DB (default v1)
GOLD_SQL = _gv.GOLD_SQL
DB_PATH = _gv.GOLD_DB


def load_gold():
    """{table: {'cols': [...], 'insert': exp.Insert}} parsed from the ported gold SQL."""
    src = open(GOLD_SQL).read()
    stmts = [s.strip() for s in re.sub(r"--[^\n]*", "", src).split(";") if s.strip()]
    out = {}
    for s in stmts:
        t = sqlglot.parse_one(s, read="duckdb")
        if not isinstance(t, exp.Insert):
            continue
        out[t.this.this.name] = {"cols": [c.name for c in t.this.expressions], "insert": t}
    return out


def uses_ctes(insert):
    return bool(insert.args.get("with") or insert.args.get("with_") or insert.expression.args.get("with")
                or insert.expression.args.get("with_"))


def _with_key(node):
    for k in ("with", "with_"):
        if node.args.get(k) is not None:
            return k
    return None


def column_types(con, table):
    return {r[0]: r[1] for r in con.execute(f"DESCRIBE {table}").fetchall()}


def _strip_alias(node):
    """Expression without its output alias. sqlglot hangs the alias of a scalar subquery on the
    Subquery node itself (not an exp.Alias wrapper), so both shapes need handling."""
    if isinstance(node, exp.Alias):
        return node.this
    if isinstance(node, exp.Subquery) and node.args.get("alias") is not None:
        node = node.copy()
        node.set("alias", None)
    return node


def _ctes(ins):
    """{cte name lower: Select} for the WITH clause attached to the INSERT (or its SELECT)."""
    out = {}
    for node in (ins, ins.expression):
        wk = _with_key(node)
        if wk:
            for cte in node.args[wk].expressions:
                out[cte.alias.lower()] = cte.this
    return out


def _leaf(sub):
    """Select behind a Subquery / UNION: the leftmost branch (UNION columns are positional and the
    left branch names them; later branches only merge/COALESCE values that derive from it)."""
    while True:
        if isinstance(sub, exp.Subquery):
            sub = sub.this
        elif isinstance(sub, exp.SetOperation if hasattr(exp, "SetOperation") else exp.Union):
            sub = sub.this
        else:
            return sub


def _relations(sel, ctes):
    """[(alias lower, leaf Select or None for a base table)] for the FROM/JOIN of `sel`."""
    rels = []
    nodes = []
    frm = sel.args.get("from") or sel.args.get("from_")
    if frm is not None:
        nodes.append(frm.this)
    for j in sel.args.get("joins") or []:
        nodes.append(j.this)
    for n in nodes:
        if isinstance(n, exp.Subquery):
            rels.append((n.alias.lower(), _leaf(n.this)))
        elif isinstance(n, exp.Table):
            inner = ctes.get(n.name.lower())
            rels.append((n.alias_or_name.lower(), _leaf(inner) if inner is not None else None))
    return rels


def _has_star(sel):
    return any(isinstance(it, exp.Star) or (isinstance(it, exp.Column) and isinstance(it.this, exp.Star))
               for it in sel.expressions)


def _find_item(sel, name):
    for i, it in enumerate(sel.expressions):
        if it.alias_or_name.lower() == name.lower():
            return i
    return None


def _exposes(sel, name):
    return _find_item(sel, name) is not None or _has_star(sel)


def defining_select(ins, col):
    """Descend from the outer SELECT through derived tables / CTEs / UNION (leftmost branch) /
    SELECT * while the column is a plain pass-through, to the SELECT that actually computes it.
    Returns (select, item_index, name). This is the SCOPE both the prompt and the grader use."""
    ctes = _ctes(ins)
    cur, name = ins.expression, col
    while True:
        i = _find_item(cur, name)
        if i is None:  # only reachable via SELECT *: a pure pass-through, nothing to swap here
            return None
        item = cur.expressions[i]
        inner = item.this if isinstance(item, exp.Alias) else item
        if not isinstance(inner, exp.Column):
            return cur, i, name
        nxt = None
        for alias, sub in _relations(cur, ctes):
            if sub is None:
                continue
            if inner.table and inner.table.lower() != alias:
                continue
            if _exposes(sub, inner.name):
                nxt = sub
                break
        if nxt is None:
            return cur, i, name
        # descend only if the next select can actually hold the column (named item, or a star that
        # we can keep following); otherwise stay here
        ni = _find_item(nxt, inner.name)
        if ni is None:
            # star pass-through: keep descending through its relations until a named item appears
            probe, pname, found = nxt, inner.name, None
            for _ in range(20):
                k = _find_item(probe, pname)
                if k is not None:
                    found = (probe, k)
                    break
                nrel = [sub for _a, sub in _relations(probe, ctes) if sub is not None and _exposes(sub, pname)]
                if not nrel:
                    break
                probe = nrel[0]
            if found is None:
                return cur, i, name
            nxt = found[0]
        cur, name = nxt, inner.name


def requalify(expr_sql, scope_select, ctes=None):
    """Rewrite table qualifiers the model used (Source.FinwireCMP.x, FinwireCMP.x) to the alias
    the gold scope gives that table, so a correct reference resolves."""
    tree = sqlglot.parse_one(expr_sql, read="duckdb")
    alias_of = {t.name.lower(): t.alias_or_name for t in scope_select.find_all(exp.Table)
                if not (t.args.get("this") is None)}
    for c in tree.find_all(exp.Column):
        q = c.table
        if q and q.lower() in alias_of and alias_of[q.lower()].lower() != q.lower():
            c.set("table", exp.to_identifier(alias_of[q.lower()]))
            c.set("db", None)
    return tree.sql(dialect="duckdb")


def probe_query(gold, table, col, expr_sql=None, types=None):
    """SQL of the gold SELECT with column `col` swapped for expr_sql at the SELECT that actually
    computes it (None = keep gold). With `types`, every OUTER select item is CAST to the target
    column's declared type, mimicking the implicit casting an INSERT does."""
    ins = gold[table]["insert"].copy()
    cols = gold[table]["cols"]
    sel = ins.expression
    if expr_sql is not None:
        found = defining_select(ins, col)
        cur, i, name = found
        new = sqlglot.parse_one(requalify(expr_sql.strip().rstrip(";"), cur), read="duckdb")
        new = _strip_alias(new)  # model may have left a trailing "AS name": drop it, we re-alias
        cur.expressions[i] = exp.Alias(this=_strip_alias(new), alias=exp.to_identifier(name))
    if types:
        items = []
        for name, item in zip(cols, sel.expressions):
            items.append(exp.Alias(this=exp.cast(_strip_alias(item), exp.DataType.build(types[name], dialect="duckdb")),
                                   alias=exp.to_identifier(name)))
        sel.set("expressions", items)
    wk = _with_key(ins)
    if wk:
        sel.set(wk, ins.args[wk])
    return sel.sql(dialect="duckdb")


def _norm(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, (int, float, decimal.Decimal)):
        return repr(round(float(v), 6))
    if isinstance(v, datetime.datetime):
        v = v.date() if (v.hour, v.minute, v.second, v.microsecond) == (0, 0, 0, 0) else v
    s = str(v).strip().lower()
    if s.endswith(" 00:00:00"):
        s = s[: -len(" 00:00:00")]
    if s in ("true", "false"):
        return s
    return s


def compare(probe_rows, t_rows, ci):
    """Multiset comparison keyed by all other columns. Returns (matched, total_T, extra_probe)."""
    def split(rows):
        c = Counter()
        for r in rows:
            other = tuple(_norm(x) for j, x in enumerate(r) if j != ci)
            c[(other, _norm(r[ci]))] += 1
        return c
    p, t = split(probe_rows), split(t_rows)
    matched = sum(min(n, p[k]) for k, n in t.items())
    return matched, sum(t.values()), sum(p.values())


def grade_candidate(con, gold, table, col, expr_sql):
    """Status dict for one candidate expression (None expr = gold, for the self-test)."""
    cols = gold[table]["cols"]
    ci = cols.index(col)
    try:
        q = probe_query(gold, table, col, expr_sql, column_types(con, table))
        probe_rows = con.execute(q).fetchall()
    except Exception as e:
        return {"status": "EXECUTION_FAILED", "error": str(e)[:300]}
    t_rows = con.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
    m, total, n_probe = compare(probe_rows, t_rows, ci)
    return {"status": "EXECUTED", "matched": m, "total": total, "probe_rows": n_probe,
            "match_pct": round(100 * m / total, 2) if total else None}


def gold_self_test(con, gold):
    """Whole-table reproduction (every column swapped for itself == the gold query unchanged)."""
    res = {}
    for table, g in gold.items():
        cols = g["cols"]
        q = probe_query(gold, table, cols[0], None, column_types(con, table))
        try:
            rows = con.execute(q).fetchall()
        except Exception as e:
            res[table] = {"status": "EXECUTION_FAILED", "error": str(e)[:200]}
            continue
        t_rows = con.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
        a = Counter(tuple(_norm(x) for x in r) for r in rows)
        b = Counter(tuple(_norm(x) for x in r) for r in t_rows)
        matched = sum(min(n, a[k]) for k, n in b.items())
        res[table] = {"status": "EXECUTED", "matched": matched, "total": sum(b.values()),
                      "probe_rows": sum(a.values()), "ctes": uses_ctes(g["insert"])}
    return res


def null_control(con, gold, table, col):
    """Swap in NULL: score should be ~0 unless the column is NULL/constant in T."""
    return grade_candidate(con, gold, table, col, "NULL")


if __name__ == "__main__":
    import sys, time
    con = duckdb.connect(DB_PATH, read_only=True)
    gold = load_gold()
    print(f"{'table':18s} {'ctes':5s} {'status':18s} {'matched':>10s} / {'T rows':>10s}  probe_rows  secs")
    for table in gold:
        t0 = time.time()
        r = gold_self_test(con, {table: gold[table]})[table]
        print(f"{table:18s} {str(r.get('ctes')):5s} {r['status']:18s} {r.get('matched',''):>10} / {r.get('total',''):>10}  {r.get('probe_rows','')}  {time.time()-t0:.1f}"
              + (f"  {r.get('error','')}" if r["status"] != "EXECUTED" else ""))
