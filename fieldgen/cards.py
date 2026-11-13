"""Field-knowledge dump (D1). Generic: reads only the package (manifest, source, target, links, profiles, dependencies,
target/reference_tables.json, target/field_docs.json). No model calls, no dataset names, never answer-key or reference data.
Deterministic (seed 2026). Resumable: progress in results/d1_progress.json, partial source cards in dump/.partial/."""
from fieldgen.profiling import profile_table
import hashlib, json, os, re, shutil, threading, time
from pathlib import Path
import duckdb
from fieldgen.package import load_package

SEED = 2026
VERSION = "d1-1"
CAPS = {"max_allowed_values": 30, "max_value_domain": 30, "random_samples": 8, "overlap_matches": 3, "overlap_min_coverage": 0.5,
        "overlap_group_top": 3, "top_shapes": 5, "max_format_notes": 8, "sample_chars": 120, "query_timeout_s": 300, "max_file_mb": 20}
SEPARATORS = [" ", "-", "/", "_", ".", ",", ":", ";", "|", "@", "'"]
OPENED = []          # every package file this module reads, for the leak-boundary test
SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas" / "dump"
FORMAT_WORDS = re.compile(r"\b(digits?|characters?|length|format\w*|only|at most|must)\b", re.I)
CUE = re.compile(r"(e\.g\.|for example|such as|example)", re.I)

def _read_json(p):
    OPENED.append(str(p))
    if os.path.getsize(p) > CAPS["max_file_mb"] * 1024 * 1024: raise ValueError(f"{p} over {CAPS['max_file_mb']} MB")
    with open(p, encoding="utf-8") as f: return json.load(f)

def _write_json(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f: json.dump(obj, f, indent=1, ensure_ascii=False, sort_keys=False)

def _write_jsonl(p, rows):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")

def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def _q(ident): return '"' + ident.replace('"', '""') + '"'

class DB:
    """In-memory DuckDB over the package CSV files (all text, empty field = NULL), with a per-query timeout."""
    def __init__(self, pkg):
        self.pkg = pkg; self.con = duckdb.connect(":memory:"); self.loaded = set()
    def q(self, sql, params=None):
        t = threading.Timer(CAPS["query_timeout_s"], self.con.interrupt); t.start()
        try: return self.con.execute(sql, params or []).fetchall()
        finally: t.cancel()
    def load(self, table):
        if table in self.loaded: return
        p = self.pkg.source.data_path(table); OPENED.append(str(p))
        if os.path.getsize(p) > CAPS["max_file_mb"] * 1024 * 1024: raise ValueError(f"{p} over {CAPS['max_file_mb']} MB")
        self.q(f"CREATE TABLE {_q(table)} AS SELECT * FROM read_csv(?, header=true, all_varchar=true, nullstr='')", [str(p)])
        self.loaded.add(table)

# ---------------------------------------------------------------- target side
def _split_sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text or "") if s.strip()]

def _base_type(declared):
    d = declared.lower()
    if d.startswith(("varchar", "char", "text", "string")): return "string"
    if d.startswith(("int", "bigint", "smallint")): return "integer"
    if d.startswith(("numeric", "decimal", "float", "double", "real")): return "numeric"
    if d.startswith("timestamp"): return "timestamp"
    if d.startswith("date"): return "date"
    return "other"

def _type_card(declared):
    ml = re.match(r"\s*(?:var)?char\s*\((\d+)\)", declared, re.I); pr = re.match(r"\s*(?:numeric|decimal)\s*\((\d+)\s*(?:,\s*(\d+))?\)", declared, re.I)
    return {"declared": declared, "base": _base_type(declared), "max_length": int(ml.group(1)) if ml else None,
            "precision": int(pr.group(1)) if pr else None, "scale": (int(pr.group(2)) if pr.group(2) else 0) if pr else None}

NUMWORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

def _doc_rules(sentences, type_card):
    """max_length from the declared type; further rules only from unambiguous documentation wording."""
    r = {"max_length": type_card["max_length"], "min_length": None, "pattern": None, "range": None, "lengths": None}; src = {}
    if r["max_length"]: src["max_length"] = "ddl"
    rule_sents = []
    for s in sentences:
        m = re.search(r"\bexactly (\d+|\w+)[- ](?:letters?|digits?|characters?)\b", s, re.I) or re.search(r"\b(\d+|two|three|four|five|six|seven|eight|nine|ten)[- ](?:letter|digit|character)s?\s+(?:code|string|value|abbreviation)\b", s, re.I)
        if m and r["pattern"] is None and "up to" not in s.lower() and "at most" not in s.lower():
            n = int(m.group(1)) if m.group(1).isdigit() else NUMWORDS.get(m.group(1).lower())
            kind = "digit" if re.search(r"digit", m.group(0), re.I) else "letter" if re.search(r"letter", m.group(0), re.I) else "char"
            if n:
                r["min_length"] = n; r["max_length"] = n if r["max_length"] is None else min(r["max_length"], n)
                r["pattern"] = {"digit": f"^[0-9]{{{n}}}$", "letter": f"^[A-Za-z]{{{n}}}$", "char": f"^.{{{n}}}$"}[kind]
                src["pattern"] = src["min_length"] = "documentation"
        if re.search(r"\bcodes?\b", s, re.I):      # a stated code format "N-digit": digits only, the stated lengths
            ns = [int(x) for x in re.findall(r"\b(\d+)-digit\b", s, re.I)]
            if ns:
                r["lengths"] = sorted(set((r["lengths"] or []) + ns)); r["pattern"] = "^[0-9]+$"; src["pattern"] = src["lengths"] = "documentation"; rule_sents.append(s)
        m = re.search(r"\bat most (\d+) characters\b", s, re.I)
        if m:
            n = int(m.group(1)); r["max_length"] = n if r["max_length"] is None else min(r["max_length"], n); src.setdefault("max_length", "documentation")
    r["_sentences"] = rule_sents
    return r, src

def _doc_samples(sentences, hints):
    out = []
    for s in sentences:
        c = CUE.search(s)
        if not c: continue
        for m in re.finditer(r"['\"‘“]([^'\"’”]{1,40})['\"’”]", s[c.end():]):
            v = m.group(1).strip()
            if v and len(v.split()) <= 3 and v not in out: out.append(v)
    for v in (hints.get("examples") or []):
        if str(v) not in out: out.append(str(v))
    return out[:10]

def _fmt_value(v, base):
    return int(v) if base == "integer" and re.fullmatch(r"-?\d+", v or "") else v

def _enum_values(checks):
    vals = []
    for c in checks:
        m = re.search(r"\bIN\s*\(([^)]*)\)", c, re.I)
        if m: vals += [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]
    return vals

def build_target_fields(pkg, db, refs, docs):
    refmap = {r["target_table"]: r for r in refs["reference_tables"]}; ff = refs["field_filters"]; rows = []
    for t in pkg.target.tables:
        parents = sorted({fk["ref_table"] for fk in t["fks"]}); fkmap = {}
        for fk in t["fks"]:
            for c, rc in zip(fk["columns"], fk["ref_columns"]): fkmap[c] = {"table": fk["ref_table"], "column": rc}
        for pos, c in enumerate(t["columns"], 1):
            key = f"{t['name']}.{c['name']}"; d = docs["fields"].get(key, {}); ddl = d.get("ddl", {}); prov = {}
            tc = _type_card(c["type"]); prov["type"] = prov["nullable"] = prov["keys"] = "ddl"
            guidance = d.get("guidance") or c.get("description"); conv = d.get("conventions")
            sents = _split_sentences(guidance) + _split_sentences(conv)
            notes = [s for s in sents if FORMAT_WORDS.search(s)][:CAPS["max_format_notes"]]
            rules, rsrc = _doc_rules(sents, tc); rule_sents = rules.pop("_sentences"); hints = dict(c.get("value_hints") or {})
            fk = fkmap.get(c["name"]); filt = ff.get(key)
            if filt: hints["reference_filter"] = filt["reference_filter"]
            av = {"kind": "none", "entries": [], "source": None, "omitted_count": 0}; special = []
            ref = refmap.get(fk["table"]) if fk else None
            if ref and fk["column"] == ref["id_column"]:
                rel = ref["source_relation"]; db.load(rel); where, par = [], []
                for fl in ([filt["reference_filter"]] + filt.get("extra_filters", []) if filt else []) + ref.get("default_filters", []):
                    where.append(f"{_q(fl['column'])} = ?"); par.append(fl["equals"])
                idc, lab = _q(ref["id_column"]), ref.get("label_column")
                got = db.q(f"SELECT {idc}{', ' + _q(lab) if lab else ''} FROM {_q(rel)}" + (" WHERE " + " AND ".join(where) if where else ""), par)
                if len(got) > CAPS["max_allowed_values"]: av = {"kind": "none", "entries": [], "source": f"reference:{rel}", "omitted_count": len(got)}
                elif got:
                    got.sort(key=lambda r: (int(r[0]) if re.fullmatch(r"-?\d+", r[0] or "") else 0, r[0] or ""))
                    ent = [{"value": _fmt_value(r[0], tc["base"]), **({"label": r[1]} if lab and r[1] is not None else {})} for r in got]
                    av = {"kind": "pairs" if lab else "values", "entries": ent, "source": f"reference:{rel}", "omitted_count": 0}
                prov["allowed_values"] = "data"
                z = db.q(f"SELECT {idc}{', ' + _q(lab) if lab else ''} FROM {_q(rel)} WHERE {idc} = '0'")
                special = [{"value": 0, **({"label": r[1]} if lab and r[1] is not None else {})} for r in z]
                prov["special_values"] = "data"
            else:
                vals = _enum_values(ddl.get("check_constraints") or [])
                if vals and len(vals) <= CAPS["max_allowed_values"]: av = {"kind": "values", "entries": [{"value": v} for v in vals], "source": "check", "omitted_count": 0}
                prov["allowed_values"] = "ddl"
            if filt: prov["value_hints"] = "documentation"
            prov.update({"description": "documentation", "rules": "documentation" if "pattern" in rsrc or "min_length" in rsrc else "ddl",
                         "format_notes": "documentation", "sample_values": "documentation", "relations": "declared"})
            rows.append({"table": t["name"], "column": c["name"], "position": pos, "type": tc, "nullable": c["nullable"],
                         "default": ddl.get("default"),
                         "keys": {"primary_key": c["name"] in t["pk"], "foreign_key": fk, "unique": bool(ddl.get("unique"))},
                         "check_constraints": ddl.get("check_constraints") or [],
                         "description": {"guidance": guidance, "conventions": conv}, "allowed_values": av, "special_values": special,
                         "rules": rules, "rule_sentences": rule_sents, "format_notes": notes, "sample_values": [{"value": v} for v in _doc_samples(sents, hints)],
                         "value_hints": hints,
                         "relations": {"siblings": [x["name"] for x in t["columns"] if x["name"] != c["name"]],
                                       "grain": {"primary_key": t["pk"], "business_ids": t["business_ids"]}, "parent_tables": parents},
                         "provenance": prov})
    return rows

# ---------------------------------------------------------------- source side
def _trunc(v):
    n = CAPS["sample_chars"]
    return v if v is None or len(v) <= n else v[:n] + "..."

def _lower_groups(db, t, c):
    return db.q(f"SELECT min(v), max(v) FROM (SELECT DISTINCT {_q(c)} v FROM {_q(t)} WHERE {_q(c)} IS NOT NULL) GROUP BY lower(v) HAVING count(*) > 1 ORDER BY min(v) LIMIT 1")

def build_source_card(pkg, db, table, col, tdef, refs_rel, ref_vals):
    c = col["name"]; T, C = _q(table["name"]), _q(c); db.load(table["name"])
    n, nn, dist, minl, maxl = db.q(f"SELECT count(*), count({C}), count(DISTINCT {C}), min(length({C})), max(length({C})) FROM {T}")[0]
    nonnull = f"{C} IS NOT NULL"
    counts = db.q(f"SELECT {C}, count(*) k FROM {T} WHERE {nonnull} GROUP BY 1 ORDER BY k DESC, 1") if dist <= CAPS["max_value_domain"] else None
    rare = db.q(f"SELECT {C} FROM {T} WHERE {nonnull} GROUP BY 1 ORDER BY count(*), 1 LIMIT 1")
    rnd = db.q(f"SELECT DISTINCT {C} FROM {T} WHERE {nonnull} ORDER BY hash({C} || '{SEED}'), 1 LIMIT {CAPS['random_samples']}")
    short = db.q(f"SELECT {C} FROM {T} WHERE {nonnull} ORDER BY length({C}), 1 LIMIT 1"); long_ = db.q(f"SELECT {C} FROM {T} WHERE {nonnull} ORDER BY length({C}) DESC, 1 LIMIT 1")
    lz = db.q(f"SELECT {C} FROM {T} WHERE regexp_matches({C}, '^0[0-9]+$') ORDER BY 1 LIMIT 1") if nn else []
    mixed = _lower_groups(db, table["name"], c) if nn else []
    samples = [{"value": _trunc(r[0]), "kind": "random"} for r in rnd]
    for kind, got in (("shortest", short), ("longest", long_), ("rarest", rare), ("leading_zero", lz)):
        if got: samples.append({"value": _trunc(got[0][0]), "kind": kind})
    if n > nn: samples.append({"value": None, "kind": "null"})
    if mixed: samples += [{"value": _trunc(mixed[0][0]), "kind": "mixed_case"}, {"value": _trunc(mixed[0][1]), "kind": "mixed_case"}]
    seps = {}
    if nn:
        sel = ", ".join(f"sum(CASE WHEN contains({C}, '{s.replace(chr(39), chr(39) * 2)}') THEN 1 ELSE 0 END)" for s in SEPARATORS)
        seps = {s: int(k) for s, k in zip(SEPARATORS, db.q(f"SELECT {sel} FROM {T}")[0]) if k}
        ws = db.q(f"SELECT sum(CASE WHEN {C} <> trim({C}) THEN 1 ELSE 0 END), sum(CASE WHEN regexp_matches({C}, '\\s\\s') THEN 1 ELSE 0 END) FROM {T}")[0]
        cv = db.q(f"SELECT count(*) FROM (SELECT 1 FROM (SELECT DISTINCT {C} v FROM {T} WHERE {nonnull}) GROUP BY lower(v) HAVING count(*) > 1)")[0][0]
        shapes = db.q(f"SELECT s, count(*) k FROM (SELECT regexp_replace(regexp_replace({C}, '[A-Za-z]', 'A', 'g'), '[0-9]', '9', 'g') s FROM {T} WHERE {nonnull}) GROUP BY s ORDER BY k DESC, s LIMIT {CAPS['top_shapes']}")
    else: ws, cv, shapes = (0, 0), 0, []
    fobs = {"case_variants": int(cv), "whitespace": {"leading_trailing": int(ws[0] or 0), "double_internal": int(ws[1] or 0)},
            "separators": seps, "top_shapes": [{"shape": s, "count": int(k)} for s, k in shapes]}
    vd = ({"kind": "list", "distinct": dist, "values": [{"value": _trunc(v), "count": int(k)} for v, k in counts]} if counts is not None else {"kind": "omitted", "distinct": dist})
    keys = {"pk": c in table["pk"], "unique": bool(nn and n == nn == dist), "business_id": c in table["business_ids"]}
    overlap = []
    if col["type"].upper().startswith(("VARCHAR", "TEXT")) and 0 < dist <= CAPS["max_value_domain"]:
        overlap = _overlap(db, table["name"], c, dist, refs_rel, ref_vals)
    prof = (tdef or {}).get("columns", {}).get(c)
    return {"relation": table["name"], "column": c, "type": col["type"], "nullable": col["nullable"], "observed_min_length": minl, "observed_max_length": maxl,
            "description": col.get("description"), "profile": prof, "value_domain": vd, "samples": samples, "format_observations": fobs, "keys": keys,
            "reference_overlap": overlap,
            "provenance": {"type": "declared", "description": "documentation" if col.get("description") else "none", "profile": "data", "value_domain": "data",
                           "samples": "data", "format_observations": "data", "keys": "declared" if keys["pk"] else "data", "reference_overlap": "data"}}

def _prepare_overlap(db, refs):
    """Distinct string values of every string column of the reference source relations, in one table."""
    db.q("CREATE TABLE _refvals (rel VARCHAR, col VARCHAR, v VARCHAR, lv VARCHAR)")
    pkg = db.pkg; info = {}
    for r in refs["reference_tables"]:
        rel = r["source_relation"]; db.load(rel); tdef = next(t for t in pkg.source.tables if t["name"] == rel); info[rel] = r
        for col in tdef["columns"]:
            if not col["type"].upper().startswith(("VARCHAR", "TEXT")): continue
            db.q(f"INSERT INTO _refvals SELECT ?, ?, v, lower(v) FROM (SELECT DISTINCT {_q(col['name'])} v FROM {_q(rel)} WHERE {_q(col['name'])} IS NOT NULL)", [rel, col["name"]])
    return info

def _overlap(db, table, c, dist, info, _):
    db.q("DROP TABLE IF EXISTS _sv"); db.q(f"CREATE TEMP TABLE _sv AS SELECT DISTINCT {_q(c)} v, lower({_q(c)}) lv FROM {_q(table)} WHERE {_q(c)} IS NOT NULL")
    got = db.q("SELECT r.rel, r.col, count(DISTINCT s.v) FILTER (WHERE s.v = r.v), count(DISTINCT s.v) FILTER (WHERE s.lv = r.lv) "
               "FROM _refvals r JOIN _sv s ON s.lv = r.lv GROUP BY r.rel, r.col")
    out = []
    for rel, col, ex, ci in got:
        ex, ci = ex / dist, ci / dist
        if max(ex, ci) < CAPS["overlap_min_coverage"]: continue
        e = {"relation": rel, "column": col, "exact_coverage": round(ex, 4), "ci_coverage": round(ci, 4), "group_values": []}
        g = info[rel].get("group_column")
        if g:
            e["group_column"] = g
            e["group_values"] = [{"value": v, "count": int(k)} for v, k in db.q(
                f"SELECT {_q(g)}, count(*) k FROM {_q(rel)} WHERE lower({_q(col)}) IN (SELECT lv FROM _sv) AND {_q(g)} IS NOT NULL GROUP BY 1 ORDER BY k DESC, 1 LIMIT {CAPS['overlap_group_top']}")]
        out.append(e)
    out.sort(key=lambda e: (-e["ci_coverage"], -e["exact_coverage"], e["relation"], e["column"]))
    return out[:CAPS["overlap_matches"]]

# ---------------------------------------------------------------- tables, links, dependencies
def _card_links(name, links):
    parents = [{"table": l["parent"], "child_columns": l["child_columns"], "parent_columns": l["parent_columns"], "cardinality": l["cardinality"],
                "provenance": l["provenance"], "support": l["support"], "weak": l.get("weak", False)} for l in links if l["child"] == name]
    children = [{"table": l["child"], "child_columns": l["child_columns"], "parent_columns": l["parent_columns"], "cardinality": l["cardinality"],
                 "provenance": l["provenance"], "support": l["support"], "weak": l.get("weak", False)} for l in links if l["parent"] == name]
    return parents, children

def target_links(pkg):
    out = []
    for t in pkg.target.tables:
        for fk in t["fks"]:
            card = "one_to_one" if fk["columns"] == t["pk"] else "many_to_one"
            out.append({"side": "target", "child": t["name"], "child_columns": fk["columns"], "parent": fk["ref_table"], "parent_columns": fk["ref_columns"],
                        "cardinality": card, "provenance": "declared", "support": "ddl", "weak": False, "evidence": "foreign key constraint"})
    return out

def build_tables(pkg, db, docs, mf):
    slinks = [dict(l, side="source") for l in pkg.source.links]; tlinks = target_links(pkg); out = []
    for t in pkg.source.tables:
        db.load(t["name"]); T = _q(t["name"]); n = db.q(f"SELECT count(*) FROM {T}")[0][0]
        cands = [{"columns": t["pk"], "kind": "primary_key", "unique": True, "provenance": (t.get("pk_provenance") or {}).get("source", "declared")}]
        seen = {tuple(t["pk"])}
        for col in t["columns"]:
            if (col["name"],) in seen or n < 2: continue
            nn, d = db.q(f"SELECT count({_q(col['name'])}), count(DISTINCT {_q(col['name'])}) FROM {T}")[0]
            if nn == n == d: cands.append({"columns": [col["name"]], "kind": "unique_column", "unique": True, "provenance": "data"}); seen.add((col["name"],))
        fkc = sorted({c for l in pkg.source.links if l["child"] == t["name"] for c in l["child_columns"]})
        for i, a in enumerate(fkc):
            for b in fkc[i + 1:]:
                if (a,) in seen or (b,) in seen or len(cands) >= 8: continue
                k = db.q(f"SELECT count(*) FROM (SELECT 1 FROM {T} GROUP BY {_q(a)}, {_q(b)})")[0][0]
                if k == n: cands.append({"columns": [a, b], "kind": "link_columns", "unique": True, "provenance": "data"})
        p, ch = _card_links(t["name"], slinks)
        out.append({"side": "source", "name": t["name"], "description": t.get("description"), "row_count": n, "primary_key": t["pk"],
                    "business_ids": t["business_ids"], "grain_candidates": cands, "parents": p, "children": ch})
    for t in pkg.target.tables:
        p, ch = _card_links(t["name"], tlinks); d = docs["tables"].get(t["name"], {})
        cands = [{"columns": t["pk"], "kind": "primary_key", "unique": True, "provenance": "ddl"}] + \
                [{"columns": [b], "kind": "business_id", "unique": False, "provenance": "declared"} for b in t["business_ids"]]
        out.append({"side": "target", "name": t["name"], "description": d.get("description") or t.get("description"), "guidance": d.get("guidance"),
                    "conventions": d.get("conventions"), "row_count": None, "primary_key": t["pk"], "business_ids": t["business_ids"],
                    "grain_candidates": cands, "parents": p, "children": ch})
    return out, slinks + tlinks

# ---------------------------------------------------------------- driver
def _filled(v):
    return v not in (None, "", [], {}) and not (isinstance(v, dict) and not any(x not in (None, "", [], {}, False) for x in v.values()))

def completeness(tf, sf):
    L = []
    tb = {"description": lambda r: _filled(r["description"]["guidance"]) or _filled(r["description"]["conventions"]),
          "allowed_values": lambda r: r["allowed_values"]["kind"] != "none", "special_values": lambda r: bool(r["special_values"]),
          "rules": lambda r: any(v is not None for v in r["rules"].values()), "format_notes": lambda r: bool(r["format_notes"]),
          "sample_values": lambda r: bool(r["sample_values"]), "keys": lambda r: r["keys"]["primary_key"] or bool(r["keys"]["foreign_key"]) or r["keys"]["unique"],
          "check_constraints": lambda r: bool(r["check_constraints"]), "relations": lambda r: bool(r["relations"]["parent_tables"])}
    sb = {"description": lambda r: _filled(r["description"]), "profile": lambda r: _filled(r["profile"]), "value_domain": lambda r: r["value_domain"]["kind"] == "list",
          "samples": lambda r: bool(r["samples"]), "keys": lambda r: any(r["keys"].values()), "reference_overlap": lambda r: bool(r["reference_overlap"]),
          "format_observations": lambda r: bool(r["format_observations"]["top_shapes"])}
    L.append(f"target fields: {len(tf)}"); counts = {}
    for k, f in tb.items():
        ok = sum(1 for r in tf if f(r)); counts[("target", k)] = ok; L.append(f"target.{k}: filled {ok}, empty {len(tf) - ok}")
    L.append(f"source fields: {len(sf)}")
    for k, f in sb.items():
        ok = sum(1 for r in sf if f(r)); counts[("source", k)] = ok; L.append(f"source.{k}: filled {ok}, empty {len(sf) - ok}")
    key = lambda r: f"{r['table']}.{r['column']}"
    L.append("target fields with no description: " + (", ".join(key(r) for r in tf if not tb["description"](r)) or "none"))
    fkno = [r for r in tf if r["keys"]["foreign_key"] and r["allowed_values"]["kind"] == "none"]
    L.append(f"foreign-key fields without allowed values ({len(fkno)}), omitted row counts: " + (", ".join(f"{key(r)}:{r['allowed_values']['omitted_count']}" for r in fkno) or "none"))
    L.append("target fields with no rules: " + (", ".join(key(r) for r in tf if not tb["rules"](r)) or "none"))
    return L

def _stamp(progress_path, state):
    _write_json(progress_path, state)

def build(pkg_root, out_dir=None, progress_path=None, include_target_samples=False, resume=True):
    pkg_root = Path(pkg_root); pkg = load_package(pkg_root); out = Path(out_dir or pkg_root / "dump"); part = out / ".partial"
    progress_path = progress_path or str(out / ".progress.json")
    refs = _read_json(pkg_root / "target" / "reference_tables.json"); docs = _read_json(pkg_root / "target" / "field_docs.json")
    state = {"blocks": {}, "done_source_tables": [], "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if resume and Path(progress_path).exists():
        s = _read_json(progress_path)
        if s.get("out") == str(out) and not s.get("finished"): state = s
    state.update({"out": str(out), "finished": False}); _stamp(progress_path, state)
    db = DB(pkg)
    tf = build_target_fields(pkg, db, refs, docs); _write_jsonl(out / "target_fields.jsonl", tf); state["blocks"]["target_fields"] = len(tf); _stamp(progress_path, state)
    info = _prepare_overlap(db, refs); sf = []
    for t in pkg.source.tables:
        pf = part / f"{t['name']}.jsonl"
        if resume and t["name"] in state["done_source_tables"] and pf.exists():
            sf += [json.loads(x) for x in pf.read_text(encoding="utf-8").splitlines()]; continue
        prof = pkg.source.profile(t["name"]) or profile_table(pkg, t); rows = [build_source_card(pkg, db, t, c, prof, info, None) for c in t["columns"]]
        _write_jsonl(pf, rows); sf += rows; state["done_source_tables"].append(t["name"]); _stamp(progress_path, state)
    _write_jsonl(out / "source_fields.jsonl", sf); state["blocks"]["source_fields"] = len(sf)
    tabs, links = build_tables(pkg, db, docs, pkg.manifest); _write_json(out / "tables.json", tabs); _write_json(out / "links.json", links)
    deps = [dict(d, side="source") for d in pkg.source.dependencies()]; _write_json(out / "dependencies.json", deps)
    state["blocks"].update({"tables": len(tabs), "links": len(links), "dependencies": len(deps)})
    lines = completeness(tf, sf); (out / "completeness.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    files = ["target_fields.jsonl", "source_fields.jsonl", "tables.json", "links.json", "dependencies.json", "completeness.txt"]
    opt = out / "optional" / "target_samples.json"
    if include_target_samples and opt.exists(): files.append("optional/target_samples.json")
    elif opt.exists() and not include_target_samples: raise RuntimeError("optional/target_samples.json present but flag not set")
    man = {"version": VERSION, "package": {"name": pkg.manifest["name"], "version": pkg.manifest["version"]}, "seed": SEED,
           "build_parameters": {"include_target_samples": include_target_samples, "reads_answer_key": False, "reads_reference_data": False, "depth_of_overlap": "reference tables"},
           "caps": CAPS, "counts": {"target_fields": len(tf), "source_fields": len(sf), "tables": len(tabs), "links": len(links), "dependencies": len(deps)},
           "content_hashes": {f: _sha(out / f) for f in files},
           "input_hashes": {f: _sha(pkg_root / f) for f in ("target/reference_tables.json", "target/field_docs.json", "target/tables.json", "source/tables.json", "source/links.json")}}
    _write_json(out / "manifest.json", man)
    shutil.rmtree(part, ignore_errors=True); state["finished"] = True; state["blocks"]["manifest"] = "done"; _stamp(progress_path, state)
    return man

# ---------------------------------------------------------------- loading and validation
def _jl(p):
    OPENED.append(str(p)); return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]

CARDS_DIR = [None]
def set_cards_dir(path): CARDS_DIR[0] = Path(path) if path else None

def load_dump(pkg_root):
    d = CARDS_DIR[0] or Path(pkg_root) / "dump"
    return {"manifest": _read_json(d / "manifest.json"), "target_fields": _jl(d / "target_fields.jsonl"), "source_fields": _jl(d / "source_fields.jsonl"),
            "tables": _read_json(d / "tables.json"), "links": _read_json(d / "links.json"), "dependencies": _read_json(d / "dependencies.json")}

def validate_dump(root):
    """Schema, referential and hash checks of the dump. Returns a list of error strings (empty = ok)."""
    from jsonschema import Draft7Validator
    root = Path(root); d = CARDS_DIR[0] or root / "dump"; errs = []
    sch = lambda n: json.loads((SCHEMA_DIR / f"{n}.schema.json").read_text(encoding="utf-8"))
    def chk(name, obj, label):
        for e in list(Draft7Validator(sch(name)).iter_errors(obj))[:2]: errs.append(f"dump schema {label}: {'/'.join(map(str, e.path))}: {e.message[:100]}")
    try: D = load_dump(root); refs = _read_json(root / "target/reference_tables.json"); docs = _read_json(root / "target/field_docs.json")
    except Exception as e: return [f"dump unreadable: {e}"]
    chk("reference_tables", refs, "reference_tables"); chk("field_docs", docs, "field_docs"); chk("manifest", D["manifest"], "manifest")
    chk("tables", D["tables"], "tables"); chk("links", D["links"], "links"); chk("dependencies", D["dependencies"], "dependencies")
    for r in D["target_fields"]: chk("target_field", r, f"target {r.get('table')}.{r.get('column')}")
    for r in D["source_fields"]: chk("source_field", r, f"source {r.get('relation')}.{r.get('column')}")
    pkg = load_package(root); man = D["manifest"]
    tset = {(t["name"], c["name"]) for t in pkg.target.tables for c in t["columns"]}; sset = {(t["name"], c["name"]) for t in pkg.source.tables for c in t["columns"]}
    if {(r["table"], r["column"]) for r in D["target_fields"]} != tset or len(D["target_fields"]) != len(tset): errs.append("dump target fields differ from package target columns")
    if {(r["relation"], r["column"]) for r in D["source_fields"]} != sset or len(D["source_fields"]) != len(sset): errs.append("dump source fields differ from package source columns")
    for r in D["target_fields"]:
        if len(r["allowed_values"]["entries"]) > CAPS["max_allowed_values"]: errs.append(f"{r['table']}.{r['column']}: more than {CAPS['max_allowed_values']} allowed values")
    for f, h in man["content_hashes"].items():
        if not (d / f).exists() or _sha(d / f) != h: errs.append(f"dump hash mismatch: {f}")
    if not man["build_parameters"]["include_target_samples"] and (d / "optional").exists(): errs.append("dump/optional exists but target samples were not requested")
    for l in D["links"]:
        tabs = {t["name"] for t in (pkg.source.tables if l["side"] == "source" else pkg.target.tables)}
        if l["child"] not in tabs or l["parent"] not in tabs: errs.append(f"dump link names unknown table {l['child']}->{l['parent']}")
    return errs
