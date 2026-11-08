"""
Phase D, first real pass: execute each candidate SQL expression for real against Source.* data,
compare to the already-verified-correct value sitting in the populated T (tpcdi_populated.duckdb).

Only implemented for "value-like" columns with a clean natural key to join back on (passthrough_
copy/rename/retype/lookup join/conditional/constant against DimCompany or Industry, keyed by
CompanyID/IN_ID). generated_key/SCD history/aggregate/copies_generated_key need a different,
structural grading approach not built yet -- those are reported as "not graded" here, not as
pass/fail, to avoid a false precision.
"""
import csv
import json
import re
import duckdb

RESULTS_PATH = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))), "pipeline/subset_results.json")
DB_PATH = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))), "deliverables/tpcdi_populated.duckdb")
MAPPING_CSV = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))), "deliverables/tpcdi_column_mapping.csv")

# Natural-key-gradable columns only, in this first pass. Each entry: how to build a FROM clause
# that exposes the alias the models tend to use, the natural key to join back on, and the
# ground-truth column read straight from the already-populated, already-verified T table.
GRADABLE = {
    "Industry.IN_NAME": {
        "from_clause": "Source.Industry",
        "natural_key_source": "IN_ID",
        "gt_table": "Industry",
        "gt_key": "IN_ID",
        "gt_column": "IN_NAME",
    },
    "DimCompany.CEO": {
        "from_clause": "Source.FinwireCMP CMP",
        "natural_key_source": "CAST(CMP.CIK AS INTEGER)",
        "gt_table": "DimCompany WHERE IsCurrent",
        "gt_key": "CompanyID",
        "gt_column": "CEO",
    },
    "DimCompany.FoundingDate": {
        "from_clause": "Source.FinwireCMP CMP",
        "natural_key_source": "CAST(CMP.CIK AS INTEGER)",
        "gt_table": "DimCompany WHERE IsCurrent",
        "gt_key": "CompanyID",
        "gt_column": "FoundingDate",
    },
    "DimCompany.Industry": {
        "from_clause": "Source.FinwireCMP CMP JOIN Source.Industry I ON CMP.IndustryID = I.IN_ID",
        "natural_key_source": "CAST(CMP.CIK AS INTEGER)",
        "gt_table": "DimCompany WHERE IsCurrent",
        "gt_key": "CompanyID",
        "gt_column": "Industry",
    },
    "DimCompany.isLowGrade": {
        "from_clause": "Source.FinwireCMP CMP",
        "natural_key_source": "CAST(CMP.CIK AS INTEGER)",
        "gt_table": "DimCompany WHERE IsCurrent",
        "gt_key": "CompanyID",
        "gt_column": "isLowGrade",
    },
    "DimCustomer.NationalTaxRateDesc": {
        "from_clause": "Source.TaxInfoXML TXML JOIN Source.CustomerXML CXML ON TXML.Customer_Id = CXML.Customer_Id JOIN Source.TaxRate TaxRate ON TXML.C_NAT_TX_ID = TaxRate.TX_ID",
        "natural_key_source": "CAST(CXML.C_ID AS INTEGER)",
        "gt_table": "DimCustomer WHERE IsCurrent",
        "gt_key": "CustomerID",
        "gt_column": "NationalTaxRateDesc",
    },
}


def clean_sql(raw_sql):
    """Strip markdown/prose artifacts extract_sql() didn't fully remove (we saw
    '**SQL expression:** `...`' and similar get through) and any trailing 'AS alias'."""
    s = raw_sql.strip()
    s = re.sub(r"^\*\*.*?\*\*:?\s*", "", s)  # leading "**SQL expression:**" etc.
    s = re.sub(r"^(SQL expression:?|Reasoning:?)\s*", "", s, flags=re.IGNORECASE)
    s = s.strip("`").strip()
    s = re.sub(r"\s+AS\s+\w+\s*$", "", s, flags=re.IGNORECASE)  # trailing alias
    return s.strip()


def grade_one(con, key, model, sql_raw):
    spec = GRADABLE[key]
    sql = clean_sql(sql_raw)
    # normalize fully-qualified references to whatever alias our FROM clause uses
    sql = sql.replace("Source.FinwireCMP.", "CMP.").replace("FinwireCMP.", "CMP.")
    sql = sql.replace("Source.Industry.", "" if spec["gt_table"] == "Industry" else "I.")
    sql = sql.replace("Source.TaxInfoXML.", "TXML.").replace("TaxInfoXML.", "TXML.")
    sql = sql.replace("Source.CustomerXML.", "CXML.").replace("CustomerXML.", "CXML.")
    sql = sql.replace("Source.TaxRate.", "TaxRate.")

    try:
        rows = con.execute(
            f"SELECT {spec['natural_key_source']} AS rowkey, {sql} AS computed FROM {spec['from_clause']}"
        ).fetchall()
    except Exception as e:
        return {"status": "EXECUTION_FAILED", "error": str(e), "cleaned_sql": sql}

    # gt_table is e.g. "DimCompany WHERE IsCurrent" or plain "Industry" -- build the real query
    # generically instead of hardcoding one table name (fixed 2026-10-04, was DimCompany-only)
    gt_rows = con.execute(
        f"SELECT {spec['gt_key']} AS rowkey, {spec['gt_column']} AS gt FROM {spec['gt_table']}"
    ).fetchall()
    gt_map = {str(k): v for k, v in gt_rows}

    total, matched = 0, 0
    mismatches = []
    for rowkey, computed in rows:
        rowkey = str(rowkey)
        if rowkey not in gt_map:
            continue
        total += 1
        gt_val = gt_map[rowkey]
        # lenient compare: stringify, trim, case-insensitive; booleans normalized.
        # Fixed 2026-10-04: a TIMESTAMP value (e.g. from STRPTIME, which returns TIMESTAMP not
        # DATE) stringifies as "1886-07-22 00:00:00" vs the ground truth DATE's "1886-07-22" --
        # same value, different string. Strip a trailing "00:00:00" so a same-day TIMESTAMP and
        # DATE compare equal instead of being counted as a false mismatch.
        def _norm(v):
            if v is None:
                return None
            s = str(v).strip().lower()
            if s.endswith(" 00:00:00"):
                s = s[: -len(" 00:00:00")]
            return s
        a = _norm(computed)
        b = _norm(gt_val)
        if a == b:
            matched += 1
        elif len(mismatches) < 3:
            mismatches.append({"rowkey": rowkey, "computed": computed, "ground_truth": gt_val})

    return {
        "status": "EXECUTED",
        "cleaned_sql": sql,
        "total_rows_compared": total,
        "matched": matched,
        "match_pct": round(100 * matched / total, 1) if total else None,
        "sample_mismatches": mismatches,
    }


if __name__ == "__main__":
    con = duckdb.connect(DB_PATH, read_only=True)
    results = json.load(open(RESULTS_PATH))

    print(f"{'column':32s} {'model':12s} {'status':18s} {'match%':8s}")
    for key, models in results.items():
        if key not in GRADABLE:
            continue
        for model, data in models.items():
            if model.startswith("_") or not isinstance(data, dict) or not data.get("sql"):
                continue
            g = grade_one(con, key, model, data["sql"])
            pct = f"{g.get('match_pct')}%" if g.get("match_pct") is not None else "n/a"
            print(f"{key:32s} {model:12s} {g['status']:18s} {pct:8s}")
            if g["status"] == "EXECUTION_FAILED":
                print(f"    cleaned_sql: {g['cleaned_sql']}")
                print(f"    error: {g['error']}")
            elif g.get("sample_mismatches"):
                print(f"    cleaned_sql: {g['cleaned_sql']}")
                for m in g["sample_mismatches"]:
                    print(f"    MISMATCH key={m['rowkey']}: computed={m['computed']!r} vs ground_truth={m['ground_truth']!r}")
