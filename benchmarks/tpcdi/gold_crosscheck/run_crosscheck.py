#!/usr/bin/env python3
"""Cross-validate the repaired TPC-DI gold (v2) against a Batch-1 DuckDB port of the dbt (Snowflake) TPC-DI implementation.

    python run_crosscheck.py [--refresh-copy]

Steps (all output lands in this directory; nothing outside it is modified):
  1. copy deliverables/tpcdi_populated_v2.duckdb -> v2_copy.duckdb (once; --refresh-copy to redo) and attach it READ-ONLY
  2. build crosscheck_results.duckdb: views Source.* / gold.* over the copy, run dbt_port.sql (schema dbt.*), normalize.sql
     (schemas v2n.* / dbtn.* with natural-key-translated FKs)
  3. compare every table at row/column level -> tables cmp_summary, cmp_columns, cmp_examples, cmp_diffs, raw_stats
  4. print + write results_summary.md / cmp_columns.csv
Deeper root-cause queries live in rootcause.py (run automatically at the end, output -> rootcause_output.txt).
"""
import argparse, os, shutil, subprocess, sys, time
import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DB = os.path.abspath(os.path.join(HERE, '..', 'deliverables', 'tpcdi_populated_v2.duckdb'))
COPY_DB = os.path.join(HERE, 'v2_copy.duckdb')
RES_DB = os.path.join(HERE, 'crosscheck_results.duckdb')

SOURCE_TABLES = ['AccountXML', 'ActionXML', 'AddressXML', 'BatchDate', 'C_PHONE_1_XML', 'C_PHONE_2_XML', 'C_PHONE_3_XML', 'CashTransaction',
                 'ContactInfoXML', 'CustomerXML', 'Date', 'FinwireCMP', 'FinwireFIN', 'FinwireSEC', 'HR', 'HoldingHistory', 'Industry',
                 'NameXML', 'Prospect', 'StatusType', 'TaxInfoXML', 'TaxRate', 'Time', 'Trade', 'TradeHistory', 'TradeType']
GOLD_TABLES = ['DimAccount', 'DimBroker', 'DimCompany', 'DimCustomer', 'DimSecurity', 'DimTrade', 'FactCashBalances', 'FactHoldings',
               'Financial', 'Prospect']

# table -> (key columns, exact columns, numeric (tolerance) columns)
SPECS = {
    'DimCompany': (['companyid', 'effectivedate'],
                   ['status', 'name', 'industry', 'sprating', 'islowgrade', 'ceo', 'description', 'foundingdate', 'addressline1', 'addressline2',
                    'postalcode', 'city', 'stateprov', 'country', 'iscurrent', 'enddate'], []),
    'DimCustomer': (['customerid', 'effectivedate'],
                    ['status', 'taxid', 'lastname', 'firstname', 'middleinitial', 'gender', 'tier', 'dob', 'addressline1', 'addressline2',
                     'postalcode', 'city', 'stateprov', 'country', 'phone1', 'phone2', 'phone3', 'phone1_fx', 'phone2_fx', 'phone3_fx',
                     'email1', 'email2', 'nationaltaxratedesc', 'nationaltaxrate', 'localtaxratedesc', 'localtaxrate', 'agencyid',
                     'creditrating', 'networth', 'marketingnameplate', 'iscurrent', 'enddate'], []),
    'DimAccount': (['accountid', 'effectivedate'],
                   ['brokerid', 'cust_customerid', 'cust_effdate', 'status', 'accountdesc', 'taxstatus', 'enddate'], []),
    'DimSecurity': (['symbol', 'effectivedate'],
                    ['issue', 'status', 'name', 'exchangeid', 'companyid', 'co_effdate', 'sharesoutstanding', 'firsttrade',
                     'firsttradeonexchange', 'enddate'], ['dividend']),
    'DimTrade': (['tradeid'],
                 ['brokerid', 'createdate', 'createtime', 'closedate', 'closetime', 'closedate_fx', 'closetime_fx', 'status', 'type',
                  'cashflag', 'sec_symbol', 'sec_effdate', 'co_companyid', 'co_effdate', 'quantity', 'cust_customerid', 'cust_effdate',
                  'acct_accountid', 'acct_effdate', 'executedby'],
                 ['bidprice', 'tradeprice', 'fee', 'commission', 'tax']),
    'FactHoldings': (['tradeid', 'currenttradeid'],
                     ['cust_customerid', 'cust_effdate', 'acct_accountid', 'acct_effdate', 'sec_symbol', 'sec_effdate', 'co_companyid',
                      'co_effdate', 'closedate', 'closetime', 'closedate_fx', 'closetime_fx', 'currentholding'], ['currentprice']),
    'FactCashBalances': (['accountid', 'datevalue'], ['cust_customerid', 'cust_effdate', 'acct_effdate'], ['cash']),
    'Financial': (['companyid', 'fi_year', 'fi_qtr'], ['co_effdate', 'fi_qtr_start_date'],
                  ['fi_revenue', 'fi_net_earn', 'fi_basic_eps', 'fi_dilut_eps', 'fi_margin', 'fi_inventory', 'fi_assets', 'fi_liability',
                   'fi_out_basic', 'fi_out_dilut']),
    'Prospect': (['agencyid'],
                 ['recorddate', 'updatedate', 'batchid', 'iscustomer', 'lastname', 'firstname', 'middleinitial', 'gender', 'addressline1',
                  'addressline2', 'postalcode', 'city', 'state', 'country', 'phone', 'maritalstatus', 'ownorrentflag', 'employer',
                  'marketingnameplate', 'marketingnameplate_nz'],
                 ['income', 'numbercars', 'numberchildren', 'age', 'creditrating', 'numbercreditcards', 'networth']),
}
# raw (pre de-duplication) dbt tables for the row-count statistics
RAW_DBT = {'DimCompany': 'dbt.DimCompany', 'DimCustomer': 'dbt.DimCustomer', 'DimAccount': 'dbt.DimAccount', 'DimSecurity': 'dbt.DimSecurity',
           'DimTrade': 'dbt.DimTrade', 'FactHoldings': 'dbt.FactHoldings', 'FactCashBalances': 'dbt.FactCashBalances',
           'Financial': 'dbt.Financial', 'Prospect': 'dbt.Prospect'}
GOLD_ROWS = {t: f'gold.{t}' for t in SPECS}
MAX_DIFFS = 200000


def q(con, sql, *a):
    return con.execute(sql, *a).fetchall()


def build(con, refresh):
    if refresh or not os.path.exists(COPY_DB):
        if os.path.exists(COPY_DB):
            os.remove(COPY_DB)
        if subprocess.call(['cp', '-c', SRC_DB, COPY_DB]) != 0:   # APFS clone, falls back to plain copy
            shutil.copyfile(SRC_DB, COPY_DB)
    con.execute(f"ATTACH '{COPY_DB}' AS v2 (READ_ONLY)")
    con.execute('CREATE SCHEMA IF NOT EXISTS Source; CREATE SCHEMA IF NOT EXISTS gold;')
    for t in SOURCE_TABLES:
        con.execute(f'CREATE OR REPLACE VIEW Source."{t}" AS SELECT * FROM v2.Source."{t}"')
    for t in GOLD_TABLES:
        con.execute(f'CREATE OR REPLACE VIEW gold."{t}" AS SELECT * FROM v2.main."{t}"')
    for f in ('dbt_port.sql', 'normalize.sql'):
        t0 = time.time()
        con.execute(open(os.path.join(HERE, f)).read())
        print(f'  ran {f} in {time.time() - t0:.1f}s')


def compare(con):
    con.execute('''CREATE OR REPLACE TABLE cmp_summary (tbl VARCHAR, v2_rows BIGINT, dbt_raw_rows BIGINT, v2_keys BIGINT, dbt_keys BIGINT,
                   matched BIGINT, only_v2 BIGINT, only_dbt BIGINT)''')
    con.execute('''CREATE OR REPLACE TABLE cmp_columns (tbl VARCHAR, col VARCHAR, matched BIGINT, agree BIGINT, pct DOUBLE)''')
    con.execute('''CREATE OR REPLACE TABLE cmp_examples (tbl VARCHAR, col VARCHAR, k VARCHAR, v2 VARCHAR, dbt VARCHAR)''')
    con.execute('''CREATE OR REPLACE TABLE cmp_diffs (tbl VARCHAR, col VARCHAR, k VARCHAR, v2 VARCHAR, dbt VARCHAR)''')
    con.execute('''CREATE OR REPLACE TABLE only_keys (tbl VARCHAR, side VARCHAR, k VARCHAR)''')
    for tbl, (keys, exact, num) in SPECS.items():
        kexpr = " || '|' || ".join(f"COALESCE(CAST(a.{k} AS VARCHAR), 'NULL')" for k in keys)
        join = ' AND '.join(f'a.{k} IS NOT DISTINCT FROM b.{k}' for k in keys)
        nrows_v2 = q(con, f'SELECT COUNT(*) FROM {GOLD_ROWS[tbl]}')[0][0]
        nrows_dbt = q(con, f'SELECT COUNT(*) FROM {RAW_DBT[tbl]}')[0][0]
        nk_v2 = q(con, f'SELECT COUNT(*) FROM v2n.{tbl}')[0][0]
        nk_dbt = q(con, f'SELECT COUNT(*) FROM dbtn.{tbl}')[0][0]
        matched = q(con, f'SELECT COUNT(*) FROM v2n.{tbl} a JOIN dbtn.{tbl} b ON {join}')[0][0]
        con.execute('INSERT INTO cmp_summary VALUES (?,?,?,?,?,?,?,?)',
                    [tbl, nrows_v2, nrows_dbt, nk_v2, nk_dbt, matched, nk_v2 - matched, nk_dbt - matched])
        con.execute(f'''INSERT INTO only_keys SELECT '{tbl}', 'v2', {kexpr} FROM v2n.{tbl} a ANTI JOIN dbtn.{tbl} b ON {join}''')
        kexpr_b = kexpr.replace('a.', 'b.')
        con.execute(f'''INSERT INTO only_keys SELECT '{tbl}', 'dbt', {kexpr_b} FROM dbtn.{tbl} b ANTI JOIN v2n.{tbl} a ON {join}''')
        for col in exact + num:
            if col in num:
                neq = (f'NOT ((a.{col} IS NULL AND b.{col} IS NULL) OR (a.{col} IS NOT NULL AND b.{col} IS NOT NULL AND '
                       f'ABS(CAST(a.{col} AS DOUBLE) - CAST(b.{col} AS DOUBLE)) <= 1e-6 * GREATEST(1.0, ABS(CAST(a.{col} AS DOUBLE)))))')
            else:
                neq = f'NOT (a.{col} IS NOT DISTINCT FROM b.{col})'
            bad = q(con, f'SELECT COUNT(*) FROM v2n.{tbl} a JOIN dbtn.{tbl} b ON {join} WHERE {neq}')[0][0]
            con.execute('INSERT INTO cmp_columns VALUES (?,?,?,?,?)', [tbl, col, matched, matched - bad, 100.0 * (matched - bad) / matched if matched else None])
            if bad:
                con.execute(f'''INSERT INTO cmp_diffs SELECT '{tbl}', '{col}', {kexpr}, CAST(a.{col} AS VARCHAR), CAST(b.{col} AS VARCHAR)
                                FROM v2n.{tbl} a JOIN dbtn.{tbl} b ON {join} WHERE {neq} LIMIT {MAX_DIFFS}''')
                con.execute(f'''INSERT INTO cmp_examples SELECT '{tbl}', '{col}', {kexpr}, CAST(a.{col} AS VARCHAR), CAST(b.{col} AS VARCHAR)
                                FROM v2n.{tbl} a JOIN dbtn.{tbl} b ON {join} WHERE {neq} ORDER BY RANDOM() LIMIT 5''')


def report(con):
    out = []
    out.append('| table | v2 rows | dbt raw rows | v2 keys | dbt keys | matched | only-v2 | only-dbt |')
    out.append('|---|---|---|---|---|---|---|---|')
    for r in q(con, 'SELECT * FROM cmp_summary'):
        out.append('| ' + ' | '.join(f'{x:,}' if isinstance(x, int) else str(x) for x in r) + ' |')
    out.append('')
    out.append('Per-column agreement over matched keys (only columns < 100% listed; all others are 100.00%):')
    out.append('')
    out.append('| table | column | matched | agree | % |')
    out.append('|---|---|---|---|---|')
    for r in q(con, 'SELECT tbl, col, matched, agree, pct FROM cmp_columns WHERE agree < matched ORDER BY tbl, pct'):
        out.append(f'| {r[0]} | {r[1]} | {r[2]:,} | {r[3]:,} | {r[4]:.2f} |')
    txt = '\n'.join(out)
    open(os.path.join(HERE, 'results_summary.md'), 'w').write(txt + '\n')
    con.execute(f"COPY cmp_columns TO '{os.path.join(HERE, 'cmp_columns.csv')}' (HEADER)")
    con.execute(f"COPY cmp_summary TO '{os.path.join(HERE, 'cmp_summary.csv')}' (HEADER)")
    print(txt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--refresh-copy', action='store_true')
    ap.add_argument('--skip-rootcause', action='store_true')
    args = ap.parse_args()
    if os.path.exists(RES_DB):
        os.remove(RES_DB)
    con = duckdb.connect(RES_DB)
    print('building ported dbt tables ...')
    build(con, args.refresh_copy)
    print('comparing ...')
    compare(con)
    report(con)
    con.close()
    if not args.skip_rootcause and os.path.exists(os.path.join(HERE, 'rootcause.py')):
        subprocess.call([sys.executable, os.path.join(HERE, 'rootcause.py')])


if __name__ == '__main__':
    main()
