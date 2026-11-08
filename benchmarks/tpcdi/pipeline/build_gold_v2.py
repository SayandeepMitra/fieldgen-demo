"""Build the repaired gold database (v2): deliverables/tpcdi_populated_v2.duckdb.

Clone of the v1 database (Source.* identical), target tables dropped and recreated from tpcdi_target_schema_v2.sql WITH all
constraints (NOT NULL / PK / FK / CHECK enforced, so a repair that violates the spec fails loudly), then the statements of
ported_historical_load_v2.sql run in file order (dimensions before facts). The v1 database and SQL are never modified.

usage: python build_gold_v2.py [--only Table1,Table2]   (default: all)
"""
import argparse, os, re, subprocess, time
import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
DELIV = os.path.join(os.path.dirname(HERE), "deliverables")
V1_DB = os.path.join(DELIV, "tpcdi_populated.duckdb")
V2_DB = os.path.join(DELIV, "tpcdi_populated_v2.duckdb")
V2_SQL = os.path.join(DELIV, "ported_historical_load_v2.sql")
V2_DDL = os.path.join(DELIV, "tpcdi_target_schema_v2.sql")


def statements(path):
    src = re.sub(r"--[^\n]*", "", open(path).read())
    return [s.strip() for s in src.split(";") if s.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    if only is None or not os.path.exists(V2_DB):
        if os.path.exists(V2_DB):
            os.remove(V2_DB)
        subprocess.run(["cp", "-c", V1_DB, V2_DB], check=True)
        con = duckdb.connect(V2_DB)
        ddl = re.sub(r"--[^\n]*", "", open(V2_DDL).read())
        created = re.findall(r"(?i)create\s+table\s+(\w+)", ddl)
        existing = [t for (t,) in con.execute("select table_name from information_schema.tables where table_schema='main' and table_type='BASE TABLE'").fetchall()]
        for t in [x for x in reversed(created) if x in existing] + [x for x in existing if x not in created]:
            con.execute(f'drop table "{t}"')
        for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
            con.execute(stmt)
    else:
        con = duckdb.connect(V2_DB)
        for t in only:
            con.execute(f"delete from {t}")
    for s in statements(V2_SQL):
        m = re.search(r"(?is)INSERT\s+INTO\s+(\w+)", s)
        t = m.group(1)
        if only and t not in only:
            continue
        t0 = time.time()
        try:
            con.execute(s)
            n = con.execute(f"select count(*) from {t}").fetchone()[0]
            print(f"{t:18s} rows={n:>9} {time.time()-t0:6.1f}s", flush=True)
        except Exception as e:
            print(f"{t:18s} FAILED {str(e)[:400]}", flush=True)
            break
    con.close()


if __name__ == "__main__":
    main()
