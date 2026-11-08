"""Independent invariants for the repaired gold (v2) that the official TPC-DI audit does NOT test.

Each check re-derives a fact from Source.* (or from the spec) with SQL that is deliberately different from the ETL, then
compares it with the v2 target table. Output: deliverables/gold_v2_checks.csv (check, expected, actual, ok).
v1 is run through the same checks (--db v1) to show which of these were broken before the repair.

usage: python gold_checks_v2.py [--db PATH] [--out CSV]
"""
import argparse, csv, os
import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
DELIV = os.path.join(os.path.dirname(HERE), "deliverables")

CHECKS = [
    # (name, SQL returning ONE row (expected, actual))
    ("DimTrade: one row per Source.Trade",
     "select (select count(*) from Source.Trade), (select count(*) from DimTrade)"),
    ("DimTrade: Status = final Source.Trade status",
     "select 0, count(*) from DimTrade d join Source.Trade t on d.TradeID=t.T_ID join Source.StatusType s on s.ST_ID=t.T_ST_ID where d.Status<>s.ST_NAME"),
    ("DimTrade: trades with a close date = trades with a CMPT/CNCL history event",
     "select (select count(distinct TH_T_ID) from Source.TradeHistory where TH_ST_ID in ('CMPT','CNCL')), (select count(*) from DimTrade where SK_CloseDateID is not null)"),
    ("DimTrade: create date never after close date",
     "select 0, count(*) from DimTrade a join DimDate c on c.SK_DateID=a.SK_CreateDateID join DimDate d on d.SK_DateID=a.SK_CloseDateID where c.DateValue>d.DateValue"),
    ("DimTrade: SK_AccountID is a version of the trade's own account",
     "select 0, count(*) from DimTrade d join Source.Trade t on t.T_ID=d.TradeID left join DimAccount a on a.SK_AccountID=d.SK_AccountID where a.AccountID is distinct from t.T_CA_ID"),
    ("DimTrade: SK_SecurityID is a version of the trade's own symbol",
     "select 0, count(*) from DimTrade d join Source.Trade t on t.T_ID=d.TradeID left join DimSecurity s on s.SK_SecurityID=d.SK_SecurityID where s.Symbol is distinct from t.T_S_SYMB"),
    ("DimTrade: more than one distinct SK_AccountID (not hardcoded)",
     "select 1, (select count(distinct SK_AccountID) > 1 from DimTrade)::int"),
    ("FactHoldings: one row per Source.HoldingHistory",
     "select (select count(*) from Source.HoldingHistory), (select count(*) from FactHoldings)"),
    ("FactHoldings: SK_DateID/TimeID = the trade's close keys",
     "select 0, count(*) from FactHoldings f join DimTrade t on t.TradeID=f.CurrentTradeID where f.SK_DateID is distinct from t.SK_CloseDateID or f.SK_TimeID is distinct from t.SK_CloseTimeID"),
    ("FactHoldings: CurrentPrice keeps cents (= Source.Trade.T_TRADE_PRICE)",
     "select 0, count(*) from FactHoldings f join Source.Trade t on t.T_ID=f.CurrentTradeID where f.CurrentPrice is distinct from t.T_TRADE_PRICE"),
    ("FactCashBalances: last balance of each account = sum of its transactions on days with a row",
     "select 0, count(*) from (select a.AccountID, max_by(f.Cash, d.DateValue) last_cash from FactCashBalances f join DimAccount a on a.SK_AccountID=f.SK_AccountID join DimDate d on d.SK_DateID=f.SK_DateID group by 1) x "
     "join (select CT_CA_ID, sum(CT_AMT) tot from Source.CashTransaction group by 1) y on y.CT_CA_ID=x.AccountID where abs(x.last_cash-y.tot)>0.005"),
    ("FactCashBalances: one row per account per day",
     "select 0, count(*) from (select a.AccountID, f.SK_DateID, count(*) n from FactCashBalances f join DimAccount a on a.SK_AccountID=f.SK_AccountID group by 1,2 having count(*)>1)"),
    ("DimSecurity: every Source SEC symbol present",
     "select (select count(distinct Symbol) from Source.FinwireSEC where RecType='SEC'), (select count(distinct Symbol) from DimSecurity)"),
    ("DimSecurity: every SEC record's PTS day starts a version of its symbol",
     "select 0, count(*) from (select Symbol, strptime(PTS,'%Y%m%d-%H%M%S')::DATE d from Source.FinwireSEC where RecType='SEC') s where not exists (select 1 from DimSecurity x where x.Symbol=s.Symbol and x.EffectiveDate=s.d)"),
    ("DimCompany: no invalid SPrating, isLowGrade NULL iff SPrating NULL",
     "select 0, count(*) from DimCompany where (SPrating is null) <> (isLowGrade is null)"),
    ("DimCompany: no empty-string text values",
     "select 0, count(*) from DimCompany where trim(AddressLine2)='' or trim(Country)='' or trim(City)='' or trim(PostalCode)=''"),
    ("DimCustomer: Gender = upper(raw M/F) else U (latest source value)",
     "select 0, count(*) from DimCustomer c where Gender not in ('M','F','U')"),
    ("DimCustomer: M/F share consistent with source (>= 40% of customers have M or F)",
     "select 1, (select count(*) filter (where Gender in ('M','F'))*1.0/count(*) >= 0.40 from DimCustomer where IsCurrent)::int"),
    ("DimCustomer: demographic fields only on the current version",
     "select 0, count(*) from DimCustomer where IsCurrent=false and (AgencyID is not null or CreditRating is not null or NetWorth is not null or MarketingNameplate is not null)"),
    ("DimCustomer: Prospect-matched current customers carry AgencyID",
     "select (select count(*) from Source.Prospect p join DimCustomer c on c.IsCurrent and upper(c.FirstName)=upper(trim(p.FirstName)) and upper(c.LastName)=upper(trim(p.LastName)) and upper(c.AddressLine1)=upper(trim(p.AddressLine1)) and upper(coalesce(c.AddressLine2,''))=upper(coalesce(trim(p.AddressLine2),'')) and upper(c.PostalCode)=upper(trim(p.PostalCode))),"
     " (select count(*) from DimCustomer where IsCurrent and AgencyID is not null)"),
    ("DimCustomer: at most one version per customer per day",
     "select 0, count(*) from (select CustomerID, EffectiveDate from DimCustomer group by 1,2 having count(*)>1)"),
    ("DimCustomer: every customer has exactly one current version",
     "select (select count(distinct CustomerID) from DimCustomer), (select count(*) from DimCustomer where IsCurrent)"),
    ("DimAccount: every account has exactly one current version",
     "select (select count(distinct AccountID) from DimAccount), (select count(*) from DimAccount where IsCurrent)"),
    ("DimAccount: one row per account per day",
     "select 0, count(*) from (select AccountID, EffectiveDate from DimAccount group by 1,2 having count(*)>1)"),
    ("DimAccount: a CLOSEACCT account's current version is Inactive",
     "select 0, count(*) from DimAccount a where IsCurrent and AccountID in (select Acc.CA_ID from Source.AccountXML Acc join Source.CustomerXML C on C.Customer_Id=Acc.Customer_Id join Source.ActionXML A on A.Action_Id=C.Action_Id where A.ActionType='CLOSEACCT') and Status<>'Inactive'"),
    ("DimAccount: an inactive customer's current accounts are Inactive",
     "select 0, count(*) from DimAccount a join DimCustomer c on c.SK_CustomerID=a.SK_CustomerID where a.IsCurrent and c.Status='Inactive' and a.Status<>'Inactive'"),
    ("Financial: one row per Source.FinwireFIN",
     "select (select count(*) from Source.FinwireFIN), (select count(*) from Financial)"),
    ("Financial: SK_CompanyID is a version of the company named in the record",
     "select 0, count(*) from Financial f join DimCompany c using(SK_CompanyID) where c.CompanyID not in (select try_cast(CoNameOrCIK as bigint) from Source.FinwireFIN where try_cast(CoNameOrCIK as bigint) is not null) and c.Name not in (select CoNameOrCIK from Source.FinwireFIN)"),
    ("Prospect: MarketingNameplate uses only spec tags in spec order",
     "select 0, count(*) from Prospect where MarketingNameplate is not null and regexp_full_match(MarketingNameplate, '(HighValue)?(\\+?Expenses)?(\\+?Boomer)?(\\+?MoneyAlert)?(\\+?Spender)?(\\+?Inherited)?') = false"),
    ("Prospect: IsCustomer only for current Active customers",
     "select 0, count(*) from Prospect p where IsCustomer and not exists (select 1 from DimCustomer c where c.IsCurrent and c.Status='Active' and upper(c.LastName)=upper(trim(p.LastName)) and upper(c.FirstName)=upper(trim(p.FirstName)))"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(DELIV, "tpcdi_populated_v2.duckdb"))
    ap.add_argument("--out", default=os.path.join(DELIV, "gold_v2_checks.csv"))
    a = ap.parse_args()
    con = duckdb.connect(a.db, read_only=True)
    rows, bad = [], 0
    for name, sql in CHECKS:
        try:
            exp_, act = con.execute(sql).fetchone()
            ok = (exp_ == act)
            err = ""
        except Exception as e:
            exp_, act, ok, err = None, None, False, str(e)[:120].replace("\n", " ")
        bad += (not ok)
        rows.append({"check": name, "expected": exp_, "actual": act, "ok": ok, "error": err})
        print(f"{'OK  ' if ok else 'FAIL'}  {name:90s} expected={exp_} actual={act} {err}")
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, ["check", "expected", "actual", "ok", "error"])
        w.writeheader(); w.writerows(rows)
    print(f"\n{len(CHECKS)-bad}/{len(CHECKS)} independent checks pass ({a.db})")


if __name__ == "__main__":
    main()
