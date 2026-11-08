#!/usr/bin/env python3
"""Root-cause evidence queries for REPORT.md. Reads crosscheck_results.duckdb (+ the v2 copy); writes rootcause_output.txt."""
import os
import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
con = duckdb.connect(os.path.join(HERE, 'crosscheck_results.duckdb'), read_only=True)
con.execute(f"ATTACH '{os.path.join(HERE, 'v2_copy.duckdb')}' AS v2 (READ_ONLY)")

CHECKS = [
 ('A1 DimAccount.Status: (owning-customer version status, v2 account status, dbt account status) -> versions',
  """SELECT c.status AS cust_status, v.status AS v2_status, d.status AS dbt_status, COUNT(*) n
     FROM v2n.DimAccount v JOIN dbtn.DimAccount d USING (accountid, effectivedate)
     JOIN v2n.DimCustomer c ON c.customerid = v.cust_customerid AND c.effectivedate = v.cust_effdate GROUP BY ALL ORDER BY 1,2,3"""),
 ('A2 the 899 status disagreements: versions starting ON the customer INACT date vs LATER versions (= UPDACCT after INACT, which dbt re-activates)',
  """WITH inact AS (SELECT customerid, effectivedate AS inact_date FROM v2n.DimCustomer WHERE status = 'Inactive'),
     diff AS (SELECT v.*, i.inact_date FROM v2n.DimAccount v JOIN dbtn.DimAccount d USING (accountid, effectivedate)
              JOIN inact i ON i.customerid = v.cust_customerid WHERE v.status <> d.status)
     SELECT COUNT(*) n_total, COUNT(*) FILTER (WHERE effectivedate = inact_date) start_on_inact_date,
            COUNT(*) FILTER (WHERE effectivedate > inact_date) after_inact_date, COUNT(*) FILTER (WHERE effectivedate < inact_date) before_inact_date FROM diff"""),
 ('A2b account actions that occur AFTER the owning customer INACT in the source data (by ActionType)',
  """WITH inact AS (SELECT customerid, update_ts AS inact_ts FROM dbt.CustomerMgmtView WHERE ActionType = 'INACT')
     SELECT m.ActionType, COUNT(*) n FROM dbt.CustomerMgmtView m JOIN inact i ON i.customerid = m.customerid AND m.update_ts > i.inact_ts GROUP BY 1"""),
 ('A3 DimAccount versions by trigger (v2): account action day / customer UPDCUST-INACT day',
  """WITH acts AS (SELECT DISTINCT CAST(ca.accountid AS BIGINT) accountid, update_ts::DATE d FROM dbt.CustomerMgmtView ca WHERE ActionType IN ('NEW','ADDACCT','UPDACCT','CLOSEACCT')),
     cust AS (SELECT customerid, effectivedate d, status FROM v2n.DimCustomer)
     SELECT COUNT(*) total_versions,
       COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM acts a WHERE a.accountid=v.accountid AND a.d=v.effectivedate)) account_action_versions,
       COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM acts a WHERE a.accountid=v.accountid AND a.d=v.effectivedate)) customer_triggered_only_versions
     FROM v2n.DimAccount v"""),
 ('A4 dbt DimAccount raw defects: zero-length rows / NULL-account rows (customers without accounts) / total',
  """SELECT COUNT(*) FILTER (WHERE effectivedate >= enddate) zero_length, COUNT(*) FILTER (WHERE accountid IS NULL) null_account_rows, COUNT(*) total FROM dbt.DimAccount"""),
 ('A5 dbt DimAccount has no IsCurrent column; v2 has (not compared)', "SELECT 'dbt.DimAccount columns' AS what, string_agg(column_name, ', ') AS cols FROM (DESCRIBE dbt.DimAccount)"),
 ('A6 account action earlier on the SAME DAY as a customer UPDCUST/INACT change (spec 4.5.1.3 uses EffectiveDate <= date <= EndDate, i.e. ambiguous on boundary days; both impls use half-open and take the later customer version)',
  """WITH ca AS (SELECT accountid, update_ts FROM dbt.CustomerMgmtView WHERE ActionType IN ('NEW','ADDACCT','UPDACCT','CLOSEACCT')),
     cc AS (SELECT customerid, update_ts FROM dbt.CustomerMgmtView WHERE ActionType IN ('UPDCUST','INACT')),
     ac AS (SELECT DISTINCT accountid, customerid FROM dbt.CustomerMgmtView WHERE accountid IS NOT NULL)
     SELECT COUNT(*) n FROM ca JOIN ac USING (accountid) JOIN cc ON cc.customerid = ac.customerid AND CAST(cc.update_ts AS DATE) = CAST(ca.update_ts AS DATE) AND ca.update_ts < cc.update_ts"""),
 ('B1 same-day consolidation exercised? (customer-days with >1 DimCustomer-relevant event; account-days with >1 account event)',
  """SELECT (SELECT COUNT(*) FROM (SELECT customerid, update_ts::DATE FROM dbt.CustomerMgmtView WHERE ActionType IN ('NEW','UPDCUST','INACT') GROUP BY 1,2 HAVING COUNT(*)>1)) AS customer_days,
            (SELECT COUNT(*) FROM (SELECT accountid, update_ts::DATE FROM dbt.CustomerMgmtView WHERE ActionType IN ('NEW','ADDACCT','UPDACCT','CLOSEACCT') GROUP BY 1,2 HAVING COUNT(*)>1)) AS account_days,
            (SELECT COUNT(*) FROM (SELECT companyid, effectivedate FROM dbt.DimCompany GROUP BY 1,2 HAVING COUNT(*)>1)) AS company_days,
            (SELECT COUNT(*) FROM (SELECT symbol, effectivedate FROM dbt.DimSecurity GROUP BY 1,2 HAVING COUNT(*)>1)) AS security_days"""),
 ('C1 DimCustomer Prospect-derived fields: (is latest version, v2 has AgencyID, dbt has AgencyID, equal) -> versions',
  """SELECT v.iscurrent, v.agencyid IS NOT NULL v2_has, d.agencyid IS NOT NULL dbt_has, v.agencyid IS NOT DISTINCT FROM d.agencyid equal, COUNT(*) n
     FROM v2n.DimCustomer v JOIN dbtn.DimCustomer d USING (customerid, effectivedate) GROUP BY ALL ORDER BY 1,2,3"""),
 ('C2 customers whose Prospect match exists only on an OLDER version (name/address changed afterwards) vs on latest',
  """WITH h AS (SELECT customerid, COUNT(*) FILTER (WHERE agencyid IS NOT NULL AND NOT iscurrent) hist, COUNT(*) FILTER (WHERE agencyid IS NOT NULL AND iscurrent) cur FROM dbtn.DimCustomer GROUP BY 1)
     SELECT COUNT(*) FILTER (WHERE hist>0 AND cur=0) hist_only_customers, COUNT(*) FILTER (WHERE hist>0 AND cur>0) hist_and_latest, COUNT(*) FILTER (WHERE hist=0 AND cur>0) latest_only FROM h"""),
 ('C3 current (latest) DimCustomer rows: Active/Inactive x has-AgencyID in v2 and dbt',
  """SELECT v.status, COUNT(*) n, COUNT(*) FILTER (WHERE v.agencyid IS NOT NULL) v2_has_prospect, COUNT(*) FILTER (WHERE d.agencyid IS NOT NULL) dbt_has_prospect
     FROM v2n.DimCustomer v JOIN dbtn.DimCustomer d USING (customerid, effectivedate) WHERE v.iscurrent GROUP BY 1"""),
 ('C4 Phone: dbt rows with NULL/stale phone because C_CTRY_CODE present (element-name typo CTRY_CODE) vs v2; versions whose phone differs',
  """SELECT COUNT(*) FILTER (WHERE d.phone1 IS DISTINCT FROM v.phone1) phone1_diff,
            COUNT(*) FILTER (WHERE d.phone1 IS DISTINCT FROM v.phone1 AND d.phone1 IS NULL) dbt_null,
            COUNT(*) FILTER (WHERE d.phone1 IS DISTINCT FROM v.phone1 AND d.phone1 IS NOT NULL) dbt_stale_or_other,
            COUNT(*) FILTER (WHERE d.phone1_fx IS DISTINCT FROM v.phone1) phone1_diff_after_typo_fix
     FROM v2n.DimCustomer v JOIN dbtn.DimCustomer d USING (customerid, effectivedate)"""),
 ('C5 Gender: (v2, dbt) value pairs', "SELECT v.gender v2, d.gender dbt, COUNT(*) n FROM v2n.DimCustomer v JOIN dbtn.DimCustomer d USING (customerid, effectivedate) GROUP BY ALL ORDER BY 3 DESC"),
 ('C6 Source gender codes other than M/F (case-insensitive) mapped to U by both', "SELECT COUNT(*) FILTER (WHERE UPPER(TRIM(C_GNDR)) NOT IN ('M','F')) non_mf, COUNT(*) FILTER (WHERE C_GNDR IS NULL) null_gender, COUNT(*) total FROM Source.CustomerXML"),
 ('D1 DimCompany: dbt keeps blanks as empty strings, v2 as NULL (counts of empty-string cells in dbt)',
  """SELECT COUNT(*) FILTER (WHERE addressline2='') addressline2, COUNT(*) FILTER (WHERE country='') country, COUNT(*) FILTER (WHERE name='') name_, COUNT(*) FILTER (WHERE ceo='') ceo,
            COUNT(*) FILTER (WHERE description='') description, COUNT(*) FILTER (WHERE postalcode='') postalcode, COUNT(*) FILTER (WHERE city='') city,
            COUNT(*) FILTER (WHERE stateprov='') stateprov, COUNT(*) FILTER (WHERE addressline1='') addressline1, COUNT(*) FROM dbt.DimCompany"""),
 ('D2 DimCompany invalid SPrating: rows with NULL SPrating / NULL isLowGrade in v2 and dbt (both NULL them)',
  """SELECT (SELECT COUNT(*) FROM v2n.DimCompany WHERE sprating IS NULL) v2_null_sp, (SELECT COUNT(*) FROM dbtn.DimCompany WHERE sprating IS NULL) dbt_null_sp,
            (SELECT COUNT(*) FROM v2n.DimCompany WHERE islowgrade IS NULL) v2_null_lowgrade, (SELECT COUNT(*) FROM dbtn.DimCompany WHERE islowgrade IS NULL) dbt_null_lowgrade"""),
 ('D3 DimCompany versions: companies with >1 version / rows', "SELECT COUNT(DISTINCT companyid) companies, COUNT(*) n_rows, COUNT(*) FILTER (WHERE NOT iscurrent) historical_rows FROM v2n.DimCompany"),
 ('E1 DimSecurity.Dividend: v2 column is INTEGER (target schema), spec says VALUE_T = SNUM(10,2). rows disagreeing / rounding error',
  """SELECT COUNT(*) FILTER (WHERE ABS(v.dividend - d.dividend) > 1e-6) disagree, COUNT(*) FILTER (WHERE v.dividend <> ROUND(d.dividend)) not_equal_to_round, MAX(ABS(v.dividend - d.dividend)) max_abs_err, COUNT(*) total
     FROM v2n.DimSecurity v JOIN dbtn.DimSecurity d USING (symbol, effectivedate)"""),
 ('E2 DimSecurity.Dividend declared type in v2 and in the spec', "SELECT column_name, data_type FROM information_schema.columns WHERE table_catalog='v2' AND table_name='DimSecurity' AND column_name IN ('Dividend','SharesOutstanding')"),
 ('E3 DimSecurity CoNameOrCIK matching: SEC records numeric(CIK) / by name; max ShOut',
  """SELECT COUNT(*) FILTER (WHERE TRY_CAST(CoNameOrCIK AS BIGINT) IS NOT NULL) by_cik, COUNT(*) FILTER (WHERE TRY_CAST(CoNameOrCIK AS BIGINT) IS NULL) by_name, COUNT(*) sec_records, COUNT(DISTINCT Symbol) symbols, MAX(TRY_CAST(ShOut AS BIGINT)) max_shout FROM Source.FinwireSEC"""),
 ('E4 DimCompany.Name uniqueness (a name-match is unambiguous iff no name is shared by two CIKs / no name is numeric)',
  """SELECT (SELECT COUNT(*) FROM (SELECT name FROM (SELECT DISTINCT companyid, name FROM dbt.DimCompany) GROUP BY 1 HAVING COUNT(*)>1)) names_shared_by_2_ciks,
            (SELECT COUNT(*) FROM dbt.DimCompany WHERE TRY_CAST(name AS BIGINT) IS NOT NULL) numeric_names"""),
 ('E5 DimSecurity versions: SEC records vs versions; versions of symbols with a single SEC record (= purely DimCompany-triggered)',
  """SELECT (SELECT COUNT(*) FROM Source.FinwireSEC) sec_records, (SELECT COUNT(*) FROM v2n.DimSecurity) v2_versions, (SELECT COUNT(*) FROM dbtn.DimSecurity) dbt_versions,
            (SELECT COUNT(*) FROM v2n.DimSecurity WHERE symbol IN (SELECT Symbol FROM Source.FinwireSEC GROUP BY 1 HAVING COUNT(*)=1)) versions_of_single_sec_symbols,
            (SELECT COUNT(*) FROM Source.FinwireSEC s WHERE NOT EXISTS (SELECT 1 FROM v2n.DimCompany c WHERE (CASE WHEN TRY_CAST(s.CoNameOrCIK AS BIGINT) IS NOT NULL THEN c.companyid = TRY_CAST(s.CoNameOrCIK AS BIGINT) ELSE c.name = s.CoNameOrCIK END)
                AND c.effectivedate <= CAST(strptime(s.PTS,'%Y%m%d-%H%M%S') AS DATE) AND CAST(strptime(s.PTS,'%Y%m%d-%H%M%S') AS DATE) < c.enddate)) sec_without_company_at_pts"""),
 ('F1 DimTrade close keys: (v2 close == create date, dbt close == create date, v2 NULL close, dbt NULL close) and create-key agreement',
  """SELECT COUNT(*) FILTER (WHERE v.closedate = v.createdate) v2_close_eq_create, COUNT(*) FILTER (WHERE d.closedate = d.createdate) dbt_close_eq_create,
            COUNT(*) FILTER (WHERE v.closedate IS NULL) v2_close_null, COUNT(*) FILTER (WHERE d.closedate IS NULL) dbt_close_null,
            COUNT(*) FILTER (WHERE v.createdate IS DISTINCT FROM d.createdate OR v.createtime IS DISTINCT FROM d.createtime) create_key_diff,
            COUNT(*) FILTER (WHERE v.closedate IS DISTINCT FROM d.closedate_fx OR v.closetime IS DISTINCT FROM d.closetime_fx) close_diff_after_fix, COUNT(*) total
     FROM v2n.DimTrade v JOIN dbtn.DimTrade d USING (tradeid)"""),
 ('F2 DimTrade by final Status: rows, rows with close-key disagreement, v2 close NULL',
  """SELECT v.status, COUNT(*) n, COUNT(*) FILTER (WHERE v.closedate IS DISTINCT FROM d.closedate) close_date_diff, COUNT(*) FILTER (WHERE v.closedate IS NULL) v2_null_close
     FROM v2n.DimTrade v JOIN dbtn.DimTrade d USING (tradeid) GROUP BY 1 ORDER BY 2 DESC"""),
 ('F3 DimTrade FK version agreement (SK_Security/Company/Account/Customer/Broker translated to natural key+EffectiveDate): rows disagreeing per FK',
  """SELECT COUNT(*) FILTER (WHERE v.sec_symbol IS DISTINCT FROM d.sec_symbol OR v.sec_effdate IS DISTINCT FROM d.sec_effdate) fk_security,
            COUNT(*) FILTER (WHERE v.co_companyid IS DISTINCT FROM d.co_companyid OR v.co_effdate IS DISTINCT FROM d.co_effdate) fk_company,
            COUNT(*) FILTER (WHERE v.acct_accountid IS DISTINCT FROM d.acct_accountid OR v.acct_effdate IS DISTINCT FROM d.acct_effdate) fk_account,
            COUNT(*) FILTER (WHERE v.cust_customerid IS DISTINCT FROM d.cust_customerid OR v.cust_effdate IS DISTINCT FROM d.cust_effdate) fk_customer,
            COUNT(*) FILTER (WHERE v.brokerid IS DISTINCT FROM d.brokerid) fk_broker, COUNT(*) total
     FROM v2n.DimTrade v JOIN dbtn.DimTrade d USING (tradeid)"""),
 ('F4 trades whose FK version differs from the version valid at trade close (shows the "earliest time encountered" rule matters): account / security',
  """SELECT COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM v2n.DimAccount a WHERE a.accountid = t.acct_accountid AND a.effectivedate <= t.closedate AND t.closedate < a.enddate AND a.effectivedate <> t.acct_effdate)) account_version_changed_before_close,
            COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM v2n.DimSecurity s WHERE s.symbol = t.sec_symbol AND s.effectivedate <= t.closedate AND t.closedate < s.enddate AND s.effectivedate <> t.sec_effdate)) security_version_changed_before_close,
            COUNT(*) FILTER (WHERE t.closedate IS NOT NULL) closed_trades
     FROM v2n.DimTrade t"""),
 ('G1 FactHoldings close keys: rows with SK_DateID disagreement before / after fixing dbt close-key bug',
  """SELECT COUNT(*) FILTER (WHERE v.closedate IS DISTINCT FROM d.closedate) date_diff, COUNT(*) FILTER (WHERE v.closetime IS DISTINCT FROM d.closetime) time_diff,
            COUNT(*) FILTER (WHERE v.closedate IS DISTINCT FROM d.closedate_fx OR v.closetime IS DISTINCT FROM d.closetime_fx) diff_after_fix, COUNT(*) total
     FROM v2n.FactHoldings v JOIN dbtn.FactHoldings d USING (tradeid, currenttradeid)"""),
 ('H1 FactCashBalances: (account, day) groups in Source vs rows in v2 / dbt; running balance disagreements',
  """SELECT (SELECT COUNT(*) FROM (SELECT CT_CA_ID, CAST(CT_DTS AS DATE) FROM Source.CashTransaction GROUP BY 1,2)) source_groups, (SELECT COUNT(*) FROM v2n.FactCashBalances) v2_rows,
            (SELECT COUNT(*) FROM dbtn.FactCashBalances) dbt_rows,
            (SELECT COUNT(*) FROM v2n.FactCashBalances v JOIN dbtn.FactCashBalances d USING (accountid, datevalue) WHERE ABS(v.cash - d.cash) > 0.005) cash_disagree"""),
 ('H2 FactCashBalances rows pointing at an Inactive DimAccount version (v2) / at an Inactive DimCustomer version',
  """SELECT COUNT(*) FILTER (WHERE a.status='Inactive') inactive_account_version, COUNT(*) FILTER (WHERE c.status='Inactive') inactive_customer_version, COUNT(*) total
     FROM v2n.FactCashBalances f JOIN v2n.DimAccount a ON a.accountid=f.accountid AND a.effectivedate=f.acct_effdate JOIN v2n.DimCustomer c ON c.customerid=f.cust_customerid AND c.effectivedate=f.cust_effdate"""),
 ('I1 Prospect.IsCustomer (v2, dbt) pairs', "SELECT v.iscustomer v2, d.iscustomer dbt, COUNT(*) n FROM v2n.Prospect v JOIN dbtn.Prospect d USING (agencyid) GROUP BY ALL"),
 ('I2 Prospect.IsCustomer disagreements that are Prospects matching an INACTIVE current customer',
  """SELECT COUNT(*) FROM v2n.Prospect v JOIN dbtn.Prospect d USING (agencyid) WHERE v.iscustomer <> d.iscustomer
       AND d.agencyid IN (SELECT agencyid FROM v2n.DimCustomer WHERE iscurrent AND status = 'Inactive' AND agencyid IS NOT NULL)"""),
 ('I3 Prospect.MarketingNameplate: (v2, dbt) value pairs where they differ (dbt gives empty string where no tag applies; spec 4.5.15: NULL)',
  """SELECT v.marketingnameplate v2, d.marketingnameplate dbt, COUNT(*) n FROM v2n.Prospect v JOIN dbtn.Prospect d USING (agencyid) WHERE v.marketingnameplate IS DISTINCT FROM d.marketingnameplate GROUP BY ALL"""),
 ('J1 Financial: SEC/FIN CoNameOrCIK numeric vs name; FIN rows with no DimCompany at PTS',
  """SELECT COUNT(*) FILTER (WHERE TRY_CAST(CoNameOrCIK AS BIGINT) IS NOT NULL) fin_by_cik, COUNT(*) FILTER (WHERE TRY_CAST(CoNameOrCIK AS BIGINT) IS NULL) fin_by_name, COUNT(*) total FROM Source.FinwireFIN"""),
 ('L1 dbt DimSecurity surrogate key = concat(exchangeid, dash, effectivedate) (NOT reproduced in the port): colliding key groups / rows involved',
  """SELECT COUNT(*) colliding_sk_groups, SUM(n) rows_involved, (SELECT COUNT(*) FROM dbt.DimSecurity) total_rows FROM (SELECT exchangeid, effectivedate, COUNT(*) n FROM dbt.DimSecurity GROUP BY 1,2 HAVING COUNT(*)>1)"""),
 ('C7 latest-version rows with a Prospect match where dbt nameplate is empty string and v2 is NULL',
  """SELECT COUNT(*) FROM v2n.DimCustomer v JOIN dbtn.DimCustomer d USING (customerid, effectivedate) WHERE v.iscurrent AND v.agencyid IS NOT NULL AND v.marketingnameplate IS DISTINCT FROM d.marketingnameplate"""),
 ('K1 DimBroker row counts (v2 vs dbt port) and BrokerID set equality',
  """SELECT (SELECT COUNT(*) FROM gold.DimBroker) v2_rows, (SELECT COUNT(*) FROM dbt.DimBroker) dbt_rows,
            (SELECT COUNT(*) FROM gold.DimBroker g ANTI JOIN dbt.DimBroker d ON g.BrokerID = d.brokerid) only_v2"""),
]

out = []
for title, sql in CHECKS:
    out.append('### ' + title)
    try:
        r = con.execute(sql)
        cols = [d[0] for d in r.description]
        rows = r.fetchall()
        out.append(' | '.join(cols))
        for row in rows:
            out.append(' | '.join(str(x) for x in row))
    except Exception as e:  # keep going
        out.append('ERROR: ' + str(e))
    out.append('')
open(os.path.join(HERE, 'rootcause_output.txt'), 'w').write('\n'.join(out))
print('\n'.join(out))
