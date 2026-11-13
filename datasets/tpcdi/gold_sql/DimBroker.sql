-- DimBroker : repo historical_load.sql DimBroker part (HR rows with EmployeeJobCode = 314)
-- Run with the target tables unqualified (current schema) and the source tables as Source.* (made by build_source.py).
-- Translation fixes (T-SQL -> DuckDB):
--  F1 removed dbo. schema prefix.
--  F2 INSERT column lists reduced to the target_ddl.sql columns (IsCurrent/EffectiveDate/EndDate/BatchID
--     and SK_* identity columns are not in the target tables).
INSERT INTO DimBroker (BrokerID, ManagerID, FirstName, LastName, MiddleInitial, Branch, Office, Phone)
SELECT EmployeeID, ManagerID, EmployeeFirstName, EmployeeLastName, EmployeeMI, EmployeeBranch, EmployeeOffice,
  EmployeePhone
FROM Source.HR
WHERE EmployeeJobCode = 314;
