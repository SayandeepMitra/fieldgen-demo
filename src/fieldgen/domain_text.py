"""Domain-knowledge text v2 (generic; generator side). Active only with the switch domain_text_v2.
Order of trust: (1) the target documentation verbatim, (2) facts measured from the source data, (3) expert text. Every line carries its source label.
Reads only the package (target/field_docs.json, field_domains.json, reference_tables.json, source tables, domain/ files) and the source data connection.
Dataset-specific wording (label prefix, which target table holds the general rule) lives in <package>/domain/domain_text_v2.json."""
import json, re
from pathlib import Path
from fieldgen.domain_files import DomainV5
from fieldgen.view_cards import keyword_sentences

EXPERT = "Written by the domain expert"
MEASURED = "Measured from the data"
DECLARED = "Declared in the package reference tables"
MEASURE_MIN = 0.5
_STR = ("VARCHAR", "TEXT")

def norm(s): return " ".join((s or "").split())
def _q(n): return '"' + n.replace('"', '""') + '"'
LABELS = [True]
def set_labels(on): LABELS[0] = bool(on)
def lab(x): return f" [{x}]" if LABELS[0] else ""

def items(text):
    """Logical lines of a wrapped text: a numbered or dash line starts an item, other non-blank lines continue the previous one."""
    out, cur = [], []
    for raw in (text or "").split("\n"):
        s = raw.strip()
        if not s:
            if cur: out.append(" ".join(cur)); cur = []
        elif cur and not re.match(r"^(\d+\.\s|- )", s): cur.append(s)
        else:
            if cur: out.append(" ".join(cur))
            cur = [s]
    if cur: out.append(" ".join(cur))
    return out

class DomainTextV2:
    def __init__(self, pkg, pkg_root, con=None, suffix="", doc_first=True, measured=True, min_coverage=MEASURE_MIN):
        self.pkg, self.root, self.con = pkg, Path(pkg_root), con
        self.doc_first, self.use_measured, self.min_cov = doc_first, measured, min_coverage
        cfg = self.root / "domain" / "domain_text.json"
        self.cfg = json.load(open(cfg, encoding="utf-8")) if cfg.exists() else {}
        self.doc_label = self.cfg.get("doc_label", "Target documentation")
        self.empties = set(self.cfg.get("empty_markers", ["", "NA"]))
        self.expert = DomainV5(pkg_root, suffix)
        fd = json.load(open(self.root / "target" / "field_docs.json", encoding="utf-8"))
        self.docs, self.tdocs = fd["fields"], fd["tables"]
        p = self.root / "target" / "field_domains.json"
        self.fdom = json.load(open(p, encoding="utf-8")) if p.exists() else {}
        p = self.root / "target" / "reference_tables.json"
        self.ref = json.load(open(p, encoding="utf-8"))["reference_tables"] if p.exists() else []
        self.lookups = sorted({r["source_relation"] for r in self.ref})
        self.src = {t["name"]: t for t in pkg.source.tables}
        self.tgt = {t["name"]: t for t in pkg.target.tables}
        self.copies = self._copies()
        self.dropped, self._measured, self.use_flow = [], None, True

    # ---- part 2/3: "is a copy of"
    def _copies(self):
        """source table -> target table whose column names are all present in the source table (largest such target; ties by name)."""
        out = {}
        for s, st in self.src.items():
            sc = {c["name"] for c in st["columns"]}
            cand = [(len(t["columns"]), n) for n, t in self.tgt.items() if t["columns"] and {c["name"] for c in t["columns"]} <= sc]
            if cand: out[s] = sorted(cand, key=lambda x: (-x[0], x[1]))[0][1]
        return out

    def copy_phrase(self, s):
        t = self.copies[s]; same = {c["name"] for c in self.src[s]["columns"]} == {c["name"] for c in self.tgt[t]["columns"]}
        return f"{s} {'has the same columns as' if same else 'has all the columns of'} {t}"

    def doc_text(self, s, col):
        t = self.copies.get(s)
        g = norm((self.docs.get(f"{t}.{col}") or {}).get("guidance")) if t else ""
        return "" if g in self.empties else g

    def column_description(self, s, col, stored=""):
        """(text, label) for a column of a copy table: documentation guidance verbatim, else expert text, else stored text, else (None, label)."""
        doc, exp = self.doc_text(s, col), self.expert.columns.get((s, col))
        if doc and (self.doc_first or not exp):
            if exp: self._drop(f"{s}.{col}: description: {norm(exp)}")
            return doc, f"{self.doc_label}: {self.copies[s]}.{col}, guidance; {self.copy_phrase(s)}"
        if exp:
            if doc: self._drop(f"{s}.{col}: documentation (expert text first): {doc}")
            return norm(exp), EXPERT
        if (stored or "").strip(): return norm(stored), "Source documentation"
        return None, "No description available"

    def table_description(self, s, stored=""):
        """(text, label): for a copy table the target table description verbatim (the expert text is dropped), else the stored text, else the expert text."""
        t = self.copies.get(s); doc = norm((self.tdocs.get(t) or {}).get("description")) if t else ""
        exp = self.expert.tables.get(s)
        if doc and doc not in self.empties and (self.doc_first or not exp):
            if exp: self._drop(f"{s}: table description: {norm(exp)}")
            return doc, f"{self.doc_label}: {t} table description; {self.copy_phrase(s)}"
        if (stored or "").strip(): return stored, None
        return (exp, EXPERT) if exp else ("", None)

    def _drop(self, x):
        if x not in self.dropped: self.dropped.append(x)

    def meaning(self, s, col, value):
        m = self.expert.meaning(s, col, value)
        if m is None: return None
        if self.doc_first and self.doc_text(s, col):
            self._drop(f"{s}.{col}: value {value!r}: {m}"); return None
        return m

    # ---- part 5: measured links
    def declared_pairs(self):
        return {(l["child"], l["child_columns"][0], l["parent"], l["parent_columns"][0]) for l in self.pkg.source.links if len(l["child_columns"]) == 1}

    def measured(self):
        """[{child, column, lookup, lookup_column, found, distinct}]: distinct non-null values of a source string column found in a lookup column, >= 50%.
        Children are the source tables that are neither lookups nor copies of a target table (those carry declared links); pairs already declared are skipped."""
        if self._measured is not None: return self._measured
        res = []
        if self.con is not None and self.use_measured:
            decl = self.declared_pairs()
            for rel, t in self.src.items():
                if rel in self.lookups or rel in self.copies: continue
                for c in t["columns"]:
                    if not c["type"].upper().startswith(_STR): continue
                    col = c["name"]
                    n = self.con.execute(f"SELECT count(DISTINCT {_q(col)}) FROM {_q(rel)}").fetchone()[0]
                    if not n: continue
                    for lr in self.lookups:
                        for lc in self.src[lr]["columns"]:
                            if not lc["type"].upper().startswith(_STR) or (rel, col, lr, lc["name"]) in decl: continue
                            k = self.con.execute(f"SELECT count(DISTINCT s.v) FROM (SELECT DISTINCT {_q(col)} v FROM {_q(rel)} WHERE {_q(col)} IS NOT NULL) s "
                                                 f"JOIN (SELECT DISTINCT {_q(lc['name'])} v FROM {_q(lr)}) l ON s.v = l.v").fetchone()[0]
                            if k / n >= self.min_cov: res.append({"child": rel, "column": col, "lookup": lr, "lookup_column": lc["name"], "found": k, "distinct": n})
        self._measured = res; return res

    def measured_for(self, rel, col): return [m for m in self.measured() if m["child"] == rel and m["column"] == col]

    @staticmethod
    def measured_line(m):
        return f"  link: -> {m['lookup']}.{m['lookup_column']} (measured, {m['found']} of {m['distinct']} distinct values found)" + lab(MEASURED)

    # ---- parts 1, 6, 7, 8: the Domain knowledge section
    def roles(self):
        out = []
        for r in self.ref:
            bits = [f"id column {r['id_column']}", f"label column {r['label_column']}"]
            if r.get("group_column"): bits.append(f"group column {r['group_column']}")
            for f in r.get("default_filters") or []: bits.append(f"default filter {f['column']} = '{f['equals']}'")
            out.append(f"- {r['source_relation']} holds the rows of the target table {r['target_table']} ({'; '.join(bits)})" + lab(DECLARED))
        return out

    def constraints(self, table, fields):
        out = []
        for col in self.tgt[table]["columns"]:
            if col["name"] not in fields: continue
            d = self.docs.get(f"{table}.{col['name']}") or {}
            for kind in ("guidance", "conventions"):
                for s in keyword_sentences(d.get(kind)):
                    out.append((col["name"], f"- {col['name']}: {s}" + lab(f"{self.doc_label}: {table}.{col['name']}, {kind}")))
        return out

    def concept_lines(self, table, fields):
        out = []
        fks = {c: (f["ref_table"], f["ref_columns"][i]) for f in self.tgt[table]["fks"] for i, c in enumerate(f["columns"])}
        for col in self.tgt[table]["columns"]:
            n = col["name"]
            if n not in fields: continue
            fk = fks.get(n); copy = sorted(s for s, t in self.copies.items() if fk and t == fk[0])
            dom = (self.fdom.get(f"{table}.{n}") or {}).get("fkDomain", "")
            if dom in self.empties: dom = ""
            if fk and copy:
                out.append(f"- {n}: foreign key to {fk[0]}.{fk[1]}; " + "; ".join(self.copy_phrase(s) for s in copy)
                           + lab(f"Declared foreign key in the target schema; copy relation from the column names"))
            if dom: out.append(f"- {n}: the referenced row belongs to the domain \"{dom}\"" + lab(f"{self.doc_label}: {table}.{n}, domain field"))
        return out

    def domain_section(self, table, fields):
        L = []
        for s in items(self.expert.text): L.append(s + lab(EXPERT))
        rt = self.cfg.get("rule_table"); d = norm((self.tdocs.get(rt) or {}).get("description")) if rt else ""
        if d: L.append(d + lab(self.cfg.get("rule_label", f"{self.doc_label}: {rt} table description")))
        r = self.roles()
        if r: L.append("Roles of the reference tables:" + lab(DECLARED)); L += r
        for s in items(self.expert.flow_text if self.use_flow else ""): L.append(s + lab(EXPERT))
        cs = self.constraints(table, fields); cl = self.concept_lines(table, fields)
        if cs or cl: L.append("Target column constraints:" + lab(f"{self.doc_label}: guidance and conventions of the target columns; declared foreign keys"))
        L += [x for _, x in cs] + cl
        return "\n".join(L), sorted({c for c, _ in cs})

# ---- step 3: data check
_Q1 = re.compile(r"(?<![A-Za-z0-9])'([^'\n]{1,60})'(?![A-Za-z0-9])")
_Q2 = re.compile(r"\"([^\"\n]{1,60})\"")

def description_part(line, doc_label):
    """The description of a card line without its label and the profile bracket that follows."""
    for m in re.finditer(r" \[(?:%s:|%s\])" % (re.escape(doc_label), re.escape(EXPERT)), line): return line[:m.start()]
    return line

def split_label(line):
    m = re.search(r"\s\[([^\[\]]+)\]$", line)
    return (line[:m.start()], m.group(1)) if m else (line, "")

def data_check(con, lines):
    """Every quoted value (single or double quotes) must exist in some source column with the same spelling; the words NULL / empty need a column
    that holds NULL or an empty string. Returns [(line, label, kind, value)]."""
    vals, has_null, has_empty = set(), False, False
    for (t,) in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()").fetchall():
        for c, ty in con.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = ? AND table_schema = current_schema()", [t]).fetchall():
            q = _q(c); r = con.execute(f"SELECT count(*) FILTER (WHERE {q} IS NULL), count(*) FILTER (WHERE CAST({q} AS VARCHAR) = '') FROM {_q(t)}").fetchone()
            has_null |= r[0] > 0; has_empty |= r[1] > 0
            vals.update(v for (v,) in con.execute(f"SELECT DISTINCT CAST({q} AS VARCHAR) FROM {_q(t)} WHERE {q} IS NOT NULL").fetchall())
    bad = []
    for line in lines:
        text, label = split_label(line)
        for rx in (_Q1, _Q2):
            for v in rx.findall(text):
                if v not in vals: bad.append((line, label, "quoted value not in data", v))
        if re.search(r"\bNULL\b", text) and not has_null: bad.append((line, label, "NULL but no column holds NULL", "NULL"))
        if re.search(r"\bempty\b", text) and not (has_empty or has_null): bad.append((line, label, "empty but no empty value", "empty"))
    return bad
