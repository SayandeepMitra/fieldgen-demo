-- TradeType : identical to A (no spec change for this table)
-- Run with the target tables unqualified (current schema) and the source tables as Source.* (made by build_source.py).
-- Translation fixes (T-SQL -> DuckDB):
--  F1 removed dbo. schema prefix.
--  F2 INSERT column lists reduced to the target_ddl.sql columns (IsCurrent/EffectiveDate/EndDate/BatchID
--     and SK_* identity columns are not in the target tables).
INSERT INTO TradeType (TT_ID, TT_NAME, TT_IS_SELL, TT_IS_MRKT)
SELECT TT_ID, TT_NAME, TT_IS_SELL, TT_IS_MRKT FROM Source.TradeType;
