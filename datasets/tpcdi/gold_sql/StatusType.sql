-- StatusType : identical to A (no spec change for this table)
-- Run with the target tables unqualified (current schema) and the source tables as Source.* (made by build_source.py).
-- Translation fixes (T-SQL -> DuckDB):
--  F1 removed dbo. schema prefix.
--  F2 INSERT column lists reduced to the target_ddl.sql columns (IsCurrent/EffectiveDate/EndDate/BatchID
--     and SK_* identity columns are not in the target tables).
INSERT INTO StatusType (ST_ID, ST_NAME)
SELECT ST_ID, ST_NAME FROM Source.StatusType;
