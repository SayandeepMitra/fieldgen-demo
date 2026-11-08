import duckdb
import glob
import os

WORK = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))), "tpcdi/work")
STAGING = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))), "tpcdi/tpcdi-kit/staging/3/Batch1")

# (field name, length) per record schema, from Helpers/Datasets/*_Records_Schema.csv
CMP_FIELDS = [("PTS",15),("RecType",3),("CompanyName",60),("CIK",10),("Status",4),
              ("IndustryID",2),("SPrating",4),("FoundingDate",8),("AddrLine1",80),
              ("AddrLine2",80),("PostalCode",12),("City",25),("StateProvince",20),
              ("Country",24),("CEOname",46),("Description",150)]
FIN_FIELDS = [("PTS",15),("RecType",3),("Year",4),("Quarter",1),("QtrStartDate",8),
              ("PostingDate",8),("Revenue",17),("Earnings",17),("EPS",12),
              ("DilutedEPS",12),("Margin",12),("Inventory",17),("Assets",17),
              ("Liabilities",17),("ShOut",13),("DilutedShOut",13),("CoNameOrCIK",60)]
SEC_FIELDS = [("PTS",15),("RecType",3),("Symbol",15),("IssueType",6),("Status",4),
              ("Name",70),("ExID",6),("ShOut",13),("FirstTradeDate",8),
              ("FirstTradeExchg",8),("Dividend",12),("CoNameOrCIK",60)]

SCHEMAS = {"CMP": CMP_FIELDS, "FIN": FIN_FIELDS, "SEC": SEC_FIELDS}
TABLES = {"CMP": "Source.FinwireCMP", "FIN": "Source.FinwireFIN", "SEC": "Source.FinwireSEC"}

def slice_fields(line, fields):
    row = []
    pos = 0
    for name, length in fields:
        row.append(line[pos:pos+length].strip())
        pos += length
    return row

rows = {"CMP": [], "FIN": [], "SEC": []}

files = sorted(f for f in glob.glob(os.path.join(STAGING, "FINWIRE*")) if not f.endswith("_audit.csv"))
print(f"found {len(files)} FINWIRE files")

for fp in files:
    with open(fp, "rb") as f:
        content = f.read().decode("latin-1")
    for line in content.split("\n"):
        line = line.rstrip("\r")
        if not line.strip():
            continue
        rectype = line[15:18]
        if rectype not in SCHEMAS:
            raise ValueError(f"unexpected RecType {rectype!r} in {fp}: {line[:40]!r}")
        rows[rectype].append(slice_fields(line, SCHEMAS[rectype]))

for rt, data in rows.items():
    print(f"{rt}: {len(data)} records parsed")

con = duckdb.connect(f"{WORK}/tpcdi.duckdb")
for rt, data in rows.items():
    table = TABLES[rt]
    cols = [name for name, _ in SCHEMAS[rt]]
    placeholders = ", ".join(["?"] * len(cols))
    con.executemany(f"INSERT INTO {table} VALUES ({placeholders})", data)
    n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    print(f"{table:25s} {n:>10,} rows loaded")
con.close()
