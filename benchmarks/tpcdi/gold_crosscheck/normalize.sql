-- Natural-key normalisation of both sides.  v2n.<T> = repaired gold (v2), dbtn.<T> = ported dbt (faithful).
-- All foreign surrogate keys are translated to (natural key, dimension EffectiveDate) / DateValue / TimeValue.
-- Each *n table has a UNIQUE natural key; the number of rows dropped by de-duplication on the dbt side is reported separately
-- (see raw_stats in run_crosscheck.py).  Extra '_fx' columns exist on both sides (v2 side = copy of the base column) so that the
-- dbt-defect-corrected variant can be compared against v2 with the same machinery.
CREATE SCHEMA IF NOT EXISTS v2n;
CREATE SCHEMA IF NOT EXISTS dbtn;

-- helper maps
CREATE OR REPLACE TABLE v2n._date AS SELECT CAST(SK_DateID AS BIGINT) AS sk, CAST(DateValue AS DATE) AS d FROM Source.Date;
CREATE OR REPLACE TABLE v2n._time AS SELECT CAST(SK_TimeID AS BIGINT) AS sk, TimeValue AS t FROM Source.Time;

-- ======================= DimCompany =======================
CREATE OR REPLACE TABLE v2n.DimCompany AS
SELECT CompanyID AS companyid, EffectiveDate AS effectivedate, Status AS status, Name AS name, Industry AS industry, SPrating AS sprating,
    isLowGrade AS islowgrade, CEO AS ceo, Description AS description, FoundingDate AS foundingdate, AddressLine1 AS addressline1,
    AddressLine2 AS addressline2, PostalCode AS postalcode, City AS city, StateProv AS stateprov, Country AS country,
    IsCurrent AS iscurrent, EndDate AS enddate
FROM gold.DimCompany;
CREATE OR REPLACE TABLE dbtn.DimCompany AS
SELECT companyid, effectivedate, status, name, industry, sprating, islowgrade, ceo, description, foundingdate, addressline1, addressline2,
    postalcode, city, stateprov, country, iscurrent, enddate
FROM dbt.DimCompany;

-- ======================= DimCustomer =======================
CREATE OR REPLACE TABLE v2n.DimCustomer AS
SELECT CAST(CustomerID AS BIGINT) AS customerid, EffectiveDate AS effectivedate, Status AS status, TaxID AS taxid, LastName AS lastname,
    FirstName AS firstname, MiddleInitial AS middleinitial, Gender AS gender, CAST(Tier AS VARCHAR) AS tier, DOB AS dob,
    AddressLine1 AS addressline1, AddressLine2 AS addressline2, PostalCode AS postalcode, City AS city, StateProv AS stateprov, Country AS country,
    Phone1 AS phone1, Phone2 AS phone2, Phone3 AS phone3, Phone1 AS phone1_fx, Phone2 AS phone2_fx, Phone3 AS phone3_fx,
    Email1 AS email1, Email2 AS email2, NationalTaxRateDesc AS nationaltaxratedesc, NationalTaxRate AS nationaltaxrate,
    LocalTaxRateDesc AS localtaxratedesc, LocalTaxRate AS localtaxrate,
    AgencyID AS agencyid, CreditRating AS creditrating, NetWorth AS networth, MarketingNameplate AS marketingnameplate,
    IsCurrent AS iscurrent, EndDate AS enddate
FROM gold.DimCustomer;
-- dbt: consolidate same-day versions (keep the latest of the day) only to obtain a unique natural key for comparison
CREATE OR REPLACE TABLE dbtn.DimCustomer AS
SELECT customerid, effectivedate, status, taxid, lastname, firstname, middleinitial, gender, tier, dob, addressline1, addressline2, postalcode,
    city, stateprov, country, phone1, phone2, phone3, phone1_fx, phone2_fx, phone3_fx, email1, email2, nationaltaxratedesc, nationaltaxrate,
    localtaxratedesc, localtaxrate, agencyid, creditrating, networth, marketingnameplate, iscurrent, enddate
FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY customerid, effectivedate ORDER BY update_ts DESC, action_seq DESC, agencyid) AS rn FROM dbt.DimCustomer)
WHERE rn = 1;

-- ======================= DimAccount =======================
CREATE OR REPLACE TABLE v2n.DimAccount AS
SELECT a.AccountID AS accountid, a.EffectiveDate AS effectivedate, b.BrokerID AS brokerid, cu.CustomerID AS cust_customerid,
    cu.EffectiveDate AS cust_effdate, a.Status AS status, a.AccountDesc AS accountdesc, a.TaxStatus AS taxstatus, a.EndDate AS enddate
FROM gold.DimAccount a
    LEFT JOIN gold.DimBroker b ON b.SK_BrokerID = a.SK_BrokerID
    LEFT JOIN gold.DimCustomer cu ON cu.SK_CustomerID = a.SK_CustomerID;
CREATE OR REPLACE TABLE dbtn.DimAccount AS
SELECT accountid, effectivedate, brokerid, c_customerid AS cust_customerid, c_effdate AS cust_effdate, status, accountdesc,
    CAST(taxstatus AS DECIMAL(1,0)) AS taxstatus, enddate
FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY accountid, effectivedate ORDER BY enddate DESC, c_update_ts DESC) AS rn
      FROM dbt.DimAccount WHERE accountid IS NOT NULL AND effectivedate < enddate)
WHERE rn = 1;

-- ======================= DimSecurity =======================
CREATE OR REPLACE TABLE v2n.DimSecurity AS
SELECT s.Symbol AS symbol, s.EffectiveDate AS effectivedate, s.Issue AS issue, s.Status AS status, s.Name AS name, s.ExchangeID AS exchangeid,
    c.CompanyID AS companyid, c.EffectiveDate AS co_effdate, s.SharesOutstanding AS sharesoutstanding, s.FirstTrade AS firsttrade,
    s.FirstTradeOnExchange AS firsttradeonexchange, CAST(s.Dividend AS DOUBLE) AS dividend, s.EndDate AS enddate
FROM gold.DimSecurity s LEFT JOIN gold.DimCompany c ON c.SK_CompanyID = s.SK_CompanyID;
CREATE OR REPLACE TABLE dbtn.DimSecurity AS
SELECT symbol, effectivedate, issue, status, name, exchangeid, companyid, co_effdate, sharesoutstanding, firsttrade, firsttradeonexchange,
    dividend, enddate
FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY symbol, effectivedate ORDER BY enddate DESC, companyid) AS rn FROM dbt.DimSecurity)
WHERE rn = 1;

-- ======================= DimTrade =======================
CREATE OR REPLACE TABLE v2n.DimTrade AS
SELECT CAST(t.TradeID AS BIGINT) AS tradeid, b.BrokerID AS brokerid,
    cd.d AS createdate, ct.t AS createtime, xd.d AS closedate, xt.t AS closetime, xd.d AS closedate_fx, xt.t AS closetime_fx,
    t.Status AS status, t.DT_Type AS type, t.CashFlag AS cashflag,
    s.Symbol AS sec_symbol, s.EffectiveDate AS sec_effdate, c.CompanyID AS co_companyid, c.EffectiveDate AS co_effdate,
    t.Quantity AS quantity, t.BidPrice AS bidprice,
    cu.CustomerID AS cust_customerid, cu.EffectiveDate AS cust_effdate, a.AccountID AS acct_accountid, a.EffectiveDate AS acct_effdate,
    t.ExecutedBy AS executedby, t.TradePrice AS tradeprice, t.Fee AS fee, t.Commission AS commission, t.Tax AS tax
FROM gold.DimTrade t
    LEFT JOIN gold.DimBroker b ON b.SK_BrokerID = t.SK_BrokerID
    LEFT JOIN v2n._date cd ON cd.sk = t.SK_CreateDateID LEFT JOIN v2n._time ct ON ct.sk = t.SK_CreateTimeID
    LEFT JOIN v2n._date xd ON xd.sk = t.SK_CloseDateID LEFT JOIN v2n._time xt ON xt.sk = t.SK_CloseTimeID
    LEFT JOIN gold.DimSecurity s ON s.SK_SecurityID = t.SK_SecurityID
    LEFT JOIN gold.DimCompany c ON c.SK_CompanyID = t.SK_CompanyID
    LEFT JOIN gold.DimCustomer cu ON cu.SK_CustomerID = t.SK_CustomerID
    LEFT JOIN gold.DimAccount a ON a.SK_AccountID = t.SK_AccountID;
CREATE OR REPLACE TABLE dbtn.DimTrade AS
SELECT CAST(t.tradeid AS BIGINT) AS tradeid, t.brokerid,
    cd.d AS createdate, ct.t AS createtime, xd.d AS closedate, xt.t AS closetime, xdf.d AS closedate_fx, xtf.t AS closetime_fx,
    t.status, t.type, t.cashflag, t.sec_symbol, t.sec_effdate, t.co_companyid, t.co_effdate, t.quantity, t.bidprice,
    t.cust_customerid, t.cust_effdate, t.acct_accountid, t.acct_effdate, t.executedby, t.tradeprice, t.fee, t.commission, t.tax
FROM dbt.DimTrade t
    LEFT JOIN v2n._date cd ON cd.sk = t.sk_createdateid LEFT JOIN v2n._time ct ON ct.sk = t.sk_createtimeid
    LEFT JOIN v2n._date xd ON xd.sk = t.sk_closedateid LEFT JOIN v2n._time xt ON xt.sk = t.sk_closetimeid
    LEFT JOIN v2n._date xdf ON xdf.sk = t.sk_closedateid_fx LEFT JOIN v2n._time xtf ON xtf.sk = t.sk_closetimeid_fx;

-- ======================= FactHoldings =======================
CREATE OR REPLACE TABLE v2n.FactHoldings AS
SELECT CAST(h.TradeID AS BIGINT) AS tradeid, CAST(h.CurrentTradeID AS BIGINT) AS currenttradeid,
    cu.CustomerID AS cust_customerid, cu.EffectiveDate AS cust_effdate, a.AccountID AS acct_accountid, a.EffectiveDate AS acct_effdate,
    s.Symbol AS sec_symbol, s.EffectiveDate AS sec_effdate, c.CompanyID AS co_companyid, c.EffectiveDate AS co_effdate,
    xd.d AS closedate, xt.t AS closetime, xd.d AS closedate_fx, xt.t AS closetime_fx, h.CurrentPrice AS currentprice, h.CurrentHolding AS currentholding
FROM gold.FactHoldings h
    LEFT JOIN gold.DimCustomer cu ON cu.SK_CustomerID = h.SK_CustomerID LEFT JOIN gold.DimAccount a ON a.SK_AccountID = h.SK_AccountID
    LEFT JOIN gold.DimSecurity s ON s.SK_SecurityID = h.SK_SecurityID LEFT JOIN gold.DimCompany c ON c.SK_CompanyID = h.SK_CompanyID
    LEFT JOIN v2n._date xd ON xd.sk = h.SK_DateID LEFT JOIN v2n._time xt ON xt.sk = h.SK_TimeID;
CREATE OR REPLACE TABLE dbtn.FactHoldings AS
SELECT CAST(h.tradeid AS BIGINT) AS tradeid, CAST(h.currenttradeid AS BIGINT) AS currenttradeid,
    h.cust_customerid, h.cust_effdate, h.acct_accountid, h.acct_effdate, h.sec_symbol, h.sec_effdate, h.co_companyid, h.co_effdate,
    xd.d AS closedate, xt.t AS closetime, xdf.d AS closedate_fx, xtf.t AS closetime_fx, h.currentprice, h.currentholding
FROM dbt.FactHoldings h
    LEFT JOIN v2n._date xd ON xd.sk = h.sk_dateid LEFT JOIN v2n._time xt ON xt.sk = h.sk_timeid
    LEFT JOIN v2n._date xdf ON xdf.sk = h.sk_dateid_fx LEFT JOIN v2n._time xtf ON xtf.sk = h.sk_timeid_fx;

-- ======================= FactCashBalances =======================
CREATE OR REPLACE TABLE v2n.FactCashBalances AS
SELECT a.AccountID AS accountid, d.d AS datevalue, cu.CustomerID AS cust_customerid, cu.EffectiveDate AS cust_effdate,
    a.EffectiveDate AS acct_effdate, CAST(f.Cash AS DOUBLE) AS cash
FROM gold.FactCashBalances f
    LEFT JOIN gold.DimAccount a ON a.SK_AccountID = f.SK_AccountID LEFT JOIN gold.DimCustomer cu ON cu.SK_CustomerID = f.SK_CustomerID
    LEFT JOIN v2n._date d ON d.sk = f.SK_DateID;
CREATE OR REPLACE TABLE dbtn.FactCashBalances AS
SELECT ct_accountid AS accountid, datevalue, cust_customerid, cust_effdate, acct_effdate, CAST(cash AS DOUBLE) AS cash
FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY ct_accountid, datevalue ORDER BY acct_effdate DESC NULLS LAST) AS rn FROM dbt.FactCashBalances)
WHERE rn = 1;

-- ======================= Financial =======================
CREATE OR REPLACE TABLE v2n.Financial AS
SELECT c.CompanyID AS companyid, f.FI_YEAR AS fi_year, f.FI_QTR AS fi_qtr, c.EffectiveDate AS co_effdate, f.FI_QTR_START_DATE AS fi_qtr_start_date,
    CAST(f.FI_REVENUE AS DOUBLE) AS fi_revenue, CAST(f.FI_NET_EARN AS DOUBLE) AS fi_net_earn, CAST(f.FI_BASIC_EPS AS DOUBLE) AS fi_basic_eps,
    CAST(f.FI_DILUT_EPS AS DOUBLE) AS fi_dilut_eps, CAST(f.FI_MARGIN AS DOUBLE) AS fi_margin, CAST(f.FI_INVENTORY AS DOUBLE) AS fi_inventory,
    CAST(f.FI_ASSETS AS DOUBLE) AS fi_assets, CAST(f.FI_LIABILITY AS DOUBLE) AS fi_liability, CAST(f.FI_OUT_BASIC AS DOUBLE) AS fi_out_basic,
    CAST(f.FI_OUT_DILUT AS DOUBLE) AS fi_out_dilut
FROM gold.Financial f LEFT JOIN gold.DimCompany c ON c.SK_CompanyID = f.SK_CompanyID;
CREATE OR REPLACE TABLE dbtn.Financial AS
SELECT companyid, fi_year, fi_qtr, co_effdate, fi_qtr_start_date, fi_revenue, fi_net_earn, fi_basic_eps, fi_dilut_eps, fi_margin, fi_inventory,
    fi_assets, fi_liability, CAST(fi_out_basic AS DOUBLE) AS fi_out_basic, CAST(fi_out_dilut AS DOUBLE) AS fi_out_dilut
FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY companyid, fi_year, fi_qtr ORDER BY co_effdate DESC) AS rn FROM dbt.Financial)
WHERE rn = 1;

-- ======================= Prospect =======================
CREATE OR REPLACE TABLE v2n.Prospect AS
SELECT p.AgencyID AS agencyid, rd.d AS recorddate, ud.d AS updatedate, p.BatchID AS batchid, p.IsCustomer AS iscustomer, p.LastName AS lastname,
    p.FirstName AS firstname, p.MiddleInitial AS middleinitial, p.Gender AS gender, p.AddressLine1 AS addressline1, p.AddressLine2 AS addressline2,
    p.PostalCode AS postalcode, p.City AS city, p.State AS state, p.Country AS country, p.Phone AS phone, p.Income AS income,
    p.numberCars AS numbercars, p.numberChildren AS numberchildren, p.MaritalStatus AS maritalstatus, p.Age AS age, p.CreditRating AS creditrating,
    p.OwnOrRentFlag AS ownorrentflag, p.Employer AS employer, p.numberCreditCards AS numbercreditcards, p.NetWorth AS networth,
    p.MarketingNameplate AS marketingnameplate, p.MarketingNameplate AS marketingnameplate_nz
FROM gold.Prospect p LEFT JOIN v2n._date rd ON rd.sk = p.SK_RecordDateID LEFT JOIN v2n._date ud ON ud.sk = p.SK_UpdateDateID;
CREATE OR REPLACE TABLE dbtn.Prospect AS
SELECT p.agencyid, rd.d AS recorddate, ud.d AS updatedate, p.batchid, p.iscustomer, p.lastname, p.firstname, p.middleinitial, p.gender,
    p.addressline1, p.addressline2, p.postalcode, p.city, p.state, p.country, p.phone, p.income, p.numbercars, p.numberchildren,
    p.maritalstatus, p.age, p.creditrating, p.ownorrentflag, p.employer, p.numbercreditcards, p.networth,
    p.marketingnameplate, NULLIF(p.marketingnameplate, '') AS marketingnameplate_nz
FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY agencyid ORDER BY iscustomer DESC) AS rn FROM dbt.Prospect) p
    LEFT JOIN v2n._date rd ON rd.sk = p.sk_recorddateid LEFT JOIN v2n._date ud ON ud.sk = p.sk_updatedateid
WHERE p.rn = 1;
