"""
Level 2 of the two-level prompting strategy: build the per-target-column prompt.

Given: the Level 1 table skeleton (shared FROM/JOIN, resolved once) + this column's own matched
source field(s) (from tpcdi_column_mapping.csv) + source PK/FK info (from tpcdi_source_schema.sql
-- mostly absent, which is itself informative) + sample data + a profile (profiling.py) +
target-side constraints (from tpcdi_target_schema.sql).

Explicitly withheld (the answer key): rule_sql, combination, lineage_path, column_kind,
rule_reliable, rule_issue, table_caution.
"""
import csv
import re
import duckdb

from table_skeleton import resolve_table_skeleton, load_mapping
from profiling import profile_column, format_profile_for_prompt

import gold_version as _gv
DB_PATH = _gv.GOLD_DB
PROMPT_VERSION = "v3-2026-10-05"  # v1 original; v2 +dialect/anti-hallucination, lookup-arrow fix; v3 +target-table schema exposure
TARGET_SCHEMA_SQL = _gv.TARGET_DDL
SOURCE_SCHEMA_SQL = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))), "deliverables/tpcdi_source_schema.sql")

# Minimal, hand-written descriptions -- no official TPC-DI spec PDF with per-column prose was
# found locally (checked in project_plan.md Sec 5.4). Filled in only for columns used in the
# worked examples below; a full pass would extend this dict (or source better descriptions) for
# every one of the 241 columns before running Phase C for real.
FIELD_DESCRIPTIONS = {
    ("DimCompany", "Status"): "Current operating status of the company (e.g. active, inactive).",
    ("DimCompany", "Industry"): "The industry sector the company operates in, as a human-readable name.",
    ("DimCompany", "FoundingDate"): "The date the company was founded.",
    ("Source.FinwireCMP", "Status"): "A status code for the company record in the FINWIRE feed.",
    ("Source.FinwireCMP", "IndustryID"): "A 2-character industry code in the FINWIRE feed.",
    ("Source.FinwireCMP", "FoundingDate"): "Company founding date as published in the FINWIRE feed.",
}


def _target_column_ddl(table, column):
    """Pull this column's declared type + constraints out of tpcdi_target_schema.sql (crude but
    sufficient: find the CREATE TABLE block, then the column's own line)."""
    sql = open(TARGET_SCHEMA_SQL).read()
    m = re.search(rf"CREATE TABLE {table}\s*\((.*?)\n\);", sql, re.DOTALL)
    if not m:
        return "(not found)"
    for line in m.group(1).splitlines():
        if line.strip().startswith(column + " ") or line.strip().startswith(column + "\t"):
            return line.strip().rstrip(",")
    return "(not found)"


def _source_pk_fk_note(source_table):
    """Source.* tables have no declared PK/FK at all in schema.sql -- this is itself a fact
    worth telling the model (it explains why keys must be derived, not read off a constraint)."""
    sql = open(SOURCE_SCHEMA_SQL).read()
    m = re.search(rf"CREATE TABLE {re.escape(source_table)}\s*\((.*?)\n\);", sql, re.DOTALL)
    if not m:
        return f"{source_table}: schema not found"
    has_pk = "PRIMARY KEY" in m.group(1)
    has_fk = "REFERENCES" in m.group(1)
    if not has_pk and not has_fk:
        return f"{source_table}: no PK or FK declared in the staging schema (flat staging table)"
    return f"{source_table}: PK={'yes' if has_pk else 'no'}, FK={'yes' if has_fk else 'no'}"


def build_column_prompt(target_table, target_column, con):
    rows = load_mapping(target_table)
    col_row = next(r for r in rows if r["target_column"] == target_column)
    skeleton = resolve_table_skeleton(target_table)

    target_ddl = _target_column_ddl(target_table, target_column)
    description = FIELD_DESCRIPTIONS.get((target_table, target_column), "(no description available)")

    # matched source field(s) -- the "matching assumed given" input. Collect every source table
    # referenced (deduped via the same tolerant parser Level 1 uses) and pull one sample + profile
    # per table/column pair named in value_columns.
    #
    # Fixed 2026-10-04: this used to mis-parse the mapping CSV's " -> " lookup-arrow notation
    # (e.g. "Source.TaxInfoXML.C_NAT_TX_ID -> Source.TaxRate.TX_NAME") by splitting the WHOLE
    # string on "." without ever looking for " -> " first -- for that example it produced
    # table="Source.TaxInfoXML", col="C_NAT_TX_ID -> Source" (mangled), so the model never saw
    # "look this up in TaxRate.TX_NAME" at all. Confirmed as the root cause of 4 of 5 new harder
    # test columns (DimSecurity.SK_CompanyID, DimAccount.SK_CustomerID, Financial.SK_CompanyID,
    # DimCustomer.NationalTaxRateDesc) all converging on the same wrong answer -- casting the raw
    # business key instead of looking up the target dimension's surrogate key -- across both
    # models that succeeded. That was a prompt bug, not a model reasoning failure.
    value_cols = [v.strip() for v in col_row["value_columns"].split(";") if v.strip()]
    matched_lines = []
    profile_lines = []
    pk_fk_lines = []
    seen_tables = set()
    target_refs = []  # already-populated target tables offered as lookup targets (for schema exposure)
    TARGET_TABLES = {"DimDate", "DimTime", "DimBroker", "DimCompany", "DimCustomer", "DimAccount",
                      "DimSecurity", "DimTrade", "FactCashBalances", "FactHoldings",
                      "FactMarketHistory", "FactWatches", "Industry", "StatusType", "TaxRate",
                      "TradeType", "Financial", "Prospect", "DImessages", "AuditTable"}

    def _resolve_table_col(vc):
        vc = vc.strip()
        parts = vc.split(".")
        if len(parts) < 2:
            return None, None
        if parts[0] == "Source":
            # "Source.Table.Column"
            return ("Source." + parts[1], parts[2]) if len(parts) >= 3 else (None, None)
        if parts[0] in TARGET_TABLES:
            # "TargetTable.Column" -- a reference to an ALREADY-POPULATED target table's own
            # column (e.g. "DimCustomer.SK_CustomerID"), not a Source.* staging table
            return parts[0], parts[1]
        # bare "TableName.Column" with no prefix -- assume it's a Source table
        return "Source." + parts[0], parts[1]

    expanded = []       # [(table, col)] from Source.* -- gets profiled + sampled
    lookup_lines = []   # explicit "look this up in an already-populated target table" notes
    for vc in value_cols:
        if " -> " in vc:
            left_raw, right_raw = vc.split(" -> ", 1)
            l_table, l_col = _resolve_table_col(left_raw)
            r_table, r_col = _resolve_table_col(right_raw)
            if l_table and l_col:
                if l_table.startswith("Source."):
                    expanded.append((l_table, l_col))
                else:
                    matched_lines.append(f"  - {l_table}.{l_col} (an ALREADY-POPULATED target table -- available to JOIN against)")
                    if l_table not in target_refs:
                        target_refs.append(l_table)
            if r_table and r_col:
                if r_table in TARGET_TABLES:
                    if r_table not in target_refs:
                        target_refs.append(r_table)
                    lookup_lines.append(
                        f"  - LOOKUP: use {l_table}.{l_col if l_col else '?'} to find the matching row in "
                        f"{r_table} (an ALREADY-POPULATED target table), then take its {r_table}.{r_col} column"
                    )
                else:
                    expanded.append((r_table, r_col))
            continue
        table, col = _resolve_table_col(vc)
        if table is None:
            continue
        if not table.startswith("Source."):
            matched_lines.append(f"  - {table}.{col} (an ALREADY-POPULATED target table -- available to JOIN against)")
            if table not in target_refs:
                target_refs.append(table)
            continue
        if col == "*":
            # wildcard placeholder (seen in the mapping CSV for e.g. Phone -- expand to the
            # table's real columns rather than leaving the model guessing at "*")
            try:
                real_cols = [c[0] for c in con.execute(f"DESCRIBE {table}").fetchall()]
                expanded.extend((table, c) for c in real_cols)
            except Exception:
                expanded.append((table, col))
        else:
            expanded.append((table, col))

    if not expanded and not lookup_lines and not matched_lines:
        # CSV gap fallback: value_columns was empty (a known data-quality issue in
        # tpcdi_column_mapping.csv -- ~86 of 210 populated rows as of the 2026-10-03 audit, see
        # project_plan.md Sec 5.4/5 "A" findings). Fall back to whatever tables Level 1 already
        # resolved, so the model at least knows which table(s) to look in instead of getting a
        # blank "matched source field" section.
        matched_lines.append("  (value_columns was empty in the mapping CSV for this column -- known gap,")
        matched_lines.append("   see project_plan.md -- falling back to the resolved join skeleton's tables)")
        for t in skeleton["source_tables"]:
            try:
                real_cols = [c[0] for c in con.execute(f"DESCRIBE {t}").fetchall()]
                matched_lines.append(f"  - {t} columns available: {', '.join(real_cols)}")
            except Exception:
                pass
    for table, col in expanded:
        matched_lines.append(f"  - {table}.{col} (source description: {FIELD_DESCRIPTIONS.get((table, col), 'n/a')})")
        if table not in seen_tables:
            seen_tables.add(table)
            pk_fk_lines.append("  - " + _source_pk_fk_note(table))
        try:
            p = profile_column(con, table, col)
            profile_lines.append(format_profile_for_prompt(p))
        except Exception as e:
            profile_lines.append(f"  (could not profile {table}.{col}: {e})")
    matched_lines.extend(lookup_lines)

    # Added 2026-10-05 (prompt v3): show the REAL columns of every already-populated target table
    # we offer as a lookup target. Before this, models were told "DimCompany is available to JOIN"
    # but never shown its columns, so all 3 invented a join column (DimCompany.CoNameOrCIK) that
    # doesn't exist. Only emitted when a target table is actually referenced, so prompts for
    # columns with no target-table lookup are unchanged vs. earlier runs.
    target_schema_lines = []
    for tt in target_refs:
        try:
            cols = con.execute(f"DESCRIBE {tt}").fetchall()
            target_schema_lines.append(f"  {tt} (already populated) columns: " + ", ".join(f"{c[0]} {c[1]}" for c in cols))
        except Exception as e:
            target_schema_lines.append(f"  {tt}: (could not describe: {e})")
    target_schema_block = ""
    if target_schema_lines:
        target_schema_block = ("ALREADY-POPULATED TARGET TABLE SCHEMAS (real column names -- use only these when joining to them)\n"
                               + "\n".join(target_schema_lines) + "\n\n")

    sample_rows = []
    for t in skeleton["source_tables"][:1]:  # keep the worked example short: one table's sample
        try:
            cols = con.execute(f"DESCRIBE {t}").fetchall()
            col_names = [c[0] for c in cols]
            data = con.execute(f"SELECT * FROM {t} LIMIT 3").fetchall()
            sample_rows.append(f"{t} sample rows (columns: {', '.join(col_names)}):")
            for d in data:
                sample_rows.append("  " + str(d))
        except Exception:
            pass

    prompt = f"""You are writing one SQL expression to populate a single column of a data warehouse table.

TARGET
  Table: {target_table}
  Column: {target_column}
  Declared type/constraints: {target_ddl}
  Description: {description}

RESOLVED JOIN CONTEXT (already solved by the matching step -- do not re-derive, just use it)
  Source tables involved in this target table: {', '.join(skeleton['source_tables'])}
  Join conditions:
{chr(10).join('    - ' + j for j in skeleton['joins']) if skeleton['joins'] else '    (none declared -- single source table, or not yet captured)'}

MATCHED SOURCE FIELD(S) FOR THIS COLUMN (the matching, given to you -- your job is only the transformation)
{chr(10).join(matched_lines) if matched_lines else '  (none recorded)'}

SOURCE TABLE KEY INFO
{chr(10).join(pk_fk_lines) if pk_fk_lines else '  (none)'}

{target_schema_block}SAMPLE SOURCE DATA
{chr(10).join(sample_rows) if sample_rows else '  (not available)'}

DATA PROFILE
{chr(10).join(profile_lines) if profile_lines else '  (not available)'}

TASK
Write the SQL expression (just the SELECT-list formula, using the join context above -- do not
write the FROM/JOIN clause again) that correctly populates {target_table}.{target_column} from
the matched source field(s), respecting the declared type/constraints. Write portable,
DuckDB-compatible SQL only -- do not use T-SQL/SQL-Server, Oracle, or Postgres-specific functions
(e.g. no TO_DATE, no NEXT VALUE FOR, no CONVERT/STUFF). Use only columns that were actually shown
to you above -- do not invent column or table names. Explain your reasoning in one sentence, then
give the SQL expression.
"""
    return prompt


if __name__ == "__main__":
    con = duckdb.connect(DB_PATH, read_only=True)
    print("=" * 100)
    print("WORKED EXAMPLE 1: DimCompany.Industry (clean lookup-join row, joins populated)")
    print("=" * 100)
    print(build_column_prompt("DimCompany", "Industry", con))

    print("=" * 100)
    print("WORKED EXAMPLE 2: DimCompany.FoundingDate (profiling should surface the YYYYMMDD format)")
    print("=" * 100)
    print(build_column_prompt("DimCompany", "FoundingDate", con))
