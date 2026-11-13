# Builds source_hist.duckdb (schema main): the source with the nine customer-event tables replaced by ONE table CustomerHistory
# (one row per customer action NEW / UPDCUST / INACT, every empty field filled from the customer's previous action).
# Fill rule = latest non-NULL value up to this action, actions ordered by (ActionTS, ActionType); raw values stay raw where the gold SQL transforms later (e.g. gender).
# Usage: python build_history.py --source-db WORK/source/tpcdi_source.duckdb --out WORK/source_hist.duckdb
import os, argparse, duckdb
ap = argparse.ArgumentParser()
ap.add_argument("--source-db", required=True, help="tpcdi_source.duckdb from build_source.py")
ap.add_argument("--out", required=True, help="output DuckDB file")
a = ap.parse_args()
OUT = a.out; SRC = a.source_db
for p in (OUT, OUT + ".wal"):
    if os.path.exists(p): os.remove(p)
con = duckdb.connect(":memory:"); con.execute(f"ATTACH '{SRC}' AS s (READ_ONLY)"); con.execute(f"ATTACH '{OUT}' AS h")
REN = {"Action_Id": "ActionSeq", "Customer_Id": "CustomerSeq", "ContactInfo_Id": "ContactSeq"}      # link columns renamed so that they do not look like keys
REPLACED = ["CustomerXML", "ActionXML", "NameXML", "AddressXML", "ContactInfoXML", "C_PHONE_1_XML", "C_PHONE_2_XML", "C_PHONE_3_XML", "TaxInfoXML"]
tabs = [r[0] for r in con.execute("select table_name from information_schema.tables where table_catalog='s' and table_schema='Source' order by 1").fetchall()]
for t in tabs:
    cols = [r[0] for r in con.execute(f"select column_name from information_schema.columns where table_catalog='s' and table_schema='Source' and table_name='{t}' order by ordinal_position").fetchall()]
    sel = ", ".join(f'"{x}" AS "{REN.get(x, x)}"' for x in cols)
    con.execute(f"CREATE TABLE h.main.{t} AS SELECT {sel} FROM s.Source.{t}")
con.execute("USE h")
def phone(p):
    return (f"CASE WHEN {p}.C_CTRY_CODE IS NOT NULL AND {p}.C_AREA_CODE IS NOT NULL AND {p}.C_LOCAL IS NOT NULL THEN '+' || {p}.C_CTRY_CODE || ' (' || {p}.C_AREA_CODE || ') ' || {p}.C_LOCAL "
            f"WHEN {p}.C_CTRY_CODE IS NULL AND {p}.C_AREA_CODE IS NOT NULL AND {p}.C_LOCAL IS NOT NULL THEN '(' || {p}.C_AREA_CODE || ') ' || {p}.C_LOCAL "
            f"WHEN {p}.C_CTRY_CODE IS NULL AND {p}.C_AREA_CODE IS NULL AND {p}.C_LOCAL IS NOT NULL THEN {p}.C_LOCAL END")
ev_cols = {"C_TAX_ID": "TRIM(c.C_TAX_ID)", "C_GNDR": "c.C_GNDR", "C_TIER": "c.C_TIER", "C_DOB": "c.C_DOB",
  "C_L_NAME": "TRIM(n.C_L_NAME)", "C_F_NAME": "TRIM(n.C_F_NAME)", "C_M_NAME": "TRIM(n.C_M_NAME)",
  "C_ADLINE1": "TRIM(ad.C_ADLINE1)", "C_ADLINE2": "TRIM(ad.C_ADLINE2)", "C_ZIPCODE": "TRIM(ad.C_ZIPCODE)", "C_CITY": "TRIM(ad.C_CITY)", "C_STATE_PROV": "TRIM(ad.C_STATE_PROV)", "C_CTRY": "TRIM(ad.C_CTRY)",
  "C_PRIM_EMAIL": "TRIM(ci.C_PRIM_EMAIL)", "C_ALT_EMAIL": "TRIM(ci.C_ALT_EMAIL)", "C_LCL_TX_ID": "ti.C_LCL_TX_ID", "C_NAT_TX_ID": "ti.C_NAT_TX_ID"}
ev_sel = ", ".join(f"{e} AS {n}" for n, e in ev_cols.items())
ph_sel = ""
for k in (1, 2, 3):
    p = f"p{k}"
    ph_sel += f", {phone(p)} IS NOT NULL AS ph{k}_ok, {p}.C_CTRY_CODE AS pc{k}, {p}.C_AREA_CODE AS pa{k}, {p}.C_LOCAL AS pl{k}, {p}.C_EXT AS pe{k}"
ev = f"""SELECT c.C_ID AS C_ID, a.ActionTS AS ActionTS, c.ActionSeq AS ActionSeq, a.ActionType AS ActionType, {ev_sel}{ph_sel}
FROM CustomerXML c JOIN ActionXML a ON c.ActionSeq = a.ActionSeq LEFT JOIN NameXML n ON c.CustomerSeq = n.CustomerSeq LEFT JOIN AddressXML ad ON c.CustomerSeq = ad.CustomerSeq
LEFT JOIN ContactInfoXML ci ON c.CustomerSeq = ci.CustomerSeq LEFT JOIN C_PHONE_1_XML p1 ON ci.ContactSeq = p1.ContactSeq LEFT JOIN C_PHONE_2_XML p2 ON ci.ContactSeq = p2.ContactSeq
LEFT JOIN C_PHONE_3_XML p3 ON ci.ContactSeq = p3.ContactSeq LEFT JOIN TaxInfoXML ti ON c.CustomerSeq = ti.CustomerSeq
WHERE a.ActionType IN ('NEW','UPDCUST','INACT')"""
W = "OVER (PARTITION BY C_ID ORDER BY ActionTS, ActionType ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)"
fill = ", ".join(f"last_value({n} IGNORE NULLS) {W} AS {n}" for n in ev_cols)
for k in (1, 2, 3):
    fill += f", last_value(CASE WHEN ph{k}_ok THEN struct_pack(c := pc{k}, a := pa{k}, l := pl{k}, e := pe{k}) END IGNORE NULLS) {W} AS ph{k}"
fin = ", ".join(ev_cols) + "".join(f", ph{k}.c AS C_CTRY_CODE_{k}, ph{k}.a AS C_AREA_CODE_{k}, ph{k}.l AS C_LOCAL_{k}, ph{k}.e AS C_EXT_{k}" for k in (1, 2, 3))
con.execute(f"CREATE TABLE CustomerHistory AS WITH ev AS ({ev}), f AS (SELECT C_ID, ActionTS, ActionSeq, ActionType, {fill} FROM ev) SELECT C_ID, ActionTS, ActionSeq, ActionType, {fin} FROM f ORDER BY C_ID, ActionTS, ActionType")
for t in REPLACED: con.execute(f"DROP TABLE {t}")
n = con.execute("select count(*), count(distinct C_ID), count(distinct ActionSeq) from CustomerHistory").fetchone()
print("CustomerHistory rows/customers/actions:", n)
print("tables:", sorted(r[0] for r in con.execute("select table_name from information_schema.tables where table_catalog='h'").fetchall()))
con.execute("CHECKPOINT"); con.close()
