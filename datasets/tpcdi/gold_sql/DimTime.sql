-- DimTime : identical to A (no spec change for this table)
-- Run with the target tables unqualified (current schema) and the source tables as Source.* (made by build_source.py).
-- Translation fixes (T-SQL -> DuckDB):
--  F1 removed dbo. schema prefix.
--  F2 INSERT column lists reduced to the target_ddl.sql columns (IsCurrent/EffectiveDate/EndDate/BatchID
--     and SK_* identity columns are not in the target tables).
--  F3 TimeValue text -> TIME; Market/OfficeHoursFlag 'true'/'false' text -> BOOLEAN.
INSERT INTO DimTime (SK_TimeID, TimeValue, HourID, HourDesc, MinuteID, MinuteDesc, SecondID, SecondDesc,
  MarketHoursFlag, OfficeHoursFlag)
SELECT SK_TimeID, CAST(TimeValue AS TIME), HourID, HourDesc, MinuteID, MinuteDesc, SecondID, SecondDesc,
  CAST(MarketHoursFlag AS BOOLEAN), CAST(OfficeHoursFlag AS BOOLEAN)
FROM Source.Time;
