"""Audit the GOLD-populated target (tpcdi_populated.duckdb) against the official TPC-DI v1.1.0 automated audit.

Independent oracles used (neither is derived from R1's ETL):
  * DIGen's own audit files (*_audit.csv, 244 files) -> an `Audit` table, exactly as the TPC-DI kit specifies.
  * The official `tpcdi_audit.sql` script (spec Clause 7), executed verbatim except the portability substitution
    `FROM DUMMY TABLE` -> (nothing), as the script header prescribes.

Our gold only ran the HISTORICAL load (Batch 1), so checks that need incremental batches 2/3 or the ETL's own
DImessages log cannot apply. They are reported as NOT_APPLICABLE, never as pass or fail.

Usage: python3 -I gold_audit.py [--db PATH] [--out CSV]
"""
import argparse, csv, glob, os, re, sys
import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
STAGING = os.path.join(BENCH, "tpcdi", "tpcdi-kit", "staging", "3")
AUDIT_SQL = os.path.join(BENCH, "tpcdi", "TPC-DI-MS-SQL-Benchmark", "Helpers", "Scripts", "tpcdi_audit.sql")
import gold_version as _gv
DEFAULT_DB = _gv.GOLD_DB
DEFAULT_OUT = _gv.AUDIT_CSV


BATCHES = {1}   # the gold is the HISTORICAL load only: audit values for incremental batches 2/3 do not apply to it
# R1's DDL names DimTrade.Type as DT_Type (the spec calls it Type); the only schema deviation the audit script hits.
COLUMN_ALIASES = [(r"\bType not in\b", "DT_Type not in"), (r"\bw\.Type\b", "w.DT_Type"),
                  (r"(\w+(?:\.\w+)?)\s*-\s*1\s+day\b", r"\1 - INTERVAL 1 DAY"),   # DB2 date arithmetic -> DuckDB
                  (r"(\w+(?:\.\w+)?)\s*\+\s*1\s+day\b", r"\1 + INTERVAL 1 DAY")]


def load_audit(con):
    con.execute("CREATE TABLE Audit (DataSet VARCHAR, BatchID INTEGER, Date DATE, Attribute VARCHAR, Value BIGINT, DValue DOUBLE)")
    n = 0
    for f in sorted(glob.glob(os.path.join(STAGING, "**", "*_audit.csv"), recursive=True)):
        with open(f, newline="") as fh:
            rd = csv.reader(fh)
            next(rd)
            for r in rd:
                if len(r) < 6 or not r[0].strip():
                    continue
                ds, b, d, a, v, dv = [x.strip() for x in r[:6]]
                if int(b) not in BATCHES:
                    continue
                con.execute("INSERT INTO Audit VALUES (?,?,?,?,?,?)",
                            [ds, int(b), d or None, a, int(float(v)) if v else None, float(dv) if dv else None])
                n += 1
    return n


def split_tests(sql):
    """The script is `select * from ( T1 union T2 ... ) order by Test, Batch`. Split into the individual SELECTs at the
    top-level `union` keywords (line-leading, outside parentheses) so one failing test cannot hide the others."""
    body = sql[sql.index("select * from ("):]
    body = body[len("select * from ("):]
    body = body[: body.rindex(") ")] if ") " in body else body
    body = re.sub(r"--[^\n]*", "", body)               # line comments
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)  # block comments
    body = re.sub(r"FROM DUMMY TABLE", "", body, flags=re.I)
    for pat, rep in COLUMN_ALIASES:
        body = re.sub(pat, rep, body)
    parts, depth, cur, i = [], 0, [], 0
    toks = re.split(r"(\(|\)|\bunion\b)", body, flags=re.I)
    for t in toks:
        if t == "(":
            depth += 1
        elif t == ")":
            depth -= 1
        if depth == 0 and t.lower() == "union":
            parts.append("".join(cur)); cur = []
        else:
            cur.append(t)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


# Not applicable to a Batch-1-only load: needs the ETL's own message log, or the previous batch's counts.
# (Per-batch tests over `Audit a where BatchID in (...)` are fine: Audit holds Batch 1 only, so only the Batch-1 row is produced.)
NEEDS_INCREMENTAL = re.compile(r"DImessages|BatchID\s*-\s*1", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()
    src = duckdb.connect(a.db, read_only=True)
    con = duckdb.connect(":memory:")
    con.execute(f"ATTACH '{a.db}' AS pop (READ_ONLY)")
    con.execute("SET search_path='memory.main,pop.main'")
    n = load_audit(con)
    print(f"Audit table loaded: {n} rows from {len(glob.glob(os.path.join(STAGING, '**', '*_audit.csv'), recursive=True))} files")
    tests = split_tests(open(AUDIT_SQL).read())
    empty = [t for (t,) in src.execute("select table_name from duckdb_tables() where schema_name='main'").fetchall()
             if src.execute(f'select count(*) from "{t}"').fetchone()[0] == 0]
    print("tables empty in the gold (checks on them are vacuous -> not applicable):", empty)
    print(f"{len(tests)} individual test queries")
    rows = []
    for q in tests:
        name_m = re.match(r"select\s+(?:'([^']*)'|(.+?))\s+as\s+Test|select\s+'([^']*)'", q, re.I | re.S)
        label = (name_m.group(1) or name_m.group(3) or "?") if name_m else "?"
        applicable = not (NEEDS_INCREMENTAL.search(q) or label.endswith(' batches') or label.split(' ')[0] in empty)  # '... batches' = 3-batch coverage checks
        try:
            res = con.execute(q).fetchall()
            cols = [d[0] for d in con.description]
            for r in res:
                rec = dict(zip(cols, r))
                rows.append(dict(test=str(rec.get(cols[0])), batch=rec.get(cols[1]), result=rec.get(cols[2]),
                                 description=rec.get(cols[3]), applicable=applicable, error=""))
        except Exception as e:
            rows.append(dict(test=label, batch=None, result="ERROR", description="", applicable=applicable, error=str(e)[:160].replace("\n", " ")))
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    app = [r for r in rows if r["applicable"]]
    napp = [r for r in rows if not r["applicable"]]
    ok = [r for r in app if r["result"] == "OK"]
    bad = [r for r in app if r["result"] != "OK"]
    print(f"\nApplicable to a Batch-1-only load: {len(app)}  OK {len(ok)}  NOT-OK {len(bad)}")
    print(f"Not applicable (need incremental batches / ETL message log): {len(napp)}")
    for r in bad:
        print(f"  FAIL  {r['test']!r:48s} batch={r['batch']}  {r['result']}  {r['error']}")
    print(f"\nwritten {a.out}")


if __name__ == "__main__":
    main()
