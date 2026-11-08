"""Level-2 (table-level, end-to-end) grader for TPC-DI.

A pipeline submission is one SQL file per target table, run in a sandbox that holds only Source.* (targets empty).
This module compares the tables it produced (candidate DB) with the gold-populated tables (reference DB).

Row identity (borrowed from fieldgen's alignment idea, adapted to a warehouse with surrogate keys):
  * each target table has an IDENTITY: the natural-key columns that say which source entity a row came from
    (e.g. DimCustomer = CustomerID + EffectiveDate). Rows of candidate and reference are matched on it.
  * surrogate keys are never compared as numbers. A foreign SK column (SK_CustomerID in a fact table, SK_DateID, ...)
    is translated, on EACH side through that side's own dimension, to the natural key of the entity it points to
    ("right = points to the same entity"). A table's own generated SK is only checked for uniqueness / not NULL.
Per table:  L0 ran  |  L1 rows (recall, precision, duplicates, correct-rows)  |  L2 columns (agreement on matched
rows, and strict agreement over ALL reference rows, so missing rows count as wrong).
Tables whose gold row set is itself defective (audit finding) additionally get a COARSE identity score so a pipeline
that fixes the grain is not scored zero; those tables are flagged and kept out of the headline.

usage: python l2_grade.py --cand CAND.duckdb [--gold GOLD.duckdb] [--out DIR]
"""
import argparse, csv, json, os, re, sys, collections
import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
import gold_version as _gv                                   # TPCDI_GOLD=v1|v2 (default v1)
GOLD_DB = _gv.GOLD_DB
SUBSET = _gv.CLEAN_SUBSET_CSV
EXACT = 99.995

# table -> identity columns (+ coarse identity for tables whose gold grain is defective)
IDENTITY = {
    "DimDate": ["DateValue"], "DimTime": ["TimeValue"], "StatusType": ["ST_ID"], "TaxRate": ["TX_ID"],
    "TradeType": ["TT_ID"], "Industry": ["IN_ID"],
    "DimBroker": ["BrokerID"],
    "DimCompany": ["CompanyID"],
    "DimCustomer": ["CustomerID"],
    "DimAccount": ["AccountID"],
    "DimSecurity": ["Symbol"],
    "DimTrade": ["TradeID"],
    "FactCashBalances": ["SK_AccountID", "SK_DateID"],
    "FactHoldings": ["TradeID", "CurrentTradeID"],
    "Financial": ["SK_CompanyID", "FI_YEAR", "FI_QTR"],
    "Prospect": ["AgencyID"],
}
# A table can hold several rows per identity (SCD2 versions, one trade's events). Rows are paired k-th with k-th, ordered by
# these columns first (then by the whole row), so a wrong EffectiveDate costs that COLUMN, not the whole table's row match.
VERSION_ORDER = {"DimCompany": ["EffectiveDate"], "DimCustomer": ["EffectiveDate"], "DimAccount": ["EffectiveDate", "EndDate"],
                 "DimSecurity": ["EffectiveDate"], "DimTrade": ["SK_CreateDateID", "SK_CreateTimeID", "Status"],
                 "FactHoldings": ["SK_DateID", "SK_TimeID"]}
# Tables whose gold grain is defective (audit F10-F12): reported, extra "value exists for the key" score, kept out of the headline.
COARSE = {"DimAccount": ["AccountID"], "DimTrade": ["TradeID"], "FactHoldings": ["TradeID", "CurrentTradeID"]}
if _gv.VERSION == "v2":      # the repaired gold has the spec grain everywhere: nothing is flagged, all 16 tables are in the headline
    COARSE = {}
# dimension -> (surrogate key column, natural column the SK is translated to)
DIMS = {"DimCustomer": ("SK_CustomerID", "CustomerID"), "DimAccount": ("SK_AccountID", "AccountID"),
        "DimSecurity": ("SK_SecurityID", "Symbol"), "DimCompany": ("SK_CompanyID", "CompanyID"),
        "DimBroker": ("SK_BrokerID", "BrokerID"), "DimDate": ("SK_DateID", "DateValue"),
        "DimTime": ("SK_TimeID", "TimeValue")}
SK_REF = [(re.compile(r"SK_(Customer)ID$"), "DimCustomer"), (re.compile(r"SK_(Account)ID$"), "DimAccount"),
          (re.compile(r"SK_(Security)ID$"), "DimSecurity"), (re.compile(r"SK_(Company)ID$"), "DimCompany"),
          (re.compile(r"SK_(Broker)ID$"), "DimBroker"), (re.compile(r"SK_.*Date"), "DimDate"),
          (re.compile(r"SK_.*Time"), "DimTime")]
Q = lambda c: '"' + c + '"'


def fk_dim(table, col):
    """Dimension an SK column points to, or None (own generated SK, or not an SK)."""
    if not col.startswith("SK_"):
        return None
    for rx, dim in SK_REF:
        if rx.search(col):
            return None if (table == dim and DIMS[dim][0] == col) else dim
    return None


def is_self_sk(table, col):
    return table in DIMS and DIMS[table][0] == col


def norm(x):
    """Same leniency as the L1 grader (_norm): text, trimmed, lower-case; the typed columns already agree."""
    return f"lower(trim(CAST({x} AS VARCHAR)))"


def tables_in(con, schema="main"):
    return {t for (t,) in con.execute("select table_name from information_schema.tables where table_schema=?", [schema]).fetchall()}


def columns_of(con, db, table):
    return [r[0] for r in con.execute(
        "select column_name from information_schema.columns where table_catalog=? and table_schema='main' and table_name=? order by ordinal_position",
        [db, table]).fetchall()]


def grade_table(con, t, cs, ref_rows):
    idc = IDENTITY[t]
    id_expr = ", ".join(Q(c) for c in idc)
    order = ", ".join(Q(c) for c in VERSION_ORDER.get(t, []) + [c for c in cs if c not in VERSION_ORDER.get(t, [])])
    # identities can repeat (same-day versions): pair the k-th row of a group on both sides, in a deterministic order
    for side, name in (("g", "g1"), ("c", "c1")):
        con.execute(f"create or replace temp table {name} as select *, row_number() over (partition by {id_expr} order by {order}) as _rn from {side}_{t}")
    on = " AND ".join(f"g.{Q(c)} IS NOT DISTINCT FROM c.{Q(c)}" for c in idc) + " AND g._rn = c._rn"
    on_id = " AND ".join(f"g.{Q(c)} IS NOT DISTINCT FROM c.{Q(c)}" for c in idc)
    cand_n = con.execute("select count(*) from c1").fetchone()[0]
    ref_dup = ref_rows - con.execute(f"select count(distinct ({id_expr})) from g1").fetchone()[0]
    matched = con.execute(f"select count(*) from g1 g join c1 c on {on}").fetchone()[0]
    ids_in_ref = con.execute(f"select count(*) from c1 c where exists (select 1 from g1 g where {on_id})").fetchone()[0]
    res = {"ref_rows": ref_rows, "cand_rows": cand_n, "matched_rows": matched, "cand_duplicate_rows": ids_in_ref - matched,
           "ref_identity_repeats": ref_dup,
           "recall": round(100 * matched / ref_rows, 3) if ref_rows else None,
           "precision": round(100 * matched / cand_n, 3) if cand_n else None,
           "rows_correct": bool(cand_n == ref_rows and matched == ref_rows)}
    # columns: strict (over all reference rows) and over matched rows
    scored = [c for c in cs if c not in idc and not is_self_sk(t, c)]
    colres = {}
    if scored:
        parts = ", ".join(f"count(*) filter (where g.{Q(c)} IS NOT DISTINCT FROM c.{Q(c)}) AS a{i}" for i, c in enumerate(scored))
        row = con.execute(f"select {parts} from g1 g join c1 c on {on}").fetchone()
        for i, c in enumerate(scored):
            colres[c] = {"agree_matched": row[i], "pct_ref": round(100 * row[i] / ref_rows, 3) if ref_rows else None,
                         "pct_matched": round(100 * row[i] / matched, 3) if matched else None}
    for c in idc:   # identity columns: equal on matched rows by construction -> their score is the row recall
        colres[c] = {"agree_matched": matched, "pct_ref": res["recall"], "pct_matched": 100.0 if matched else None, "identity": True}
    # coarse (defective-grain tables): a reference row counts if some candidate row with the same coarse key has the value
    if t in COARSE:
        ck = COARSE[t]
        con_on = " AND ".join(f"g.{Q(c)} IS NOT DISTINCT FROM c.{Q(c)}" for c in ck)
        cc = {}
        for c in scored:
            n = con.execute(f"select count(*) from g_{t} g where exists (select 1 from c_{t} c where {con_on} and g.{Q(c)} IS NOT DISTINCT FROM c.{Q(c)})").fetchone()[0]
            cc[c] = round(100 * n / ref_rows, 3)
        res["coarse_key"] = ck
        res["coarse_pct_ref"] = cc
    res["columns"] = colres
    return res


def grade(cand_db, gold_db=GOLD_DB, only=None):
    con = duckdb.connect(":memory:")
    con.execute(f"ATTACH '{gold_db}' AS g_db (READ_ONLY)")
    con.execute(f"ATTACH '{cand_db}' AS c_db (READ_ONLY)")
    tabs = {"g": {t for (t,) in con.execute("select table_name from information_schema.tables where table_catalog='g_db' and table_schema='main'").fetchall()},
            "c": {t for (t,) in con.execute("select table_name from information_schema.tables where table_catalog='c_db' and table_schema='main'").fetchall()}}
    cols = {t: columns_of(con, "g_db", t) for t in tabs["g"] if only is None or t in only}
    gold_notnull = collections.defaultdict(list)
    for t, c in con.execute("select table_name, column_name from information_schema.columns where table_catalog='g_db' and table_schema='main' and is_nullable='NO'").fetchall():
        gold_notnull[t].append(c)
    ginfo = materialise_side(con, "g", "g_db", tabs["g"], cols)
    cinfo = materialise_side(con, "c", "c_db", tabs["c"], cols)
    out = {"tables": {}}
    for t, idc in IDENTITY.items():
        if t not in tabs["g"] or (only is not None and t not in only):
            continue
        ref_rows = con.execute(f"select count(*) from g_{t}").fetchone()[0]
        if ref_rows == 0:
            continue
        if t not in tabs["c"]:
            out["tables"][t] = {"ref_rows": ref_rows, "cand_rows": 0, "status": "MISSING", "rows_correct": False,
                                "recall": 0.0, "precision": None, "columns": {c: {"pct_ref": 0.0, "pct_matched": None} for c in cols[t]}}
            continue
        r = grade_table(con, t, cols[t], ref_rows)
        r["status"] = "OK"
        if t in DIMS:
            sk = cinfo.get(t, {})
            n, nd, nn = sk.get("own_sk_rows", 0), sk.get("own_sk_distinct", 0), sk.get("own_sk_null", 0)
            keygen_ok = n > 0 and nd == n and nn == 0
            r["own_sk"] = {"column": DIMS[t][0], "unique_not_null": keygen_ok}
            r["columns"][DIMS[t][0]] = {"pct_ref": 100.0 if (keygen_ok and r["cand_rows"] == ref_rows) else (0.0 if not keygen_ok else r["recall"]),
                                        "pct_matched": 100.0 if keygen_ok else 0.0, "generated_key": True}
        r["constraints"] = constraint_report(con, t, cols[t], gold_notnull.get(t, []))
        out["tables"][t] = r
    return out


def materialise_side(con, side, db, tables, cols):
    """like materialise(), with the catalog alias (db) separate from the short side prefix"""
    for dim, (sk, nat) in DIMS.items():
        if dim in tables:
            con.execute(f"""create table {side}_map_{dim} as
                select {Q(sk)} as sk, min({norm(Q(nat))}) as nat from {db}.main.{dim} group by 1""")
        else:
            con.execute(f"create table {side}_map_{dim} (sk BIGINT, nat VARCHAR)")
    info = {}
    for t, cs in cols.items():
        if t not in tables:
            continue
        sel, joins = [], []
        for i, c in enumerate(cs):
            d = fk_dim(t, c)
            if d:
                sel.append(f"m{i}.nat AS {Q(c)}")
                joins.append(f"LEFT JOIN {side}_map_{d} m{i} ON t.{Q(c)} = m{i}.sk")
            else:
                sel.append(f"{norm('t.' + Q(c))} AS {Q(c)}")
        con.execute(f"create table {side}_{t} as select {', '.join(sel)} from {db}.main.{t} t {' '.join(joins)}")
        info[t] = {}
        if t in DIMS:
            sk = DIMS[t][0]
            n, nd, nn = con.execute(f"select count(*), count(distinct {Q(sk)}), count(*) filter (where {Q(sk)} is null) from {db}.main.{t}").fetchone()
            info[t] = {"own_sk_rows": n, "own_sk_distinct": nd, "own_sk_null": nn}
    return info


def constraint_report(con, t, cs, notnull):
    """What a constraint-enforcing warehouse would have rejected: NULLs in NOT NULL columns, and foreign SKs pointing at no
    dimension row (counted on the candidate's own dimension)."""
    nn = {}
    for c in notnull:
        n = con.execute(f"select count(*) from c_db.main.{t} where {Q(c)} is null").fetchone()[0]
        if n:
            nn[c] = n
    dang = {}
    for c in cs:
        d = fk_dim(t, c)
        if d:
            n = con.execute(f"select count(*) from c_db.main.{t} t left join c_map_{d} m on t.{Q(c)} = m.sk where t.{Q(c)} is not null and m.sk is null").fetchone()[0]
            if n:
                dang[c] = n
    return {"not_null_violations": nn, "dangling_fk": dang}


def summarise(result):
    """Headline numbers: tables with correct rows, exact columns overall / core171 / hard37, by reference quality."""
    sub = {f"{r['table']}.{r['column']}": r for r in csv.DictReader(open(SUBSET))}
    core = {k for k, r in sub.items() if r["tier"] in ("clean", "clean_column", "fk_entity_only")}
    hard = set()
    bp = os.path.join(HERE, _gv.RUNS_SUBDIR, "baseline_trivial", "graded.json")
    if os.path.exists(bp):
        ok = {r["key"]: (r["status"] == "EXECUTED" and (r["match_pct"] or 0) >= EXACT) for r in json.load(open(bp)) if r["model"] == "trivial_name"}
        hard = {k for k in core if not ok.get(k)}
    ex = {}
    for t, r in result["tables"].items():
        for c, v in r.get("columns", {}).items():
            ex[f"{t}.{c}"] = (v.get("pct_ref") or 0) >= EXACT
    tabs = result["tables"]
    sound = [t for t in tabs if t not in COARSE]
    s = {"tables_graded": len(tabs),
         "tables_rows_correct": sum(1 for t in tabs if tabs[t]["rows_correct"]),
         "tables_rows_correct_sound_reference": f"{sum(1 for t in sound if tabs[t]['rows_correct'])}/{len(sound)}",
         "columns_exact_all": f"{sum(ex.get(k, False) for k in sub)}/{len(sub)}",
         "columns_exact_core171": f"{sum(ex.get(k, False) for k in core)}/{len(core)}",
         "columns_exact_hard37": f"{sum(ex.get(k, False) for k in hard)}/{len(hard)}" if hard else None,
         "columns_exact_core": f"{sum(ex.get(k, False) for k in core)}/{len(core)}",          # same numbers, size-neutral key names
         "columns_exact_hard": f"{sum(ex.get(k, False) for k in hard)}/{len(hard)}" if hard else None,
         "constraint_violations": {"not_null_cells": sum(sum(r.get("constraints", {}).get("not_null_violations", {}).values()) for r in tabs.values()),
                                   "dangling_fk_cells": sum(sum(r.get("constraints", {}).get("dangling_fk", {}).values()) for r in tabs.values())},
         "defective_reference_tables_flagged": sorted(COARSE)}
    return s


def render(result, summary):
    L = ["# L2 report", "", "| table | ref rows | cand rows | recall % | precision % | dup | rows correct | cols exact / scored |", "|---|---:|---:|---:|---:|---:|---|---|"]
    for t, r in result["tables"].items():
        cols = r.get("columns", {})
        ne = sum(1 for v in cols.values() if (v.get("pct_ref") or 0) >= EXACT)
        flag = " (defective ref. grain)" if t in COARSE else ""
        L.append(f"| {t}{flag} | {r['ref_rows']} | {r['cand_rows']} | {r.get('recall')} | {r.get('precision')} | {r.get('cand_duplicate_rows', '')} | {r['rows_correct']} | {ne}/{len(cols)} |")
    L += ["", "## Headline", ""] + [f"- {k}: {v}" for k, v in summary.items()]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", required=True); ap.add_argument("--gold", default=GOLD_DB); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    res = grade(a.cand, a.gold)
    summ = summarise(res)
    res["summary"] = summ
    json.dump(res, open(os.path.join(a.out, "l2_scores.json"), "w"), indent=1)
    rep = render(res, summ)
    open(os.path.join(a.out, "l2_report.md"), "w").write(rep)
    print(rep)


if __name__ == "__main__":
    main()
