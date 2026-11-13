-- DimDate : identical to A (no spec change for this table)
-- Run with the target tables unqualified (current schema) and the source tables as Source.* (made by build_source.py).
-- Translation fixes (T-SQL -> DuckDB):
--  F1 removed dbo. schema prefix.
--  F2 INSERT column lists reduced to the target_ddl.sql columns (IsCurrent/EffectiveDate/EndDate/BatchID
--     and SK_* identity columns are not in the target tables).
--  F3 DateValue CHAR text -> DATE; HolidayFlag 'true'/'false' text -> BOOLEAN (BIT in T-SQL).
INSERT INTO DimDate (SK_DateID, DateValue, DateDesc, CalendarYearID, CalendarYearDesc, CalendarQtrID,
  CalendarQtrDesc, CalendarMonthID, CalendarMonthDesc, CalendarWeekID, CalendarWeekDesc, DayOfWeeknumeric,
  DayOfWeekDesc, FiscalYearID, FiscalYearDesc, FiscalQtrID, FiscalQtrDesc, HolidayFlag)
SELECT SK_DateID, CAST(DateValue AS DATE), DateDesc, CalendarYearID, CalendarYearDesc, CalendarQtrID,
  CalendarQtrDesc, CalendarMonthID, CalendarMonthDesc, CalendarWeekID, CalendarWeekDesc, DayOfWeekNum,
  DayOfWeekDesc, FiscalYearID, FiscalYearDesc, FiscalQtrID, FiscalQtrDesc, CAST(HolidayFlag AS BOOLEAN)
FROM Source.Date;
