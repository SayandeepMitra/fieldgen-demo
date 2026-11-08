import csv

FIELDS = ["target_table","target_column","target_type","table_status","producing_models",
          "source_tables","value_columns","key_columns","joins","rule_sql","combination",
          "lineage_path","column_kind","notes","rule_reliable","rule_issue","table_caution"]

rows = []
def row(table, col, status, src, sql, kind, note, reliable, issue="", caution=""):
    rows.append({
        "target_table": table, "target_column": col, "target_type": "varies", "table_status": status,
        "producing_models": "historical_load.sql", "source_tables": src, "value_columns": "",
        "key_columns": "", "joins": "", "rule_sql": sql, "combination": "none",
        "lineage_path": f"{table}.{col} <- {src}" if src else f"{table}.{col} <- (derived)",
        "column_kind": kind, "notes": note, "rule_reliable": reliable, "rule_issue": issue, "table_caution": caution,
    })

# ================= DimAccount (11, from Task A3) =================
for c, src, sql, kind, note in [
    ("SK_AccountID","","ROW_NUMBER() OVER (ORDER BY AccountID, ActionTS)","generated_key","surrogate key, matches original's explicit final ORDER BY"),
    ("AccountID","Source.AccountXML.CA_ID","Acc.CA_ID AS AccountID","rename",""),
    ("SK_BrokerID","Source.AccountXML.CA_B_ID -> DimBroker.SK_BrokerID","INNER JOIN DimBroker ON CA_B_ID=BrokerID","lookup join","surrogate-key lookup against already-loaded DimBroker"),
    ("SK_CustomerID","Source.CustomerXML.C_ID -> DimCustomer.SK_CustomerID","INNER JOIN DimCustomer ON C_ID=CustomerID, gated by SCD window","lookup join","surrogate-key lookup gated by customer's SCD-current window"),
    ("Status","Source.ActionXML.ActionType","'ACTIVE' for NEW/ADDACCT/UPDACCT, 'INACTIVE' for CLOSEACCT","conditional",""),
    ("AccountDesc","Source.AccountXML.CA_NAME","COALESCE across NEW vs UPDACCT versions","rename","COALESCE only bridges update history, no value transform"),
    ("TaxStatus","Source.AccountXML.CA_TAX_ST","same COALESCE-across-history pattern","rename","retyped text->int during port (TRY_CAST)"),
    ("IsCurrent","","CASE WHEN LEAD(ActionTS) OVER (PARTITION BY AccountID ORDER BY ActionTS) IS NULL THEN true ELSE false END","SCD history",""),
    ("BatchID","","1 AS BatchID","constant",""),
    ("EffectiveDate","Source.ActionXML.ActionTS","ActionTS AS EffectiveDate","SCD history",""),
    ("EndDate","","COALESCE(LEAD(ActionTS) OVER (...), TIMESTAMP '9999-12-31')","SCD history",""),
]:
    row("DimAccount", c, "populated", src, sql, kind, note, "yes")

# ================= DimSecurity (15) =================
row("DimSecurity","SK_SecurityID","populated","","ROW_NUMBER() OVER (ORDER BY Symbol, EffectiveDate)","generated_key","matches original's explicit final ORDER BY","yes")
row("DimSecurity","Symbol","populated","Source.FinwireSEC.Symbol","Symbol","passthrough_copy","","yes")
row("DimSecurity","Issue","populated","Source.FinwireSEC.IssueType","IssueType AS Issue","rename","","yes")
row("DimSecurity","Status","populated","Source.FinwireSEC.Status -> Source.StatusType.ST_NAME","JOIN StatusType","lookup join","","yes")
row("DimSecurity","Name","populated","Source.FinwireSEC.Name","Name","passthrough_copy","","yes")
row("DimSecurity","ExchangeID","populated","Source.FinwireSEC.ExID","ExID AS ExchangeID","rename","","yes")
row("DimSecurity","SK_CompanyID","populated","Source.FinwireSEC.CoNameOrCIK -> DimCompany","JOIN DimCompany ON CASE WHEN numeric THEN CompanyID ELSE Name END = CoNameOrCIK","lookup join",
    "author's own comment: 'TODO: improve query because it is joining varchars' -- fragile string-based join predicate (compares a CAST'd integer-as-text OR a company name against one text field), flagged by README as a table with 'unresolved data issues'","no",
    "fragile varchar-based join predicate, flagged by the original author as needing improvement","yes")
row("DimSecurity","SharesOutstanding","populated","Source.FinwireSEC.ShOut","TRY_CAST(ShOut AS INTEGER)","retype","","yes")
row("DimSecurity","FirstTrade","populated","Source.FinwireSEC.FirstTradeDate","try_strptime(...,'%Y%m%d')::DATE","retype","YYYYMMDD text, fixed via try_strptime during port (plain CAST silently returned NULL)","yes")
row("DimSecurity","FirstTradeOnExchange","populated","Source.FinwireSEC.FirstTradeExchg","try_strptime(...,'%Y%m%d')::DATE","retype","same YYYYMMDD fix","yes")
row("DimSecurity","Dividend","populated","Source.FinwireSEC.Dividend","TRY_CAST(Dividend AS NUMERIC)","retype","","yes")
row("DimSecurity","IsCurrent","populated","","CASE WHEN LEAD(EffectiveDate) OVER (PARTITION BY Symbol ORDER BY EffectiveDate) IS NULL THEN true ELSE false END","SCD history","","yes")
row("DimSecurity","BatchID","populated","","1 AS BatchID","constant","","yes")
row("DimSecurity","EffectiveDate","populated","Source.FinwireSEC.PTS","strptime(PTS,'%Y%m%d-%H%M%S')","SCD history","","yes")
row("DimSecurity","EndDate","populated","","COALESCE(LEAD(EffectiveDate) OVER (...), TIMESTAMP '9999-12-31')","SCD history","","yes")

# ================= DimTrade (21) -- table_caution=yes throughout, matches README + our new finding =================
CAUTION = "yes"
row("DimTrade","TradeID","populated","Source.Trade.T_ID","T.T_ID AS TradeID","passthrough_copy","not a generated surrogate -- copied directly, acts as a natural/business key here","yes","","")
row("DimTrade","SK_BrokerID","populated","","1 AS SK_BrokerID (literal placeholder)","constant",
    "author's own comment '-- FIX SK': never implemented as a real lookup join to DimBroker","no","hardcoded placeholder constant, not a real FK lookup",CAUTION)
row("DimTrade","SK_CreateDateID","populated","Source.TradeHistory.TH_DTS","COALESCE(CASE WHEN...,TH_DTS) -- ADDED COALESCE fallback","lookup join",
    "R1's original CASE is non-exhaustive: never matches SBMT trades whose T_TT_ID is not in (TMB,TMS), leaving NULL and violating the NOT NULL target -- COALESCE(...,TH_DTS) fallback added during DuckDB port to get real rows; this is OUR addition, not R1's logic",
    "no","non-exhaustive CASE in the original, patched with an added fallback",CAUTION)
row("DimTrade","SK_CreateTimeID","populated","Source.TradeHistory.TH_DTS","same COALESCE fallback as SK_CreateDateID","lookup join","see SK_CreateDateID","no","same non-exhaustive CASE, same patch",CAUTION)
row("DimTrade","SK_CloseDateID","populated","Source.TradeHistory.TH_DTS","CASE WHEN TH_ST_ID IN (CMPT,CNCL) THEN TH_DTS ELSE NULL END (nullable target, no patch needed)","lookup join","legitimately NULL for still-open trades -- target column is nullable so no patch needed here","yes","","")
row("DimTrade","SK_CloseTimeID","populated","Source.TradeHistory.TH_DTS","same as SK_CloseDateID","lookup join","","yes","","")
row("DimTrade","Status","populated","Source.Trade.T_ST_ID -> Source.StatusType.ST_NAME","JOIN StatusType","lookup join","","yes","","")
row("DimTrade","DT_Type","populated","Source.Trade.T_TT_ID -> Source.TradeType.TT_NAME","JOIN TradeType","lookup join","","yes","","")
row("DimTrade","CashFlag","populated","Source.Trade.T_IS_CASH","CASE WHEN UPPER(T_IS_CASH)='TRUE' THEN true ELSE false END","value","source stores literal text 'true'/'false'","yes","","")
row("DimTrade","SK_SecurityID","populated","","1 AS SK_SecurityID (literal placeholder)","constant","author's own '-- FIX SK' comment, never implemented","no","hardcoded placeholder constant",CAUTION)
row("DimTrade","SK_CompanyID","populated","","1 AS SK_CompanyID (literal placeholder)","constant","author's own '-- FIX SK' comment, never implemented","no","hardcoded placeholder constant",CAUTION)
row("DimTrade","Quantity","populated","Source.Trade.T_QTY","T_QTY AS Quantity","rename","","yes","","")
row("DimTrade","BidPrice","populated","Source.Trade.T_BID_PRICE","T_BID_PRICE AS BidPrice","rename","","yes","","")
row("DimTrade","SK_CustomerID","populated","","1 AS SK_CustomerID (literal placeholder)","constant","author's own '-- FIX SK' comment, never implemented","no","hardcoded placeholder constant",CAUTION)
row("DimTrade","SK_AccountID","populated","","1 AS SK_AccountID (literal placeholder)","constant","author's own '-- FIX SK' comment, never implemented","no","hardcoded placeholder constant",CAUTION)
row("DimTrade","ExecutedBy","populated","Source.Trade.T_EXEC_NAME","T_EXEC_NAME AS ExecutedBy","rename","","yes","","")
row("DimTrade","TradePrice","populated","Source.Trade.T_TRADE_PRICE","T_TRADE_PRICE AS TradePrice","rename","","yes","","")
row("DimTrade","Fee","populated","Source.Trade.T_CHRG","T_CHRG AS Fee","rename","","yes","","")
row("DimTrade","Commission","populated","Source.Trade.T_COMM","T_COMM AS Commission","rename","","yes","","")
row("DimTrade","Tax","populated","Source.Trade.T_TAX","T_TAX AS Tax","rename","","yes","","")
row("DimTrade","BatchID","populated","","1 AS BatchID","constant","","yes","","")

# ================= FactCashBalances (5) =================
row("FactCashBalances","SK_CustomerID","populated","Source.CashTransaction.CT_CA_ID -> DimAccount","JOIN DimAccount ON CT_CA_ID=AccountID","copies_generated_key","","yes","","")
row("FactCashBalances","SK_AccountID","populated","Source.CashTransaction.CT_CA_ID -> DimAccount","same join","copies_generated_key","","yes","","")
row("FactCashBalances","SK_DateID","populated","Source.CashTransaction.CT_DTS -> DimDate","JOIN DimDate ON date match","lookup join","","yes","","")
row("FactCashBalances","Cash","populated","Source.CashTransaction.CT_AMT","SUM(CT_AMT) GROUP BY customer/account/date","aggregate",
    "author's own TODO: 'Add to previous account balance (after having DimAccount)' -- as written this is a per-day net sum, NOT a running/cumulative balance carried forward from prior days, which is what a 'cash balance' normally implies","no",
    "daily net sum, not a true running balance, per the author's own unresolved TODO","")
row("FactCashBalances","BatchID","populated","","1 AS BatchID","constant","","yes","","")

# ================= FactHoldings (11) -- inherits DimTrade's placeholder-SK caution =================
row("FactHoldings","SK_CustomerID","populated","DimTrade.SK_CustomerID","DT.SK_CustomerID","copies_generated_key","inherits DimTrade's hardcoded-1 placeholder","no","inherited from DimTrade's unreliable SK_CustomerID","yes")
row("FactHoldings","SK_AccountID","populated","DimTrade.SK_AccountID","DT.SK_AccountID","copies_generated_key","inherits DimTrade's hardcoded-1 placeholder","no","inherited from DimTrade's unreliable SK_AccountID","yes")
row("FactHoldings","SK_SecurityID","populated","DimTrade.SK_SecurityID","DT.SK_SecurityID","copies_generated_key","inherits DimTrade's hardcoded-1 placeholder","no","inherited from DimTrade's unreliable SK_SecurityID","yes")
row("FactHoldings","SK_CompanyID","populated","DimTrade.SK_CompanyID","DT.SK_CompanyID","copies_generated_key","inherits DimTrade's hardcoded-1 placeholder","no","inherited from DimTrade's unreliable SK_CompanyID","yes")
row("FactHoldings","CurrentPrice","populated","DimTrade.TradePrice","DT.TradePrice AS CurrentPrice","value",
    "author's own comment: 'seemed like the field that made sense, but not explicit in TPC-DI spec' -- QUESTION left in the original code","no","author explicitly flagged their own uncertainty about this field choice","yes")
row("FactHoldings","SK_DateID","populated","DimTrade.SK_CloseDateID","COALESCE(DT.SK_CloseDateID, DT.SK_CreateDateID) -- ADDED fallback","lookup join",
    "R1's plain join could surface a still-open DimTrade row with NULL SK_CloseDateID, violating the target's NOT NULL -- COALESCE fallback to SK_CreateDateID added during DuckDB port; this is OUR addition","no","patched to avoid NULLs from an unfiltered join to DimTrade","yes")
row("FactHoldings","SK_TimeID","populated","DimTrade.SK_CloseTimeID","COALESCE(DT.SK_CloseTimeID, DT.SK_CreateTimeID) -- ADDED fallback","lookup join","same as SK_DateID","no","same patch as SK_DateID","yes")
row("FactHoldings","TradeID","populated","Source.HoldingHistory.HH_H_T_ID","HH.HH_H_T_ID AS TradeID","rename","","yes","","")
row("FactHoldings","CurrentTradeID","populated","Source.HoldingHistory.HH_T_ID","HH.HH_T_ID AS CurrentTradeID","rename","","yes","","")
row("FactHoldings","CurrentHolding","populated","Source.HoldingHistory.HH_AFTER_QTY","HH.HH_AFTER_QTY AS CurrentHolding","rename","","yes","","")
row("FactHoldings","BatchID","populated","","1 AS BatchID","constant","","yes","","")

# ================= Financial (14) =================
row("Financial","SK_CompanyID","populated","Source.FinwireFIN.CoNameOrCIK -> DimCompany","correlated subquery matching CIK or Name, WHERE IsCurrent","lookup join",
    "verified 0 of 98,576 rows failed to match a company (checked during C7 verification)","yes","","")
for tc, sc in [("FI_YEAR","Year"),("FI_QTR","Quarter"),("FI_QTR_START_DATE","QtrStartDate"),("FI_REVENUE","Revenue"),
               ("FI_NET_EARN","Earnings"),("FI_BASIC_EPS","EPS"),("FI_DILUT_EPS","DilutedEPS"),("FI_MARGIN","Margin"),
               ("FI_INVENTORY","Inventory"),("FI_ASSETS","Assets"),("FI_LIABILITY","Liabilities"),
               ("FI_OUT_BASIC","ShOut"),("FI_OUT_DILUT","DilutedShOut")]:
    note = "YYYYMMDD text, fixed via try_strptime during port" if tc == "FI_QTR_START_DATE" else ""
    row("Financial", tc, "populated", f"Source.FinwireFIN.{sc}", f"TRY_CAST({sc} AS ...)", "retype", note, "yes", "", "")

# ================= Prospect (27) =================
row("Prospect","AgencyID","populated","Source.Prospect.AgencyID","AgencyID","passthrough_copy","","yes","","")
row("Prospect","SK_RecordDateID","populated","Source.BatchDate -> DimDate","lookup join on the single BatchDate value","lookup join","","yes","","")
row("Prospect","SK_UpdateDateID","populated","Source.BatchDate -> DimDate","identical lookup to SK_RecordDateID","lookup join","same BatchDate lookup repeated","yes","","")
row("Prospect","BatchID","populated","","1 AS BatchID","constant","","yes","","")
row("Prospect","IsCustomer","populated","Source.Prospect.{FirstName,LastName,AddressLine1,AddressLine2,PostalCode} -> DimCustomer",
    "correlated subquery fuzzy name/address match against DimCustomer WHERE Status='ACTIVE'",
    "conditional","target column is BOOLEAN but R1's original query returns a bare COUNT(*) (an integer), a real type mismatch -- patched to COUNT(*)>0 during DuckDB port to produce an actual boolean","no",
    "type-mismatch bug in the original (COUNT(*) into a BOOLEAN column), patched to COUNT(*)>0","")
for c in ["LastName","FirstName","MiddleInitial","Gender","AddressLine1","AddressLine2","PostalCode","City","State",
          "Country","Phone","Income","numberCars","numberChildren","MaritalStatus","Age","CreditRating",
          "OwnOrRentFlag","Employer","numberCreditCards","NetWorth"]:
    row("Prospect", c, "populated", f"Source.Prospect.{c}", c, "passthrough_copy", "", "yes", "", "")
row("Prospect","MarketingNameplate","populated","Source.Prospect.{NetWorth,Income,NumberChildren,NumberCreditCards,Age,CreditRating,NumberCars}",
    "6-branch CASE (same pattern as DimCustomer's)","conditional","", "yes","","")

# ================= Not-built tables =================
for c in ["SK_SecurityID","SK_CompanyID","SK_DateID","PERatio","Yield","FiftyTwoWeekHigh","SK_FiftyTwoWeekHighDate",
          "FiftyTwoWeekLow","SK_FiftyTwoWeekLowDate","ClosePrice","DayHigh","DayLow","Volume","BatchID"]:
    row("FactMarketHistory", c, "not_built", "", "entire INSERT commented out in historical_load.sql", "n/a",
        "classified from dead/commented code only (see tpcdi_transformations.csv from Task A3 for the inferred category per column) -- not executable, table stays empty", "no",
        "transformation never completed by R1 -- table excluded from their own benchmark per README", "yes")
for c in ["SK_CustomerID","SK_SecurityID","SK_DateID_DatePlaced","SK_DateID_DateRemoved","BatchID"]:
    row("FactWatches", c, "not_built", "", "entire INSERT commented out in historical_load.sql", "n/a",
        "no reference implementation found (R3/dbtpcdi not checked for this table)", "no",
        "transformation never completed by R1 -- table excluded from their own benchmark per README", "yes")
for c in ["MessageDateAndTime","BatchID","MessageSource","MessageText","MessageType","MessageData"]:
    row("DImessages", c, "not_built", "", "only a '-- TODO: DImessages' comment, zero code", "n/a",
        "not even an attempt exists in historical_load.sql, unlike FactMarketHistory/FactWatches which at least have dead code", "no",
        "no transformation attempted at all", "yes")
for c in ["DataSet","BatchID","AT_Date","AT_Attribute","AT_Value","DValue"]:
    row("AuditTable", c, "not_built", "", "populated by a separate audit/validation process (tpcdi_audit.sql), not historical_load.sql", "n/a",
        "out of scope for the ETL transformation proper -- this table holds TPC-DI's own benchmark audit/validation values, a different concern from S->T transformation", "n/a",
        "out of scope, not a transformation gap", "")

with open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))), "tpcdi/work/_part3.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(rows)
print(f"part 3: {len(rows)} rows written")
