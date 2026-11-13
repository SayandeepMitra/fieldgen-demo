-- DimCustomer [spec-fixed]: copy of A's preprocessing (phones, names, tax, Gender trim/upper) with changes:
-- Run with the target tables unqualified (current schema) and the source tables as Source.* (made by build_source.py).
--  B1 carry-forward: every field = latest non-NULL over NEW/UPDCUST/INACT events in (ActionTS, ActionType) order
--     (last_value IGNORE NULLS); INACT supplies no values and sets Status INACTIVE (any INACT event).
--  B2 Gender: uppercase; NEW with missing/non M-F -> 'U'; UPDCUST/INACT with missing Gender -> keep previous.
--  B3 AgencyID/CreditRating/NetWorth/MarketingNameplate: Prospect matched on the CURRENT (carried-forward) values
--     with NULLIF(UPPER(TRIM(x)),'') on both sides for LastName/FirstName/AddressLine1/AddressLine2/PostalCode, compared by
--     IS NOT DISTINCT FROM ,
--     NULL when no match; several Prospect matches -> lowest AgencyID.
--  B4 MarketingNameplate: all applicable tags joined by '+' in spec order, NULL if none.
-- Rules (TPC-DI clauses): Gender 4.5.4.3; UPDCUST and INACT handling 4.5.4.3; Prospect match and demographic columns 4.5.4.3;
--   MarketingNameplate tags 4.5.15.1. The wording of the clauses is in the specification (not stored here).
WITH Customers_Preproc AS (
  SELECT
    CXML.C_ID AS CustomerID,
    CXML.C_GNDR AS RawGender,
    TRIM(CXML.C_TAX_ID) AS TaxID,
    TRIM(
      UPPER(
        CASE
          WHEN NOT LOWER(CXML.C_GNDR) IN ('m', 'f') OR CXML.C_GNDR IS NULL
          THEN 'u'
          ELSE CXML.C_GNDR
        END
      )
    ) AS Gender,
    CXML.C_TIER AS Tier,
    CXML.C_DOB AS DOB,
    TRIM(CCIN.C_PRIM_EMAIL) AS Email1,
    TRIM(CCIN.C_ALT_EMAIL) AS Email2,
    TRIM(NXML.C_F_NAME) AS FirstName,
    TRIM(NXML.C_M_NAME) AS MiddleInitial,
    TRIM(NXML.C_L_NAME) AS LastName,
    TRIM(ADXML.C_ADLINE1) AS AddressLine1,
    TRIM(ADXML.C_ADLINE2) AS AddressLine2,
    TRIM(ADXML.C_ZIPCODE) AS PostalCode,
    TRIM(ADXML.C_CITY) AS City,
    TRIM(ADXML.C_STATE_PROV) AS StateProv,
    TRIM(ADXML.C_CTRY) AS Country,
    CASE
      WHEN NOT CP1XML.C_CTRY_CODE IS NULL
      AND NOT CP1XML.C_AREA_CODE IS NULL
      AND NOT CP1XML.C_LOCAL IS NULL
      THEN '+' || CP1XML.C_CTRY_CODE || ' (' || CP1XML.C_AREA_CODE || ') ' || CP1XML.C_LOCAL
      WHEN CP1XML.C_CTRY_CODE IS NULL
      AND (
        NOT CP1XML.C_AREA_CODE IS NULL AND NOT CP1XML.C_LOCAL IS NULL
      )
      THEN '(' || CP1XML.C_AREA_CODE || ') ' || CP1XML.C_LOCAL
      WHEN (
        CP1XML.C_CTRY_CODE IS NULL AND CP1XML.C_AREA_CODE IS NULL
      )
      AND NOT CP1XML.C_LOCAL IS NULL
      THEN CP1XML.C_LOCAL
    END AS Phone1_V1,
    CASE
      WHEN NOT CP2XML.C_CTRY_CODE IS NULL
      AND NOT CP2XML.C_AREA_CODE IS NULL
      AND NOT CP2XML.C_LOCAL IS NULL
      THEN '+' || CP2XML.C_CTRY_CODE || ' (' || CP2XML.C_AREA_CODE || ') ' || CP2XML.C_LOCAL
      WHEN CP2XML.C_CTRY_CODE IS NULL
      AND (
        NOT CP2XML.C_AREA_CODE IS NULL AND NOT CP2XML.C_LOCAL IS NULL
      )
      THEN '(' || CP2XML.C_AREA_CODE || ') ' || CP2XML.C_LOCAL
      WHEN (
        CP2XML.C_CTRY_CODE IS NULL AND CP2XML.C_AREA_CODE IS NULL
      )
      AND NOT CP2XML.C_LOCAL IS NULL
      THEN CP2XML.C_LOCAL
    END AS Phone2_V1,
    CASE
      WHEN NOT CP3XML.C_CTRY_CODE IS NULL
      AND NOT CP3XML.C_AREA_CODE IS NULL
      AND NOT CP3XML.C_LOCAL IS NULL
      THEN '+' || CP3XML.C_CTRY_CODE || ' (' || CP3XML.C_AREA_CODE || ') ' || CP3XML.C_LOCAL
      WHEN CP3XML.C_CTRY_CODE IS NULL
      AND (
        NOT CP3XML.C_AREA_CODE IS NULL AND NOT CP3XML.C_LOCAL IS NULL
      )
      THEN '(' || CP3XML.C_AREA_CODE || ') ' || CP3XML.C_LOCAL
      WHEN (
        CP3XML.C_CTRY_CODE IS NULL AND CP3XML.C_AREA_CODE IS NULL
      )
      AND NOT CP3XML.C_LOCAL IS NULL
      THEN CP3XML.C_LOCAL
    END AS Phone3_V1,
    TRIM(TR.TX_NAME) AS NationalTaxRateDesc,
    TR.TX_RATE AS NationalTaxRate,
    TRIM(TR2.TX_NAME) AS LocalTaxRateDesc,
    TR2.TX_RATE AS LocalTaxRate,
    CP1XML.C_EXT AS C_EXT1,
    CP2XML.C_EXT AS C_EXT2,
    CP3XML.C_EXT AS C_EXT3,
    AXML.ActionType,
    CAST(AXML.ActionTS AS TIMESTAMP) AS ActionTS
  FROM "Source"."CustomerXML" AS CXML
  LEFT JOIN "Source"."ActionXML" AS AXML
    ON CXML.Action_Id = AXML.Action_Id
  LEFT JOIN "Source"."NameXML" AS NXML
    ON CXML.Customer_Id = NXML.Customer_Id
  LEFT JOIN "Source"."ContactInfoXML" AS CCIN
    ON CXML.Customer_Id = CCIN.Customer_Id
  LEFT JOIN "Source"."AddressXML" AS ADXML
    ON CXML.Customer_Id = ADXML.Customer_Id
  LEFT JOIN "Source"."TaxInfoXML" AS TXML
    ON CXML.Customer_Id = TXML.Customer_Id
  LEFT JOIN "Source"."TaxRate" AS TR
    ON TXML.C_NAT_TX_ID = TR.TX_ID
  LEFT JOIN "Source"."TaxRate" AS TR2
    ON TXML.C_LCL_TX_ID = TR2.TX_ID
  LEFT JOIN "Source"."C_PHONE_1_XML" AS CP1XML
    ON CCIN.ContactInfo_Id = CP1XML.ContactInfo_Id
  LEFT JOIN "Source"."C_PHONE_2_XML" AS CP2XML
    ON CCIN.ContactInfo_Id = CP2XML.ContactInfo_Id
  LEFT JOIN "Source"."C_PHONE_3_XML" AS CP3XML
    ON CCIN.ContactInfo_Id = CP3XML.ContactInfo_Id

), Customers AS (
  SELECT
    *,
    CASE WHEN NOT C_EXT1 IS NULL THEN Phone1_V1 || C_EXT1 ELSE Phone1_V1 END AS Phone1,
    CASE WHEN NOT C_EXT2 IS NULL THEN Phone2_V1 || C_EXT2 ELSE Phone2_V1 END AS Phone2,
    CASE WHEN NOT C_EXT3 IS NULL THEN Phone3_V1 || C_EXT3 ELSE Phone3_V1 END AS Phone3
  FROM Customers_Preproc

), Ev AS (
  SELECT CustomerID, ActionTS, ActionType, TaxID,
    LastName,
    FirstName,
    MiddleInitial,
    CASE WHEN ActionType <> 'NEW' AND RawGender IS NULL THEN NULL ELSE Gender END AS Gender,
    Tier,
    DOB,
    AddressLine1,
    AddressLine2,
    PostalCode,
    City,
    StateProv,
    Country,
    Phone1,
    Phone2,
    Phone3,
    Email1,
    Email2,
    NationalTaxRateDesc,
    NationalTaxRate,
    LocalTaxRateDesc,
    LocalTaxRate FROM Customers WHERE ActionType IN ('NEW','UPDCUST','INACT')
), Filled AS (
  SELECT CustomerID, ActionTS, ActionType,
    last_value(TaxID IGNORE NULLS) OVER w AS TaxID,
    last_value(LastName IGNORE NULLS) OVER w AS LastName,
    last_value(FirstName IGNORE NULLS) OVER w AS FirstName,
    last_value(MiddleInitial IGNORE NULLS) OVER w AS MiddleInitial,
    last_value(Gender IGNORE NULLS) OVER w AS Gender,
    last_value(Tier IGNORE NULLS) OVER w AS Tier,
    last_value(DOB IGNORE NULLS) OVER w AS DOB,
    last_value(AddressLine1 IGNORE NULLS) OVER w AS AddressLine1,
    last_value(AddressLine2 IGNORE NULLS) OVER w AS AddressLine2,
    last_value(PostalCode IGNORE NULLS) OVER w AS PostalCode,
    last_value(City IGNORE NULLS) OVER w AS City,
    last_value(StateProv IGNORE NULLS) OVER w AS StateProv,
    last_value(Country IGNORE NULLS) OVER w AS Country,
    last_value(Phone1 IGNORE NULLS) OVER w AS Phone1,
    last_value(Phone2 IGNORE NULLS) OVER w AS Phone2,
    last_value(Phone3 IGNORE NULLS) OVER w AS Phone3,
    last_value(Email1 IGNORE NULLS) OVER w AS Email1,
    last_value(Email2 IGNORE NULLS) OVER w AS Email2,
    last_value(NationalTaxRateDesc IGNORE NULLS) OVER w AS NationalTaxRateDesc,
    last_value(NationalTaxRate IGNORE NULLS) OVER w AS NationalTaxRate,
    last_value(LocalTaxRateDesc IGNORE NULLS) OVER w AS LocalTaxRateDesc,
    last_value(LocalTaxRate IGNORE NULLS) OVER w AS LocalTaxRate,
    bool_or(ActionType = 'INACT') OVER w AS WasInact,
    row_number() OVER (PARTITION BY CustomerID ORDER BY ActionTS DESC, ActionType DESC) AS rn_last
  FROM Ev
  WINDOW w AS (PARTITION BY CustomerID ORDER BY ActionTS, ActionType ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
)
, Cur AS (
  SELECT * FROM Filled WHERE rn_last = 1
), M AS (
  SELECT C.*, P.AgencyID AS P_AgencyID, P.CreditRating AS P_CreditRating, P.NetWorth AS P_NetWorth,
    P.Income, P.NumberChildren, P.NumberCreditCards, P.Age, P.NumberCars,
    row_number() OVER (PARTITION BY C.CustomerID ORDER BY P.AgencyID) AS pn
  FROM Cur AS C
  LEFT JOIN "Source"."Prospect" AS P
    ON NULLIF(UPPER(TRIM(C.LastName)), '') IS NOT DISTINCT FROM NULLIF(UPPER(TRIM(P.LastName)), '')
    AND NULLIF(UPPER(TRIM(C.FirstName)), '') IS NOT DISTINCT FROM NULLIF(UPPER(TRIM(P.FirstName)), '')
    AND NULLIF(UPPER(TRIM(C.AddressLine1)), '') IS NOT DISTINCT FROM NULLIF(UPPER(TRIM(P.AddressLine1)), '')
    AND NULLIF(UPPER(TRIM(C.AddressLine2)), '') IS NOT DISTINCT FROM NULLIF(UPPER(TRIM(P.AddressLine2)), '')
    AND NULLIF(UPPER(TRIM(C.PostalCode)), '') IS NOT DISTINCT FROM NULLIF(UPPER(TRIM(P.PostalCode)), '')
)
INSERT INTO DimCustomer (
  CustomerID,
  TaxID,
  Status,
  LastName,
  FirstName,
  MiddleInitial,
  Gender,
  Tier,
  DOB,
  AddressLine1,
  AddressLine2,
  PostalCode,
  City,
  StateProv,
  Country,
  Phone1,
  Phone2,
  Phone3,
  Email1,
  Email2,
  NationalTaxRateDesc,
  NationalTaxRate,
  LocalTaxRateDesc,
  LocalTaxRate,
  AgencyID,
  CreditRating,
  NetWorth,
  MarketingNameplate
)
SELECT
  CustomerID,
  TaxID,
  CASE WHEN WasInact THEN 'INACTIVE' ELSE 'ACTIVE' END AS Status,
  LastName,
  FirstName,
  MiddleInitial,
  Gender,
  Tier,
  DOB,
  AddressLine1,
  AddressLine2,
  PostalCode,
  City,
  StateProv,
  Country,
  Phone1,
  Phone2,
  Phone3,
  Email1,
  Email2,
  NationalTaxRateDesc,
  NationalTaxRate,
  LocalTaxRateDesc,
  LocalTaxRate,
  TRIM(P_AgencyID) AS AgencyID,
  P_CreditRating AS CreditRating,
  P_NetWorth AS NetWorth,
  NULLIF(concat_ws('+',
      CASE WHEN P_NetWorth > 1000000 OR Income > 200000 THEN 'HighValue' END,
      CASE WHEN NumberChildren > 3 OR NumberCreditCards > 5 THEN 'Expenses' END,
      CASE WHEN Age > 45 THEN 'Boomer' END,
      CASE WHEN Income < 50000 OR P_CreditRating < 600 OR P_NetWorth < 100000 THEN 'MoneyAlert' END,
      CASE WHEN NumberCars > 3 OR NumberCreditCards > 7 THEN 'Spender' END,
      CASE WHEN Age < 25 AND P_NetWorth > 1000000 THEN 'Inherited' END), '') AS MarketingNameplate
FROM M
WHERE pn = 1
ORDER BY CustomerID;
