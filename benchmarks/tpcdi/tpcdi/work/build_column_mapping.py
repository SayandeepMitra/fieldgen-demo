import csv

FIELDS = ["target_table","target_column","target_type","table_status","producing_models",
          "source_tables","value_columns","key_columns","joins","rule_sql","combination",
          "lineage_path","column_kind","notes","rule_reliable","rule_issue","table_caution"]

rows = []

def row(table, col, typ, status, cte, src_tables, value_cols, key_cols, joins, sql, comb,
        lineage, kind, notes, reliable, issue="", caution=""):
    rows.append({
        "target_table": table, "target_column": col, "target_type": typ, "table_status": status,
        "producing_models": cte, "source_tables": src_tables, "value_columns": value_cols,
        "key_columns": key_cols, "joins": joins, "rule_sql": sql, "combination": comb,
        "lineage_path": lineage, "column_kind": kind, "notes": notes,
        "rule_reliable": reliable, "rule_issue": issue, "table_caution": caution,
    })

# ============================================================ reference / lookup tables (pure copy)
for table, cols, src in [
    ("Industry", [("IN_ID","CHAR(2)"),("IN_NAME","CHAR(50)"),("IN_SC_ID","CHAR(4)")], "Source.Industry"),
    ("StatusType", [("ST_ID","CHAR(4)"),("ST_NAME","CHAR(10)")], "Source.StatusType"),
    ("TaxRate", [("TX_ID","CHAR(4)"),("TX_NAME","CHAR(50)"),("TX_RATE","NUMERIC(6,5)")], "Source.TaxRate"),
    ("TradeType", [("TT_ID","CHAR(3)"),("TT_NAME","CHAR(12)"),("TT_IS_SELL","NUMERIC(1)"),("TT_IS_MRKT","NUMERIC(1)")], "Source.TradeType"),
]:
    for c, t in cols:
        row(table, c, t, "populated", "historical_load.sql", src, f"{src}.{c}", "", "",
            f"FROM {src.split('.')[1]}: {c}", "none",
            f"{table}.{c} <- {src}.{c}", "passthrough_copy",
            "pure 1:1 copy, no transform", "yes")

# ============================================================ DimDate (pure copy + 1 boolean cast)
for c, t in [("SK_DateID","INTEGER"),("DateValue","DATE"),("DateDesc","CHAR(20)"),
             ("CalendarYearID","NUMERIC(4)"),("CalendarYearDesc","CHAR(20)"),("CalendarQtrID","NUMERIC(5)"),
             ("CalendarQtrDesc","CHAR(20)"),("CalendarMonthID","NUMERIC(6)"),("CalendarMonthDesc","CHAR(20)"),
             ("CalendarWeekID","NUMERIC(6)"),("CalendarWeekDesc","CHAR(20)"),("DayOfWeekNum","NUMERIC(1)"),
             ("DayOfWeekDesc","CHAR(10)"),("FiscalYearID","NUMERIC(4)"),("FiscalYearDesc","CHAR(20)"),
             ("FiscalQtrID","NUMERIC(5)"),("FiscalQtrDesc","CHAR(20)")]:
    row("DimDate", c, t, "populated", "historical_load.sql", "Source.Date", f"Source.Date.{c}", "", "",
        f"FROM Date: {c}", "none", f"DimDate.{c} <- Source.Date.{c}", "passthrough_copy",
        "pure 1:1 copy; target renamed Source.Date.DayOfWeekNum from upstream 'DayOfWeeknumeric' spelling", "yes")
row("DimDate", "HolidayFlag", "BOOLEAN", "populated", "historical_load.sql", "Source.Date", "Source.Date.HolidayFlag", "", "",
    "CASE WHEN UPPER(HolidayFlag)='TRUE' THEN true ELSE false END", "case",
    "DimDate.HolidayFlag <- Source.Date.HolidayFlag", "value",
    "source stores literal text 'true'/'false', not 0/1 as the schema comment expects -- explicit boolean cast added during DuckDB port", "yes")

# ============================================================ DimTime
for c, t in [("SK_TimeID","INTEGER"),("TimeValue","TIME"),("HourID","NUMERIC(2)"),("HourDesc","CHAR(20)"),
             ("MinuteID","NUMERIC(2)"),("MinuteDesc","CHAR(20)"),("SecondID","NUMERIC(2)"),("SecondDesc","CHAR(20)")]:
    row("DimTime", c, t, "populated", "historical_load.sql", "Source.Time", f"Source.Time.{c}", "", "",
        f"FROM Time: {c}", "none", f"DimTime.{c} <- Source.Time.{c}", "passthrough_copy",
        "pure 1:1 copy", "yes")
for c in ["MarketHoursFlag", "OfficeHoursFlag"]:
    row("DimTime", c, "BOOLEAN", "populated", "historical_load.sql", "Source.Time", f"Source.Time.{c}", "", "",
        f"CASE WHEN UPPER({c})='TRUE' THEN true ELSE false END", "case",
        f"DimTime.{c} <- Source.Time.{c}", "value",
        "source stores literal text 'true'/'false' -- explicit boolean cast added during DuckDB port", "yes")

with open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))), "tpcdi/work/_part1.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(rows)
print(f"part 1: {len(rows)} rows written")
