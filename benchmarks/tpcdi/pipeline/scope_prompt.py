"""
Prompt v4: the SCOPE CONTRACT.

Why: with prompt v3 the model was shown an informal, CSV-derived skeleton, while the grader (and the
gold) evaluate an expression inside one specific executable query. A correct expression could fail to
resolve there (aliases, derived tables, CTE chains), and ~half of the failures in the first full
grading pass were that mismatch, not model error.

Fix: derive the scope ONCE from the gold (grade_swap.defining_select -> the SELECT that actually
computes the column) and use the same object for both:
  * the prompt shows that SELECT's FROM/JOIN/WHERE/GROUP BY (select list replaced by a placeholder),
    the relations/aliases/columns visible in it, and the columns the gold expression reads;
  * the grader (grade_swap.probe_query) swaps the model's expression into exactly that SELECT.
They cannot disagree by construction.

Held out (never shown): the gold expression itself, other columns' expressions (derived relations are
shown as a name + column list, not their bodies), rule_sql / column_kind / rule_reliable.
"""
import duckdb
import sqlglot
from sqlglot import exp

import grade_swap as g
from build_prompt import _target_column_ddl, FIELD_DESCRIPTIONS, DB_PATH
from profiling import profile_column, format_profile_for_prompt

PROMPT_VERSION = "v4-scope-2026-11-04"
PROMPT_VERSION_V5 = "v5-spec-2026-11-05"
SPEC_DESC_PATH = f"{g.BASE}/deliverables/tpcdi_spec_target_descriptions.json"

# TPC-DI spec Clause 4.4.1.1: the history-tracking (SCD type 2) dimensions. A spec fact, not derived from the gold.
SCD2_TABLES = {"DimAccount", "DimBroker", "DimCompany", "DimCustomer", "DimSecurity"}

LOAD_CONTEXT = """LOAD CONTEXT (TPC-DI specification, Clause 4.4.2)
  You are writing the Historical Load: the first load of an empty warehouse from the Batch 1 source files.
  The spec fixes BatchID per execution phase: Initialization = 0, Historical Load = 1,
  Incremental Update 1 = 2, Incremental Update 2 = 3."""

SCD2_CONTEXT = """HISTORY-TRACKING DIMENSION (TPC-DI specification, Clause 4.4.1)
  {table} is a history-tracking ("type 2") dimension: a source record's natural key stays constant, each
  recorded change becomes a new row. A row for a natural key that is not yet in the table gets IsCurrent = TRUE,
  EffectiveDate = the value given by the transformation, and EndDate = 9999-12-31. When a later record for the
  same natural key arrives, the earlier row is expired: IsCurrent = FALSE and EndDate = the EffectiveDate of the
  new record. So per natural key the rows form one consecutive chain and exactly one row is current."""

INTERMEDIATE_NOTE = """NOTE ON THIS SCOPE
  This SELECT is an intermediate step of a multi-step query, not the final INSERT: its output is consumed by
  later steps before it reaches {table}. Constraints declared on the target column (NOT NULL, CHAR length) are
  enforced on the final result."""

_spec_cache = {}


def spec_description(table, col):
    if "d" not in _spec_cache:
        import json
        _spec_cache["d"] = json.load(open(SPEC_DESC_PATH))
    return _spec_cache["d"].get(f"{table}.{col}")


def build_prompt_v5(gold, con, table, col, v4_text, features=("desc", "conv", "note")):
    """v4 prompt text + exactly three spec-derived additions (nothing else changes, so v4 vs v5 is a paired
    comparison): (1) target description from spec Clause 3.2, (2) load-context / history-tracking conventions
    from spec Clause 4.4.1-4.4.2, (3) a note when the scope is an intermediate step of the gold query.
    None of it is taken from, or conditioned on, the gold expression of the column."""
    import re
    scope = derive_scope(gold, con, table, col)
    sd = spec_description(table, col) if "desc" in features else None
    text = v4_text
    if sd:
        text, n = re.subn(r"(?m)^  Description: .*$", lambda m: f"  Description: {sd}  [TPC-DI spec, Clause 3.2]", text, count=1)
        assert n == 1
    blocks = []
    if "conv" in features:
        blocks.append(LOAD_CONTEXT)
        if table in SCD2_TABLES:
            blocks.append(SCD2_CONTEXT.format(table=table))
    if "note" in features and scope["cur"] is not scope["ins"].expression:
        blocks.append(INTERMEDIATE_NOTE.format(table=table))
    if not blocks:
        return text
    marker = "\nQUERY SCOPE"
    assert text.count(marker) == 1
    return text.replace(marker, "\n" + "\n\n".join(blocks) + "\n" + marker)
SAMPLE_ROWS = 3
PROFILE_LIMIT = 200000  # rows used when a profiled column lives in a derived relation


def _with_sql(ins):
    for node in (ins, ins.expression):
        wk = g._with_key(node)
        if wk:
            return node.args[wk].sql(dialect="duckdb") + "\n"
    return ""


def _tname(t):
    return (t.db + "." if t.db else "") + t.name


def _describe(con, sql):
    return [(r[0], r[1]) for r in con.execute("DESCRIBE " + sql).fetchall()]


def _scope_relations(cur, ins, con):
    """[{alias, kind: base|cte|derived, table, name, sql, columns[(name,type)]}] for cur's FROM/JOINs."""
    ctes = g._ctes(ins)
    w = _with_sql(ins)
    frm = cur.args.get("from") or cur.args.get("from_")
    nodes = ([frm.this] if frm is not None else []) + [j.this for j in (cur.args.get("joins") or [])]
    rels = []
    for n in nodes:
        if isinstance(n, exp.Subquery):
            sub = n.this.sql(dialect="duckdb")
            cols = _describe(con, f"{w}SELECT * FROM ({sub}) q")
            rels.append({"alias": n.alias, "kind": "derived", "table": None, "name": n.alias, "sql": sub, "columns": cols})
        elif isinstance(n, exp.Table):
            if not n.db and n.name.lower() in ctes:
                cols = _describe(con, f"{w}SELECT * FROM {n.name}")
                rels.append({"alias": n.alias_or_name, "kind": "cte", "table": None, "name": n.name,
                             "sql": f"SELECT * FROM {n.name}", "columns": cols})
            else:
                tn = _tname(n)
                rels.append({"alias": n.alias_or_name, "kind": "base", "table": tn, "name": tn, "sql": None,
                             "columns": _describe(con, f"SELECT * FROM {tn}")})
    return rels


def _scope_query_text(cur, col):
    """The scope SELECT with its select list replaced by a placeholder and derived tables shown by name."""
    c = cur.copy()
    frm = c.args.get("from") or c.args.get("from_")
    if frm is not None and isinstance(frm.this, exp.Subquery):
        frm.set("this", exp.Table(this=exp.to_identifier(frm.this.alias)))
    for j in c.args.get("joins") or []:
        if isinstance(j.this, exp.Subquery):
            j.set("this", exp.Table(this=exp.to_identifier(j.this.alias)))
    c.set("expressions", [exp.Alias(this=exp.Var(this="<YOUR_EXPRESSION>"), alias=exp.to_identifier(col))])
    for k in ("order", "limit", "distinct", "qualify", "windows", "with", "with_"):
        if c.args.get(k) is not None:
            c.set(k, None)
    return c.sql(dialect="duckdb", pretty=True)


def derive_scope(gold, con, table, col):
    """Everything the prompt (and audit) needs about the column's scope, derived from the gold only."""
    ins = gold[table]["insert"].copy()
    found = g.defining_select(ins, col)
    if found is None:
        return None
    cur, i, name = found
    rels = _scope_relations(cur, ins, con)
    by_alias = {r["alias"].lower(): r for r in rels}
    item_expr = g._strip_alias(cur.expressions[i])

    # columns the gold expression reads; lookups inside sub-selects resolve against their own FROM
    inner_tables = {t.alias_or_name.lower(): _tname(t) for t in item_expr.find_all(exp.Table)}
    refs, lookup_tables = [], []
    for c in item_expr.find_all(exp.Column):
        q = (c.table or "").lower()
        if q in by_alias:
            r = by_alias[q]
            refs.append({"alias": r["alias"], "col": c.name, "relation": r})
        elif q in inner_tables:
            if inner_tables[q] not in lookup_tables:
                lookup_tables.append(inner_tables[q])
        elif not q:
            for r in rels:
                if c.name.lower() in (x[0].lower() for x in r["columns"]):
                    refs.append({"alias": r["alias"], "col": c.name, "relation": r})
                    break
    for t in item_expr.find_all(exp.Table):
        tn = _tname(t)
        if tn not in lookup_tables and tn.lower() not in {x["name"].lower() for x in rels if x["kind"] == "base"}:
            lookup_tables.append(tn)
    seen, uniq = set(), []
    for r in refs:
        k = (r["alias"].lower(), r["col"].lower())
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return {"cur": cur, "ins": ins, "item_index": i, "relations": rels, "refs": uniq,
            "lookup_tables": lookup_tables, "query_text": _scope_query_text(cur, col),
            "grouped": cur.args.get("group") is not None, "with_sql": _with_sql(ins)}


def matched_fields(scope):
    """['Source.FinwireCMP.FoundingDate', ...] -- base-table refs resolved to table.column, derived ones as alias.column."""
    out = []
    for r in scope["refs"]:
        rel = r["relation"]
        out.append(f"{rel['table']}.{r['col']}" if rel["kind"] == "base" else f"{r['alias']}.{r['col']}")
    return out


def _sample_and_profile(con, scope):
    sample_lines, profile_lines = [], []
    by_rel = {}
    for r in scope["refs"]:
        by_rel.setdefault(r["alias"], (r["relation"], []))[1].append(r["col"])
    w = scope["with_sql"]
    for alias, (rel, cols) in by_rel.items():
        collist = ", ".join(dict.fromkeys(cols))
        src = rel["table"] if rel["kind"] == "base" else f"({rel['sql']})"
        try:
            rows = con.execute(f"{w}SELECT {collist} FROM {src} {'' if rel['kind'] == 'base' else 'q'} LIMIT {SAMPLE_ROWS}").fetchall()
            sample_lines.append(f"{alias} ({rel['name']}) sample rows (columns: {collist}):")
            sample_lines += ["  " + str(x) for x in rows]
        except Exception:
            pass
        for c in dict.fromkeys(cols):
            try:
                if rel["kind"] == "base":
                    p = profile_column(con, rel["table"], c)
                    p["table"] = f"{alias} ({rel['table']})"
                else:
                    p = profile_column(con, f"({w}SELECT CAST({c} AS VARCHAR) AS v FROM ({rel['sql']}) q LIMIT {PROFILE_LIMIT})", "v")
                    p["table"], p["column"] = f"{alias} ({rel['name']})", c
                profile_lines.append(format_profile_for_prompt(p))
            except Exception as e:
                profile_lines.append(f"  (could not profile {alias}.{c}: {str(e)[:60]})")
    return sample_lines, profile_lines


def build_prompt_v4(gold, con, table, col):
    scope = derive_scope(gold, con, table, col)
    if scope is None:
        raise ValueError(f"no defining select for {table}.{col}")
    ddl = _target_column_ddl(table, col)
    desc = FIELD_DESCRIPTIONS.get((table, col), "(no description available)")

    rel_lines = []
    for r in scope["relations"]:
        what = r["table"] if r["kind"] == "base" else f"derived relation {r['name']}"
        rel_lines.append(f"  {r['alias']} = {what}: " + ", ".join(f"{n} {t}" for n, t in r["columns"]))
    lookup_lines = []
    for t in scope["lookup_tables"]:
        try:
            cols = _describe(con, f"SELECT * FROM {t}")
            lookup_lines.append(f"  {t} (already populated): " + ", ".join(f"{n} {ty}" for n, ty in cols))
        except Exception:
            pass
    sample_lines, profile_lines = _sample_and_profile(con, scope)
    fields = matched_fields(scope)

    return f"""You are writing one SQL expression to populate a single column of a data warehouse table.

TARGET
  Table: {table}
  Column: {col}
  Declared type/constraints: {ddl}
  Description: {desc}

QUERY SCOPE (fixed by the benchmark -- do not change it). Your expression replaces <YOUR_EXPRESSION>
in this query, so it may only use the relations and aliases below:
{scope['query_text']}

RELATIONS VISIBLE IN THAT SCOPE (alias = relation: columns -- use only these names)
{chr(10).join(rel_lines)}
{('ALREADY-POPULATED TABLES YOU MAY ALSO QUERY (e.g. in a lookup sub-select)' + chr(10) + chr(10).join(lookup_lines)) if lookup_lines else ''}
MATCHED SOURCE FIELD(S) FOR THIS COLUMN (the matching, given to you -- your job is only the transformation)
{chr(10).join('  - ' + f for f in fields) if fields else '  (none -- the value is not read from any column of the scope)'}

SAMPLE DATA
{chr(10).join(sample_lines) if sample_lines else '  (not available)'}

DATA PROFILE
{chr(10).join(profile_lines) if profile_lines else '  (not available)'}

TASK
Write the SQL expression (only the select-list formula; the FROM/JOIN/WHERE above are already
written) that correctly populates {table}.{col}, respecting the declared type/constraints. Write
DuckDB-compatible SQL only (no T-SQL/Oracle/Postgres-specific functions such as TO_DATE, CONVERT,
STUFF, NEXT VALUE FOR). Use only aliases and columns shown above; do not invent names. Explain your
reasoning in one sentence, then give the SQL expression.
"""


if __name__ == "__main__":
    import sys
    con = duckdb.connect(DB_PATH, read_only=True)
    gold = g.load_gold()
    t, c = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("DimCompany", "FoundingDate")
    print(build_prompt_v4(gold, con, t, c))
