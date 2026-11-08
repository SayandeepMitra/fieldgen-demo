"""Convert a fieldgen run folder (run/sql/<lowercase table>.sql) into an L2 submission directory (<Table>.sql, our table names).

fieldgen's SQL refers to source tables by bare name (it runs in a DB that holds only the source). The L2 sandbox also holds the (empty)
target tables, some with the same name as a source table (Industry, StatusType, TaxRate, TradeType), so every table reference that is not a
CTE/derived alias is rewritten to Source."<Name>" (matched case-insensitively against the 31 source tables). Nothing else is changed:
the query text, its casts and its generated keys are exactly what fieldgen produced.

usage: python fieldgen_to_l2.py convert RUN_DIR OUT_SUBMISSION_DIR      # then: python l2_run.py OUT_SUBMISSION_DIR --name NAME --audit
       python fieldgen_to_l2.py built RUN_DIR/built_parquet NAME [--gold GOLD_DB]   # grade the tables fieldgen built itself
"""
import os, re, sys
import sqlglot
from sqlglot import exp

HERE = os.path.dirname(os.path.abspath(__file__))
DELIV = os.path.join(os.path.dirname(HERE), "deliverables")


def names(ddl_path, pat=r"(?i)create\s+table\s+(\w+)"):
    return re.findall(pat, re.sub(r"--[^\n]*", "", open(ddl_path).read()))


def qualify(sql, source_tables):
    src = {t.lower(): t for t in source_tables}
    tree = sqlglot.parse_one(sql, read="duckdb")
    ctes = {c.alias.lower() for c in tree.find_all(exp.CTE)}
    for t in tree.find_all(exp.Table):
        if t.db or not t.name or t.name.lower() in ctes:
            continue
        if t.name.lower() in src:
            t.set("this", exp.to_identifier(src[t.name.lower()], quoted=True))
            t.set("db", exp.to_identifier("Source", quoted=True))
    return tree.sql(dialect="duckdb")


def convert(run_dir, out_dir):
    tables = names(os.path.join(DELIV, "tpcdi_target_schema.sql"))
    sources = names(os.path.join(DELIV, "tpcdi_source_schema.sql"), r"(?i)create\s+table\s+Source\.(\w+)")
    low = {t.lower(): t for t in tables}
    os.makedirs(out_dir, exist_ok=True)
    done, skipped = [], []
    sql_dir = os.path.join(run_dir, "sql")
    for f in sorted(os.listdir(sql_dir)) if os.path.isdir(sql_dir) else []:
        t = low.get(f[:-4].lower())
        if not f.endswith(".sql") or t is None:
            continue
        q = open(os.path.join(sql_dir, f)).read().strip().rstrip(";")
        try:
            open(os.path.join(out_dir, t + ".sql"), "w").write(qualify(q, sources) + ";\n")
            done.append(t)
        except Exception as e:
            skipped.append((t, str(e)[:120]))
    return done, skipped




# ---- grading the tables fieldgen itself built (run/tables.duckdb, executed on the package's CSV copy of the source) ----
def grade_built(tables_db, name, gold_db=None, audit=True):
    """Copy the empty-constraint sandbox, load fieldgen's own built tables into it BY NAME (lower-case -> our names; case-insensitive),
    then grade exactly like an L2 submission (l2_grade.grade / summarise / render, optional official audit)."""
    import json, subprocess, duckdb
    import l2_grade, l2_run
    gold_db = gold_db or l2_grade.GOLD_DB
    base = l2_run.build_base(constraints="off")
    rd = os.path.join(l2_run.RUNS, name); os.makedirs(rd, exist_ok=True)
    db = os.path.join(rd, "sandbox.duckdb")
    if os.path.exists(db): os.remove(db)
    subprocess.run(["cp", "-c", base, db], check=True)
    con = duckdb.connect(db)
    # tables_db is a folder of <lower-case table>.parquet (fieldgen's duckdb 2.x file cannot be opened by our duckdb 1.4: export with run_fieldgen_export.py)
    con.execute("CREATE SCHEMA fg")
    built = {f[:-8].lower() for f in os.listdir(tables_db) if f.endswith(".parquet")}
    for t in built:
        con.execute(f"CREATE VIEW fg.\"{t}\" AS SELECT * FROM read_parquet('{os.path.join(tables_db, t)}.parquet')")
    ex = {}
    for t in names(os.path.join(DELIV, "tpcdi_target_schema.sql")):
        if t.lower() in built:
            con.execute(f'INSERT INTO {t} BY NAME SELECT * FROM fg."{t.lower()}"')
            ex[t] = {"status": "OK", "rows": con.execute(f"select count(*) from {t}").fetchone()[0]}
    con.close()
    res = l2_grade.grade(db, gold_db)
    summ = l2_grade.summarise(res); res["summary"] = summ
    if audit:
        import re, sys as _s
        out = subprocess.run([_s.executable, os.path.join(HERE, "gold_audit.py"), "--db", db, "--out", os.path.join(rd, "audit.csv")], capture_output=True, text=True).stdout
        m = re.search(r"Applicable to a Batch-1-only load: (\d+)\s+OK (\d+)\s+NOT-OK (\d+)", out)
        res["audit"] = {"applicable": int(m.group(1)), "ok": int(m.group(2)), "not_ok": int(m.group(3))} if m else {"error": out[-300:]}
    json.dump(res, open(os.path.join(rd, "l2_scores.json"), "w"), indent=1)
    open(os.path.join(rd, "l2_report.md"), "w").write(l2_grade.render(res, summ) + (f"\n- official audit (Batch-1 applicable): {res.get('audit')}" if audit else ""))
    return res, summ


if __name__ == "__main__":
    if sys.argv[1] == "convert":
        d, s = convert(sys.argv[2], sys.argv[3])
        print(f"converted {len(d)} tables: {', '.join(d)}")
        for t, e in s:
            print("SKIPPED", t, e)
    elif sys.argv[1] == "built":
        gold = sys.argv[sys.argv.index("--gold") + 1] if "--gold" in sys.argv else None
        res, summ = grade_built(sys.argv[2], sys.argv[3], gold)
        print(summ, res.get("audit"))
