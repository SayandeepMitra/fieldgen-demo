-- Batch-1 (historical load) port of benchmark/tpcdi/dbtpcdi/Snowflake/models/{base,silver,incremental}/*.sql to DuckDB.
-- Reads the parsed Source.* tables (views over the v2 DB), writes schema dbt.*.
-- Conventions
--   * Snowflake CONCAT() propagates NULL, DuckDB concat() ignores NULL -> the || operator is used where NULL propagation matters.
--   * Window ordering: dbt orders by the timestamp only; we add the file order (Action_Id) as a deterministic tie-break.
--   * dbt's string surrogate keys (e.g. concat(customerid,'-',update_ts)) are NOT reproduced; instead each ported table carries
--     the natural key (and the effective date) of every dimension version it points at, so FKs can be compared naturally.
--   * Columns suffixed _fx are sensitivity variants that undo a *known dbt defect* (documented in REPORT.md); the unsuffixed
--     columns are the faithful dbt result.
--   * Batch-2/3 incremental inputs (CustomerIncremental, AccountIncremental, TradeIncremental, ...) are omitted; the
--     UNION ALL branches that read them contribute nothing to Batch 1.

CREATE SCHEMA IF NOT EXISTS dbt;

-- ===================== base/CustomerMgmtView (one row per Action; first Account only, as xmlget() does) ====================
-- NOTE the dbt view builds the phone country part from xmlget(..., 'CTRY_CODE') (element name typo; the real element is
-- 'C_CTRY_CODE').  The typo yields NULL, '+' || NULL || ' ' is NULL, and Snowflake CONCAT() of a NULL argument is NULL, so
-- the whole phone becomes NULL whenever a country code exists.  phoneN is the faithful result, phoneN_fx the typo-corrected one.
CREATE OR REPLACE TABLE dbt.CustomerMgmtView AS
SELECT
    CAST(C.C_ID AS BIGINT) AS customerid,
    CAST(ACC.CA_ID AS BIGINT) AS accountid,
    CAST(ACC.CA_B_ID AS BIGINT) AS brokerid,
    NULLIF(C.C_TAX_ID, '') AS taxid,
    NULLIF(ACC.CA_NAME, '') AS accountdesc,
    CAST(ACC.CA_TAX_ST AS INTEGER) AS taxstatus,
    CASE A.ActionType WHEN 'NEW' THEN 'Active' WHEN 'ADDACCT' THEN 'Active' WHEN 'UPDACCT' THEN 'Active' WHEN 'UPDCUST' THEN 'Active'
                      WHEN 'CLOSEACCT' THEN 'Inactive' WHEN 'INACT' THEN 'Inactive' END AS status,
    NULLIF(N.C_L_NAME, '') AS lastname,
    NULLIF(N.C_F_NAME, '') AS firstname,
    NULLIF(N.C_M_NAME, '') AS middleinitial,
    NULLIF(UPPER(C.C_GNDR), '') AS gender,
    NULLIF(C.C_TIER, '') AS tier,
    CAST(C.C_DOB AS DATE) AS dob,
    NULLIF(AD.C_ADLINE1, '') AS addressline1,
    NULLIF(AD.C_ADLINE2, '') AS addressline2,
    NULLIF(AD.C_ZIPCODE, '') AS postalcode,
    NULLIF(AD.C_CITY, '') AS city,
    NULLIF(AD.C_STATE_PROV, '') AS stateprov,
    NULLIF(AD.C_CTRY, '') AS country,
    CASE WHEN NULLIF(P1.C_LOCAL, '') IS NOT NULL THEN
        (CASE WHEN NULLIF(P1.C_CTRY_CODE, '') IS NOT NULL THEN CAST(NULL AS VARCHAR) ELSE '' END)
        || (CASE WHEN NULLIF(P1.C_AREA_CODE, '') IS NOT NULL THEN '(' || P1.C_AREA_CODE || ') ' ELSE '' END)
        || P1.C_LOCAL || COALESCE(P1.C_EXT, '') END AS phone1,
    CASE WHEN NULLIF(P2.C_LOCAL, '') IS NOT NULL THEN
        (CASE WHEN NULLIF(P2.C_CTRY_CODE, '') IS NOT NULL THEN CAST(NULL AS VARCHAR) ELSE '' END)
        || (CASE WHEN NULLIF(P2.C_AREA_CODE, '') IS NOT NULL THEN '(' || P2.C_AREA_CODE || ') ' ELSE '' END)
        || P2.C_LOCAL || COALESCE(P2.C_EXT, '') END AS phone2,
    CASE WHEN NULLIF(P3.C_LOCAL, '') IS NOT NULL THEN
        (CASE WHEN NULLIF(P3.C_CTRY_CODE, '') IS NOT NULL THEN CAST(NULL AS VARCHAR) ELSE '' END)
        || (CASE WHEN NULLIF(P3.C_AREA_CODE, '') IS NOT NULL THEN '(' || P3.C_AREA_CODE || ') ' ELSE '' END)
        || P3.C_LOCAL || COALESCE(P3.C_EXT, '') END AS phone3,
    CASE WHEN NULLIF(P1.C_LOCAL, '') IS NOT NULL THEN
        (CASE WHEN NULLIF(P1.C_CTRY_CODE, '') IS NOT NULL THEN '+' || P1.C_CTRY_CODE || ' ' ELSE '' END)
        || (CASE WHEN NULLIF(P1.C_AREA_CODE, '') IS NOT NULL THEN '(' || P1.C_AREA_CODE || ') ' ELSE '' END)
        || P1.C_LOCAL || COALESCE(P1.C_EXT, '') END AS phone1_fx,
    CASE WHEN NULLIF(P2.C_LOCAL, '') IS NOT NULL THEN
        (CASE WHEN NULLIF(P2.C_CTRY_CODE, '') IS NOT NULL THEN '+' || P2.C_CTRY_CODE || ' ' ELSE '' END)
        || (CASE WHEN NULLIF(P2.C_AREA_CODE, '') IS NOT NULL THEN '(' || P2.C_AREA_CODE || ') ' ELSE '' END)
        || P2.C_LOCAL || COALESCE(P2.C_EXT, '') END AS phone2_fx,
    CASE WHEN NULLIF(P3.C_LOCAL, '') IS NOT NULL THEN
        (CASE WHEN NULLIF(P3.C_CTRY_CODE, '') IS NOT NULL THEN '+' || P3.C_CTRY_CODE || ' ' ELSE '' END)
        || (CASE WHEN NULLIF(P3.C_AREA_CODE, '') IS NOT NULL THEN '(' || P3.C_AREA_CODE || ') ' ELSE '' END)
        || P3.C_LOCAL || COALESCE(P3.C_EXT, '') END AS phone3_fx,
    NULLIF(CI.C_PRIM_EMAIL, '') AS email1,
    NULLIF(CI.C_ALT_EMAIL, '') AS email2,
    NULLIF(T.C_LCL_TX_ID, '') AS lcl_tx_id,
    NULLIF(T.C_NAT_TX_ID, '') AS nat_tx_id,
    CAST(A.ActionTS AS TIMESTAMP) AS update_ts,
    A.ActionType AS ActionType,
    CAST(A.Action_Id AS BIGINT) AS action_seq
FROM Source.ActionXML A
    JOIN Source.CustomerXML C ON C.Action_Id = A.Action_Id
    LEFT JOIN Source.AccountXML ACC ON ACC.Customer_Id = C.Customer_Id
    LEFT JOIN Source.NameXML N ON N.Customer_Id = C.Customer_Id
    LEFT JOIN Source.AddressXML AD ON AD.Customer_Id = C.Customer_Id
    LEFT JOIN Source.ContactInfoXML CI ON CI.Customer_Id = C.Customer_Id
    LEFT JOIN Source.C_PHONE_1_XML P1 ON P1.ContactInfo_Id = CI.ContactInfo_Id
    LEFT JOIN Source.C_PHONE_2_XML P2 ON P2.ContactInfo_Id = CI.ContactInfo_Id
    LEFT JOIN Source.C_PHONE_3_XML P3 ON P3.ContactInfo_Id = CI.ContactInfo_Id
    LEFT JOIN Source.TaxInfoXML T ON T.Customer_Id = C.Customer_Id;

-- ===================== incremental/DimCustomerStg (Batch-1 branch only) ====================
-- Faithful: NO same-day consolidation; effectivedate = date(update_ts), enddate = next version's date (so same-day versions
-- are zero-length); status is the per-action decode (NOT forward filled).
CREATE OR REPLACE TABLE dbt.DimCustomerStg AS
SELECT customerid, update_ts, action_seq, ActionType,
    status,
    COALESCE(taxid, LAST_VALUE(taxid IGNORE NULLS) OVER w) AS taxid,
    COALESCE(lastname, LAST_VALUE(lastname IGNORE NULLS) OVER w) AS lastname,
    COALESCE(firstname, LAST_VALUE(firstname IGNORE NULLS) OVER w) AS firstname,
    COALESCE(middleinitial, LAST_VALUE(middleinitial IGNORE NULLS) OVER w) AS middleinitial,
    COALESCE(gender, LAST_VALUE(gender IGNORE NULLS) OVER w) AS gender,
    COALESCE(tier, LAST_VALUE(tier IGNORE NULLS) OVER w) AS tier,
    COALESCE(dob, LAST_VALUE(dob IGNORE NULLS) OVER w) AS dob,
    COALESCE(addressline1, LAST_VALUE(addressline1 IGNORE NULLS) OVER w) AS addressline1,
    COALESCE(addressline2, LAST_VALUE(addressline2 IGNORE NULLS) OVER w) AS addressline2,
    COALESCE(postalcode, LAST_VALUE(postalcode IGNORE NULLS) OVER w) AS postalcode,
    COALESCE(city, LAST_VALUE(city IGNORE NULLS) OVER w) AS city,
    COALESCE(stateprov, LAST_VALUE(stateprov IGNORE NULLS) OVER w) AS stateprov,
    COALESCE(country, LAST_VALUE(country IGNORE NULLS) OVER w) AS country,
    COALESCE(phone1, LAST_VALUE(phone1 IGNORE NULLS) OVER w) AS phone1,
    COALESCE(phone2, LAST_VALUE(phone2 IGNORE NULLS) OVER w) AS phone2,
    COALESCE(phone3, LAST_VALUE(phone3 IGNORE NULLS) OVER w) AS phone3,
    COALESCE(phone1_fx, LAST_VALUE(phone1_fx IGNORE NULLS) OVER w) AS phone1_fx,
    COALESCE(phone2_fx, LAST_VALUE(phone2_fx IGNORE NULLS) OVER w) AS phone2_fx,
    COALESCE(phone3_fx, LAST_VALUE(phone3_fx IGNORE NULLS) OVER w) AS phone3_fx,
    COALESCE(email1, LAST_VALUE(email1 IGNORE NULLS) OVER w) AS email1,
    COALESCE(email2, LAST_VALUE(email2 IGNORE NULLS) OVER w) AS email2,
    COALESCE(lcl_tx_id, LAST_VALUE(lcl_tx_id IGNORE NULLS) OVER w) AS lcl_tx_id,
    COALESCE(nat_tx_id, LAST_VALUE(nat_tx_id IGNORE NULLS) OVER w) AS nat_tx_id,
    1 AS batchid,
    (LEAD(update_ts) OVER (PARTITION BY customerid ORDER BY update_ts, action_seq) IS NULL) AS iscurrent,
    CAST(update_ts AS DATE) AS effectivedate,
    COALESCE(LEAD(CAST(update_ts AS DATE)) OVER (PARTITION BY customerid ORDER BY update_ts, action_seq), DATE '9999-12-31') AS enddate
FROM dbt.CustomerMgmtView
WHERE ActionType IN ('NEW', 'INACT', 'UPDCUST')
WINDOW w AS (PARTITION BY customerid ORDER BY update_ts, action_seq ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW);

-- ===================== incremental/Prospect (Batch-1: ProspectRaw = Source.Prospect with batchid 1) ====================
CREATE OR REPLACE TABLE dbt.Prospect AS
WITH P0 AS (
    SELECT agencyid, MAX(batchid) AS recordbatchid, lastname, firstname, middleinitial, gender, addressline1, addressline2, postalcode,
           city, state, country, phone, income, numbercars, numberchildren, maritalstatus, age, creditrating, ownorrentflag, employer,
           numbercreditcards, networth, MIN(batchid) AS batchid
    FROM (SELECT AgencyID AS agencyid, LastName AS lastname, FirstName AS firstname, MiddleInitial AS middleinitial, Gender AS gender,
                 AddressLine1 AS addressline1, AddressLine2 AS addressline2, PostalCode AS postalcode, City AS city, State AS state,
                 Country AS country, Phone AS phone, Income AS income, NumberCars AS numbercars, NumberChildren AS numberchildren,
                 MaritalStatus AS maritalstatus, Age AS age, CreditRating AS creditrating, OwnOrRentFlag AS ownorrentflag,
                 Employer AS employer, NumberCreditCards AS numbercreditcards, NetWorth AS networth, 1 AS batchid
          FROM Source.Prospect) x
    GROUP BY ALL
), P AS (
    SELECT * FROM P0 QUALIFY ROW_NUMBER() OVER (PARTITION BY agencyid ORDER BY batchid DESC) = 1
), tagged AS (
    SELECT P.*,
        (CASE WHEN networth > 1000000 OR income > 200000 THEN 'HighValue+' ELSE '' END) ||
        (CASE WHEN numberchildren > 3 OR numbercreditcards > 5 THEN 'Expenses+' ELSE '' END) ||
        (CASE WHEN age > 45 THEN 'Boomer+' ELSE '' END) ||
        (CASE WHEN income < 50000 OR creditrating < 600 OR networth < 100000 THEN 'MoneyAlert+' ELSE '' END) ||
        (CASE WHEN numbercars > 3 OR numbercreditcards > 7 THEN 'Spender+' ELSE '' END) ||
        (CASE WHEN age < 25 AND networth > 1000000 THEN 'Inherited+' ELSE '' END) AS tagstr
    FROM P
)
SELECT p.agencyid,
    DD.SK_DateID AS sk_recorddateid, DD.SK_DateID AS sk_updatedateid, p.batchid,
    (c.customerid IS NOT NULL) AS iscustomer,
    p.lastname, p.firstname, p.middleinitial, p.gender, p.addressline1, p.addressline2, p.postalcode, p.city, p.state, p.country,
    p.phone, p.income, p.numbercars, p.numberchildren, p.maritalstatus, p.age, p.creditrating, p.ownorrentflag, p.employer,
    p.numbercreditcards, p.networth,
    -- Snowflake: IFF(<concat> IS NOT NULL, LEFT(<concat>, LENGTH(<concat>)-1), NULL).  The concat is '' (never NULL) when no tag
    -- applies, so the result is '' (empty string), not NULL.
    CASE WHEN p.tagstr IS NOT NULL THEN LEFT(p.tagstr, LENGTH(p.tagstr) - 1) END AS marketingnameplate,
    c.customerid AS match_customerid
FROM tagged p
    JOIN Source.BatchDate B ON TRUE
    JOIN Source.Date DD ON CAST(DD.DateValue AS DATE) = B.BatchDate
    LEFT JOIN (SELECT customerid, lastname, firstname, addressline1, addressline2, postalcode FROM dbt.DimCustomerStg WHERE iscurrent) c
        ON UPPER(p.lastname) = UPPER(c.lastname) AND UPPER(p.firstname) = UPPER(c.firstname)
        AND UPPER(p.addressline1) = UPPER(c.addressline1)
        AND UPPER(COALESCE(p.addressline2, '')) = UPPER(COALESCE(c.addressline2, ''))
        AND UPPER(p.postalcode) = UPPER(c.postalcode);

-- ===================== incremental/DimCustomer ====================
-- Prospect demographics are joined onto EVERY version (no "latest version only" restriction).
CREATE OR REPLACE TABLE dbt.DimCustomer AS
SELECT c.customerid, c.update_ts, c.action_seq, c.ActionType, c.status, c.taxid, c.lastname, c.firstname, c.middleinitial,
    CASE WHEN c.gender IN ('M', 'F') THEN c.gender ELSE 'U' END AS gender,
    c.tier, c.dob, c.addressline1, c.addressline2, c.postalcode, c.city, c.stateprov, c.country,
    c.phone1, c.phone2, c.phone3, c.phone1_fx, c.phone2_fx, c.phone3_fx, c.email1, c.email2,
    r_nat.TX_NAME AS nationaltaxratedesc, r_nat.TX_RATE AS nationaltaxrate,
    r_lcl.TX_NAME AS localtaxratedesc, r_lcl.TX_RATE AS localtaxrate,
    p.agencyid, p.creditrating, p.networth, p.marketingnameplate,
    c.iscurrent, c.batchid, c.effectivedate, c.enddate
FROM dbt.DimCustomerStg c
    LEFT JOIN Source.TaxRate r_lcl ON c.lcl_tx_id = r_lcl.TX_ID
    LEFT JOIN Source.TaxRate r_nat ON c.nat_tx_id = r_nat.TX_ID
    LEFT JOIN dbt.Prospect p
        ON UPPER(p.lastname) = UPPER(c.lastname) AND UPPER(p.firstname) = UPPER(c.firstname)
        AND UPPER(p.addressline1) = UPPER(c.addressline1)
        AND UPPER(COALESCE(p.addressline2, '')) = UPPER(COALESCE(c.addressline2, ''))
        AND UPPER(p.postalcode) = UPPER(c.postalcode);

-- ===================== silver/DimBroker ====================
CREATE OR REPLACE TABLE dbt.DimBroker AS
SELECT CAST(EmployeeID AS BIGINT) AS brokerid, CAST(ManagerID AS BIGINT) AS managerid, EmployeeFirstName AS firstname,
    EmployeeLastName AS lastname, EmployeeMI AS middleinitial, EmployeeBranch AS branch, EmployeeOffice AS office,
    EmployeePhone AS phone, true AS iscurrent, 1 AS batchid,
    (SELECT MIN(CAST(DateValue AS DATE)) FROM Source.Date) AS effectivedate, DATE '9999-12-31' AS enddate
FROM Source.HR WHERE EmployeeJobCode = 314;

-- ===================== incremental/DimAccount (Batch-1 branch) ====================
-- CustomerMgmtView rows with ActionType NOT IN (UPDCUST, INACT): the account's own Status comes from the account action only
-- (INACT is ignored => accounts of inactivated customers stay 'Active').  Customer versions are overlaid with a FULL OUTER JOIN
-- on interval overlap (zero-length customer versions overlap strictly-inside account intervals => zero-length account rows).
CREATE OR REPLACE TABLE dbt.DimAccount AS
WITH acc AS (
    SELECT accountid, customerid,
        COALESCE(accountdesc, LAST_VALUE(accountdesc IGNORE NULLS) OVER w) AS accountdesc,
        COALESCE(taxstatus, LAST_VALUE(taxstatus IGNORE NULLS) OVER w) AS taxstatus,
        COALESCE(brokerid, LAST_VALUE(brokerid IGNORE NULLS) OVER w) AS brokerid,
        COALESCE(status, LAST_VALUE(status IGNORE NULLS) OVER w) AS status,
        CAST(update_ts AS DATE) AS effectivedate,
        COALESCE(LEAD(CAST(update_ts AS DATE)) OVER (PARTITION BY accountid ORDER BY update_ts, action_seq), DATE '9999-12-31') AS enddate,
        1 AS batchid
    FROM dbt.CustomerMgmtView
    WHERE ActionType NOT IN ('UPDCUST', 'INACT')
    WINDOW w AS (PARTITION BY accountid ORDER BY update_ts, action_seq ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
), a AS (SELECT * FROM acc WHERE effectivedate < enddate)
SELECT a2.accountid, b.brokerid AS brokerid, a2.c_customerid, a2.c_effdate, a2.c_update_ts,
    a2.accountdesc, a2.taxstatus, a2.status, a2.batchid, a2.effectivedate, a2.enddate
FROM (
    SELECT a.accountid, a.brokerid, a.accountdesc, a.taxstatus, a.status, a.batchid,
        c.customerid AS c_customerid, c.effectivedate AS c_effdate, c.update_ts AS c_update_ts,
        CASE WHEN a.effectivedate < c.effectivedate THEN c.effectivedate ELSE a.effectivedate END AS effectivedate,
        CASE WHEN a.enddate > c.enddate THEN c.enddate ELSE a.enddate END AS enddate
    FROM a FULL OUTER JOIN dbt.DimCustomerStg c
        ON a.customerid = c.customerid AND c.enddate > a.effectivedate AND c.effectivedate < a.enddate
) a2
LEFT JOIN dbt.DimBroker b ON a2.brokerid = b.brokerid;

-- ===================== silver/DimCompany ====================
-- Blank text is NOT converted to NULL (only FoundingDate is); invalid SPrating -> NULL (matches spec).
CREATE OR REPLACE TABLE dbt.DimCompany AS
SELECT * FROM (
    SELECT CAST(cik AS BIGINT) AS companyid, st.ST_NAME AS status, companyname AS name, ind.IN_NAME AS industry,
        CASE WHEN SPrating IN ('AAA','AA','AA+','AA-','A','A+','A-','BBB','BBB+','BBB-','BB','BB+','BB-','B','B+','B-','CCC','CCC+','CCC-','CC','C','D')
             THEN SPrating END AS sprating,
        CASE WHEN SPrating IN ('AAA','AA','A','AA+','A+','AA-','A-','BBB','BBB+','BBB-') THEN false
             WHEN SPrating IN ('BB','B','CCC','CC','C','D','BB+','B+','CCC+','BB-','B-','CCC-') THEN true END AS islowgrade,
        ceoname AS ceo, addrline1 AS addressline1, addrline2 AS addressline2, postalcode, city, stateprovince AS stateprov, country,
        description, foundingdate,
        (LEAD(pts) OVER (PARTITION BY cik ORDER BY pts) IS NOT NULL) AS _hasnext,
        (LEAD(pts) OVER (PARTITION BY cik ORDER BY pts) IS NULL) AS iscurrent,
        1 AS batchid, CAST(pts AS DATE) AS effectivedate,
        COALESCE(LEAD(CAST(pts AS DATE)) OVER (PARTITION BY cik ORDER BY pts), DATE '9999-12-31') AS enddate
    FROM (
        SELECT strptime(PTS, '%Y%m%d-%H%M%S') AS PTS, TRIM(CompanyName) AS CompanyName, TRIM(CIK) AS CIK, TRIM(Status) AS Status,
            TRIM(IndustryID) AS IndustryID, TRIM(SPrating) AS SPrating,
            try_strptime(NULLIF(TRIM(FoundingDate), ''), '%Y%m%d')::DATE AS FoundingDate,
            TRIM(AddrLine1) AS AddrLine1, TRIM(AddrLine2) AS AddrLine2, TRIM(PostalCode) AS PostalCode, TRIM(City) AS City,
            TRIM(StateProvince) AS StateProvince, TRIM(Country) AS Country, TRIM(CEOname) AS CEOname, TRIM(Description) AS Description
        FROM Source.FinwireCMP WHERE RecType = 'CMP'
    ) cmp
    JOIN Source.StatusType st ON cmp.status = st.ST_ID
    JOIN Source.Industry ind ON cmp.industryid = ind.IN_ID
);

-- ===================== silver/DimSecurity ====================
CREATE OR REPLACE TABLE dbt.DimSecurity AS
WITH fws0 AS (
    SELECT CAST(strptime(PTS, '%Y%m%d-%H%M%S') AS DATE) AS effectivedate, TRIM(Symbol) AS Symbol, TRIM(IssueType) AS issue,
        TRIM(Status) AS st, TRIM(Name) AS Name, TRIM(ExID) AS exchangeid, TRY_CAST(ShOut AS BIGINT) AS sharesoutstanding,
        try_strptime(FirstTradeDate, '%Y%m%d')::DATE AS firsttrade, try_strptime(FirstTradeExchg, '%Y%m%d')::DATE AS firsttradeonexchange,
        TRY_CAST(Dividend AS DOUBLE) AS Dividend, TRIM(CoNameOrCIK) AS conameorcik0
    FROM Source.FinwireSEC WHERE RecType = 'SEC'
), fws AS (
    SELECT f.effectivedate, f.Symbol, f.issue, s.ST_NAME AS status, f.Name, f.exchangeid, f.sharesoutstanding, f.firsttrade,
        f.firsttradeonexchange, f.Dividend,
        COALESCE(CAST(TRY_CAST(f.conameorcik0 AS BIGINT) AS VARCHAR), f.conameorcik0) AS conameorcik,
        COALESCE(LEAD(f.effectivedate) OVER (PARTITION BY f.Symbol ORDER BY f.effectivedate), DATE '9999-12-31') AS enddate
    FROM fws0 f JOIN Source.StatusType s ON s.ST_ID = f.st
), dcs AS (
    SELECT name AS conameorcik, companyid, effectivedate, enddate FROM dbt.DimCompany
    UNION ALL
    SELECT CAST(companyid AS VARCHAR), companyid, effectivedate, enddate FROM dbt.DimCompany
)
SELECT * FROM (
    SELECT fws.Symbol, fws.issue, fws.status, fws.Name, fws.exchangeid, dc.companyid, dc.effectivedate AS co_effdate,
        fws.sharesoutstanding, fws.firsttrade, fws.firsttradeonexchange, fws.Dividend,
        CASE WHEN fws.effectivedate < dc.effectivedate THEN dc.effectivedate ELSE fws.effectivedate END AS effectivedate,
        CASE WHEN fws.enddate > dc.enddate THEN dc.enddate ELSE fws.enddate END AS enddate
    FROM fws JOIN dcs dc ON fws.conameorcik = dc.conameorcik AND fws.effectivedate < dc.enddate AND fws.enddate > dc.effectivedate
) x
WHERE effectivedate != enddate;

-- ===================== silver/Financial ====================
CREATE OR REPLACE TABLE dbt.Financial AS
WITH f AS (
    SELECT strptime(PTS, '%Y%m%d-%H%M%S') AS PTS, TRY_CAST(Year AS INTEGER) AS fi_year, TRY_CAST(Quarter AS INTEGER) AS fi_qtr,
        try_strptime(QtrStartDate, '%Y%m%d')::DATE AS fi_qtr_start_date, TRY_CAST(Revenue AS DOUBLE) AS fi_revenue,
        TRY_CAST(Earnings AS DOUBLE) AS fi_net_earn, TRY_CAST(EPS AS DOUBLE) AS fi_basic_eps, TRY_CAST(DilutedEPS AS DOUBLE) AS fi_dilut_eps,
        TRY_CAST(Margin AS DOUBLE) AS fi_margin, TRY_CAST(Inventory AS DOUBLE) AS fi_inventory, TRY_CAST(Assets AS DOUBLE) AS fi_assets,
        TRY_CAST(Liabilities AS DOUBLE) AS fi_liability, TRY_CAST(ShOut AS BIGINT) AS fi_out_basic, TRY_CAST(DilutedShOut AS BIGINT) AS fi_out_dilut,
        TRIM(CoNameOrCIK) AS conameorcik0
    FROM Source.FinwireFIN WHERE RecType = 'FIN'
), f2 AS (
    SELECT *, COALESCE(CAST(TRY_CAST(conameorcik0 AS BIGINT) AS VARCHAR), conameorcik0) AS conameorcik FROM f
), dcs AS (
    SELECT name AS conameorcik, companyid, effectivedate, enddate FROM dbt.DimCompany
    UNION ALL
    SELECT CAST(companyid AS VARCHAR), companyid, effectivedate, enddate FROM dbt.DimCompany
)
SELECT dc.companyid, dc.effectivedate AS co_effdate, fi_year, fi_qtr, fi_qtr_start_date, fi_revenue, fi_net_earn, fi_basic_eps, fi_dilut_eps,
    fi_margin, fi_inventory, fi_assets, fi_liability, fi_out_basic, fi_out_dilut
FROM f2 f JOIN dcs dc ON f.conameorcik = dc.conameorcik AND CAST(f.PTS AS DATE) >= dc.effectivedate AND CAST(f.PTS AS DATE) < dc.enddate;

-- ===================== incremental/DimTrade (Batch-1 branch) ====================
-- NOTE the dbt model builds BOTH sk_createdateid and sk_closedateid (and the time keys) with iff(create_flg, ...): the close
-- keys are populated from the CREATE events and are therefore always equal to the create keys.  *_fx = corrected variant
-- (close keys from the CMPT/CNCL events, i.e. create_flg = FALSE) for sensitivity.
CREATE OR REPLACE TABLE dbt.DimTrade AS
WITH ev AS (
    SELECT T.T_ID AS tradeid, TH.TH_DTS AS t_dts, T.T_ST_ID AS t_st_id, T.T_TT_ID AS t_tt_id, T.T_IS_CASH AS t_is_cash, T.T_S_SYMB AS t_s_symb,
        T.T_QTY AS quantity, T.T_BID_PRICE AS bidprice, T.T_CA_ID AS t_ca_id, T.T_EXEC_NAME AS executedby, T.T_TRADE_PRICE AS tradeprice,
        T.T_CHRG AS fee, T.T_COMM AS commission, T.T_TAX AS tax, 1 AS batchid,
        CASE WHEN (TH.TH_ST_ID = 'SBMT' AND T.T_TT_ID IN ('TMB', 'TMS')) OR TH.TH_ST_ID = 'PNDG' THEN TRUE
             WHEN TH.TH_ST_ID IN ('CMPT', 'CNCL') THEN FALSE END AS create_flg
    FROM Source.Trade T JOIN Source.TradeHistory TH ON TH.TH_T_ID = T.T_ID
), ev2 AS (
    SELECT ev.*, dd.SK_DateID AS sk_dateid, dt.SK_TimeID AS sk_timeid
    FROM ev JOIN Source.Date dd ON CAST(ev.t_dts AS DATE) = CAST(dd.DateValue AS DATE)
            JOIN Source.Time dt ON strftime(ev.t_dts, '%H:%M:%S') = dt.TimeValue
), ev3 AS (
    SELECT tradeid, t_dts,
        MIN(CAST(t_dts AS DATE)) OVER (PARTITION BY tradeid) AS createdate,
        CASE WHEN create_flg THEN sk_dateid END AS sk_createdateid, CASE WHEN create_flg THEN sk_timeid END AS sk_createtimeid,
        CASE WHEN create_flg THEN sk_dateid END AS sk_closedateid, CASE WHEN create_flg THEN sk_timeid END AS sk_closetimeid,
        CASE WHEN NOT create_flg THEN sk_dateid END AS sk_closedateid_fx, CASE WHEN NOT create_flg THEN sk_timeid END AS sk_closetimeid_fx,
        CASE WHEN t_is_cash = '1' THEN TRUE WHEN t_is_cash = '0' THEN FALSE END AS cashflag,
        t_st_id, t_tt_id, t_s_symb, quantity, bidprice, t_ca_id, executedby, tradeprice, fee, commission, tax, batchid
    FROM ev2
), ev4 AS (
    SELECT tradeid, createdate, t_dts,
        COALESCE(sk_createdateid, LAST_VALUE(sk_createdateid IGNORE NULLS) OVER w) AS sk_createdateid,
        COALESCE(sk_createtimeid, LAST_VALUE(sk_createtimeid IGNORE NULLS) OVER w) AS sk_createtimeid,
        COALESCE(sk_closedateid, LAST_VALUE(sk_closedateid IGNORE NULLS) OVER w) AS sk_closedateid,
        COALESCE(sk_closetimeid, LAST_VALUE(sk_closetimeid IGNORE NULLS) OVER w) AS sk_closetimeid,
        COALESCE(sk_closedateid_fx, LAST_VALUE(sk_closedateid_fx IGNORE NULLS) OVER w) AS sk_closedateid_fx,
        COALESCE(sk_closetimeid_fx, LAST_VALUE(sk_closetimeid_fx IGNORE NULLS) OVER w) AS sk_closetimeid_fx,
        cashflag, t_st_id, t_tt_id, t_s_symb, quantity, bidprice, t_ca_id, executedby, tradeprice, fee, commission, tax, batchid
    FROM ev3
    WINDOW w AS (PARTITION BY tradeid ORDER BY t_dts)
), trade AS (
    SELECT * EXCLUDE (t_dts) FROM ev4 QUALIFY ROW_NUMBER() OVER (PARTITION BY tradeid ORDER BY t_dts DESC) = 1
)
SELECT trade.tradeid, da.brokerid, trade.sk_createdateid, trade.sk_createtimeid, trade.sk_closedateid, trade.sk_closetimeid,
    trade.sk_closedateid_fx, trade.sk_closetimeid_fx,
    st.ST_NAME AS status, tt.TT_NAME AS type, trade.cashflag,
    ds.Symbol AS sec_symbol, ds.effectivedate AS sec_effdate, ds.companyid AS co_companyid, ds.co_effdate AS co_effdate,
    trade.quantity, trade.bidprice,
    da.c_customerid AS cust_customerid, da.c_effdate AS cust_effdate,
    da.accountid AS acct_accountid, da.effectivedate AS acct_effdate,
    trade.executedby, trade.tradeprice, trade.fee, trade.commission, trade.tax, trade.batchid
FROM trade
    JOIN Source.StatusType st ON st.ST_ID = trade.t_st_id
    JOIN Source.TradeType tt ON tt.TT_ID = trade.t_tt_id
    LEFT JOIN dbt.DimSecurity ds ON ds.Symbol = trade.t_s_symb AND trade.createdate >= ds.effectivedate AND trade.createdate < ds.enddate
    LEFT JOIN dbt.DimAccount da ON trade.t_ca_id = da.accountid AND trade.createdate >= da.effectivedate AND trade.createdate < da.enddate;

-- ===================== incremental/FactCashBalances (Batch-1 branch) ====================
CREATE OR REPLACE TABLE dbt.FactCashBalances AS
SELECT a.c_customerid AS cust_customerid, a.c_effdate AS cust_effdate, a.accountid AS acct_accountid, a.effectivedate AS acct_effdate,
    c.accountid AS ct_accountid, d.SK_DateID AS sk_dateid, c.datevalue,
    SUM(c.account_daily_total) OVER (PARTITION BY c.accountid ORDER BY c.datevalue) AS cash, c.batchid
FROM (
    SELECT ct_ca_id AS accountid, CAST(ct_dts AS DATE) AS datevalue, SUM(ct_amt) AS account_daily_total, 1 AS batchid
    FROM (SELECT CT_CA_ID AS ct_ca_id, CT_DTS AS ct_dts, CT_AMT AS ct_amt FROM Source.CashTransaction) x
    GROUP BY accountid, datevalue, batchid
) c
    JOIN Source.Date d ON c.datevalue = CAST(d.DateValue AS DATE)
    LEFT JOIN dbt.DimAccount a ON c.accountid = a.accountid AND c.datevalue >= a.effectivedate AND c.datevalue < a.enddate;

-- ===================== incremental/FactHoldings (Batch-1 branch) ====================
CREATE OR REPLACE TABLE dbt.FactHoldings AS
SELECT hh.HH_H_T_ID AS tradeid, hh.HH_T_ID AS currenttradeid,
    dt.cust_customerid, dt.cust_effdate, dt.acct_accountid, dt.acct_effdate, dt.sec_symbol, dt.sec_effdate, dt.co_companyid, dt.co_effdate,
    dt.sk_closedateid AS sk_dateid, dt.sk_closetimeid AS sk_timeid, dt.sk_closedateid_fx AS sk_dateid_fx, dt.sk_closetimeid_fx AS sk_timeid_fx,
    dt.tradeprice AS currentprice, hh.HH_AFTER_QTY AS currentholding, 1 AS batchid,
    (dt.tradeid IS NOT NULL) AS dt_matched
FROM Source.HoldingHistory hh LEFT JOIN dbt.DimTrade dt ON dt.tradeid = hh.HH_T_ID;
