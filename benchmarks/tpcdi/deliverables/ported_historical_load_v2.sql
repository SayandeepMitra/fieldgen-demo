-- REPAIRED GOLD (v2). Derived from ported_historical_load.sql (v1, R1's historical_load.sql ported to DuckDB).
-- v1 reproduced R1's ETL faithfully, including its defects (see gold_audit_findings.csv: 17 failed official-audit checks plus
-- defects the audit does not test). v2 repairs them against the TPC-DI v1.1.0 specification (Clauses 4.4, 4.5) and the official
-- audit script. Every repaired statement carries a "REPAIRED (v2)" comment naming the clause and the defect it fixes.
-- Unchanged from v1: DimDate, DimTime, StatusType, TaxRate, TradeType, Industry, DimBroker.
-- See deliverables/GOLD_V2_CHANGES.md for the full change log and the before/after audit.
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
-- REPAIRED (v2): spec 4.5.3.2/4.5.3.3. Invalid S&P ratings -> SPrating and isLowGrade NULL (F03); all-blank text -> NULL.
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
        CASE WHEN TRIM(CMP.CompanyName) = '' THEN NULL ELSE CMP.CompanyName END AS Name,
        CASE WHEN CMP.SPrating IN ('AAA','AA','A','BBB','BB','B','CCC','CC','C','D','AA+','A+','BBB+','BB+','B+','CCC+','AA-','A-','BBB-','BB-','B-','CCC-')
             THEN CMP.SPrating END AS SPrating,
        CASE WHEN TRIM(CMP.CEOname) = '' THEN NULL ELSE CMP.CEOname END AS CEO,
        CASE WHEN TRIM(CMP.Description) = '' THEN NULL ELSE CMP.Description END AS Description,
        try_strptime(FoundingDate, '%Y%m%d')::DATE AS FoundingDate,
        CASE WHEN TRIM(CMP.AddrLine1) = '' THEN NULL ELSE CMP.AddrLine1 END AS AddressLine1,
        CASE WHEN TRIM(CMP.AddrLine2) = '' THEN NULL ELSE CMP.AddrLine2 END AS AddressLine2,
        CASE WHEN TRIM(CMP.PostalCode) = '' THEN NULL ELSE CMP.PostalCode END AS PostalCode,
        CASE WHEN TRIM(CMP.City) = '' THEN NULL ELSE CMP.City END AS City,
        CASE WHEN TRIM(CMP.StateProvince) = '' THEN NULL ELSE CMP.StateProvince END AS StateProv,
        CASE WHEN TRIM(CMP.Country) = '' THEN NULL ELSE CMP.Country END AS Country,
        S.ST_NAME AS Status,
        I.IN_NAME AS Industry,
        CASE WHEN CMP.SPrating IN ('AAA','AA','A','BBB','BB','B','CCC','CC','C','D','AA+','A+','BBB+','BB+','B+','CCC+','AA-','A-','BBB-','BB-','B-','CCC-')
             THEN (CASE WHEN CMP.SPrating LIKE 'A%' OR CMP.SPrating LIKE 'BBB%' THEN false ELSE true END) END AS isLowGrade,
        strptime(PTS, '%Y%m%d-%H%M%S')::DATE AS EffectiveDate
    FROM Source.FinwireCMP CMP, Source.StatusType S, Source.Industry I
    WHERE CMP.Status = S.ST_ID
      AND CMP.IndustryID = I.IN_ID
) AS c;

-- ================= DimCustomer =================
-- REPAIRED (v2), spec 4.5.4 + 4.4.1: (a) Status 'Active'/'Inactive' (F02); (b) Gender is upper-cased BEFORE the M/F test
-- (v1 compared lower-case literals, turning every upper-case M/F into 'U'); (c) every UPDCUST/INACT version inherits the
-- fields of the CURRENT record (forward fill), v1 only inherited from the NEW record; (d) at most one version per customer
-- per day, latest wins (4.4.1.5); (e) AgencyID/CreditRating/NetWorth/MarketingNameplate come from the matching Prospect
-- record for the LATEST version only, NULL on earlier ones (4.5.4.3, F08); (f) MarketingNameplate = the tag rule of 4.5.15 (F07).
WITH Customers_Preproc AS (
    SELECT CXML.C_ID AS CustomerID
        , TRIM(CXML.C_TAX_ID) AS TaxID
        , CXML.C_GNDR AS GenderRaw
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
        , AXML.ActionType
        , TRY_CAST(AXML.ActionTS AS TIMESTAMP) AS ActionTS
        , TRY_CAST(AXML.Action_Id AS BIGINT) AS ActionSeq
    FROM Source.CustomerXML CXML
        INNER JOIN Source.ActionXML AXML ON CXML.Action_Id = AXML.Action_Id
        LEFT JOIN Source.NameXML NXML ON CXML.Customer_Id = NXML.Customer_Id
        LEFT JOIN Source.ContactInfoXML CCIN ON CXML.Customer_Id = CCIN.Customer_Id
        LEFT JOIN Source.AddressXML ADXML ON CXML.Customer_Id = ADXML.Customer_Id
        LEFT JOIN Source.TaxInfoXML TXML ON CXML.Customer_Id = TXML.Customer_Id
        LEFT JOIN Source.TaxRate TR ON TXML.C_NAT_TX_ID = TR.TX_ID
        LEFT JOIN Source.TaxRate TR2 ON TXML.C_LCL_TX_ID = TR2.TX_ID
        LEFT JOIN Source.C_PHONE_1_XML CP1XML ON CCIN.ContactInfo_Id = CP1XML.ContactInfo_Id
        LEFT JOIN Source.C_PHONE_2_XML CP2XML ON CCIN.ContactInfo_Id = CP2XML.ContactInfo_Id
        LEFT JOIN Source.C_PHONE_3_XML CP3XML ON CCIN.ContactInfo_Id = CP3XML.ContactInfo_Id
    WHERE AXML.ActionType IN ('NEW', 'UPDCUST', 'INACT')
)
, CustomerEvents AS (
    SELECT *
        , CASE WHEN C_EXT1 IS NOT NULL THEN Phone1_V1 || C_EXT1 ELSE Phone1_V1 END AS Phone1
        , CASE WHEN C_EXT2 IS NOT NULL THEN Phone2_V1 || C_EXT2 ELSE Phone2_V1 END AS Phone2
        , CASE WHEN C_EXT3 IS NOT NULL THEN Phone3_V1 || C_EXT3 ELSE Phone3_V1 END AS Phone3
    FROM Customers_Preproc
)
, CustomersFilled AS (
    SELECT CustomerID, ActionTS, ActionSeq, ActionType
        , LAST_VALUE(TaxID IGNORE NULLS) OVER w AS TaxID
        , LAST_VALUE(GenderRaw IGNORE NULLS) OVER w AS GenderRaw
        , LAST_VALUE(Tier IGNORE NULLS) OVER w AS Tier
        , LAST_VALUE(DOB IGNORE NULLS) OVER w AS DOB
        , LAST_VALUE(Email1 IGNORE NULLS) OVER w AS Email1
        , LAST_VALUE(Email2 IGNORE NULLS) OVER w AS Email2
        , LAST_VALUE(FirstName IGNORE NULLS) OVER w AS FirstName
        , LAST_VALUE(MiddleInitial IGNORE NULLS) OVER w AS MiddleInitial
        , LAST_VALUE(LastName IGNORE NULLS) OVER w AS LastName
        , LAST_VALUE(AddressLine1 IGNORE NULLS) OVER w AS AddressLine1
        , LAST_VALUE(AddressLine2 IGNORE NULLS) OVER w AS AddressLine2
        , LAST_VALUE(PostalCode IGNORE NULLS) OVER w AS PostalCode
        , LAST_VALUE(City IGNORE NULLS) OVER w AS City
        , LAST_VALUE(StateProv IGNORE NULLS) OVER w AS StateProv
        , LAST_VALUE(Country IGNORE NULLS) OVER w AS Country
        , LAST_VALUE(Phone1 IGNORE NULLS) OVER w AS Phone1
        , LAST_VALUE(Phone2 IGNORE NULLS) OVER w AS Phone2
        , LAST_VALUE(Phone3 IGNORE NULLS) OVER w AS Phone3
        , LAST_VALUE(NationalTaxRateDesc IGNORE NULLS) OVER w AS NationalTaxRateDesc
        , LAST_VALUE(NationalTaxRate IGNORE NULLS) OVER w AS NationalTaxRate
        , LAST_VALUE(LocalTaxRateDesc IGNORE NULLS) OVER w AS LocalTaxRateDesc
        , LAST_VALUE(LocalTaxRate IGNORE NULLS) OVER w AS LocalTaxRate
        , MAX(CASE WHEN ActionType = 'INACT' THEN 1 ELSE 0 END) OVER w AS WasInactivated
    FROM CustomerEvents
    WINDOW w AS (PARTITION BY CustomerID ORDER BY ActionTS, ActionSeq ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
)
, CustomersDaily AS (
    SELECT * FROM CustomersFilled
    QUALIFY ROW_NUMBER() OVER (PARTITION BY CustomerID, CAST(ActionTS AS DATE) ORDER BY ActionTS DESC, ActionSeq DESC) = 1
)
, CustomerVersions AS (
    SELECT *
        , CAST(ActionTS AS DATE) AS EffectiveDate
        , COALESCE(LEAD(CAST(ActionTS AS DATE)) OVER (PARTITION BY CustomerID ORDER BY ActionTS ASC), DATE '9999-12-31') AS EndDate
        , (LEAD(ActionTS) OVER (PARTITION BY CustomerID ORDER BY ActionTS ASC) IS NULL) AS IsLatest
    FROM CustomersDaily
)
INSERT INTO DimCustomer (SK_CustomerID, CustomerID, TaxID, Status, LastName, FirstName, MiddleInitial, Gender, Tier, DOB, AddressLine1, AddressLine2, PostalCode, City, StateProv, Country, Phone1, Phone2, Phone3, Email1, Email2, NationalTaxRateDesc, NationalTaxRate, LocalTaxRateDesc, LocalTaxRate, AgencyID, CreditRating, NetWorth, MarketingNameplate, IsCurrent, BatchID, EffectiveDate, EndDate)
SELECT
    ROW_NUMBER() OVER (ORDER BY V.CustomerID, V.EffectiveDate) AS SK_CustomerID,
    V.CustomerID, V.TaxID,
    CASE WHEN V.WasInactivated = 1 THEN 'Inactive' ELSE 'Active' END AS Status,
    V.LastName, V.FirstName, V.MiddleInitial,
    CASE WHEN UPPER(TRIM(V.GenderRaw)) IN ('M', 'F') THEN UPPER(TRIM(V.GenderRaw)) ELSE 'U' END AS Gender,
    V.Tier, V.DOB,
    V.AddressLine1, V.AddressLine2, V.PostalCode, V.City, V.StateProv, V.Country, V.Phone1, V.Phone2, V.Phone3,
    V.Email1, V.Email2, V.NationalTaxRateDesc, V.NationalTaxRate, V.LocalTaxRateDesc, V.LocalTaxRate,
    TRIM(P.AgencyID) AS AgencyID,
    P.CreditRating AS CreditRating,
    P.NetWorth AS NetWorth,
    CASE WHEN P.AgencyID IS NULL THEN NULL ELSE NULLIF(CONCAT_WS('+',
        CASE WHEN P.NetWorth > 1000000 OR P.Income > 200000 THEN 'HighValue' END,
        CASE WHEN P.NumberChildren > 3 OR P.NumberCreditCards > 5 THEN 'Expenses' END,
        CASE WHEN P.Age > 45 THEN 'Boomer' END,
        CASE WHEN P.Income < 50000 OR P.CreditRating < 600 OR P.NetWorth < 100000 THEN 'MoneyAlert' END,
        CASE WHEN P.NumberCars > 3 OR P.NumberCreditCards > 7 THEN 'Spender' END,
        CASE WHEN P.Age < 25 AND P.NetWorth > 1000000 THEN 'Inherited' END), '') END AS MarketingNameplate,
    V.IsLatest AS IsCurrent,
    1 AS BatchID,
    V.EffectiveDate,
    V.EndDate
FROM CustomerVersions V
    LEFT JOIN Source.Prospect P
        ON V.IsLatest
        AND UPPER(V.FirstName) = UPPER(TRIM(P.FirstName))
        AND UPPER(V.LastName) = UPPER(TRIM(P.LastName))
        AND UPPER(V.AddressLine1) = UPPER(TRIM(P.AddressLine1))
        AND UPPER(COALESCE(V.AddressLine2, '')) = UPPER(COALESCE(TRIM(P.AddressLine2), ''))
        AND UPPER(V.PostalCode) = UPPER(TRIM(P.PostalCode))
ORDER BY V.CustomerID, V.EffectiveDate;

-- ================= DimAccount =================
-- REPAIRED (v2), spec 4.5.1 + 4.4.1.5/4.4.1.6: one version per account per day (latest wins); a new version whenever the
-- owning customer's DimCustomer record changes (UPDCUST / INACT) with the new SK_CustomerID; accounts of an inactivated
-- customer become Inactive; closed accounts stay Inactive; Status is 'Active'/'Inactive' (F01, F05, F09, F10).
WITH AccountEvents AS (
    SELECT Acc.CA_ID AS AccountID
        , C.C_ID AS CustomerID
        , Act.ActionType
        , TRY_CAST(Act.ActionTS AS TIMESTAMP) AS ActionTS
        , TRY_CAST(Act.Action_Id AS BIGINT) AS ActionSeq
        , TRY_CAST(Acc.CA_B_ID AS BIGINT) AS BrokerID
        , Acc.CA_NAME AS AccountDesc
        , TRY_CAST(Acc.CA_TAX_ST AS INTEGER) AS TaxStatus
    FROM Source.CustomerXML C
        INNER JOIN Source.ActionXML Act ON C.Action_Id = Act.Action_Id
        INNER JOIN Source.AccountXML Acc ON C.Customer_Id = Acc.Customer_Id
    WHERE Act.ActionType IN ('NEW', 'ADDACCT', 'UPDACCT', 'CLOSEACCT')
)
, AccountFirst AS (
    SELECT AccountID, MIN(CustomerID) AS CustomerID, CAST(MIN(ActionTS) AS DATE) AS FirstDay
    FROM AccountEvents GROUP BY AccountID
)
, AccountTimeline AS (
    SELECT AccountID, CustomerID, ActionTS, ActionSeq, ActionType, BrokerID, AccountDesc, TaxStatus
    FROM AccountEvents
    UNION ALL
    SELECT F.AccountID, F.CustomerID
        , CAST(CV.EffectiveDate AS TIMESTAMP) + INTERVAL '23 hours 59 minutes 59 seconds' AS ActionTS
        , 999999999999 AS ActionSeq
        , 'CUSTCHANGE' AS ActionType
        , NULL AS BrokerID, NULL AS AccountDesc, NULL AS TaxStatus
    FROM AccountFirst F
        INNER JOIN DimCustomer CV ON CV.CustomerID = F.CustomerID AND CV.EffectiveDate > F.FirstDay
)
, AccountFilled AS (
    SELECT AccountID, CustomerID, ActionTS, ActionSeq
        , LAST_VALUE(BrokerID IGNORE NULLS) OVER w AS BrokerID
        , LAST_VALUE(AccountDesc IGNORE NULLS) OVER w AS AccountDesc
        , LAST_VALUE(TaxStatus IGNORE NULLS) OVER w AS TaxStatus
        , MAX(CASE WHEN ActionType = 'CLOSEACCT' THEN 1 ELSE 0 END) OVER w AS WasClosed
    FROM AccountTimeline
    WINDOW w AS (PARTITION BY AccountID ORDER BY ActionTS, ActionSeq ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
)
, AccountDaily AS (
    SELECT * FROM AccountFilled
    QUALIFY ROW_NUMBER() OVER (PARTITION BY AccountID, CAST(ActionTS AS DATE) ORDER BY ActionTS DESC, ActionSeq DESC) = 1
)
, AccountVersions AS (
    SELECT D.AccountID, D.AccountDesc, D.TaxStatus, D.WasClosed
        , CAST(D.ActionTS AS DATE) AS EffectiveDate
        , COALESCE(LEAD(CAST(D.ActionTS AS DATE)) OVER (PARTITION BY D.AccountID ORDER BY D.ActionTS ASC), DATE '9999-12-31') AS EndDate
        , Br.SK_BrokerID AS SK_BrokerID
        , Cu.SK_CustomerID AS SK_CustomerID
        , Cu.Status AS CustomerStatus
    FROM AccountDaily D
        LEFT JOIN DimBroker Br ON D.BrokerID = Br.BrokerID
        LEFT JOIN DimCustomer Cu ON Cu.CustomerID = D.CustomerID
            AND Cu.EffectiveDate <= CAST(D.ActionTS AS DATE) AND CAST(D.ActionTS AS DATE) < Cu.EndDate
)
INSERT INTO DimAccount (SK_AccountID, AccountID, SK_BrokerID, SK_CustomerID, Status, AccountDesc, TaxStatus, IsCurrent, BatchID, EffectiveDate, EndDate)
SELECT
    ROW_NUMBER() OVER (ORDER BY AccountID, EffectiveDate ASC) AS SK_AccountID,
    AccountID, SK_BrokerID, SK_CustomerID,
    CASE WHEN WasClosed = 1 OR CustomerStatus = 'Inactive' THEN 'Inactive' ELSE 'Active' END AS Status,
    AccountDesc, TaxStatus,
    CASE WHEN EndDate = DATE '9999-12-31' THEN true ELSE false END AS IsCurrent,
    1 AS BatchID,
    EffectiveDate,
    EndDate
FROM AccountVersions
ORDER BY AccountID, EffectiveDate ASC;

-- ================= DimSecurity =================
-- REPAIRED (v2), spec 4.5.6 + 4.4.1.6.1: SK_CompanyID is found by CIK (numeric CoNameOrCIK, any zero padding) or by company
-- name, valid at PTS (v1 compared '0000000005' with '5' as text and silently dropped every numeric-CIK security: 1,227 of
-- 2,400 rows kept); and a new security version starts whenever the company's DimCompany record changes (F04).
WITH SecurityRecords AS (
    SELECT F.Symbol AS Symbol
        , F.IssueType AS Issue
        , ST.ST_NAME AS Status
        , F.Name AS Name
        , F.ExID AS ExchangeID
        , F.CoNameOrCIK AS CoNameOrCIK
        , TRY_CAST(F.ShOut AS INTEGER) AS SharesOutstanding
        , try_strptime(F.FirstTradeDate, '%Y%m%d')::DATE AS FirstTrade
        , try_strptime(F.FirstTradeExchg, '%Y%m%d')::DATE AS FirstTradeOnExchange
        , TRY_CAST(F.Dividend AS NUMERIC) AS Dividend
        , strptime(F.PTS, '%Y%m%d-%H%M%S') AS EffectiveTS
    FROM Source.FinwireSEC F
    INNER JOIN Source.StatusType ST ON F.Status = ST.ST_ID
    WHERE F.RecType = 'SEC'
)
, SecurityCompany AS (
    SELECT R.*
        , (SELECT DimCo.CompanyID FROM DimCompany DimCo
           WHERE (CASE WHEN TRY_CAST(R.CoNameOrCIK AS BIGINT) IS NOT NULL
                       THEN DimCo.CompanyID = TRY_CAST(R.CoNameOrCIK AS BIGINT)
                       ELSE DimCo.Name = R.CoNameOrCIK END)
             AND DimCo.EffectiveDate <= R.EffectiveTS AND R.EffectiveTS < DimCo.EndDate
           ORDER BY DimCo.EffectiveDate LIMIT 1) AS CompanyID
    FROM SecurityRecords R
)
, SecuritySegments AS (
    -- a SEC record ties the symbol to one company until the symbol's next SEC record (a symbol can be re-issued by another company)
    SELECT Symbol, CompanyID
        , CAST(EffectiveTS AS DATE) AS SegStart
        , LEAD(CAST(EffectiveTS AS DATE)) OVER (PARTITION BY Symbol ORDER BY EffectiveTS) AS SegEnd
    FROM SecurityCompany WHERE CompanyID IS NOT NULL
)
, SecurityTimeline AS (
    SELECT Symbol, CompanyID, EffectiveTS, Issue, Status, Name, ExchangeID, SharesOutstanding, FirstTrade, FirstTradeOnExchange, Dividend
    FROM SecurityCompany WHERE CompanyID IS NOT NULL
    UNION ALL
    SELECT G.Symbol, G.CompanyID
        , CAST(DimCo.EffectiveDate AS TIMESTAMP) + INTERVAL '23 hours 59 minutes 59 seconds' AS EffectiveTS
        , NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    FROM SecuritySegments G
        INNER JOIN DimCompany DimCo ON DimCo.CompanyID = G.CompanyID
            AND DimCo.EffectiveDate > G.SegStart AND (G.SegEnd IS NULL OR DimCo.EffectiveDate < G.SegEnd)
)
, SecurityFilled AS (
    SELECT Symbol, EffectiveTS
        , LAST_VALUE(CompanyID IGNORE NULLS) OVER w AS CompanyID
        , LAST_VALUE(Issue IGNORE NULLS) OVER w AS Issue
        , LAST_VALUE(Status IGNORE NULLS) OVER w AS Status
        , LAST_VALUE(Name IGNORE NULLS) OVER w AS Name
        , LAST_VALUE(ExchangeID IGNORE NULLS) OVER w AS ExchangeID
        , LAST_VALUE(SharesOutstanding IGNORE NULLS) OVER w AS SharesOutstanding
        , LAST_VALUE(FirstTrade IGNORE NULLS) OVER w AS FirstTrade
        , LAST_VALUE(FirstTradeOnExchange IGNORE NULLS) OVER w AS FirstTradeOnExchange
        , LAST_VALUE(Dividend IGNORE NULLS) OVER w AS Dividend
    FROM SecurityTimeline
    WINDOW w AS (PARTITION BY Symbol ORDER BY EffectiveTS ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
)
, SecurityDaily AS (
    SELECT * FROM SecurityFilled
    QUALIFY ROW_NUMBER() OVER (PARTITION BY Symbol, CAST(EffectiveTS AS DATE) ORDER BY EffectiveTS DESC) = 1
)
, SecurityFinal AS (
    SELECT D.Symbol, D.Issue, D.Status, D.Name, D.ExchangeID
        , DimCo.SK_CompanyID AS SK_CompanyID
        , D.SharesOutstanding, D.FirstTrade, D.FirstTradeOnExchange, D.Dividend
        , CAST(D.EffectiveTS AS DATE) AS EffectiveDate
    FROM SecurityDaily D
        LEFT JOIN DimCompany DimCo ON DimCo.CompanyID = D.CompanyID
            AND DimCo.EffectiveDate <= CAST(D.EffectiveTS AS DATE) AND CAST(D.EffectiveTS AS DATE) < DimCo.EndDate
)
INSERT INTO DimSecurity(SK_SecurityID, Symbol, Issue, Status, Name, ExchangeID, SK_CompanyID, SharesOutstanding, FirstTrade, FirstTradeOnExchange, Dividend, IsCurrent, BatchID, EffectiveDate, EndDate)
SELECT
    ROW_NUMBER() OVER (ORDER BY Symbol, EffectiveDate) AS SK_SecurityID,
    Symbol, Issue, Status, Name, ExchangeID, SK_CompanyID, SharesOutstanding, FirstTrade, FirstTradeOnExchange, Dividend,
    CASE WHEN LEAD(EffectiveDate) OVER (PARTITION BY Symbol ORDER BY EffectiveDate ASC) IS NULL THEN true ELSE false END AS IsCurrent,
    1 AS BatchID,
    EffectiveDate,
    COALESCE(LEAD(EffectiveDate) OVER (PARTITION BY Symbol ORDER BY EffectiveDate ASC), DATE '9999-12-31') AS EndDate
FROM SecurityFinal
ORDER BY Symbol, EffectiveDate;

-- ================= DimTrade =================
-- REPAIRED (v2), spec 4.5.8: ONE row per trade (T_ID); v1 produced one row per TradeHistory event (982,180 rows, 390,978 trades)
-- and hardcoded the five surrogate keys to 1 (F11, I01). Create/Close date+time come from the history events (spec 4.5.8.2);
-- Security/Company and Account/Customer/Broker surrogate keys are the dimension versions valid on the day the trade was
-- first seen (earliest history event). Status/Type come from the trade's final state.
WITH TradeEvents AS (
    SELECT TH.TH_T_ID AS TradeID
        , MIN(CASE WHEN TH.TH_ST_ID = 'PNDG' OR (TH.TH_ST_ID = 'SBMT' AND T.T_TT_ID IN ('TMB', 'TMS')) THEN TH.TH_DTS END) AS CreateTS
        , MAX(CASE WHEN TH.TH_ST_ID IN ('CMPT', 'CNCL') THEN TH.TH_DTS END) AS CloseTS
        , MIN(TH.TH_DTS) AS FirstSeenTS
    FROM Source.TradeHistory TH
        INNER JOIN Source.Trade T ON T.T_ID = TH.TH_T_ID
    GROUP BY TH.TH_T_ID
)
, DimTradeStaging AS (
    SELECT T.T_ID AS TradeID
        , DA.SK_BrokerID AS SK_BrokerID
        , E.CreateTS AS CreateTS
        , E.CloseTS AS CloseTS
        , ST.ST_NAME AS Status
        , TT.TT_NAME AS DT_Type
        , CASE WHEN T.T_IS_CASH = '1' THEN true ELSE false END AS CashFlag
        , DS.SK_SecurityID AS SK_SecurityID
        , DS.SK_CompanyID AS SK_CompanyID
        , T.T_QTY AS Quantity
        , T.T_BID_PRICE AS BidPrice
        , DA.SK_CustomerID AS SK_CustomerID
        , DA.SK_AccountID AS SK_AccountID
        , T.T_EXEC_NAME AS ExecutedBy
        , T.T_TRADE_PRICE AS TradePrice
        , T.T_CHRG AS Fee
        , T.T_COMM AS Commission
        , T.T_TAX AS Tax
        , 1 AS BatchID
    FROM Source.Trade T
        INNER JOIN TradeEvents E ON T.T_ID = E.TradeID
        INNER JOIN Source.StatusType ST ON T.T_ST_ID = ST.ST_ID
        INNER JOIN Source.TradeType TT ON T.T_TT_ID = TT.TT_ID
        LEFT JOIN DimAccount DA ON DA.AccountID = T.T_CA_ID
            AND DA.EffectiveDate <= CAST(E.FirstSeenTS AS DATE) AND CAST(E.FirstSeenTS AS DATE) < DA.EndDate
        LEFT JOIN DimSecurity DS ON DS.Symbol = T.T_S_SYMB
            AND DS.EffectiveDate <= CAST(E.FirstSeenTS AS DATE) AND CAST(E.FirstSeenTS AS DATE) < DS.EndDate
)
INSERT INTO DimTrade (TradeID, SK_BrokerID, SK_CreateDateID, SK_CreateTimeID, SK_CloseDateID, SK_CloseTimeID, Status, DT_Type, CashFlag, SK_SecurityID, SK_CompanyID, Quantity, BidPrice, SK_CustomerID, SK_AccountID, ExecutedBy, TradePrice, Fee, Commission, Tax, BatchID)
SELECT TradeID
    , SK_BrokerID
    , (SELECT SK_DateID FROM DimDate WHERE DateValue = CAST(CreateTS AS DATE)) AS SK_CreateDateID
    , (SELECT SK_TimeID FROM DimTime WHERE TimeValue = CAST(date_trunc('second', CreateTS) AS TIME)) AS SK_CreateTimeID
    , (SELECT SK_DateID FROM DimDate WHERE DateValue = CAST(CloseTS AS DATE)) AS SK_CloseDateID
    , (SELECT SK_TimeID FROM DimTime WHERE TimeValue = CAST(date_trunc('second', CloseTS) AS TIME)) AS SK_CloseTimeID
    , Status, DT_Type, CashFlag, SK_SecurityID, SK_CompanyID, Quantity, BidPrice, SK_CustomerID, SK_AccountID,
    ExecutedBy, TradePrice, Fee, Commission, Tax, BatchID
FROM DimTradeStaging;

-- ================= FactCashBalances =================
-- REPAIRED (v2), spec 4.5.9.2: Cash is the RUNNING balance of the account (prior balance + the day's net amount); v1 stored
-- the day's net amount only. The account/customer keys are the DimAccount version valid on the transaction day (half-open
-- [EffectiveDate, EndDate) so a boundary day matches exactly one version).
INSERT INTO FactCashBalances(SK_CustomerID, SK_AccountID, SK_DateID, BatchID, Cash)
SELECT
    DA.SK_CustomerID AS SK_CustomerID,
    DA.SK_AccountID AS SK_AccountID,
    DD.SK_DateID AS SK_DateID,
    1 AS BatchID,
    SUM(SUM(CT.CT_AMT)) OVER (PARTITION BY DA.AccountID ORDER BY CAST(CT.CT_DTS AS DATE) ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS Cash
FROM Source.CashTransaction CT
    INNER JOIN DimAccount DA ON CT.CT_CA_ID = DA.AccountID
        AND DA.EffectiveDate <= CAST(CT.CT_DTS AS DATE) AND CAST(CT.CT_DTS AS DATE) < DA.EndDate
    INNER JOIN DimDate DD ON CAST(CT.CT_DTS AS DATE) = DD.DateValue
GROUP BY DA.AccountID, DA.SK_CustomerID, DA.SK_AccountID, DD.SK_DateID, CAST(CT.CT_DTS AS DATE);

-- ================= FactHoldings =================
-- REPAIRED (v2), spec 4.5.10.2: one row per HoldingHistory record joined to the (now unique) DimTrade row; SK_DateID/SK_TimeID
-- are the trade's CLOSE keys (v1 fell back to the create keys); CurrentPrice keeps its cents (v1 truncated it to INTEGER).
INSERT INTO FactHoldings(SK_CustomerID, SK_AccountID, SK_SecurityID, SK_CompanyID, CurrentPrice, SK_DateID, SK_TimeID, TradeID, CurrentTradeID, CurrentHolding, BatchID)
SELECT
    DT.SK_CustomerID,
    DT.SK_AccountID,
    DT.SK_SecurityID,
    DT.SK_CompanyID,
    DT.TradePrice AS CurrentPrice,
    DT.SK_CloseDateID AS SK_DateID,
    DT.SK_CloseTimeID AS SK_TimeID,
    HH.HH_H_T_ID AS TradeID,
    HH.HH_T_ID AS CurrentTradeID,
    HH.HH_AFTER_QTY AS CurrentHolding,
    1 AS BatchID
FROM Source.HoldingHistory HH
    INNER JOIN DimTrade DT ON HH.HH_T_ID = DT.TradeID;

-- ================= Financial =================
-- REPAIRED (v2), spec 4.5.14.2: SK_CompanyID is the DimCompany version valid at PTS (EffectiveDate <= PTS < EndDate);
-- v1 always took the current version.
INSERT INTO Financial (SK_CompanyID, FI_YEAR, FI_QTR, FI_QTR_START_DATE, FI_REVENUE, FI_NET_EARN, FI_BASIC_EPS, FI_DILUT_EPS, FI_MARGIN, FI_INVENTORY, FI_ASSETS, FI_LIABILITY, FI_OUT_BASIC, FI_OUT_DILUT)
SELECT (
        SELECT DC.SK_CompanyID
        FROM DimCompany DC
        WHERE (CASE WHEN DS.CIK IS NOT NULL THEN DC.CompanyID = DS.CIK ELSE DC.Name = DS.CoName END)
          AND DC.EffectiveDate <= DS.PTS AND DS.PTS < DC.EndDate
        LIMIT 1
    ) AS SK_CompanyID
    , FI_YEAR, FI_QTR, FI_QTR_START_DATE, FI_REVENUE, FI_NET_EARN, FI_BASIC_EPS, FI_DILUT_EPS, FI_MARGIN,
    FI_INVENTORY, FI_ASSETS, FI_LIABILITY, FI_OUT_BASIC, FI_OUT_DILUT
FROM (
    SELECT strptime(PTS, '%Y%m%d-%H%M%S') AS PTS
        , CASE WHEN TRY_CAST(CoNameOrCIK AS BIGINT) IS NOT NULL THEN TRY_CAST(CoNameOrCIK AS BIGINT) END AS CIK
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
-- REPAIRED (v2), spec 4.5.15: MarketingNameplate = the tags of 4.5.15 joined with '+' in the listed order, NULL when none
-- (F07); IsCustomer = matches the CURRENT, Active DimCustomer record (v1 matched any historical version).
INSERT INTO Prospect (AgencyID, SK_RecordDateID, SK_UpdateDateID, BatchID, IsCustomer, LastName, FirstName, MiddleInitial, Gender, AddressLine1, AddressLine2, PostalCode, City, State, Country, Phone, Income, numberCars, numberChildren, MaritalStatus, Age, CreditRating, OwnOrRentFlag, Employer, numberCreditCards, NetWorth, MarketingNameplate)
SELECT AgencyID
    , (SELECT SK_DateID FROM DimDate WHERE DateValue = (SELECT BatchDate FROM Source.BatchDate)) AS SK_RecordDateID
    , (SELECT SK_DateID FROM DimDate WHERE DateValue = (SELECT BatchDate FROM Source.BatchDate)) AS SK_UpdateDateID
    , 1 AS BatchID
    , (
        SELECT COUNT(*) > 0
        FROM DimCustomer DC
        WHERE DC.IsCurrent = true
            AND DC.Status = 'Active'
            AND UPPER(DC.FirstName) = UPPER(TRIM(P.FirstName))
            AND UPPER(DC.LastName) = UPPER(TRIM(P.LastName))
            AND UPPER(DC.AddressLine1) = UPPER(TRIM(P.AddressLine1))
            AND UPPER(COALESCE(DC.AddressLine2, '')) = UPPER(COALESCE(TRIM(P.AddressLine2), ''))
            AND UPPER(DC.PostalCode) = UPPER(TRIM(P.PostalCode))
    ) AS IsCustomer
    , LastName, FirstName, MiddleInitial, Gender, AddressLine1, AddressLine2, PostalCode, City, State, Country,
    Phone, Income, numberCars, numberChildren, MaritalStatus, Age, CreditRating, OwnOrRentFlag, Employer,
    numberCreditCards, NetWorth
    , NULLIF(CONCAT_WS('+',
        CASE WHEN NetWorth > 1000000 OR Income > 200000 THEN 'HighValue' END,
        CASE WHEN NumberChildren > 3 OR NumberCreditCards > 5 THEN 'Expenses' END,
        CASE WHEN Age > 45 THEN 'Boomer' END,
        CASE WHEN Income < 50000 OR CreditRating < 600 OR NetWorth < 100000 THEN 'MoneyAlert' END,
        CASE WHEN NumberCars > 3 OR NumberCreditCards > 7 THEN 'Spender' END,
        CASE WHEN Age < 25 AND NetWorth > 1000000 THEN 'Inherited' END), '') AS MarketingNameplate
FROM Source.Prospect P;
