-- DimCompany [spec-fixed]: copy of A with ONE change
-- Run with the target tables unqualified (current schema) and the source tables as Source.* (made by build_source.py).
-- Change: invalid SPrating -> SPrating NULL and isLowGrade NULL (TPC-DI clause 4.5.3.3).
--   Reading used: [+/-] = optional sign, so AA, A, BBB, BB, B, CCC are valid (they occur in the data); regexp below.
-- Translation fixes (T-SQL -> DuckDB):
--  F1 removed dbo. schema prefix.
--  F2 INSERT column lists reduced to the target_ddl.sql columns (IsCurrent/EffectiveDate/EndDate/BatchID
--     and SK_* identity columns are not in the target tables).
INSERT INTO DimCompany (CompanyID, Status, Name, Industry, SPrating, isLowGrade, CEO, AddressLine1,
  AddressLine2, PostalCode, City, StateProv, Country, Description, FoundingDate)
WITH hist AS (
  SELECT
    CASE WHEN LEAD((SELECT BatchDate FROM Source.BatchDate LIMIT 1)) OVER (PARTITION BY CIK ORDER BY PTS ASC NULLS FIRST)
         IS NULL THEN 1 ELSE 0 END AS IsCurrent,
    CAST(CIK AS INTEGER) AS CompanyID, CompanyName AS Name,
    CASE WHEN regexp_full_match(SPrating, '(AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?|CCC[+-]?|CC|C|D)') THEN SPrating END AS SPrating, CEOname AS CEO, Description,
    CAST(STRPTIME(FoundingDate, '%Y%m%d') AS DATE) AS FoundingDate,
    AddrLine1 AS AddressLine1, AddrLine2 AS AddressLine2, PostalCode, City, StateProvince AS StateProv, Country,
    S.ST_NAME AS Status, I.IN_NAME AS Industry,
    CASE WHEN regexp_full_match(SPrating, '(AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?|CCC[+-]?|CC|C|D)') THEN (CASE WHEN SPrating LIKE 'A%' OR SPrating LIKE 'BBB%' THEN FALSE ELSE TRUE END) END AS isLowGrade
  FROM Source.FinwireCMP AS CMP, Source.StatusType AS S, Source.Industry AS I
  WHERE CMP.Status = S.ST_ID AND CMP.IndustryID = I.IN_ID
)
SELECT CompanyID, Status, Name, Industry, SPrating, isLowGrade, CEO, AddressLine1, AddressLine2, PostalCode, City,
  StateProv, Country, Description, FoundingDate
FROM hist WHERE IsCurrent = 1
ORDER BY CompanyID;
