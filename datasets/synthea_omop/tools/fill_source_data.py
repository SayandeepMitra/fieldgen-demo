#!/usr/bin/env python3
"""Copies the Synthea sample data and the OMOP vocabulary seed files from a local checkout of dbt-synthea (https://github.com/OHDSI/dbt-synthea) into package/source/data/.
These files are NOT part of this repository (see LICENSES.md): you are responsible for the licences of the data you copy (Synthea sample data; SNOMED CT, LOINC, RxNorm and other vocabulary content).
usage: python fill_source_data.py /path/to/dbt-synthea   [--package ../package]"""
import argparse, csv, json, sys
from pathlib import Path

def main():
    import duckdb
    ap = argparse.ArgumentParser(); ap.add_argument("dbt_synthea"); ap.add_argument("--package", default=str(Path(__file__).resolve().parent.parent / "package")); a = ap.parse_args()
    seeds = Path(a.dbt_synthea) / "seeds"; pkg = Path(a.package); out = pkg / "source" / "data"; out.mkdir(parents=True, exist_ok=True)
    tables = json.loads((pkg / "source" / "tables.json").read_text()); raw = {}
    for sub in ("synthea", "map", "vocabulary", "stcm"):
        for f in sorted((seeds / sub).glob("*.csv")): raw[f.stem] = f
    con = duckdb.connect(":memory:"); con.execute("SET TimeZone='UTC'"); missing = []
    for t in tables:
        if t["name"] not in raw: missing.append(t["name"]); continue
        con.execute(f'CREATE TABLE "{t["name"]}" ({", ".join(chr(34) + c["name"] + chr(34) + " " + c["type"] for c in t["columns"])})'); con.execute(f"COPY \"{t['name']}\" FROM '{raw[t['name']]}' (HEADER true)")
    con.execute("SET TimeZone='Asia/Kolkata'")      # the time zone the example package was built in; the instants are the same, only the printed offset differs
    for t in tables:
        if t["name"] in raw: con.execute(f"COPY (SELECT * FROM \"{t['name']}\") TO '{out / (t['name'] + '.csv')}' (HEADER, DELIMITER ',')")
    man = json.loads((pkg / "manifest.json").read_text()); bad = len(missing)
    for m in missing: print("MISSING seed file for", m)
    for t, rows in man["source_row_counts"].items():
        p = out / f"{t}.csv"
        if not p.exists(): continue
        with open(p, newline="", encoding="utf-8") as fh: got = sum(1 for _ in csv.reader(fh)) - 1
        if got != rows: print(f"row count of {t}: manifest {rows}, file {got}"); bad += 1
    print(f"wrote {len(tables) - len(missing)} data files into {out}"); print("all row counts match the manifest" if not bad else f"{bad} problem(s): check the dbt-synthea version (the example was built from the 27-patient seed dataset)")
    return 1 if bad else 0

if __name__ == "__main__": sys.exit(main())
