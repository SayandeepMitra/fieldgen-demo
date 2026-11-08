import duckdb
import re
import sys

WORK = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))), "tpcdi/work")

sql_file = sys.argv[1] if len(sys.argv) > 1 else f"{WORK}/ported_historical_load.sql"

con = duckdb.connect(f"{WORK}/tpcdi.duckdb")

content = open(sql_file).read()
# strip '--' comments to end-of-line first (they may contain stray semicolons/quotes), then split
content = re.sub(r'--[^\n]*', '', content)
statements = [s.strip() for s in content.split(';') if s.strip()]

# figure out the target table each INSERT touches, for a readable progress line
for i, stmt in enumerate(statements):
    m = re.search(r'INSERT INTO\s+(\w+)', stmt, re.IGNORECASE)
    table = m.group(1) if m else f"statement {i}"
    try:
        con.execute(stmt)
        n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        print(f"OK   {table:20s} now {n:>10,} rows")
    except Exception as e:
        print(f"FAIL {table:20s}: {e}")
        print("--- failing statement (first 500 chars) ---")
        print(stmt[:500])
        con.close()
        sys.exit(1)

con.close()
print("all statements executed successfully")
