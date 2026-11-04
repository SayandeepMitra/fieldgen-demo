"""Builds reference tables by running reference recipes (reference side; never imported by the generator).
Each reference recipe plus the reference expressions of its columns is run on the source data like a tool recipe: one query per target table, written as reference_data/<table>.csv.
What is exact: every scored column (kind value) and the row identities. What cannot be rebuilt from the source tables: numbered ids, and keys that the original program took from the output of
another target table (those fields are marked excluded, with an exclusion_reason). Such a foreign key is filled from the referenced reference table when both tables identify their rows by the same
source column; otherwise it stays NULL."""
import glob, json
from pathlib import Path
from fieldgen.package import load_package
from fieldgen.db import package_connection
from fieldgen.build import table_query

def _identity(fields_t):
    """(source columns, reference columns) that identify a row of a table in the reference alignment; the source list is None for a table without row identity."""
    if not fields_t: return None
    a = next(iter(fields_t.values()))["alignment"]; src = [x.split(":", 1)[1] for x in a["source"]]
    return (None if any(x == "@const" for x in src) else src), a["reference"]

def _write(con, t, q, out):
    con.execute(f'CREATE OR REPLACE TABLE "__built_{t}" AS {q}'); con.execute(f"COPY \"__built_{t}\" TO '{Path(out) / 'reference_data' / (t + '.csv')}' (HEADER, DELIMITER ',')")
    return con.execute(f'select count(*) from "__built_{t}"').fetchone()[0]

def build_reference_tables(package_dir, reference_dir, out_dir, log=print):
    """Writes out_dir/reference_data/*.csv (and links recipes/ and fields/) and returns ({table: rows}, {table: error})."""
    pkg = load_package(package_dir); con = package_connection(pkg); ref = Path(reference_dir); out = Path(out_dir); (out / "reference_data").mkdir(parents=True, exist_ok=True)
    types = {t["name"]: {c["name"]: c["type"] for c in t["columns"]} for t in pkg.target.tables}; fks = {t["name"]: t["fks"] for t in pkg.target.tables}; fields, recipes = {}, {}
    for f in glob.glob(str(ref / "fields" / "*.json")):
        g = json.load(open(f, encoding="utf-8")); fields.setdefault(g["table"], {})[g["column"]] = g
    for f in sorted(glob.glob(str(ref / "recipes" / "*.json"))):
        r = json.load(open(f, encoding="utf-8"))
        if r["table"] in types: recipes[r["table"]] = r
    built, errors = {}, {}
    for t, r in recipes.items():
        rec = {"branches": r["branches"], "combine": r["combine"], "group_by": r["group_by"]}
        for only_value in (False, True):          # first with every reference expression, then (if that fails) with the scored columns only
            exprs = {c: {e["branch"]: e["expr"] for e in g["expressions"]} for c, g in fields.get(t, {}).items() if g.get("expressions") and (not only_value or g["kind"] == "value")}
            try: built[t] = _write(con, t, table_query(rec, list(types[t]), exprs, types[t]), out); errors.pop(t, None); break
            except Exception as e: errors[t] = str(e)[:160]; built.pop(t, None)
    for t in sorted(built):          # second pass: foreign keys that the original program took from another target table's output
        mine = _identity(fields.get(t, {})); filled = []
        if not mine or not mine[0] or len(mine[0]) != 1: continue
        ex = {c: {e["branch"]: e["expr"] for e in g["expressions"]} for c, g in fields[t].items() if g.get("expressions") and g["kind"] == "value"}
        for c, g in fields[t].items():
            if g["kind"] != "excluded" or "another target table" not in (g.get("exclusion_reason") or ""): continue
            fk = next((f for f in fks[t] if f["columns"] == [c]), None)
            if not fk or fk["ref_table"] not in built or fk["ref_table"] == t: continue
            theirs = _identity(fields.get(fk["ref_table"], {}))
            if not theirs or theirs[0] != mine[0] or len(theirs[1]) != 1 or not theirs[1][0].startswith("r."): continue
            ex[c] = {b["id"]: f'(SELECT "{fk["ref_columns"][0]}" FROM "__built_{fk["ref_table"]}" WHERE "{theirs[1][0][2:]}" = CAST({mine[0][0]} AS VARCHAR))' for b in recipes[t]["branches"]}; filled.append(c)
        if filled:
            r = recipes[t]
            try: _write(con, t, table_query({"branches": r["branches"], "combine": r["combine"], "group_by": r["group_by"]}, list(types[t]), ex, types[t]), out); log(f"  {t}: filled {', '.join(filled)} from the referenced reference table")
            except Exception as e: errors[t] = "foreign key fill failed: " + str(e)[:120]; _write(con, t, table_query({"branches": r["branches"], "combine": r["combine"], "group_by": r["group_by"]}, list(types[t]), {c: {e_["branch"]: e_["expr"] for e_ in g["expressions"]} for c, g in fields[t].items() if g.get("expressions") and g["kind"] == "value"}, types[t]), out)
    for name in ("recipes", "fields"):
        dst = out / name
        if not dst.exists(): dst.symlink_to((ref / name).resolve(), target_is_directory=True)
    return built, errors
