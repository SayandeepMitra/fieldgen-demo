"""`fieldgen init`: creates the package layout from your source data and your target schema.
Filled from the data: source tables, columns, types, row counts, profiles, and PROPOSED primary keys and links (marked "proposed", please confirm).
Filled from the target schema: target tables, columns, types, keys.
Left as TODO templates: descriptions, target documentation, matched columns, lookup-table list, domain knowledge (see TODO.md in the package)."""
import csv, json, re, shutil
from pathlib import Path
import duckdb
import sqlglot
from sqlglot import exp
from fieldgen.profiling import profile_table
from fieldgen.package import load_package

class InitError(Exception): pass

def _w(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
def _q(n): return '"' + n.replace('"', '""') + '"'

# ------------------------------------------------------------------ source
def read_source(source, data_dir):
    """Copies the source tables into data_dir as CSV (header, NULL = empty cell) and returns [{name, columns: [(name, type)], rows}]."""
    src = Path(source); data_dir.mkdir(parents=True, exist_ok=True); out = []
    con = duckdb.connect(":memory:"); con.execute("SET TimeZone='UTC'")
    if src.is_dir():
        files = sorted(src.glob("*.csv"))
        if not files: raise InitError(f"no .csv files in {src}")
        for f in files:
            desc = con.execute("SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM read_csv(?, header=true, sample_size=-1))", [str(f)]).fetchall()
            n = con.execute("SELECT count(*) FROM read_csv(?, header=true, sample_size=-1)", [str(f)]).fetchone()[0]
            shutil.copy(f, data_dir / f"{f.stem}.csv"); out.append({"name": f.stem, "columns": [(c, t) for c, t in desc], "rows": n})
    elif src.is_file():
        s = duckdb.connect(str(src), read_only=True); s.execute("SET TimeZone='UTC'")
        for (t,) in s.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' AND table_type = 'BASE TABLE' ORDER BY 1").fetchall():
            cols = s.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'main' AND table_name = ? ORDER BY ordinal_position", [t]).fetchall()
            s.execute(f"COPY (SELECT * FROM main.{_q(t)}) TO '{data_dir / (t + '.csv')}' (HEADER, DELIMITER ',')")
            out.append({"name": t, "columns": [(c, d) for c, d in cols], "rows": s.execute(f"SELECT count(*) FROM main.{_q(t)}").fetchone()[0]})
        if not out: raise InitError(f"no tables in {src}")
    else: raise InitError(f"--source {src} is neither a folder of CSV files nor a DuckDB file")
    return out

def _cat(t):
    t = t.upper()
    return "num" if any(x in t for x in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "REAL")) else ("time" if any(x in t for x in ("DATE", "TIME")) else "text")

def propose_keys_and_links(pkg):
    """Proposed primary keys and links from the data. Returns (keys {table: [cols]}, links [dict])."""
    con = duckdb.connect(":memory:"); con.execute("SET TimeZone='UTC'"); stats = {}; keys = {}
    for t in pkg.source.tables:
        con.execute(f'CREATE TABLE {_q(t["name"])} ({", ".join(_q(c["name"]) + " " + c["type"] for c in t["columns"])})'); con.execute(f"COPY {_q(t['name'])} FROM '{pkg.source.data_path(t['name'])}' (HEADER true)")
        n = con.execute(f"SELECT count(*) FROM {_q(t['name'])}").fetchone()[0]; cs = []
        for i, c in enumerate(t["columns"]):
            nn, d = con.execute(f"SELECT count({_q(c['name'])}), count(DISTINCT {_q(c['name'])}) FROM {_q(t['name'])}").fetchone(); cs.append((i, c["name"], c["type"], nn, d))
        stats[t["name"]] = (n, cs)
        cand = [(0 if c.lower() == "id" else (1 if re.search(r"(^|_)id$", c.lower()) else (2 if c.lower().startswith(t["name"].lower().rstrip("s")) else 3)), i, c) for i, c, ty, nn, d in cs if n and nn == n and d == n]
        if cand: keys[t["name"]] = [sorted(cand)[0][2]]
        else:
            comp = None
            names = [c for _, c, *_ in cs][:6]
            for a in range(len(names)):
                for b in range(a + 1, len(names)):
                    if n and con.execute(f"SELECT count(*) = (SELECT count(*) FROM (SELECT DISTINCT {_q(names[a])}, {_q(names[b])} FROM {_q(t['name'])})) FROM {_q(t['name'])} WHERE {_q(names[a])} IS NOT NULL AND {_q(names[b])} IS NOT NULL").fetchone()[0] and comp is None: comp = [names[a], names[b]]
            keys[t["name"]] = comp or []
    links = []; seen = set()
    for A in pkg.source.tables:
        nA, csA = stats[A["name"]]
        for i, c, ty, nn, d in csA:
            if d < 2 or nn == 0: continue
            for B in pkg.source.tables:
                pk = keys.get(B["name"]) or []
                if len(pk) != 1 or (A["name"] == B["name"]) or (B["name"], pk[0], A["name"], c) in seen: continue
                pty = next(x[2] for x in stats[B["name"]][1] if x[1] == pk[0])
                if _cat(ty) != _cat(pty): continue
                found = con.execute(f"SELECT count(DISTINCT a.{_q(c)}) FROM {_q(A['name'])} a JOIN {_q(B['name'])} b ON a.{_q(c)} = b.{_q(pk[0])}").fetchone()[0]
                if found / d < 0.95: continue
                cn, pn = re.sub(r"[^a-z0-9]", "", c.lower()), re.sub(r"[^a-z0-9]", "", pk[0].lower()); similar = cn == pn or cn.endswith(pn) or pn.endswith(cn)
                if not similar and c in (keys.get(A["name"]) or []): continue            # a primary key that only matches by value is not a link
                support = "name" if similar else "value_only"
                links.append({"child": A["name"], "child_columns": [c], "parent": B["name"], "parent_columns": pk, "cardinality": "one_to_one" if d == nn == nA else "many_to_one", "provenance": "inferred",
                              "support": support, "weak": support == "value_only", "coverage": round(found / d, 4), "evidence": "the values of the child column are found in the parent key", "note": "proposed by fieldgen init; confirm or delete"})
                seen.add((A["name"], c, B["name"], pk[0]))
    return keys, links

# ------------------------------------------------------------------ target
def read_target(target):
    """[{name, columns: [{name, type, nullable, constraints}], pk, fks}] from a DDL file (.sql) or a DuckDB file; names in lower case."""
    t = Path(target)
    if t.is_dir():          # a folder of .sql files, for example the three DuckDB DDL files of the OMOP CDM (tables, primary keys, foreign keys)
        files = sorted(t.glob("*.sql"))
        if not files: raise InitError(f"no .sql files in {t}")
        return _target_from_ddl("\n".join(f.read_text(encoding="utf-8") for f in files))
    if not t.is_file(): raise InitError(f"--target {t} is neither a DDL file (.sql), a folder of .sql files, nor a DuckDB file")
    return _target_from_ddl(t.read_text(encoding="utf-8")) if t.suffix.lower() == ".sql" else _target_from_duckdb(t)

def _type(kind):
    """The column type as written (VARCHAR(50) keeps its length). DuckDB has no TIMESTAMPNTZ: a plain timestamp stays timestamp."""
    return kind.sql().lower().replace("timestampntz", "timestamp")

def _target_from_ddl(text):
    text = re.sub(r"@\w+\.", "", text); tabs = {}; order = []; stmts = [e for e in sqlglot.parse(text) if e is not None]
    for e in sorted(stmts, key=lambda e: 0 if isinstance(e, exp.Create) else 1):          # CREATE TABLE first, then ALTER TABLE (keys), whatever the order of the files
        if isinstance(e, exp.Create) and str(e.args.get("kind")).upper() == "TABLE" and isinstance(e.this, exp.Schema):
            name = e.this.this.name.lower(); cols = []; pk = []; fks = []
            for x in e.this.expressions:
                if isinstance(x, exp.ColumnDef):
                    cons = x.args.get("constraints") or []; kinds = [type(c.args.get("kind")).__name__ for c in cons]; ref = next((c.args["kind"] for c in cons if isinstance(c.args.get("kind"), exp.Reference)), None)
                    notnull = "NotNullColumnConstraint" in kinds and not any(isinstance(c.args.get("kind"), exp.NotNullColumnConstraint) and c.args["kind"].args.get("allow_null") for c in cons)
                    isp = "PrimaryKeyColumnConstraint" in kinds
                    cols.append({"name": x.name.lower(), "type": _type(x.args["kind"]), "nullable": not (notnull or isp), "constraints": (["primary key"] if isp else []) + (["not null"] if notnull or isp else [])})
                    if isp: pk.append(x.name.lower())
                    if ref is not None and isinstance(ref.this, exp.Schema): fks.append({"columns": [x.name.lower()], "ref_table": ref.this.this.name.lower(), "ref_columns": [i.name.lower() for i in ref.this.expressions]})
                elif isinstance(x, exp.PrimaryKey): pk = [i.name.lower() for i in x.expressions]
                elif isinstance(x, exp.ForeignKey) and x.args.get("reference") is not None:
                    r = x.args["reference"]; fks.append({"columns": [i.name.lower() for i in x.expressions], "ref_table": r.this.this.name.lower(), "ref_columns": [i.name.lower() for i in r.this.expressions]})
            tabs[name] = {"name": name, "columns": cols, "pk": pk, "fks": fks}; order.append(name)
        elif isinstance(e, exp.Alter) and e.this is not None:
            name = e.this.name.lower()
            for a in e.args.get("actions") or []:
                c = a.find(exp.PrimaryKey) or None; f = a.find(exp.ForeignKey) or None
                if c is not None and name in tabs: tabs[name]["pk"] = [i.name.lower() for i in c.expressions]
                if f is not None and name in tabs and f.args.get("reference") is not None:
                    r = f.args["reference"]; tabs[name]["fks"].append({"columns": [i.name.lower() for i in f.expressions], "ref_table": r.this.this.name.lower(), "ref_columns": [i.name.lower() for i in r.this.expressions]})
    if not tabs: raise InitError("no CREATE TABLE statements found in the target DDL")
    for t in tabs.values():
        for c in t["columns"]:
            if c["name"] in t["pk"] and "primary key" not in c["constraints"]: c["constraints"] = ["primary key", "not null"] + [x for x in c["constraints"] if x != "not null"]; c["nullable"] = False
    return [tabs[n] for n in order]

def _target_from_duckdb(path):
    con = duckdb.connect(str(path), read_only=True); out = []
    cons = con.execute("SELECT table_name, constraint_type, constraint_column_names FROM duckdb_constraints() WHERE schema_name = 'main'").fetchall()
    for (t,) in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' AND table_type = 'BASE TABLE' ORDER BY 1").fetchall():
        pk = next((list(map(str.lower, c[2])) for c in cons if c[0] == t and c[1] == "PRIMARY KEY"), [])
        cols = [{"name": c.lower(), "type": d.lower(), "nullable": n == "YES" and c.lower() not in pk, "constraints": (["primary key"] if c.lower() in pk else []) + ([] if n == "YES" and c.lower() not in pk else ["not null"])}
                for c, d, n in con.execute("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema = 'main' AND table_name = ? ORDER BY ordinal_position", [t]).fetchall()]
        out.append({"name": t.lower(), "columns": cols, "pk": pk, "fks": []})
    if not out: raise InitError(f"no tables in {path}")
    return out

# ------------------------------------------------------------------ the package
FLOW_TEMPLATE = "TODO: describe how a code or value in a source table becomes a value in the target.\nTODO: a short numbered list works best; see docs/domain_knowledge.md. Remove these TODO lines when you are done.\n"
RULES_TEMPLATE = "TODO: general rules of the data model, one sentence each (what a column or table means, in the words of an expert).\nTODO: remove these TODO lines when you are done.\n"

def init_package(package_dir, source, target, log=print):
    root = Path(package_dir)
    if (root / "manifest.json").exists(): raise InitError(f"{root} already holds a package (manifest.json); init does not overwrite. Use a new folder.")
    root.mkdir(parents=True, exist_ok=True); src = read_source(source, root / "source" / "data"); tgt = read_target(target)
    _w(root / "source" / "tables.json", [{"name": t["name"], "columns": [{"name": c, "type": ty, "nullable": True} for c, ty in t["columns"]], "pk": [], "business_ids": []} for t in src])
    _w(root / "source" / "links.json", []); _w(root / "manifest.json", {"name": root.resolve().name, "version": "0.1", "source_row_counts": {t["name"]: t["rows"] for t in src}, "target_tables": len(tgt)})
    _w(root / "matches" / "matches.json", {f"{t['name']}.{c['name']}": [] for t in tgt for c in t["columns"]})
    _w(root / "target" / "tables.json", [{"name": t["name"], "columns": t["columns"], "pk": t["pk"], "fks": t["fks"], "business_ids": []} for t in tgt])
    _w(root / "target" / "field_docs.json", {"tables": {t["name"]: {"description": None, "guidance": None, "conventions": None} for t in tgt},
                                             "fields": {f"{t['name']}.{c['name']}": {"guidance": None, "conventions": None, "ddl": {"type": c["type"], "default": None, "check_constraints": [], "unique": False}} for t in tgt for c in t["columns"]}})
    _w(root / "target" / "reference_tables.json", {"reference_tables": [], "field_filters": {}})
    d = root / "domain"; d.mkdir(exist_ok=True); (d / "domain_knowledge.md").write_text(RULES_TEMPLATE, encoding="utf-8"); (d / "flow_text.md").write_text(FLOW_TEMPLATE, encoding="utf-8")
    _w(d / "descriptions_supplement.json", []); _w(d / "value_meanings.json", []); _w(d / "domain_text.json", {"doc_label": "Target documentation", "empty_markers": ["", "NA"]})
    pkg = load_package(root); keys, links = propose_keys_and_links(pkg)
    tabs = json.loads((root / "source" / "tables.json").read_text())
    for t in tabs:
        t["pk"] = keys.get(t["name"], []); t["business_ids"] = list(t["pk"]); t["pk_provenance"] = {"source": "proposed", "note": "proposed by fieldgen init; confirm"} if t["pk"] else {"source": "none found: TODO"}
        for c in t["columns"]:
            if c["name"] in t["pk"]: c["nullable"] = False
    _w(root / "source" / "tables.json", tabs); _w(root / "source" / "links.json", links)
    pkg = load_package(root)
    for t in pkg.source.tables: _w(root / "source" / "profiles" / f"{t['name']}.json", profile_table(pkg, t))
    nokey = [t["name"] for t in tabs if not t["pk"]]
    todo = ["# TODO: what is left to fill in", "", "`fieldgen generate` stops until the BLOCKING items are done. The others are hints that make the result better.", "",
            "## Blocking", "", "- [ ] `matches/matches.json`: for every target column, list the source columns that probably feed it (`{\"relation\": ..., \"column\": ...}`). All lists are empty now.",
            "- [ ] `domain/`: write `domain_knowledge.md` and/or `flow_text.md` (remove the TODO lines), or set `domain_knowledge: optional` (or `off`) in `config.yaml`.", "",
            "## Please confirm", "", f"- [ ] `source/tables.json`: primary keys proposed for {len(tabs) - len(nokey)} of {len(tabs)} tables (`pk_provenance` says \"proposed\")."]
    if nokey: todo.append(f"- [ ] `source/tables.json`: NO key could be proposed for: {', '.join(nokey)}. Every source table needs a primary key.")
    todo += [f"- [ ] `source/links.json`: {len(links)} link(s) proposed from the data (`note` says \"proposed\"). Confirm, delete, or add the ones you know.", "",
             "## Make it better", "", "- [ ] `source/tables.json`: add a `description` to tables and columns (your data dictionary).", "- [ ] `target/field_docs.json`: add the target documentation (`guidance`, `conventions`).",
             "- [ ] `target/reference_tables.json`: list the lookup tables (code lists, vocabularies), if any.", "- [ ] `domain/descriptions_supplement.json`, `domain/value_meanings.json`: expert descriptions and value meanings (optional).", "",
             "See `docs/input_package.md` and `docs/domain_knowledge.md`.", ""]
    (root / "TODO.md").write_text("\n".join(todo), encoding="utf-8")
    log(f"package written to {root}")
    log(f"  source: {len(src)} tables, {sum(t['rows'] for t in src)} rows, profiles written; proposed keys for {len(tabs) - len(nokey)} tables" + (f" (none for: {', '.join(nokey)})" if nokey else "") + f"; {len(links)} proposed links")
    log(f"  target: {len(tgt)} tables, {sum(len(t['columns']) for t in tgt)} columns")
    log(f"  TODO templates left: matches, descriptions, target documentation, lookup-table list, domain knowledge (see {root / 'TODO.md'})")
    return {"source_tables": len(src), "target_tables": len(tgt), "proposed_links": len(links), "no_key": nokey}
