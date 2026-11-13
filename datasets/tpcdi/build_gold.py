# Builds the reference ("gold") tables: runs the nine SQL files of gold_sql/ on the source database and writes gold.duckdb and gold_csv/<Table>.csv.
# The SQL is our DuckDB translation of the TPC-DI historical load, with the specification's rules applied (clause numbers in the file headers).
# Usage: python build_gold.py --source-db WORK/source/tpcdi_source.duckdb --target-ddl WORK/source/target_ddl.sql --sql gold_sql --out WORK/gold
import os, json, argparse, shutil, duckdb
ap = argparse.ArgumentParser()
ap.add_argument("--source-db", required=True, help="tpcdi_source.duckdb from build_source.py")
ap.add_argument("--target-ddl", required=True, help="target_ddl.sql from build_source.py")
ap.add_argument("--sql", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "gold_sql"), help="folder with the nine .sql files")
ap.add_argument("--out", required=True, help="output folder (created)")
a = ap.parse_args()
os.makedirs(a.out + "/gold_csv", exist_ok=True)
TABLES = ["DimDate", "DimTime", "StatusType", "TaxRate", "TradeType", "Industry", "DimBroker", "DimCompany", "DimCustomer"]
KEY = {"DimBroker": "BrokerID", "DimCompany": "CompanyID", "DimCustomer": "CustomerID", "DimDate": "SK_DateID", "DimTime": "SK_TimeID",
       "StatusType": "ST_ID", "TaxRate": "TX_ID", "TradeType": "TT_ID", "Industry": "IN_ID"}
EXPECTED = {"DimDate": 25933, "DimTime": 86400, "StatusType": 6, "TaxRate": 320, "TradeType": 5, "Industry": 102,
            "DimBroker": 4293, "DimCompany": 1096, "DimCustomer": 4728}
db = a.out + "/gold.duckdb"
for p in (db, db + ".wal"):
    if os.path.exists(p): os.remove(p)
con = duckdb.connect(":memory:")
con.execute(f"ATTACH '{a.source_db}' AS srcdb (READ_ONLY)"); con.execute(f"ATTACH '{db}' AS gold"); con.execute("USE gold")
con.execute("CREATE SCHEMA Source")                       # staging copy of the source tables, dropped at the end
for (t,) in con.execute("select table_name from information_schema.tables where table_catalog='srcdb' and table_schema='Source'").fetchall():
    con.execute(f"CREATE TABLE gold.Source.{t} AS SELECT * FROM srcdb.Source.{t}")
con.execute("USE gold.main"); con.execute(open(a.target_ddl).read())      # empty target tables
for t in TABLES: con.execute(open(f"{a.sql}/{t}.sql").read())
bad = 0
for t in TABLES:
    n = con.execute(f"select count(*) from {t}").fetchone()[0]; k = con.execute(f"select count(distinct {KEY[t]}) from {t}").fetchone()[0]
    ok = n == EXPECTED[t] and k == n; bad += not ok
    print(f"{t:12} rows {n:6} expected {EXPECTED[t]:6} {'ok' if ok else 'DIFFERENT'}")
    con.execute(f"COPY (select * from main.{t} order by {KEY[t]}) TO '{a.out}/gold_csv/{t}.csv' (HEADER, DELIMITER ',', NULLSTR '')")
con.execute("DROP SCHEMA Source CASCADE"); con.execute("CHECKPOINT")
con.execute("USE memory"); con.execute("DETACH gold"); con.execute("DETACH srcdb"); con.close()
print("gold built;", "all row counts as expected" if not bad else f"{bad} table(s) differ from the expected row counts")
