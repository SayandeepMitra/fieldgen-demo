"""Turn the gold audit into (1) a findings table with live evidence and (2) a per-column clean-subset definition.

Inputs : deliverables/tpcdi_populated.duckdb (gold-populated target), gold_audit_results.csv (official audit run),
         deliverables/tpcdi_column_mapping.csv (rule_reliable = R1-gold lineage review), pipeline/null_control_results.json.
Outputs: deliverables/gold_audit_findings.csv   one row per finding: check, mechanism, evidence rows/total, scope
         deliverables/tpcdi_clean_subset.csv    one row per populated column: tier + all reasons

Tiers (first match wins, evidence-ordered):
  known_defect   rule_reliable = no          (gold lineage review: hardcoded FKs, invented thresholds, ...)
  audit_flagged  implicated by a failed official audit check or an independent invariant below
  fk_entity_only surrogate key points at the right ENTITY but a date-invalid version (audit F04-F06): fine under the
                 project's "same entity = right" grading rule, not under exact-SK grading
  weak           NULL-control scores >= 20 % (an answer of NULL already gets partial credit; exact still meaningful, lift is not)
  clean          none of the above AND its table's row set passes the audit
  clean_column   column is clean but its TABLE's row set deviates from the audit (valid for expression-level swap-in
                 grading; NOT valid as a table-level / end-to-end target until the gold is repaired)
Run: python3 -I build_clean_subset.py
"""
import csv, json, os
import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(os.path.dirname(HERE), "deliverables")
import gold_version as _gv
DB = _gv.GOLD_DB
con = duckdb.connect(DB, read_only=True)


def one(sql):
    return con.execute(sql).fetchone()[0]


# --- audit expectations from DIGen's own audit files (Batch 1) -------------------------------------------------------
import glob
STAGING = os.path.join(os.path.dirname(HERE), "tpcdi", "tpcdi-kit", "staging", "3")
A = {}
for f in glob.glob(os.path.join(STAGING, "Batch1", "*_audit.csv")):
    for r in list(csv.reader(open(f)))[1:]:
        if len(r) >= 5 and r[0].strip() and r[4].strip():
            A[(r[0].strip(), r[3].strip())] = A.get((r[0].strip(), r[3].strip()), 0) + int(float(r[4]))

# --- findings: (id, check name in the official audit or 'independent', mechanism, scope, evidence sql -> (bad,total)) ----
RANGE = "c.EffectiveDate <= {a}.EffectiveDate and {a}.EndDate <= c.EndDate"
CANCELED_SQL = "select count(*) from DimTrade where Status = 'Canceled'"
F = []


def add(fid, check, mechanism, level, cols, bad_sql, tot_sql, note=""):
    F.append(dict(id=fid, source_check=check, mechanism=mechanism, level=level, columns=cols,
                  bad=one(bad_sql), total=one(tot_sql), note=note))


add("F01", "DimAccount Status", "gold writes ACTIVE/INACTIVE; audit (and spec 3.2) allow only Active/Inactive", "column",
    ["DimAccount.Status"], "select count(*) from DimAccount where Status not in ('Active','Inactive')", "select count(*) from DimAccount")
add("F02", "DimCustomer Status", "same as F01", "column", ["DimCustomer.Status"],
    "select count(*) from DimCustomer where Status not in ('Active','Inactive')", "select count(*) from DimCustomer")
add("F03", "DimCompany SPrating", "generator injects invalid ratings (FWSPRatingErrPct=10%); the ETL must NULL them, the gold passes them through", "column",
    ["DimCompany.SPrating"],
    "select count(*) from DimCompany where SPrating is not null and SPrating not in ('AAA','AA','A','BBB','BB','B','CCC','CC','C','D','AA+','A+','BBB+','BB+','B+','CCC+','AA-','A-','BBB-','BB-','B-','CCC-')",
    "select count(*) from DimCompany")
add("F04", "DimSecurity SK_CompanyID", "FK points at a company version whose date range does not cover the security row", "fk_version",
    ["DimSecurity.SK_CompanyID"],
    f"select count(*) from DimSecurity a where not exists(select 1 from DimCompany c where a.SK_CompanyID=c.SK_CompanyID and {RANGE.format(a='a')})",
    "select count(*) from DimSecurity")
add("F05", "DimAccount SK_CustomerID", "FK points at a customer version whose date range does not cover the account row", "fk_version",
    ["DimAccount.SK_CustomerID"],
    f"select count(*) from DimAccount a where not exists(select 1 from DimCustomer c where a.SK_CustomerID=c.SK_CustomerID and {RANGE.format(a='a')})",
    "select count(*) from DimAccount")
add("F06", "FactCashBalances SK_CustomerID", "FK points at a customer version not valid on the balance date", "fk_version",
    ["FactCashBalances.SK_CustomerID"],
    """select count(*) from FactCashBalances f where not exists(select 1 from DimCustomer c join DimDate d on d.SK_DateID=f.SK_DateID
       where c.SK_CustomerID=f.SK_CustomerID and c.EffectiveDate<=d.DateValue and d.DateValue<=c.EndDate)""",
    "select count(*) from FactCashBalances")
# MarketingNameplate: the six conditional rules published in the audit script (official thresholds).
MN = """ (  ((COALESCE(NetWorth,0)>1000000 or COALESCE(Income,0)>200000) and COALESCE(MarketingNameplate,'') not like '%HighValue%')
          or ((COALESCE(NumberChildren,0)>3 or COALESCE(NumberCreditCards,0)>5) and COALESCE(MarketingNameplate,'') not like '%Expenses%')
          or (COALESCE(Age,0)>45 and COALESCE(MarketingNameplate,'') not like '%Boomer%')
          or ((COALESCE(Income,50000)<50000 or COALESCE(CreditRating,600)<600 or COALESCE(NetWorth,100000)<100000) and COALESCE(MarketingNameplate,'') not like '%MoneyAlert%')
          or ((COALESCE(NumberCars,0)>3 or COALESCE(NumberCreditCards,0)>7) and COALESCE(MarketingNameplate,'') not like '%Spender%')
          or ((COALESCE(Age,25)<25 and COALESCE(NetWorth,0)>1000000) and COALESCE(MarketingNameplate,'') not like '%Inherited%') ) """
add("F07", "Prospect MarketingNameplate", "gold's thresholds differ from the spec's published rules (rows violating >=1 official rule)", "column",
    ["Prospect.MarketingNameplate"], f"select count(*) from Prospect where {MN}", "select count(*) from Prospect",
    "official rule set: spec Clause 4.5 / audit script; also feeds DimCustomer.MarketingNameplate")
KC = "upper(COALESCE({a}.FirstName,'')||COALESCE({a}.LastName,'')||COALESCE({a}.AddressLine1,'')||COALESCE({a}.AddressLine2,'')||COALESCE({a}.PostalCode,''))"
add("F08", "DimCustomer demographic fields",
    "Prospect-derived fields are carried from the older version onto the new version of a customer whose name/address changed; "
    "a per-version derivation would drop the match (all misses are multi-version customers)", "column",
    ["DimCustomer.AgencyID", "DimCustomer.CreditRating", "DimCustomer.NetWorth", "DimCustomer.MarketingNameplate"],
    f"""select count(*) from DimCustomer c where c.IsCurrent=1 and c.AgencyID is not null and not exists(
        select 1 from Prospect p where {KC.format(a='p')}={KC.format(a='c')})""",
    "select count(*) from DimCustomer where IsCurrent=1 and AgencyID is not null",
    "DimCustomer.Income shares the mechanism but is not tested by the audit: flagged as 'suspect'")
add("F09", "DimAccount EndDate / Overlap / consolidation",
    "same-day versions are not consolidated (spec 4.4.1.5): identical EffectiveDate for one AccountID, so EndDate/IsCurrent depend on tie order", "column",
    ["DimAccount.EffectiveDate", "DimAccount.EndDate", "DimAccount.IsCurrent"],
    """select count(*) from DimAccount a where exists(select 1 from DimAccount b where a.AccountID=b.AccountID and a.SK_AccountID<>b.SK_AccountID and a.EffectiveDate=b.EffectiveDate)""",
    "select count(*) from DimAccount")
add("F10", "DimAccount row count", "account versions that should follow customer updates/inactivations are missing (audit minimum from C_NEW, CA_*, C_UPDCUST, C_INACT)", "table",
    ["DimAccount.*"], "select 0", "select 1",
    f"rows {one('select count(*) from DimAccount')} < audit minimum {A[('DimCustomer','C_NEW')]+A[('DimAccount','CA_ADDACCT')]+A[('DimAccount','CA_CLOSEACCT')]+A[('DimAccount','CA_UPDACCT')]+A[('DimCustomer','C_UPDCUST')]+A[('DimCustomer','C_INACT')]-A[('DimCustomer','C_ID_HIST')]-A[('DimAccount','CA_ID_HIST')]}")
F[-1]["bad"], F[-1]["total"] = one("select count(*) from DimAccount"), (A[('DimCustomer','C_NEW')]+A[('DimAccount','CA_ADDACCT')]+A[('DimAccount','CA_CLOSEACCT')]+A[('DimAccount','CA_UPDACCT')]+A[('DimCustomer','C_UPDCUST')]+A[('DimCustomer','C_INACT')]-A[('DimCustomer','C_ID_HIST')]-A[('DimAccount','CA_ID_HIST')])
if _gv.VERSION == "v2":      # F10 is "rows below the audit minimum"; F11/F12 "duplicated keys / rows != audit". 0 = repaired
    F[-1]["bad"] = max(0, F[-1]["total"] - F[-1]["bad"])
add("F11", "DimTrade distinct keys / canceled trades",
    "one row per TradeHistory EVENT (982,180 = TH_Records) instead of one per trade; canceled trades are counted twice", "table",
    ["DimTrade.*"], "select count(*) from DimTrade", "select count(distinct TradeID) from DimTrade",
    f"bad=rows, total=distinct TradeID (audit T_Records={A[('DimTrade','T_Records')]}); "
    f"Canceled rows {one(CANCELED_SQL)} vs audit {A[('DimTrade','T_CanceledTrades')]}")
add("F12", "FactHoldings CurrentTradeID (+ row count)",
    "consequence of F11: the join to the duplicated DimTrade multiplies holdings rows (audit HH_RECORDS expected)", "table",
    ["FactHoldings.*"], "select count(*) from FactHoldings", f"select {A[('FactHoldings','HH_RECORDS')]}",
    "bad=rows, total=audit HH_RECORDS; CurrentTradeID values themselves all exist in DimTrade")
if _gv.VERSION == "v2":
    F[-2]["bad"] = F[-2]["bad"] - F[-2]["total"]                       # F11: rows - distinct TradeID (0 when one row per trade)
    F[-1]["bad"] = abs(F[-1]["bad"] - F[-1]["total"])                  # F12: |rows - audit HH_RECORDS|

# --- independent invariants the audit script cannot see ---------------------------------------------------------------
mapping = {(r["target_table"], r["target_column"]): r for r in csv.DictReader(open(_gv.MAPPING_CSV))}
populated = [(t, c) for (t, c), r in mapping.items() if r["table_status"] == "populated"]
const_fk = []
for t, c in populated:
    # entity FKs only: a date FK can legitimately be constant (e.g. Prospect is one snapshot); an entity FK never is
    if c in ("SK_CustomerID", "SK_AccountID", "SK_SecurityID", "SK_CompanyID", "SK_BrokerID") and t not in ("DimAccount", "DimSecurity", "DimCompany", "DimCustomer", "DimBroker"):
        n, nd = con.execute(f'select count(*), count(distinct "{c}") from "{t}"').fetchone()
        if n > 1 and nd <= 1:
            const_fk.append(f"{t}.{c}")
for k in const_fk:
    t, c = k.split(".")
    F.append(dict(id="I01", source_check="independent: constant surrogate key", mechanism="FK column has a single distinct value over the whole table "
                  "(hardcoded); the audit's date-range join cannot detect it when that key's range covers every date", level="column",
                  columns=[k], bad=one(f'select count(*) from "{t}"'), total=one(f'select count(*) from "{t}"'), note=""))

# Negative finding, recorded on purpose: does the gold's OUTPUT contradict the spec's "Not NULL" column descriptions?
import re
specdesc = json.load(open(os.path.join(D, "tpcdi_spec_target_descriptions.json")))
nn_cols = [(t, c) for t, c in populated if re.search(r"\bNot NULL\b", specdesc.get(f"{t}.{c}", ""), re.I)]
nn_viol = [(t, c) for t, c in nn_cols if one(f'select count(*)-count("{c}") from "{t}"') > 0]
F.append(dict(id="N01", source_check="independent: spec Not-NULL conformance", level="info", columns=[], bad=len(nn_viol), total=len(nn_cols),
              mechanism="spec Clause 3.2 'Not NULL' columns that contain NULLs in the gold output (0 = none). NULLs that exist only in the "
                        "intermediate CTE where an expression is swapped in are required by the gold's later COALESCE merges and are not output defects.",
              note="violations: " + ",".join(f"{t}.{c}" for t, c in nn_viol)))

with open(os.path.join(D, "gold_audit_findings" + _gv.SUFFIX + ".csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["id", "source_check", "level", "columns", "bad_rows", "total_rows", "pct", "mechanism", "note"])
    for f in F:
        w.writerow([f["id"], f["source_check"], f["level"], ";".join(f["columns"]), f["bad"], f["total"],
                    round(100 * f["bad"] / f["total"], 2) if f["total"] else "", f["mechanism"], f["note"]])

# --- per-column tiers -------------------------------------------------------------------------------------------------
nc = json.load(open(os.path.join(HERE, "null_control_results" + __import__("gold_version").SUFFIX + ".json")))
col_flags, fkv_flags, table_flags = {}, {}, {}
for f in F:
    if f["bad"] == 0:        # a finding with no violating rows (all of them in v2) flags nothing
        continue
    for k in f["columns"]:
        if k.endswith(".*"):
            table_flags.setdefault(k[:-2], []).append(f["id"])
        elif f["level"] == "fk_version":
            fkv_flags.setdefault(k, []).append(f["id"])
        else:
            col_flags.setdefault(k, []).append(f["id"])
SUSPECT = {"DimCustomer.Income": "F08"}   # same mechanism as F08, not covered by the audit test
rows, counts = [], {}
for t, c in sorted(populated):
    k = f"{t}.{c}"
    m = mapping[(t, c)]
    reasons, tier = [], None
    if m["rule_reliable"] == "no":
        tier = "known_defect"; reasons.append("rule_reliable=no: " + (m["rule_issue"] or "")[:120])
    if k in col_flags:
        tier = tier or "audit_flagged"; reasons.append("audit/invariant " + ",".join(col_flags[k]))
    if k in fkv_flags:
        tier = tier or "fk_entity_only"; reasons.append("FK points at a date-invalid VERSION of the right entity (" + ",".join(fkv_flags[k]) + "): valid only under same-entity grading")
    if k in SUSPECT:
        tier = tier or "audit_flagged"; reasons.append(f"same mechanism as {SUSPECT[k]} (suspect, untested by audit)")
    nm = (nc.get(k) or {}).get("match_pct") or 0
    if tier is None and nm >= 20:
        tier = "weak"; reasons.append(f"NULL control already scores {nm}%")
    if tier is None:
        if t in table_flags:
            tier = "clean_column"; reasons.append("column ok; table row set deviates: " + ",".join(table_flags[t]))
        else:
            tier = "clean"
    counts[tier] = counts.get(tier, 0) + 1
    rows.append(dict(table=t, column=c, kind=m["column_kind"], tier=tier, null_control_pct=nm, table_rowset_ok=t not in table_flags,
                     reasons=" | ".join(reasons)))
with open(_gv.CLEAN_SUBSET_CSV, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)

print(f"{len(populated)} populated columns")
print("tier counts:", dict(sorted(counts.items(), key=lambda x: -x[1])))
print("\nfindings:")
for f in F:
    pct = f"{100*f['bad']/f['total']:.1f}%" if f["total"] else "-"
    print(f"  {f['id']} [{f['level']:6s}] {','.join(f['columns'])[:60]:60s} {f['bad']}/{f['total']} ({pct})")
print("\nconstant-FK detector found:", const_fk)
dk = sorted(k for k in (f"{t}.{c}" for t, c in populated) if mapping[tuple(k.split('.'))]["rule_reliable"] == "no")
print("rule_reliable=no columns not caught by the detector:", [k for k in dk if k not in const_fk])
print("detector hits not in rule_reliable=no:", [k for k in const_fk if k not in dk])
