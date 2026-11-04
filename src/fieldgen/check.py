"""`fieldgen check`: validates an input package against the documented format (docs/input_package.md). No model calls. It never reads a reference folder."""
import csv, json
from pathlib import Path
from jsonschema import Draft7Validator
from fieldgen.paths import SCHEMAS_DIR

def _j(p):
    with open(p, encoding="utf-8") as f: return json.load(f)
def _schema(name): return _j(SCHEMAS_DIR / "package" / f"{name}.schema.json")
def check_package(path):
    """{"ok", "errors", "warnings", "checks"}"""
    root = Path(path); errs, warns = [], []
    def need(cond, msg):
        if not cond: errs.append(msg)
    def sch(name, obj, label):
        for e in list(Draft7Validator(_schema(name)).iter_errors(obj))[:3]: errs.append(f"schema {label}: {'/'.join(map(str, e.path))}: {e.message[:120]}")
    if not root.is_dir(): return {"ok": False, "errors": [f"{root} is not a folder"], "warnings": [], "checks": {}}
    try: man = _j(root / "manifest.json"); st = _j(root / "source/tables.json"); ln = _j(root / "source/links.json"); tt = _j(root / "target/tables.json")
    except Exception as e: return {"ok": False, "errors": [f"cannot read the core files (manifest.json, source/tables.json, source/links.json, target/tables.json): {e}"], "warnings": [], "checks": {}}
    sch("manifest", man, "manifest"); sch("source_tables", st, "source/tables"); sch("links", ln, "source/links"); sch("target_tables", tt, "target/tables")
    if "gold" in man: errs.append("manifest.json has a 'gold' section: the package must not describe the reference")
    if errs: return {"ok": False, "errors": errs[:40], "warnings": warns, "checks": {}}
    scols = {t["name"]: [c["name"] for c in t["columns"]] for t in st}; tcols = {t["name"]: [c["name"] for c in t["columns"]] for t in tt}
    for t in st:
        for k in t["pk"] + t["business_ids"]: need(k in scols[t["name"]], f"source key {t['name']}.{k} is not a column")
        need(bool(t["pk"]), f"source table {t['name']} has no primary key")
    for l in ln:
        for tab, cols, role in ((l["child"], l["child_columns"], "child"), (l["parent"], l["parent_columns"], "parent")):
            need(tab in scols, f"link {role} table {tab} unknown")
            for c in cols: need(tab in scols and c in scols[tab], f"link {role} column {tab}.{c} unknown")
        need(bool(l.get("provenance")), f"link {l['child']}->{l['parent']} has no provenance")
        lab = f"link {l['child']}.{l['child_columns']}->{l['parent']}.{l['parent_columns']}"
        need(l.get("weak") == (l.get("support") == "value_only"), f"{lab}: weak must be true exactly when support is value_only")
        if l.get("provenance") == "declared": need(l.get("support") == "dictionary", f"{lab}: declared links need support 'dictionary'")
        if l.get("provenance") == "inferred":
            ppk = next((t["pk"] for t in st if t["name"] == l["parent"]), None)
            need(l["support"] != "dictionary" and ppk == l["parent_columns"], f"{lab}: inferred link must point to the parent's primary key")
    for t in st:
        p = root / "source/data" / f"{t['name']}.csv"
        if not p.exists(): errs.append(f"missing data file source/data/{p.name}"); continue
        with open(p, newline="", encoding="utf-8") as f:
            rd = csv.reader(f); hdr = next(rd, None); n = sum(1 for _ in rd)
        need(hdr == scols[t["name"]], f"data header of {t['name']} differs from the declared columns")
        need(man["source_row_counts"].get(t["name"]) == n, f"row count of {t['name']}: manifest {man['source_row_counts'].get(t['name'])} vs file {n}")
    for p in (root / "source/data").glob("*.csv"): need(p.stem in scols, f"data file {p.name} has no table in source/tables.json")
    nprof = 0
    for p in sorted((root / "source/profiles").glob("*.json")) if (root / "source/profiles").exists() else []:
        nprof += 1; pr = _j(p); tab = p.stem; need(tab in scols, f"profile for unknown table {tab}")
        for c in pr.get("columns", {}): need(tab in scols and c in scols[tab], f"profile column {tab}.{c} unknown")
    missing = [t["name"] for t in st if not (root / "source/profiles" / f"{t['name']}.json").exists()]
    if missing: warns.append(f"no profile file for {len(missing)} source table(s) ({', '.join(missing[:3])}...): the tool computes the profiles from the data")
    ndep = 0; dp = root / "source/dependencies.json"
    for d in (_j(dp) if dp.exists() else []):
        ndep += 1
        for c in d["lhs"] + d["rhs"]: need(d["table"] in scols and c in scols[d["table"]], f"dependency column {d['table']}.{c} unknown")
    mp = root / "matches" / "matches.json"
    if not mp.exists(): errs.append("missing matches/matches.json")
    else:
        m = _j(mp); sch("matches", m, "matches/matches"); nt = sum(len(v) for v in tcols.values())
        need(len(m) == nt, f"matches/matches.json: {len(m)} fields, the target has {nt} (give every target field, with an empty list when nothing matches)")
        for k, lst in m.items():
            tab, _, col = k.partition("."); need(tab in tcols and col in tcols[tab], f"matches: target field {k} unknown")
            for x in lst: need(x["relation"] in scols and x["column"] in scols.get(x["relation"], []), f"matches: {k} -> {x['relation']}.{x['column']} unknown")
    for t in tt:
        if not t["pk"]: warns.append(f"target table {t['name']} has no primary key in the DDL")
        for k in t["pk"]: need(k in tcols[t["name"]], f"target pk {t['name']}.{k} unknown")
        for fk in t["fks"]: need(fk["ref_table"] in tcols and all(c in tcols[fk["ref_table"]] for c in fk["ref_columns"]), f"target fk {t['name']}.{fk['columns']} -> {fk['ref_table']} unknown")
    fd = root / "target/field_docs.json"
    if not fd.exists(): errs.append("missing target/field_docs.json (the target documentation)")
    else:
        docs = _j(fd); tkeys = {f"{t}.{c}" for t, cs in tcols.items() for c in cs}
        try: Draft7Validator(_j(SCHEMAS_DIR / "dump" / "field_docs.schema.json")).validate(docs)
        except Exception as e: errs.append(f"schema target/field_docs: {str(e)[:120]}")
        need(set(docs.get("fields", {})) <= tkeys, "target/field_docs.json names an unknown target field"); need(set(docs.get("tables", {})) <= set(tcols), "target/field_docs.json names an unknown target table")
    rt = root / "target/reference_tables.json"
    if not rt.exists(): errs.append("missing target/reference_tables.json (the lookup-table list)")
    else:
        try: Draft7Validator(_j(SCHEMAS_DIR / "dump" / "reference_tables.schema.json")).validate(_j(rt))
        except Exception as e: errs.append(f"schema target/reference_tables: {str(e)[:120]}")
        for r in _j(rt).get("reference_tables", []): need(r.get("source_relation") in scols, f"reference_tables: source relation {r.get('source_relation')} unknown")
    dm = root / "domain"
    if not dm.exists(): warns.append("no domain/ folder: domain_knowledge = required will stop the run; use domain_knowledge: optional or off")
    else:
        for f in dm.glob("*.json"):
            try: _j(f)
            except Exception as e: errs.append(f"domain/{f.name} is not valid JSON: {e}")
    return {"ok": not errs, "errors": errs[:40], "warnings": warns, "checks": {"source_tables": len(st), "target_tables": len(tt), "links": len(ln), "profiles": nprof, "dependencies": ndep}}
