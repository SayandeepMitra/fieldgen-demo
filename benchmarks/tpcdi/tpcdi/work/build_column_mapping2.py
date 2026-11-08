import csv

FIELDS = ["target_table","target_column","target_type","table_status","producing_models",
          "source_tables","value_columns","key_columns","joins","rule_sql","combination",
          "lineage_path","column_kind","notes","rule_reliable","rule_issue","table_caution"]

rows = []
def row(table, col, typ, status, src_tables, value_cols, key_cols, joins, sql, comb,
        lineage, kind, notes, reliable, issue="", caution=""):
    rows.append({
        "target_table": table, "target_column": col, "target_type": typ, "table_status": status,
        "producing_models": "historical_load.sql", "source_tables": src_tables,
        "value_columns": value_cols, "key_columns": key_cols, "joins": joins, "rule_sql": sql,
        "combination": comb, "lineage_path": lineage, "column_kind": kind, "notes": notes,
        "rule_reliable": reliable, "rule_issue": issue, "table_caution": caution,
    })

# ================= DimBroker =================
row("DimBroker","SK_BrokerID","INTEGER","populated","Source.HR","","HR.EmployeeID","",
    "ROW_NUMBER() OVER (ORDER BY EmployeeID)","none","DimBroker.SK_BrokerID <- (generated)","generated_key",
    "surrogate key; original relied on SQL Server IDENTITY with no explicit order -- ORDER BY EmployeeID added during DuckDB port for determinism","yes")
for tc, sc in [("BrokerID","EmployeeID"),("ManagerID","ManagerID"),("FirstName","EmployeeFirstName"),
               ("LastName","EmployeeLastName"),("MiddleInitial","EmployeeMI"),("Branch","EmployeeBranch"),
               ("Office","EmployeeOffice"),("Phone","EmployeePhone")]:
    row("DimBroker", tc, "varies", "populated", "Source.HR", f"HR.{sc}", "", "WHERE EmployeeJobCode=314",
        f"HR.{sc} AS {tc}", "none", f"DimBroker.{tc} <- Source.HR.{sc}", "rename" if tc!=sc else "passthrough_copy",
        "filtered to HR rows with EmployeeJobCode=314 (brokers only)", "yes")
row("DimBroker","IsCurrent","BOOLEAN","populated","","","","","1 AS IsCurrent (literal, always true)","none",
    "DimBroker.IsCurrent <- (constant)","constant",
    "no SCD tracking at all for DimBroker in historical_load -- every row is hardcoded current, unlike DimCustomer/DimAccount/DimCompany/DimSecurity which derive IsCurrent via a LEAD() window. Plausible for a historical (batch-1) load where brokers have no prior history yet, but means broker updates in later batches have no handling here.","yes")
row("DimBroker","BatchID","INTEGER","populated","","","","","1 AS BatchID","none","DimBroker.BatchID <- (constant)","constant","hardcoded constant","yes")
row("DimBroker","EffectiveDate","DATE","populated","Source.Date (via DimDate)","","","",
    "(SELECT MIN(DateValue) FROM DimDate)","none","DimBroker.EffectiveDate <- DimDate (MIN)","value",
    "earliest date in the whole calendar dimension, used as a blanket effective date for all brokers","yes")
row("DimBroker","EndDate","DATE","populated","","","","","DATE '9999-12-31'","none","DimBroker.EndDate <- (constant)","constant","hardcoded open-ended constant","yes")

# ================= DimCompany =================
row("DimCompany","SK_CompanyID","INTEGER","populated","Source.FinwireCMP","","CompanyID,EffectiveDate","",
    "ROW_NUMBER() OVER (ORDER BY CompanyID, EffectiveDate)","none","DimCompany.SK_CompanyID <- (generated)","generated_key",
    "surrogate key; original IDENTITY had no explicit order -- ORDER BY CompanyID, EffectiveDate added during DuckDB port","yes")
row("DimCompany","CompanyID","INTEGER","populated","Source.FinwireCMP","FinwireCMP.CIK","","","CIK AS CompanyID","none","DimCompany.CompanyID <- Source.FinwireCMP.CIK","rename","","yes")
row("DimCompany","Status","CHAR(10)","populated","Source.FinwireCMP;Source.StatusType","FinwireCMP.Status","","JOIN StatusType ST ON CMP.Status=ST.ST_ID","S.ST_NAME","none","DimCompany.Status <- Source.StatusType.ST_NAME <- Source.FinwireCMP.Status","lookup join","","yes")
row("DimCompany","Name","CHAR(60)","populated","Source.FinwireCMP","FinwireCMP.CompanyName","","","CompanyName AS Name","none","DimCompany.Name <- Source.FinwireCMP.CompanyName","rename","","yes")
row("DimCompany","Industry","CHAR(50)","populated","Source.FinwireCMP;Source.Industry","FinwireCMP.IndustryID","","JOIN Industry I ON CMP.IndustryID=I.IN_ID","I.IN_NAME","none","DimCompany.Industry <- Source.Industry.IN_NAME <- Source.FinwireCMP.IndustryID","lookup join","","yes")
row("DimCompany","SPrating","CHAR(4)","populated","Source.FinwireCMP","FinwireCMP.SPrating","","","SPrating","none","DimCompany.SPrating <- Source.FinwireCMP.SPrating","passthrough_copy","","yes")
row("DimCompany","isLowGrade","BOOLEAN","populated","Source.FinwireCMP","FinwireCMP.SPrating","","",
    "CASE WHEN SPrating LIKE 'A%' OR SPrating LIKE 'BBB%' THEN false ELSE true END","case",
    "DimCompany.isLowGrade <- Source.FinwireCMP.SPrating","conditional","","yes")
row("DimCompany","CEO","CHAR(100)","populated","Source.FinwireCMP","FinwireCMP.CEOname","","","CEOname AS CEO","none","DimCompany.CEO <- Source.FinwireCMP.CEOname","rename","","yes")
for tc, sc in [("AddressLine1","AddrLine1"),("AddressLine2","AddrLine2"),("PostalCode","PostalCode"),
               ("City","City"),("StateProv","StateProvince"),("Country","Country"),("Description","Description")]:
    row("DimCompany", tc, "varies", "populated", "Source.FinwireCMP", f"FinwireCMP.{sc}", "", "", f"{sc} AS {tc}", "none",
        f"DimCompany.{tc} <- Source.FinwireCMP.{sc}", "rename" if tc!=sc else "passthrough_copy", "", "yes")
row("DimCompany","FoundingDate","DATE","populated","Source.FinwireCMP","FinwireCMP.FoundingDate","","",
    "try_strptime(FoundingDate, '%Y%m%d')::DATE","none","DimCompany.FoundingDate <- Source.FinwireCMP.FoundingDate","retype",
    "source is fixed-width YYYYMMDD text, not ISO date -- plain CAST(...AS DATE) silently returned NULL for every row at first; fixed with try_strptime during DuckDB port","yes")
row("DimCompany","IsCurrent","BOOLEAN","populated","","","CompanyID,EffectiveDate","",
    "CASE WHEN LEAD(EffectiveDate) OVER (PARTITION BY CompanyID ORDER BY EffectiveDate) IS NULL THEN true ELSE false END","none",
    "DimCompany.IsCurrent <- (window function)","SCD history","","yes")
row("DimCompany","BatchID","NUMERIC(5)","populated","","","","","1 AS BatchID","none","DimCompany.BatchID <- (constant)","constant","","yes")
row("DimCompany","EffectiveDate","DATE","populated","Source.FinwireCMP","FinwireCMP.PTS","","",
    "strptime(PTS, '%Y%m%d-%H%M%S')","none","DimCompany.EffectiveDate <- Source.FinwireCMP.PTS","SCD history",
    "PTS is the FINWIRE record timestamp, used as the SCD effective date","yes")
row("DimCompany","EndDate","DATE","populated","","","CompanyID,EffectiveDate","",
    "COALESCE(LEAD(EffectiveDate) OVER (...), DATE '9999-12-31')","none","DimCompany.EndDate <- (window function)","SCD history","","yes")

# ================= DimCustomer (33 cols, carried over from Task A3's close reading) =================
dimcustomer_rows = [
 ("SK_CustomerID","INTEGER","","ROW_NUMBER() OVER (ORDER BY CustomerID, ActionTS)","generated_key","surrogate key; original relied on IDENTITY + an explicit final ORDER BY CustomerID, ActionTS -- preserved as the ROW_NUMBER's ORDER BY"),
 ("CustomerID","INTEGER","Source.CustomerXML.C_ID","CXML.C_ID AS CustomerID","rename",""),
 ("TaxID","CHAR(20)","Source.CustomerXML.C_TAX_ID","TRIM(CXML.C_TAX_ID)","rename","TRIM() whitespace cleanup only"),
 ("Status","CHAR(10)","Source.ActionXML.ActionType","'ACTIVE'/'INACTIVE' branches via unioned CTEs keyed on ActionType","conditional",""),
 ("LastName","CHAR(30)","Source.NameXML.C_L_NAME","TRIM(NXML.C_L_NAME)","rename",""),
 ("FirstName","CHAR(30)","Source.NameXML.C_F_NAME","TRIM(NXML.C_F_NAME)","rename",""),
 ("MiddleInitial","CHAR(1)","Source.NameXML.C_M_NAME","TRIM(NXML.C_M_NAME)","rename",""),
 ("Gender","CHAR(1)","Source.CustomerXML.C_GNDR","TRIM(UPPER(CASE WHEN C_GNDR NOT IN('m','f') OR NULL THEN 'u' ELSE C_GNDR END))","conditional",""),
 ("Tier","INTEGER","Source.CustomerXML.C_TIER","C_TIER","copy",""),
 ("DOB","DATE","Source.CustomerXML.C_DOB","C_DOB","copy",""),
 ("AddressLine1","VARCHAR(80)","Source.AddressXML.C_ADLINE1","TRIM(ADXML.C_ADLINE1)","rename",""),
 ("AddressLine2","VARCHAR(80)","Source.AddressXML.C_ADLINE2","TRIM(ADXML.C_ADLINE2)","rename",""),
 ("PostalCode","CHAR(12)","Source.AddressXML.C_ZIPCODE","TRIM(ADXML.C_ZIPCODE)","rename",""),
 ("City","CHAR(25)","Source.AddressXML.C_CITY","TRIM(ADXML.C_CITY)","rename",""),
 ("StateProv","CHAR(20)","Source.AddressXML.C_STATE_PROV","TRIM(ADXML.C_STATE_PROV)","rename",""),
 ("Country","CHAR(24)","Source.AddressXML.C_CTRY","TRIM(ADXML.C_CTRY)","rename",""),
 ("Phone1","CHAR(30)","Source.C_PHONE_1_XML.*","multi-branch CASE concatenating country/area/local (+ext)","concat",""),
 ("Phone2","CHAR(30)","Source.C_PHONE_2_XML.*","same pattern against C_PHONE_2_XML","concat",""),
 ("Phone3","CHAR(30)","Source.C_PHONE_3_XML.*","same pattern against C_PHONE_3_XML","concat",""),
 ("Email1","CHAR(50)","Source.ContactInfoXML.C_PRIM_EMAIL","TRIM(CCIN.C_PRIM_EMAIL)","rename",""),
 ("Email2","CHAR(50)","Source.ContactInfoXML.C_ALT_EMAIL","TRIM(CCIN.C_ALT_EMAIL)","rename",""),
 ("NationalTaxRateDesc","VARCHAR(50)","Source.TaxInfoXML.C_NAT_TX_ID -> Source.TaxRate.TX_NAME","LEFT JOIN TaxRate TR ON C_NAT_TX_ID=TX_ID","lookup join",""),
 ("NationalTaxRate","NUMERIC(6,5)","Source.TaxInfoXML.C_NAT_TX_ID -> Source.TaxRate.TX_RATE","TR.TX_RATE","lookup join",""),
 ("LocalTaxRateDesc","VARCHAR(50)","Source.TaxInfoXML.C_LCL_TX_ID -> Source.TaxRate.TX_NAME","LEFT JOIN TaxRate TR2 ON C_LCL_TX_ID=TX_ID","lookup join","second self-join of TaxRate"),
 ("LocalTaxRate","NUMERIC(6,5)","Source.TaxInfoXML.C_LCL_TX_ID -> Source.TaxRate.TX_RATE","TR2.TX_RATE","lookup join",""),
 ("AgencyID","CHAR(30)","Source.Prospect.AgencyID","LEFT JOIN Prospect on fuzzy name/address match","lookup join","join key is a name/address match, not an ID"),
 ("CreditRating","INTEGER","Source.Prospect.CreditRating","P.CreditRating","lookup join","same Prospect join"),
 ("NetWorth","NUMERIC(10)","Source.Prospect.NetWorth","P.NetWorth","lookup join","same Prospect join"),
 ("MarketingNameplate","VARCHAR(100)","Source.Prospect.{NetWorth,Income,NumberChildren,NumberCreditCards,Age,CreditRating,NumberCars}","6-branch CASE","conditional","6-branch CASE over 6 different Prospect columns"),
 ("IsCurrent","BOOLEAN","","CASE WHEN LEAD(ActionTS) OVER (PARTITION BY CustomerID ORDER BY ActionTS) IS NULL THEN true ELSE false END","SCD history","window function (LEAD) over ActionTS history"),
 ("BatchID","INTEGER","","1 AS BatchID","constant",""),
 ("EffectiveDate","TIMESTAMP","Source.ActionXML.ActionTS","ActionTS AS EffectiveDate","SCD history",""),
 ("EndDate","TIMESTAMP","","COALESCE(LEAD(ActionTS) OVER (...), TIMESTAMP '9999-12-31')","SCD history","window function (LEAD) + COALESCE default"),
]
for c, t, src, sql, kind, note in dimcustomer_rows:
    kind_map = {"generated_key":"generated_key","rename":"rename","conditional":"conditional","copy":"passthrough_copy",
                "concat":"value","lookup join":"lookup join","SCD history":"SCD history","constant":"constant"}
    row("DimCustomer", c, t, "populated", src.split(" -> ")[0] if src else "", src, "", "", sql,
        "case" if kind=="conditional" else ("union_all" if c=="Status" else "none"),
        f"DimCustomer.{c} <- {src}" if src else f"DimCustomer.{c} <- (derived)",
        kind_map.get(kind, kind), note, "yes")

with open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))), "tpcdi/work/_part2.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(rows)
print(f"part 2: {len(rows)} rows written")
