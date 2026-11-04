#!/usr/bin/env python3
"""Exports the reference tables (the OMOP tables built by dbt-synthea) from the DuckDB file of a dbt-synthea run into reference/reference_data/*.csv.
Run dbt-synthea first (`dbt seed && dbt run`, see its README); the file is usually synthea_omop_etl.duckdb. It is opened read-only. Columns are written in the order of package/target/tables.json.
usage: python export_reference.py /path/to/synthea_omop_etl.duckdb   [--package ../package] [--reference ../reference]"""
import argparse, json, sys
from pathlib import Path
import duckdb

def main():
    here = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(); ap.add_argument("duckdb_file"); ap.add_argument("--package", default=str(here / "package")); ap.add_argument("--reference", default=str(here / "reference")); ap.add_argument("--schema", default="main"); a = ap.parse_args()
    tt = {t["name"]: [c["name"] for c in t["columns"]] for t in json.loads((Path(a.package) / "target" / "tables.json").read_text())}
    ref = Path(a.reference); out = ref / "reference_data"; out.mkdir(parents=True, exist_ok=True); con = duckdb.connect(a.duckdb_file, read_only=True); con.execute("SET TimeZone='UTC'"); n = 0      # fixed zone: the exported text does not depend on the zone of your machine
    wanted = sorted(p.stem for p in (ref / "recipes").glob("*.json")) if (ref / "recipes").is_dir() else sorted(tt)
    for t in wanted:
        if t not in tt: continue
        cols = ", ".join(f'"{c}"' for c in tt[t]); con.execute(f"COPY (SELECT {cols} FROM {a.schema}.\"{t}\") TO '{out / (t + '.csv')}' (HEADER, DELIMITER ',')"); n += 1
    print(f"exported {n} reference tables into {out}"); return 0

if __name__ == "__main__": sys.exit(main())
