-- Ported from TPC-DI-MS-SQL-Benchmark/Helpers/Scripts/historical_load.sql (T-SQL) to DuckDB SQL.
-- Dialect fixes applied throughout: GO removed (one statement per ';'), bracket identifiers
-- stripped, TOP n -> LIMIT n, IDENTITY surrogate keys -> explicit ROW_NUMBER() OVER (...),
-- string '+' concat -> '||', CONVERT(...)/STUFF(...) date hacks -> strptime(), ISNUMERIC(...)
-- -> TRY_CAST(...) IS NOT NULL, 'true'/'false' text flags -> explicit BOOLEAN CASE, dbo. prefix
-- dropped (target tables live in DuckDB's default "main" schema).
-- Known-unreliable logic from the original (R1) is PRESERVED, not fixed, and flagged with a
-- comment -- see benchmark/deliverables/tpcdi_column_mapping.csv for the rule_reliable flag.

-- ================= DimDate =================
INSERT INTO DimDate (SK_DateID, DateValue, DateDesc, CalendarYearID, CalendarYearDesc, CalendarQtrID, CalendarQtrDesc, CalendarMonthID, CalendarMonthDesc, CalendarWeekID, CalendarWeekDesc, DayOfWeekNum, DayOfWeekDesc, FiscalYearID, FiscalYearDesc, FiscalQtrID, FiscalQtrDesc, HolidayFlag)
SELECT SK_DateID, DateValue, DateDesc, CalendarYearID, CalendarYearDesc, CalendarQtrID, CalendarQtrDesc, CalendarMonthID, CalendarMonthDesc, CalendarWeekID, CalendarWeekDesc, DayOfWeekNum, DayOfWeekDesc, FiscalYearID, FiscalYearDesc, FiscalQtrID, FiscalQtrDesc,
    CASE WHEN UPPER(HolidayFlag) = 'TRUE' THEN true ELSE false END AS HolidayFlag
FROM Source.Date;

-- ================= DimTime =================
INSERT INTO DimTime (SK_TimeID, TimeValue, HourID, HourDesc, MinuteID, MinuteDesc, SecondID, SecondDesc, MarketHoursFlag, OfficeHoursFlag)
SELECT SK_TimeID, TimeValue, HourID, HourDesc, MinuteID, MinuteDesc, SecondID, SecondDesc,
    CASE WHEN UPPER(MarketHoursFlag) = 'TRUE' THEN true ELSE false END AS MarketHoursFlag,
    CASE WHEN UPPER(OfficeHoursFlag) = 'TRUE' THEN true ELSE false END AS OfficeHoursFlag
FROM Source.Time;

-- ================= StatusType =================
INSERT INTO StatusType (ST_ID, ST_NAME)
SELECT ST_ID, ST_NAME FROM Source.StatusType;

-- ================= TaxRate =================
INSERT INTO TaxRate (TX_ID, TX_NAME, TX_RATE)
SELECT TX_ID, TX_NAME, TX_RATE FROM Source.TaxRate;

-- ================= TradeType =================
INSERT INTO TradeType (TT_ID, TT_NAME, TT_IS_SELL, TT_IS_MRKT)
SELECT TT_ID, TT_NAME, TT_IS_SELL, TT_IS_MRKT FROM Source.TradeType;

-- ================= Industry =================
INSERT INTO Industry (IN_ID, IN_NAME, IN_SC_ID)
SELECT IN_ID, IN_NAME, IN_SC_ID FROM Source.Industry;

-- ================= DimBroker =================
-- Original has no ORDER BY on the final SELECT -- added ORDER BY BrokerID for a deterministic
-- surrogate key (IDENTITY's insertion order was implementation-defined in SQL Server anyway).
INSERT INTO DimBroker (SK_BrokerID, BrokerID, ManagerID, FirstName, LastName, MiddleInitial, Branch, Office, Phone, IsCurrent, BatchID, EffectiveDate, EndDate)
SELECT
    ROW_NUMBER() OVER (ORDER BY EmployeeID) AS SK_BrokerID,
    EmployeeID AS BrokerID,
    ManagerID,
    EmployeeFirstName AS FirstName,
    EmployeeLastName AS LastName,
    EmployeeMI AS MiddleInitial,
    EmployeeBranch AS Branch,
    EmployeeOffice AS Office,
    EmployeePhone AS Phone,
    true AS IsCurrent,
    1 AS BatchID,
    (SELECT MIN(DateValue) FROM DimDate) AS EffectiveDate,
    DATE '9999-12-31' AS EndDate
FROM Source.HR
WHERE EmployeeJobCode = 314;

-- ================= DimCompany =================
-- Original has no ORDER BY on the final SELECT -- added ORDER BY CompanyID, EffectiveDate.
INSERT INTO DimCompany (SK_CompanyID, CompanyID, Status, Name, Industry, SPrating, isLowGrade, CEO, Description, FoundingDate, AddressLine1, AddressLine2, PostalCode, City, StateProv, Country, IsCurrent, BatchID, EffectiveDate, EndDate)
SELECT
    ROW_NUMBER() OVER (ORDER BY CompanyID, EffectiveDate) AS SK_CompanyID,
    CompanyID, Status, Name, Industry, SPrating, isLowGrade, CEO, Description, FoundingDate,
    AddressLine1, AddressLine2, PostalCode, City, StateProv, Country,
    CASE WHEN LEAD(EffectiveDate) OVER (PARTITION BY CompanyID ORDER BY EffectiveDate ASC) IS NULL THEN true ELSE false END AS IsCurrent,
    1 AS BatchID,
    EffectiveDate,
    COALESCE(LEAD(EffectiveDate) OVER (PARTITION BY CompanyID ORDER BY EffectiveDate ASC), DATE '9999-12-31') AS EndDate
FROM (
    SELECT
        CIK AS CompanyID,
        CompanyName AS Name,
        SPrating,
        CEOname AS CEO,
        Description,
        try_strptime(FoundingDate, '%Y%m%d')::DATE AS FoundingDate,
        AddrLine1 AS AddressLine1,
        AddrLine2 AS AddressLine2,
        PostalCode,
        City,
        StateProvince AS StateProv,
        Country,
        S.ST_NAME AS Status,
        I.IN_NAME AS Industry,
        (CASE WHEN SPrating LIKE 'A%' OR SPrating LIKE 'BBB%' THEN false ELSE true END) AS isLowGrade,
        strptime(PTS, '%Y%m%d-%H%M%S') AS EffectiveDate
    FROM Source.FinwireCMP CMP, Source.StatusType S, Source.Industry I
    WHERE CMP.Status = S.ST_ID
      AND CMP.IndustryID = I.IN_ID
) AS c;

-- ================= DimCustomer =================
-- Faithful port of the original 9-table CTE chain (Action/Customer/Name/Address/ContactInfo/
-- Phone-1-2-3/TaxInfo/Prospect fuzzy match). Logic unchanged; only dialect fixed: '+' -> '||'
-- for string concat, bracket identifiers stripped, dbo. prefix dropped.
WITH Customers_Preproc AS (
    SELECT CXML.C_ID AS CustomerID
        , TRIM(CXML.C_TAX_ID) AS TaxID
        , TRIM(UPPER(CASE WHEN CXML.C_GNDR NOT IN ('m', 'f') OR CXML.C_GNDR IS NULL THEN 'u' ELSE CXML.C_GNDR END)) AS Gender
        , TRY_CAST(CXML.C_TIER AS INTEGER) AS Tier
        , TRY_CAST(CXML.C_DOB AS DATE) AS DOB
        , TRIM(CCIN.C_PRIM_EMAIL) AS Email1
        , TRIM(CCIN.C_ALT_EMAIL) AS Email2
        , TRIM(NXML.C_F_NAME) AS FirstName
        , TRIM(NXML.C_M_NAME) AS MiddleInitial
        , TRIM(NXML.C_L_NAME) AS LastName
        , TRIM(ADXML.C_ADLINE1) AS AddressLine1
        , TRIM(ADXML.C_ADLINE2) AS AddressLine2
        , TRIM(ADXML.C_ZIPCODE) AS PostalCode
        , TRIM(ADXML.C_CITY) AS City
        , TRIM(ADXML.C_STATE_PROV) AS StateProv
        , TRIM(ADXML.C_CTRY) AS Country
        , CASE
            WHEN CP1XML.C_CTRY_CODE IS NOT NULL AND CP1XML.C_AREA_CODE IS NOT NULL AND CP1XML.C_LOCAL IS NOT NULL
                THEN '+' || CP1XML.C_CTRY_CODE || ' (' || CP1XML.C_AREA_CODE || ') ' || CP1XML.C_LOCAL
            WHEN CP1XML.C_CTRY_CODE IS NULL AND (CP1XML.C_AREA_CODE IS NOT NULL AND CP1XML.C_LOCAL IS NOT NULL)
                THEN '(' || CP1XML.C_AREA_CODE || ') ' || CP1XML.C_LOCAL
            WHEN (CP1XML.C_CTRY_CODE IS NULL AND CP1XML.C_AREA_CODE IS NULL) AND CP1XML.C_LOCAL IS NOT NULL
                THEN CP1XML.C_LOCAL
        END AS Phone1_V1
        , CASE
            WHEN CP2XML.C_CTRY_CODE IS NOT NULL AND CP2XML.C_AREA_CODE IS NOT NULL AND CP2XML.C_LOCAL IS NOT NULL
                THEN '+' || CP2XML.C_CTRY_CODE || ' (' || CP2XML.C_AREA_CODE || ') ' || CP2XML.C_LOCAL
            WHEN CP2XML.C_CTRY_CODE IS NULL AND (CP2XML.C_AREA_CODE IS NOT NULL AND CP2XML.C_LOCAL IS NOT NULL)
                THEN '(' || CP2XML.C_AREA_CODE || ') ' || CP2XML.C_LOCAL
            WHEN (CP2XML.C_CTRY_CODE IS NULL AND CP2XML.C_AREA_CODE IS NULL) AND CP2XML.C_LOCAL IS NOT NULL
                THEN CP2XML.C_LOCAL
        END AS Phone2_V1
        , CASE
            WHEN CP3XML.C_CTRY_CODE IS NOT NULL AND CP3XML.C_AREA_CODE IS NOT NULL AND CP3XML.C_LOCAL IS NOT NULL
                THEN '+' || CP3XML.C_CTRY_CODE || ' (' || CP3XML.C_AREA_CODE || ') ' || CP3XML.C_LOCAL
            WHEN CP3XML.C_CTRY_CODE IS NULL AND (CP3XML.C_AREA_CODE IS NOT NULL AND CP3XML.C_LOCAL IS NOT NULL)
                THEN '(' || CP3XML.C_AREA_CODE || ') ' || CP3XML.C_LOCAL
            WHEN (CP3XML.C_CTRY_CODE IS NULL AND CP3XML.C_AREA_CODE IS NULL) AND CP3XML.C_LOCAL IS NOT NULL
                THEN CP3XML.C_LOCAL
        END AS Phone3_V1
        , TRIM(TR.TX_NAME) AS NationalTaxRateDesc
        , TR.TX_RATE AS NationalTaxRate
        , TRIM(TR2.TX_NAME) AS LocalTaxRateDesc
        , TR2.TX_RATE AS LocalTaxRate
        , CP1XML.C_EXT AS C_EXT1
        , CP2XML.C_EXT AS C_EXT2
        , CP3XML.C_EXT AS C_EXT3
        , TRIM(P.AgencyID) AS AgencyID
        , P.CreditRating
        , P.NetWorth
        , CASE
            WHEN P.NetWorth > 1000000 OR P.Income > 200000 THEN 'HighValue'
            WHEN P.NumberChildren > 3 OR P.NumberCreditCards > 5 THEN 'Expenses'
            WHEN P.Age > 45 THEN 'Boomer'
            WHEN P.Income < 50000 OR P.CreditRating < 600 OR P.NetWorth < 100000 THEN 'MoneyAlert'
            WHEN P.NumberCars > 3 OR P.NumberCreditCards > 7 THEN 'Spender'
            WHEN P.Age < 25 AND P.NetWorth > 1000000 THEN 'Inherited'
        END AS MarketingNameplate
        , AXML.ActionType
        , TRY_CAST(AXML.ActionTS AS TIMESTAMP) AS ActionTS
    FROM Source.CustomerXML CXML
        LEFT JOIN Source.ActionXML AXML ON CXML.Action_Id = AXML.Action_Id
        LEFT JOIN Source.NameXML NXML ON CXML.Customer_Id = NXML.Customer_Id
        LEFT JOIN Source.ContactInfoXML CCIN ON CXML.Customer_Id = CCIN.Customer_Id
        LEFT JOIN Source.AddressXML ADXML ON CXML.Customer_Id = ADXML.Customer_Id
        LEFT JOIN Source.TaxInfoXML TXML ON CXML.Customer_Id = TXML.Customer_Id
        LEFT JOIN Source.TaxRate TR ON TXML.C_NAT_TX_ID = TR.TX_ID
        LEFT JOIN Source.TaxRate TR2 ON TXML.C_LCL_TX_ID = TR2.TX_ID
        LEFT JOIN Source.C_PHONE_1_XML CP1XML ON CCIN.ContactInfo_Id = CP1XML.ContactInfo_Id
        LEFT JOIN Source.C_PHONE_2_XML CP2XML ON CCIN.ContactInfo_Id = CP2XML.ContactInfo_Id
        LEFT JOIN Source.C_PHONE_3_XML CP3XML ON CCIN.ContactInfo_Id = CP3XML.ContactInfo_Id
        LEFT JOIN Source.Prospect P
            ON COALESCE(UPPER(TRIM(NXML.C_F_NAME)), ' ') = COALESCE(UPPER(TRIM(P.FirstName)), ' ')
            AND COALESCE(UPPER(TRIM(NXML.C_L_NAME)), ' ') = COALESCE(UPPER(TRIM(P.LastName)), ' ')
            AND COALESCE(UPPER(TRIM(ADXML.C_ADLINE1)), ' ') = COALESCE(UPPER(TRIM(P.AddressLine1)), ' ')
            AND COALESCE(UPPER(TRIM(ADXML.C_ADLINE2)), ' ') = COALESCE(UPPER(TRIM(P.AddressLine2)), ' ')
            AND COALESCE(UPPER(TRIM(ADXML.C_ZIPCODE)), ' ') = COALESCE(UPPER(TRIM(P.PostalCode)), ' ')
)
, Customers AS (
    SELECT *
        , CASE WHEN C_EXT1 IS NOT NULL THEN Phone1_V1 || C_EXT1 ELSE Phone1_V1 END AS Phone1
        , CASE WHEN C_EXT2 IS NOT NULL THEN Phone2_V1 || C_EXT2 ELSE Phone2_V1 END AS Phone2
        , CASE WHEN C_EXT3 IS NOT NULL THEN Phone3_V1 || C_EXT3 ELSE Phone3_V1 END AS Phone3
    FROM Customers_Preproc
)
, CustomersNew AS (
    SELECT *, 'ACTIVE' AS Status FROM Customers WHERE ActionType = 'NEW'
)
, CustomersUpd AS (
    SELECT * FROM Customers WHERE ActionType = 'UPDCUST'
)
, CustomersInactive AS (
    SELECT CXML.C_ID AS C_ID, TRY_CAST(AXML.ActionTS AS TIMESTAMP) AS ActionTS
    FROM Source.CustomerXML CXML
        INNER JOIN Source.ActionXML AXML ON CXML.Action_Id = AXML.Action_Id
    WHERE AXML.ActionType = 'INACT'
)
, CustomersNewAndUpd AS (
    SELECT CustomerID, TaxID, 'ACTIVE' AS Status, LastName, FirstName, MiddleInitial, Gender, Tier, DOB,
        AddressLine1, AddressLine2, PostalCode, City, StateProv, Country, Phone1, Phone2, Phone3,
        Email1, Email2, NationalTaxRateDesc, NationalTaxRate, LocalTaxRateDesc, LocalTaxRate,
        AgencyID, CreditRating, NetWorth, MarketingNameplate, ActionTS, ActionType
    FROM CustomersNew
    UNION ALL
    SELECT NC.CustomerID
        , COALESCE(UC.TaxID, NC.TaxID) AS TaxID
        , NC.Status AS Status
        , COALESCE(UC.LastName, NC.LastName) AS LastName
        , COALESCE(UC.FirstName, NC.FirstName) AS FirstName
        , COALESCE(UC.MiddleInitial, NC.MiddleInitial) AS MiddleInitial
        , COALESCE(UC.Gender, NC.Gender) AS Gender
        , COALESCE(UC.Tier, NC.Tier) AS Tier
        , COALESCE(UC.DOB, NC.DOB) AS DOB
        , COALESCE(UC.AddressLine1, NC.AddressLine1) AS AddressLine1
        , COALESCE(UC.AddressLine2, NC.AddressLine2) AS AddressLine2
        , COALESCE(UC.PostalCode, NC.PostalCode) AS PostalCode
        , COALESCE(UC.City, NC.City) AS City
        , COALESCE(UC.StateProv, NC.StateProv) AS StateProv
        , COALESCE(UC.Country, NC.Country) AS Country
        , COALESCE(UC.Phone1, NC.Phone1) AS Phone1
        , COALESCE(UC.Phone2, NC.Phone2) AS Phone2
        , COALESCE(UC.Phone3, NC.Phone3) AS Phone3
        , COALESCE(UC.Email1, NC.Email1) AS Email1
        , COALESCE(UC.Email2, NC.Email2) AS Email2
        , COALESCE(UC.NationalTaxRateDesc, NC.NationalTaxRateDesc) AS NationalTaxRateDesc
        , COALESCE(UC.NationalTaxRate, NC.NationalTaxRate) AS NationalTaxRate
        , COALESCE(UC.LocalTaxRateDesc, NC.LocalTaxRateDesc) AS LocalTaxRateDesc
        , COALESCE(UC.LocalTaxRate, NC.LocalTaxRate) AS LocalTaxRate
        , COALESCE(UC.AgencyID, NC.AgencyID) AS AgencyID
        , COALESCE(UC.CreditRating, NC.CreditRating) AS CreditRating
        , COALESCE(UC.NetWorth, NC.NetWorth) AS NetWorth
        , COALESCE(UC.MarketingNameplate, NC.MarketingNameplate) AS MarketingNameplate
        , UC.ActionTS
        , UC.ActionType
    FROM CustomersNew NC
        INNER JOIN CustomersUpd UC ON NC.CustomerID = UC.CustomerID
)
, CustomersFinal AS (
    SELECT * FROM CustomersNewAndUpd
    UNION ALL
    SELECT CNU.CustomerID, CNU.TaxID, 'INACTIVE' AS Status, CNU.LastName, CNU.FirstName, CNU.MiddleInitial,
        CNU.Gender, CNU.Tier, CNU.DOB, CNU.AddressLine1, CNU.AddressLine2, CNU.PostalCode, CNU.City,
        CNU.StateProv, CNU.Country, CNU.Phone1, CNU.Phone2, CNU.Phone3, CNU.Email1, CNU.Email2,
        CNU.NationalTaxRateDesc, CNU.NationalTaxRate, CNU.LocalTaxRateDesc, CNU.LocalTaxRate,
        CNU.AgencyID, CNU.CreditRating, CNU.NetWorth, CNU.MarketingNameplate, CI.ActionTS, 'INACT' AS ActionType
    FROM CustomersNewAndUpd CNU
        INNER JOIN CustomersInactive CI ON CNU.CustomerID = CI.C_ID
        INNER JOIN (
            SELECT CustomerID, MAX(ActionTS) AS ActionTSLatestCustomer
            FROM CustomersNewAndUpd GROUP BY CustomerID
        ) LC ON CNU.CustomerID = LC.CustomerID AND CNU.ActionTS = LC.ActionTSLatestCustomer
)
INSERT INTO DimCustomer (SK_CustomerID, CustomerID, TaxID, Status, LastName, FirstName, MiddleInitial, Gender, Tier, DOB, AddressLine1, AddressLine2, PostalCode, City, StateProv, Country, Phone1, Phone2, Phone3, Email1, Email2, NationalTaxRateDesc, NationalTaxRate, LocalTaxRateDesc, LocalTaxRate, AgencyID, CreditRating, NetWorth, MarketingNameplate, IsCurrent, BatchID, EffectiveDate, EndDate)
SELECT
    ROW_NUMBER() OVER (ORDER BY CustomerID, ActionTS ASC) AS SK_CustomerID,
    CustomerID, TaxID, Status, LastName, FirstName, MiddleInitial, Gender, Tier, DOB,
    AddressLine1, AddressLine2, PostalCode, City, StateProv, Country, Phone1, Phone2, Phone3,
    Email1, Email2, NationalTaxRateDesc, NationalTaxRate, LocalTaxRateDesc, LocalTaxRate,
    AgencyID, CreditRating, NetWorth, MarketingNameplate,
    CASE WHEN LEAD(ActionTS) OVER (PARTITION BY CustomerID ORDER BY ActionTS ASC) IS NULL THEN true ELSE false END AS IsCurrent,
    1 AS BatchID,
    ActionTS AS EffectiveDate,
    COALESCE(LEAD(ActionTS) OVER (PARTITION BY CustomerID ORDER BY ActionTS ASC), TIMESTAMP '9999-12-31 00:00:00') AS EndDate
FROM CustomersFinal
ORDER BY CustomerID, ActionTS ASC;

-- ================= DimAccount =================
WITH Accounts AS (
    SELECT Acc.CA_ID AS AccountID
        , Br.SK_BrokerID AS SK_BrokerID
        , DimC.SK_CustomerID AS SK_CustomerID
        , Acc.Customer_Id AS Customer_Id
        , Acc.CA_NAME AS AccountDesc
        , TRY_CAST(Acc.CA_TAX_ST AS INTEGER) AS TaxStatus
        , Act.ActionType AS ActionType
        , TRY_CAST(Act.ActionTS AS TIMESTAMP) AS ActionTS
    FROM Source.CustomerXML C
        INNER JOIN Source.ActionXML Act ON C.Action_Id = Act.Action_Id
        INNER JOIN Source.AccountXML Acc ON C.Customer_Id = Acc.Customer_Id
        INNER JOIN DimBroker Br ON TRY_CAST(Acc.CA_B_ID AS INTEGER) = Br.BrokerID
        INNER JOIN DimCustomer DimC ON C.C_ID = DimC.CustomerID
    WHERE TRY_CAST(Act.ActionTS AS TIMESTAMP) >= DimC.EffectiveDate
      AND TRY_CAST(Act.ActionTS AS TIMESTAMP) <= DimC.EndDate
)
, AccountsNewAndAddAcct AS (
    SELECT *, 'ACTIVE' AS Status
    FROM Accounts
    WHERE ActionType IN ('NEW', 'ADDACCT')
)
, AccountsUpd AS (
    SELECT * FROM Accounts WHERE ActionType = 'UPDACCT'
)
, AccountsCloseAcct AS (
    SELECT Acc.CA_ID AS AccountID, TRY_CAST(Act.ActionTS AS TIMESTAMP) AS ActionTS
    FROM Source.AccountXML Acc
        INNER JOIN Source.CustomerXML C ON C.Customer_Id = Acc.Customer_Id
        INNER JOIN Source.ActionXML Act ON C.Action_Id = Act.Action_Id
    WHERE Act.ActionType = 'CLOSEACCT'
)
, AccountsNewAndAddAcctAndUpd AS (
    SELECT AccountID, SK_BrokerID, SK_CustomerID, 'ACTIVE' AS Status, AccountDesc, TaxStatus, ActionTS, ActionType
    FROM AccountsNewAndAddAcct
    UNION ALL
    SELECT UpdAcct.AccountID
        , COALESCE(UpdAcct.SK_BrokerID, NewAcct.SK_BrokerID) AS SK_BrokerID
        , COALESCE(UpdAcct.SK_CustomerID, NewAcct.SK_CustomerID) AS SK_CustomerID
        , NewAcct.Status AS Status
        , COALESCE(UpdAcct.AccountDesc, NewAcct.AccountDesc) AS AccountDesc
        , COALESCE(UpdAcct.TaxStatus, NewAcct.TaxStatus) AS TaxStatus
        , UpdAcct.ActionTS
        , UpdAcct.ActionType
    FROM AccountsNewAndAddAcct NewAcct
        INNER JOIN AccountsUpd UpdAcct ON NewAcct.AccountID = UpdAcct.AccountID
)
, AccountsFinal AS (
    SELECT * FROM AccountsNewAndAddAcctAndUpd
    UNION ALL
    SELECT AcctNewUpd.AccountID, SK_BrokerID, SK_CustomerID, 'INACTIVE' AS Status, AccountDesc, TaxStatus,
        AcctNewUpd.ActionTS, 'CLOSEACCT' AS ActionType
    FROM AccountsNewAndAddAcctAndUpd AcctNewUpd
        INNER JOIN AccountsCloseAcct AcctClose ON AcctNewUpd.AccountID = AcctClose.AccountID
        INNER JOIN (
            SELECT AccountID, MAX(ActionTS) AS ActionTSLatestAccount
            FROM AccountsNewAndAddAcctAndUpd GROUP BY AccountID
        ) LastAcct ON AcctNewUpd.AccountID = LastAcct.AccountID AND AcctNewUpd.ActionTS = LastAcct.ActionTSLatestAccount
)
INSERT INTO DimAccount (SK_AccountID, AccountID, SK_BrokerID, SK_CustomerID, Status, AccountDesc, TaxStatus, IsCurrent, BatchID, EffectiveDate, EndDate)
SELECT
    ROW_NUMBER() OVER (ORDER BY AccountID, ActionTS ASC) AS SK_AccountID,
    AccountID, SK_BrokerID, SK_CustomerID, Status, AccountDesc, TaxStatus,
    CASE WHEN LEAD(ActionTS) OVER (PARTITION BY AccountID ORDER BY ActionTS ASC) IS NULL THEN true ELSE false END AS IsCurrent,
    1 AS BatchID,
    ActionTS AS EffectiveDate,
    COALESCE(LEAD(ActionTS) OVER (PARTITION BY AccountID ORDER BY ActionTS ASC), TIMESTAMP '9999-12-31 00:00:00') AS EndDate
FROM AccountsFinal
ORDER BY AccountID, ActionTS ASC;

-- ================= DimSecurity =================
-- Original has a TODO acknowledging the varchar-based CIK/Name join is fragile -- preserved as-is.
WITH SecurityFinal AS (
    SELECT F.Symbol AS Symbol
        , F.IssueType AS Issue
        , ST.ST_NAME AS Status
        , F.Name AS Name
        , F.ExID AS ExchangeID
        , DimCo.SK_CompanyID AS SK_CompanyID
        , TRY_CAST(F.ShOut AS INTEGER) AS SharesOutstanding
        , try_strptime(F.FirstTradeDate, '%Y%m%d')::DATE AS FirstTrade
        , try_strptime(F.FirstTradeExchg, '%Y%m%d')::DATE AS FirstTradeOnExchange
        , TRY_CAST(F.Dividend AS NUMERIC) AS Dividend
        , strptime(F.PTS, '%Y%m%d-%H%M%S') AS EffectiveDate
    FROM Source.FinwireSEC F
    INNER JOIN DimCompany DimCo
        ON (CASE
            WHEN TRY_CAST(F.CoNameOrCIK AS BIGINT) IS NOT NULL THEN CAST(DimCo.CompanyID AS VARCHAR)
            ELSE DimCo.Name
        END) = F.CoNameOrCIK
    INNER JOIN StatusType ST ON F.Status = ST.ST_ID
    WHERE F.RecType = 'SEC'
      AND strptime(F.PTS, '%Y%m%d-%H%M%S') >= DimCo.EffectiveDate
      AND strptime(F.PTS, '%Y%m%d-%H%M%S') < DimCo.EndDate
)
INSERT INTO DimSecurity(SK_SecurityID, Symbol, Issue, Status, Name, ExchangeID, SK_CompanyID, SharesOutstanding, FirstTrade, FirstTradeOnExchange, Dividend, IsCurrent, BatchID, EffectiveDate, EndDate)
SELECT
    ROW_NUMBER() OVER (ORDER BY Symbol, EffectiveDate) AS SK_SecurityID,
    Symbol, Issue, Status, Name, ExchangeID, SK_CompanyID, SharesOutstanding, FirstTrade, FirstTradeOnExchange, Dividend,
    CASE WHEN LEAD(EffectiveDate) OVER (PARTITION BY Symbol ORDER BY EffectiveDate ASC) IS NULL THEN true ELSE false END AS IsCurrent,
    1 AS BatchID,
    EffectiveDate,
    COALESCE(LEAD(EffectiveDate) OVER (PARTITION BY Symbol ORDER BY EffectiveDate ASC), TIMESTAMP '9999-12-31 00:00:00') AS EndDate
FROM SecurityFinal
ORDER BY Symbol, EffectiveDate;

-- ================= DimTrade =================
-- NOT RELIABLE: SK_BrokerID/SK_SecurityID/SK_CompanyID/SK_CustomerID/SK_AccountID are hardcoded
-- to literal 1 in the original (author's own "-- FIX SK" comments) -- preserved faithfully, not
-- fixed, per the gold-standard-fidelity rule. See tpcdi_column_mapping.csv (rule_reliable=no).
WITH DimTradeStaging AS (
    SELECT T.T_ID AS TradeID
        , 1 AS SK_BrokerID
        -- ADDED (not in R1's original): COALESCE(...) fallback to TH_DTS. R1's own CASE is
        -- non-exhaustive -- it never matches 'SBMT' rows whose T_TT_ID is NOT IN ('TMB','TMS')
        -- (i.e. TSL/TLS/TLB), leaving SK_CreateDateID/TimeID NULL, which violates the target's
        -- NOT NULL constraint. Confirmed via Source.TradeHistory: all 4 real TH_ST_ID values
        -- (SBMT/CNCL/PNDG/CMPT) occur, so the gap is genuinely in the branch logic, not absent
        -- data -- almost certainly why R1's README excludes "part of DimTrade" from the
        -- benchmark. Flagged rule_reliable=no in tpcdi_column_mapping.csv.
        , COALESCE(CASE
            WHEN (TH.TH_ST_ID = 'SBMT' AND T.T_TT_ID IN ('TMB', 'TMS')) OR TH.TH_ST_ID = 'PNDG' THEN TH.TH_DTS
            WHEN TH.TH_ST_ID IN ('CMPT', 'CNCL') THEN NULL
        END, TH.TH_DTS) AS SK_CreateDateID
        , COALESCE(CASE
            WHEN (TH.TH_ST_ID = 'SBMT' AND T.T_TT_ID IN ('TMB', 'TMS')) OR TH.TH_ST_ID = 'PNDG' THEN TH.TH_DTS
            WHEN TH.TH_ST_ID IN ('CMPT', 'CNCL') THEN NULL
        END, TH.TH_DTS) AS SK_CreateTimeID
        , CASE
            WHEN (TH.TH_ST_ID = 'SBMT' AND T.T_TT_ID IN ('TMB', 'TMS')) OR TH.TH_ST_ID = 'PNDG' THEN NULL
            WHEN TH.TH_ST_ID IN ('CMPT', 'CNCL') THEN TH.TH_DTS
        END AS SK_CloseDateID
        , CASE
            WHEN (TH.TH_ST_ID = 'SBMT' AND T.T_TT_ID IN ('TMB', 'TMS')) OR TH.TH_ST_ID = 'PNDG' THEN NULL
            WHEN TH.TH_ST_ID IN ('CMPT', 'CNCL') THEN TH.TH_DTS
        END AS SK_CloseTimeID
        , ST.ST_NAME AS Status
        , TT.TT_NAME AS DT_Type
        , CASE WHEN UPPER(T.T_IS_CASH) = 'TRUE' THEN true ELSE false END AS CashFlag
        , 1 AS SK_SecurityID
        , 1 AS SK_CompanyID
        , T.T_QTY AS Quantity
        , T.T_BID_PRICE AS BidPrice
        , 1 AS SK_CustomerID
        , 1 AS SK_AccountID
        , T.T_EXEC_NAME AS ExecutedBy
        , T.T_TRADE_PRICE AS TradePrice
        , T.T_CHRG AS Fee
        , T.T_COMM AS Commission
        , T.T_TAX AS Tax
        , 1 AS BatchID
    FROM Source.Trade T
        INNER JOIN Source.TradeHistory TH ON T.T_ID = TH.TH_T_ID
        INNER JOIN Source.StatusType ST ON T.T_ST_ID = ST.ST_ID
        INNER JOIN Source.TradeType TT ON T.T_TT_ID = TT.TT_ID
)
INSERT INTO DimTrade (TradeID, SK_BrokerID, SK_CreateDateID, SK_CreateTimeID, SK_CloseDateID, SK_CloseTimeID, Status, DT_Type, CashFlag, SK_SecurityID, SK_CompanyID, Quantity, BidPrice, SK_CustomerID, SK_AccountID, ExecutedBy, TradePrice, Fee, Commission, Tax, BatchID)
SELECT TradeID
    , SK_BrokerID
    , (SELECT SK_DateID FROM DimDate WHERE DateValue = CAST(SK_CreateDateID AS DATE)) AS SK_CreateDateID
    , (SELECT SK_TimeID FROM DimTime WHERE TimeValue = CAST(SK_CreateTimeID AS TIME)) AS SK_CreateTimeID
    , (SELECT SK_DateID FROM DimDate WHERE DateValue = CAST(SK_CloseDateID AS DATE)) AS SK_CloseDateID
    , (SELECT SK_TimeID FROM DimTime WHERE TimeValue = CAST(SK_CloseTimeID AS TIME)) AS SK_CloseTimeID
    , Status, DT_Type, CashFlag, SK_SecurityID, SK_CompanyID, Quantity, BidPrice, SK_CustomerID, SK_AccountID,
    ExecutedBy, TradePrice, Fee, Commission, Tax, BatchID
FROM DimTradeStaging;

-- ================= FactCashBalances =================
-- Original has a TODO: this is a daily net-amount aggregate, not a running balance carried
-- forward from a prior day -- preserved as-is (flagged in tpcdi_column_mapping.csv).
INSERT INTO FactCashBalances(SK_CustomerID, SK_AccountID, SK_DateID, BatchID, Cash)
SELECT
    DA.SK_CustomerID AS SK_CustomerID,
    DA.SK_AccountID AS SK_AccountID,
    DD.SK_DateID AS SK_DateID,
    1 AS BatchID,
    SUM(CT_AMT) AS Cash
FROM Source.CashTransaction CT, DimAccount DA, DimDate DD
WHERE CT.CT_CA_ID = DA.AccountID
    AND CAST(CT_DTS AS DATE) BETWEEN DA.EffectiveDate AND DA.EndDate
    AND CAST(CT_DTS AS DATE) = DD.DateValue
GROUP BY DA.SK_CustomerID, DA.SK_AccountID, DD.SK_DateID, CAST(CT_DTS AS DATE);

-- ================= FactHoldings =================
-- Original flags its own uncertainty about which field should represent CurrentPrice
-- (TradePrice used, "not explicit in TPC-DI spec") -- preserved as-is.
INSERT INTO FactHoldings(SK_CustomerID, SK_AccountID, SK_SecurityID, SK_CompanyID, CurrentPrice, SK_DateID, SK_TimeID, TradeID, CurrentTradeID, CurrentHolding, BatchID)
SELECT
    DT.SK_CustomerID,
    DT.SK_AccountID,
    DT.SK_SecurityID,
    DT.SK_CompanyID,
    TRY_CAST(DT.TradePrice AS INTEGER) AS CurrentPrice,
    -- ADDED (not in R1's original): COALESCE fallback to SK_Create*ID. R1's join picks up
    -- DimTrade rows regardless of trade state, so HoldingHistory can match a still-open
    -- (SBMT/PNDG) DimTrade row whose SK_CloseDateID/TimeID is legitimately NULL, violating
    -- FactHoldings' NOT NULL constraint -- same root cause as the DimTrade fallback above.
    COALESCE(DT.SK_CloseDateID, DT.SK_CreateDateID) AS SK_DateID,
    COALESCE(DT.SK_CloseTimeID, DT.SK_CreateTimeID) AS SK_TimeID,
    HH.HH_H_T_ID AS TradeID,
    HH.HH_T_ID AS CurrentTradeID,
    HH.HH_AFTER_QTY AS CurrentHolding,
    1 AS BatchID
FROM Source.HoldingHistory HH, DimTrade DT
WHERE HH.HH_T_ID = DT.TradeID;

-- ================= Financial =================
INSERT INTO Financial (SK_CompanyID, FI_YEAR, FI_QTR, FI_QTR_START_DATE, FI_REVENUE, FI_NET_EARN, FI_BASIC_EPS, FI_DILUT_EPS, FI_MARGIN, FI_INVENTORY, FI_ASSETS, FI_LIABILITY, FI_OUT_BASIC, FI_OUT_DILUT)
SELECT (
        SELECT DC.SK_CompanyID
        FROM DimCompany DC
        WHERE (DS.CIK = DC.CompanyID OR DS.CoName = DC.Name)
          AND DC.IsCurrent = true
        LIMIT 1
    ) AS SK_CompanyID
    , FI_YEAR, FI_QTR, FI_QTR_START_DATE, FI_REVENUE, FI_NET_EARN, FI_BASIC_EPS, FI_DILUT_EPS, FI_MARGIN,
    FI_INVENTORY, FI_ASSETS, FI_LIABILITY, FI_OUT_BASIC, FI_OUT_DILUT
FROM (
    SELECT strptime(PTS, '%Y%m%d-%H%M%S') AS PTS
        , CASE WHEN TRY_CAST(CoNameOrCIK AS BIGINT) IS NOT NULL THEN TRY_CAST(CoNameOrCIK AS INTEGER) END AS CIK
        , CASE WHEN TRY_CAST(CoNameOrCIK AS BIGINT) IS NULL THEN CoNameOrCIK END AS CoName
        , TRY_CAST(Year AS INTEGER) AS FI_YEAR
        , TRY_CAST(Quarter AS INTEGER) AS FI_QTR
        , try_strptime(QtrStartDate, '%Y%m%d')::DATE AS FI_QTR_START_DATE
        , TRY_CAST(Revenue AS NUMERIC) AS FI_REVENUE
        , TRY_CAST(Earnings AS NUMERIC) AS FI_NET_EARN
        , TRY_CAST(EPS AS NUMERIC) AS FI_BASIC_EPS
        , TRY_CAST(DilutedEPS AS NUMERIC) AS FI_DILUT_EPS
        , TRY_CAST(Margin AS NUMERIC) AS FI_MARGIN
        , TRY_CAST(Inventory AS NUMERIC) AS FI_INVENTORY
        , TRY_CAST(Assets AS NUMERIC) AS FI_ASSETS
        , TRY_CAST(Liabilities AS NUMERIC) AS FI_LIABILITY
        , TRY_CAST(ShOut AS NUMERIC) AS FI_OUT_BASIC
        , TRY_CAST(DilutedShOut AS NUMERIC) AS FI_OUT_DILUT
    FROM Source.FinwireFIN F
) AS DS;

-- ================= Prospect =================
-- Original type mismatch preserved: IsCustomer is declared BOOLEAN in the target schema but the
-- source query computes a COUNT(*) -- cast to boolean here (0 -> false, >0 -> true) rather than
-- silently truncating, closest faithful behavior; flagged in tpcdi_column_mapping.csv as a bug.
INSERT INTO Prospect (AgencyID, SK_RecordDateID, SK_UpdateDateID, BatchID, IsCustomer, LastName, FirstName, MiddleInitial, Gender, AddressLine1, AddressLine2, PostalCode, City, State, Country, Phone, Income, numberCars, numberChildren, MaritalStatus, Age, CreditRating, OwnOrRentFlag, Employer, numberCreditCards, NetWorth, MarketingNameplate)
SELECT AgencyID
    , (SELECT SK_DateID FROM DimDate WHERE DateValue = (SELECT BatchDate FROM Source.BatchDate)) AS SK_RecordDateID
    , (SELECT SK_DateID FROM DimDate WHERE DateValue = (SELECT BatchDate FROM Source.BatchDate)) AS SK_UpdateDateID
    , 1 AS BatchID
    , (
        SELECT COUNT(*) > 0
        FROM DimCustomer DC
        WHERE UPPER(DC.FirstName) = UPPER(P.FirstName)
            AND UPPER(DC.LastName) = UPPER(P.LastName)
            AND UPPER(DC.AddressLine1) = UPPER(P.AddressLine1)
            AND UPPER(DC.AddressLine2) = UPPER(P.AddressLine2)
            AND UPPER(DC.PostalCode) = UPPER(P.PostalCode)
            AND DC.Status = 'ACTIVE'
    ) AS IsCustomer
    , LastName, FirstName, MiddleInitial, Gender, AddressLine1, AddressLine2, PostalCode, City, State, Country,
    Phone, Income, numberCars, numberChildren, MaritalStatus, Age, CreditRating, OwnOrRentFlag, Employer,
    numberCreditCards, NetWorth
    , CASE
        WHEN NetWorth > 1000000 OR Income > 200000 THEN 'HighValue'
        WHEN NumberChildren > 3 OR NumberCreditCards > 5 THEN 'Expenses'
        WHEN Age > 45 THEN 'Boomer'
        WHEN Income < 50000 OR CreditRating < 600 OR NetWorth < 100000 THEN 'MoneyAlert'
        WHEN NumberCars > 3 OR NumberCreditCards > 7 THEN 'Spender'
        WHEN Age < 25 AND NetWorth > 1000000 THEN 'Inherited'
    END AS MarketingNameplate
FROM Source.Prospect P;
