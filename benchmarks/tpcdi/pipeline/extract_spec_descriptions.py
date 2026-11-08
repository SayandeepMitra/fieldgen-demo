"""
Parse the target-table column descriptions (TPC-DI spec Clause 3.2, Tables 3.2.x) into
deliverables/tpcdi_spec_target_descriptions.json: {"Table.Column": "<verbatim spec row text after the column name>"}.

Anchored on OUR table's real column names (DuckDB DESCRIBE), so no gold SQL is involved: a row starts at a
line beginning with `<column> ` and continues until the next row. The row text is kept verbatim (spec type
alias, restriction, description) -- nothing is paraphrased.
"""
import json, re, sys
import duckdb
import pypdf

BASE = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))
PDF = f"{BASE}/spec/tpc-di_v1.1.0.pdf"
OUT = f"{BASE}/deliverables/tpcdi_spec_target_descriptions.json"
FIRST_PAGE, LAST_PAGE = 38, 47  # Clause 3.2 target tables
SPEC_NAME_TO_DDL = {"DimTrade": {"Type": "DT_Type"}}  # spec column name -> name in our DDL

def main():
    con = duckdb.connect(f"{BASE}/deliverables/tpcdi_populated.duckdb", read_only=True)
    tables = [r[0] for r in con.execute("select table_name from information_schema.tables where table_schema='main'").fetchall()]
    cols = {t: [r[0] for r in con.execute(f"DESCRIBE {t}").fetchall()] for t in tables}
    rd = pypdf.PdfReader(PDF)
    lines = []
    for p in range(FIRST_PAGE - 1, LAST_PAGE):
        for ln in (rd.pages[p].extract_text() or "").splitlines():
            if ln.startswith("TPC Benchmark"):
                continue
            lines.append(ln.rstrip())
    out, cur_table, cur_key = {}, None, None
    for ln in lines:
        m = re.match(r"^3\.2\.\d+(?:\.\d+)?\s+(\w+)\s*$", ln)
        if m and m.group(1) in cols:
            cur_table, cur_key = m.group(1), None
            continue
        if cur_table is None:
            continue
        if ln.startswith("Table 3.2.") or ln.startswith("Field Name"):
            cur_key = None
            continue
        first = ln.split(" ", 1)[0] if ln else ""
        lookup = {c.lower(): c for c in cols[cur_table]}
        for spec_name, db_name in SPEC_NAME_TO_DDL.get(cur_table, {}).items():  # DDL renamed a reserved word
            lookup[spec_name.lower()] = db_name
        if first.lower() in lookup and f"{cur_table}.{lookup[first.lower()]}" not in out and " " in ln:
            cur_key = f"{cur_table}.{lookup[first.lower()]}"
            out[cur_key] = ln.split(" ", 1)[1].strip()
        elif cur_key:
            out[cur_key] += " " + ln.strip()
    json.dump(out, open(OUT, "w"), indent=1, sort_keys=True)
    miss = [f"{t}.{c}" for t in tables for c in cols[t] if f"{t}.{c}" not in out]
    print(f"{len(out)} descriptions for {sum(len(v) for v in cols.values())} columns in {len(tables)} tables; missing {len(miss)}:")
    print(miss)

main()
