# Builds the TPC-DI source database (tpcdi_source.duckdb, schema Source, 19 tables) and the DuckDB DDL files from the DIGen output (scale 3, Batch1).
# Also writes source_ddl.sql, target_ddl.sql (9 target tables) and results.json (row counts).
# Usage: python build_source.py --data DIGEN/Batch1 --repo TPC-DI-MS-SQL-Benchmark-main --out WORK/source
import sys, re, glob, os, json, argparse, collections, duckdb
from lxml import etree
ap = argparse.ArgumentParser()
ap.add_argument("--data", required=True, help="DIGen output folder Batch1 (holds Date.txt, HR.csv, CustomerMgmt.xml, FINWIRE*)")
ap.add_argument("--repo", required=True, help="the TPC-DI-MS-SQL-Benchmark repo folder (has Helpers/Scripts/schema.sql)")
ap.add_argument("--out", required=True, help="output folder (created)")
a = ap.parse_args()
D = a.data; R = a.repo; O = a.out; os.makedirs(O, exist_ok=True)
schema = open(f"{R}/Helpers/Scripts/schema.sql", encoding="utf-8-sig").read()

def block(name):
    m = re.search(r"(?is)CREATE TABLE\s+" + re.escape(name) + r"\s*\((.*?)\n\)\s*;?", schema)
    assert m, name
    return m.group(1)

SRC = ["Date","Time","StatusType","TaxRate","TradeType","Industry","HR","Prospect","BatchDate",
       "FinwireCMP","ActionXML","CustomerXML","NameXML","AddressXML","ContactInfoXML",
       "C_PHONE_1_XML","C_PHONE_2_XML","C_PHONE_3_XML","TaxInfoXML"]
def clean_cols(body):
    lines = []
    for l in body.split("\n"):
        l = re.sub(r"--.*$", "", l).rstrip()
        if l.strip(): lines.append(l)
    lines[-1] = lines[-1].rstrip().rstrip(",")        # trailing comma on last column
    out = [re.sub(r",?\s*$", "", l) for l in lines]    # normalise, re-join with commas
    out = [l.replace("NVARCHAR", "VARCHAR") for l in out]
    out = [re.sub(r"\bBIT\b", "BOOLEAN", l, flags=re.I) for l in out]
    out = [re.sub(r"\s+IDENTITY\s*\(\s*\d+\s*,\s*\d+\s*\)", "", l, flags=re.I) for l in out]
    return ",\n".join(out)
hdr = """-- Source DDL for DuckDB (schema Source), derived from repo Helpers/Scripts/schema.sql.
-- Fixes applied:
--  1. Dropped DROP/CREATE DATABASE, USE and GO lines; CREATE SCHEMA Source kept.
--  2. Kept only the 19 Source tables the 9 targets read (others omitted).
--  3. Removed SQL comments (incl. commented CDC columns) inside table bodies.
--  4. Removed trailing commas before ')' and added ';' after each statement
--     (the repo had no ';' on several tables, which made parsers treat them as commands).
--  5. NVARCHAR -> VARCHAR (DuckDB has no NVARCHAR type; lengths are not enforced).
--  6. BIT -> BOOLEAN and IDENTITY dropped: no such columns in these Source tables, rule kept.
--  7. CHAR(n) kept as written; DuckDB treats it as VARCHAR (no padding).
--  8. Source.Date/Time flag columns stay VARCHAR(5) ('true'/'false'), as in the repo.
--  9. XML link columns (Action_Id, Customer_Id, ContactInfo_Id) are filled by the loader
--     with the 1-based position of the Action in the file (one Customer/ContactInfo per Action).
CREATE SCHEMA IF NOT EXISTS Source;
"""
ddl = hdr + "\n".join(f"\nCREATE TABLE Source.{t} (\n{clean_cols(block('Source.'+t))}\n);" for t in SRC) + "\n"
open(f"{O}/source_ddl.sql", "w").write(ddl)

# target DDL
TGT_KEEP = ["DimDate","DimTime","StatusType","TaxRate","TradeType","Industry"]
TGT_DROP = {"DimBroker":["SK_BrokerID","IsCurrent","BatchID","EffectiveDate","EndDate"],
            "DimCompany":["SK_CompanyID","IsCurrent","BatchID","EffectiveDate","EndDate"],
            "DimCustomer":["SK_CustomerID","IsCurrent","BatchID","EffectiveDate","EndDate"]}
UNIQ = {"DimBroker":"BrokerID","DimCompany":"CompanyID","DimCustomer":"CustomerID"}
def cols(name):
    body = block(name)
    out = []
    for l in body.split("\n"):
        l = re.sub(r"--.*$", "", l).strip().rstrip(",").strip()
        if l: out.append(l)
    return out
def colname(l): return l.split()[0]
tdd = ["-- Target DDL for DuckDB, derived from repo schema.sql (warehouse tables).",
 "-- Fixes: BIT -> BOOLEAN (DimDate.HolidayFlag, DimTime flags, DimCompany.isLowGrade);",
 "--   'Not NULL' casing normalised by DuckDB; IDENTITY columns removed.",
 "-- DimBroker/DimCompany/DimCustomer: dropped SK_*ID (IDENTITY surrogate), IsCurrent,",
 "--   BatchID, EffectiveDate, EndDate; added UNIQUE on BrokerID / CompanyID / CustomerID."]
counts = {}
for t in TGT_KEEP + list(TGT_DROP):
    cs = cols(t); before = len(cs)
    if t in TGT_DROP: cs = [c for c in cs if colname(c) not in TGT_DROP[t]]
    cs = [re.sub(r"\bBIT\b", "BOOLEAN", c, flags=re.I) for c in cs]
    cs = [re.sub(r"\s+IDENTITY\s*\(\s*\d+\s*,\s*\d+\s*\)", "", c, flags=re.I) for c in cs]
    cs = [re.sub(r"\s+PRIMARY KEY", " PRIMARY KEY", c) for c in cs]
    if t in UNIQ: cs = [c + " UNIQUE" if colname(c) == UNIQ[t] else c for c in cs]
    counts[t] = (before, len(cs))
    tdd.append(f"\nCREATE TABLE {t} (\n  " + ",\n  ".join(cs) + "\n);")
open(f"{O}/target_ddl.sql", "w").write("\n".join(tdd) + "\n")
m = duckdb.connect(":memory:"); m.execute(open(f"{O}/target_ddl.sql").read())
tgt_ok = m.execute("select count(*) from information_schema.tables").fetchone()[0]


# source DB (written directly to step2/tpcdi_source.duckdb; name avoids the "source" catalog clash)
import time; T0 = time.time()
dbp = f"{O}/tpcdi_source.duckdb"
for ext in ("", ".wal"):
    if os.path.exists(dbp + ext): os.remove(dbp + ext)
con = duckdb.connect(":memory:"); con.execute(f"ATTACH '{dbp}' AS srcdb"); con.execute("USE srcdb")
con.execute("BEGIN"); con.execute(ddl)
def stage(x): print(f"[{time.time()-T0:6.1f}s] {x}", flush=True)
def tcols(t): return [r[0] for r in con.execute(f"select column_name from information_schema.columns where table_schema='Source' and table_name='{t}' order by ordinal_position").fetchall()]
def load_csv(t, fn, delim, quote):
    cs = tcols(t); spec = ",".join(f"'{c}':'VARCHAR'" for c in cs)
    con.execute(f"insert into Source.{t} select * from read_csv('{D}/{fn}', delim='{delim}', header=false, "
                f"columns={{{spec}}}, quote='{quote}', nullstr='', strict_mode=false)")
for t, fn, d, q in [("Date","Date.txt","|",""),("Time","Time.txt","|",""),("StatusType","StatusType.txt","|",""),
    ("TaxRate","TaxRate.txt","|",""),("TradeType","TradeType.txt","|",""),("Industry","Industry.txt","|",""),
    ("HR","HR.csv",",",""),("Prospect","Prospect.csv",",",'"')]:
    load_csv(t, fn, d, q)
stage("plain files loaded")
# Prospect.Gender: single space -> NULL (logged)
gender_fixed = con.execute("select count(*) from Source.Prospect where Gender is not null and trim(Gender)=''").fetchone()[0]
con.execute("update Source.Prospect set Gender=NULL where Gender is not null and trim(Gender)=''")
con.execute("insert into Source.BatchDate values (?)", [open(f"{D}/BatchDate.txt").read().strip()])
import csv, tempfile
def ins(t, rs):  # bulk insert: dump rows to a temp CSV (local /tmp) and load with read_csv
    if not rs: return
    cs = tcols(t); spec = ",".join(f"'{c}':'VARCHAR'" for c in cs)
    with tempfile.TemporaryDirectory() as td:
        p = f"{td}/{t}.csv"
        with open(p, "w", newline="", encoding="utf-8") as fh: csv.writer(fh).writerows(rs)
        con.execute(f"insert into Source.{t} select * from read_csv('{p}', header=false, columns={{{spec}}}, "
                    f"quote='\"', nullstr='', strict_mode=false)")
sch = [l.split(",") for l in open(f"{R}/Helpers/Datasets/CMP_Records_Schema.csv").read().splitlines()[1:] if l.strip()]
rows = []
for f in sorted(g for g in glob.glob(f"{D}/FINWIRE*") if not g.endswith("_audit.csv")):
    for line in open(f, encoding="latin-1", newline=""):
        line = line.rstrip("\r\n")
        if line[15:18] != "CMP": continue
        pos = 0; r = []
        for name, w in sch:
            v = line[pos:pos+int(w)].strip(); pos += int(w); r.append(v or None)
        rows.append(r)
ins("FinwireCMP", rows)
stage("FINWIRE CMP loaded")
def txt(e):
    if e is None: return None
    s = (e.text or "").strip(); return s or None
def att(e, k):
    v = e.get(k); v = v.strip() if v is not None else None; return v or None
A=[];C=[];N=[];AD=[];CI=[];P={1:[],2:[],3:[]};TX=[]
i = 0
for ev, a in etree.iterparse(f"{D}/CustomerMgmt.xml", tag="{*}Action"):
    ty = a.get("ActionType")
    if ty in ("NEW","UPDCUST","INACT"):
        i += 1; aid = str(i); cu = a.find("Customer")
        A.append((ty, a.get("ActionTS"), aid))
        C.append((att(cu,"C_ID"), att(cu,"C_TAX_ID"), att(cu,"C_GNDR"), att(cu,"C_TIER"), att(cu,"C_DOB"), aid, aid))
        n = cu.find("Name")
        if n is not None: N.append((txt(n.find("C_L_NAME")),txt(n.find("C_F_NAME")),txt(n.find("C_M_NAME")),aid))
        ad = cu.find("Address")
        if ad is not None: AD.append(tuple(txt(ad.find(k)) for k in ["C_ADLINE1","C_ADLINE2","C_ZIPCODE","C_CITY","C_STATE_PROV","C_CTRY"])+(aid,))
        ci = cu.find("ContactInfo")
        if ci is not None:
            CI.append((txt(ci.find("C_PRIM_EMAIL")),txt(ci.find("C_ALT_EMAIL")),aid,aid))
            for k in (1,2,3):
                p = ci.find(f"C_PHONE_{k}")
                if p is not None: P[k].append(tuple(txt(p.find(x)) for x in ["C_CTRY_CODE","C_AREA_CODE","C_LOCAL","C_EXT"])+(aid,))
        tx = cu.find("TaxInfo")
        if tx is not None: TX.append((txt(tx.find("C_LCL_TX_ID")),txt(tx.find("C_NAT_TX_ID")),aid))
    a.clear()
    while a.getprevious() is not None: del a.getparent()[0]
for t, rs in [("ActionXML",A),("CustomerXML",C),("NameXML",N),("AddressXML",AD),("ContactInfoXML",CI),
              ("C_PHONE_1_XML",P[1]),("C_PHONE_2_XML",P[2]),("C_PHONE_3_XML",P[3]),("TaxInfoXML",TX)]: ins(t, rs)
stage("XML loaded")
con.execute("COMMIT")
exp = dict(Date=25933,Time=86400,StatusType=6,TaxRate=320,TradeType=5,Industry=102,HR=15000,Prospect=14982,
           BatchDate=1,FinwireCMP=1500,ActionXML=6440)
res = {"source": {t: con.execute(f"select count(*) from Source.{t}").fetchone()[0] for t in SRC},
       "expected": exp, "actions": dict(con.execute("select ActionType,count(*) from Source.ActionXML group by 1").fetchall()),
       "target_cols": counts, "target_tables_ok": tgt_ok, "gender_space_to_null": gender_fixed}
chk = {}
for t in SRC:
    for c in tcols(t):
        n = con.execute(f"select count(*) from Source.{t} where trim(cast({c} as varchar))=''").fetchone()[0]
        if n: chk[f"{t}.{c}"] = n
res["empty_string_cells"] = chk
res["cik_sample"] = [r[0] for r in con.execute("select CIK from Source.FinwireCMP limit 3").fetchall()]
res["col_counts"] = {t: len(tcols(t)) for t in SRC}
res["build_seconds"] = round(time.time() - T0, 1)
json.dump(res, open(f"{O}/results.json","w"), indent=1, default=str)
con.execute("CHECKPOINT"); con.execute("USE memory"); con.execute("DETACH srcdb"); con.close()
stage("done")
