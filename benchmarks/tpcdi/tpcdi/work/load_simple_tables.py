import duckdb
import re

WORK = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))), "tpcdi/work")
STAGING = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))), "tpcdi/tpcdi-kit/staging/3/Batch1")

con = duckdb.connect(f"{WORK}/tpcdi.duckdb")

for label, path in [("source (S)", f"{WORK}/tpcdi_source_schema.sql"), ("target (T)", f"{WORK}/tpcdi_target_schema.sql")]:
    sql = open(path).read()
    sql = re.sub(r'^\s*--.*', '', sql, flags=re.M)
    for statement in sql.split(';'):
        statement = statement.strip()
        if statement:
            con.execute(statement)
    print(f"loaded schema: {label}")

# (file, table, delimiter)
SIMPLE_TABLES = [
    ("BatchDate.txt", "Source.BatchDate", "|"),
    ("CashTransaction.txt", "Source.CashTransaction", "|"),
    ("DailyMarket.txt", "Source.DailyMarket", "|"),
    ("Date.txt", "Source.Date", "|"),
    ("HR.csv", "Source.HR", ","),
    ("HoldingHistory.txt", "Source.HoldingHistory", "|"),
    ("Industry.txt", "Source.Industry", "|"),
    ("Prospect.csv", "Source.Prospect", ","),
    ("StatusType.txt", "Source.StatusType", "|"),
    ("TaxRate.txt", "Source.TaxRate", "|"),
    ("Time.txt", "Source.Time", "|"),
    ("Trade.txt", "Source.Trade", "|"),
    ("TradeHistory.txt", "Source.TradeHistory", "|"),
    ("TradeType.txt", "Source.TradeType", "|"),
    ("WatchHistory.txt", "Source.WatchHistory", "|"),
]

print()
for fname, table, delim in SIMPLE_TABLES:
    con.execute(f"""
        COPY {table} FROM '{STAGING}/{fname}' (DELIMITER '{delim}', HEADER false, NULLSTR '')
    """)
    n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    print(f"{table:30s} <- {fname:25s} {n:>10,} rows")

con.close()
