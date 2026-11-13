"""Template D view for the step-1 (recipe) prompt (generic; generator side). Reuses Step1View and build_step1_task from src/step1_view.py.
Descriptions are guidance only and are cut only between sentences; value lists carry no counts (optionally a meaning); every link of a
column is shown on the column's own card; optional project knowledge comes from <package>/domain/ (src/domain_v3.py)."""
import json, re, threading
from pathlib import Path
from fieldgen.view_base import Step1View, build_step1_task, PARENT_LIMIT, OTHER_LIMIT, _j, _clip
from fieldgen.cards import _split_sentences
from fieldgen.domain_base import Domain

NO_DESC = "no description supplied"
DESC_LIMIT = 600
OVERLAP_MIN, OVERLAP_TOP, TIMEOUT_S = 0.5, 3, 120
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")

def whole_sentences(text, limit=DESC_LIMIT):
    """Whole sentences in their order up to `limit` characters; the first sentence is kept whole even if longer."""
    out, n = [], 0
    for s in _split_sentences(" ".join((text or "").split())):
        if out and n + 1 + len(s) > limit: break
        out.append(s); n += len(s) + (1 if len(out) > 1 else 0)
    return " ".join(out)

def keyword_sentences(text, word="domain"):
    """Whole sentences of `text` that contain `word` (case-insensitive); a markdown link is reduced to its text."""
    clean = _MD_LINK.sub(r"\1", " ".join((text or "").split()))
    return [s for s in _split_sentences(clean) if re.search(rf"\b{word}\b", s, re.I)]

def _q(n): return '"' + n.replace('"', '""') + '"'

class Step1ViewV3(Step1View):
    def __init__(self, pkg, pkg_root, con=None, use_domain=False):
        super().__init__(pkg, pkg_root)
        self.root = Path(pkg_root); self.con = con; self.domain = Domain(pkg_root if use_domain else None); self.use_domain = use_domain
        self.shown = None; self.matched = set(); self._lazy = False; self._overlap = {}
        ref = self.root / "target" / "reference_tables.json"
        self.lookups = sorted({r["source_relation"] for r in json.load(open(ref, encoding="utf-8"))["reference_tables"]}) if ref.exists() else []
        fd = self.root / "target" / "field_docs.json"
        self.field_docs = json.load(open(fd, encoding="utf-8"))["fields"] if fd.exists() else {}
        self.by_child = {}
        for l in self.links:
            for i, c in enumerate(l["child_columns"]): self.by_child.setdefault((l["child"], c), []).append((l, l["parent_columns"][i]))

    # ---- target field cards: guidance only, whole sentences, no format notes
    def field_cards(self, table, fields):
        out = []
        for line in super().field_cards(table, fields).split("\n"):
            if line.startswith("  format notes:"): continue
            m = re.match(r"^(- (\w+) \(.*?(?:nullable|not null)\))(?:: .*)?$", line)
            if m:
                r = self.tf.get((table, m.group(2))); g = whole_sentences((r["description"]["guidance"] if r else "") or "")
                line = f"{m.group(1)}: {g or NO_DESC}"
            out.append(line)
        return "\n".join(out)

    # ---- source relations
    def overlaps(self, rel, col):
        """[(lookup relation, lookup column, exact, case-insensitive)] with coverage >= 0.5, top 3, or None when it could not be computed."""
        if (rel, col) in self._overlap: return self._overlap[(rel, col)]
        res = []
        if self.con is not None and self.lookups:
            parts = []
            for lr in self.lookups:
                if lr == rel or lr not in self.src: continue
                for c in self.src[lr]["columns"]:
                    if c["type"].upper().startswith(("VARCHAR", "TEXT")):
                        parts.append(f"SELECT '{lr}' rel, '{c['name']}' col, CAST({_q(c['name'])} AS VARCHAR) v FROM {_q(lr)} WHERE {_q(c['name'])} IS NOT NULL GROUP BY 3")
            sql = (f"WITH s AS (SELECT DISTINCT CAST({_q(col)} AS VARCHAR) v FROM {_q(rel)} WHERE {_q(col)} IS NOT NULL), r AS ({' UNION ALL '.join(parts)}) "
                   "SELECT r.rel, r.col, count(DISTINCT s.v) FILTER (WHERE s.v = r.v), count(DISTINCT s.v) FILTER (WHERE lower(s.v) = lower(r.v)), (SELECT count(*) FROM s) "
                   "FROM r JOIN s ON lower(s.v) = lower(r.v) GROUP BY r.rel, r.col") if parts else None
            if sql:
                cur = self.con.cursor(); timer = threading.Timer(TIMEOUT_S, cur.interrupt); timer.start()
                try: rows = cur.execute(sql).fetchall()
                except Exception: rows = None
                finally: timer.cancel()
                if rows is None: self._overlap[(rel, col)] = None; return None
                for lr, lc, ex, ci, n in rows:
                    if n and max(ex, ci) / n >= OVERLAP_MIN: res.append((lr, lc, round(ex / n, 2), round(ci / n, 2)))
                res.sort(key=lambda e: (-e[3], -e[2], e[0], e[1])); res = res[:OVERLAP_TOP]
        self._overlap[(rel, col)] = res; return res

    def relation_text(self, name):
        if self._lazy: return ""
        t = self.src[name]; limit = PARENT_LIMIT if name in self.parents else OTHER_LIMIT
        rows = self.pkg.manifest["source_row_counts"].get(name); L = [f"#### {name} ({rows} rows)"]
        td = whole_sentences(self.domain.table_text(name, t.get("description")))
        if td: L.append(td)
        L.append(f"PK: {', '.join(t['pk']) or 'none'}; business ids: {', '.join(t['business_ids']) or 'none'}")
        for c in t["columns"]:
            card = self.sf.get((name, c["name"])) if self.profiling else None; desc = whole_sentences(self.domain.column_text(name, c["name"], c.get("description")))
            line = f"- {c['name']} ({c['type']}): {desc or NO_DESC}"
            if card:
                vd, pr = card["value_domain"], card.get("profile") or {}; bits = [f"distinct {vd['distinct']}", f"null rate {pr.get('null_rate')}"]
                if vd["kind"] == "list" and vd["distinct"] <= limit and c["type"].upper().startswith(("VARCHAR", "TEXT", "INT", "BIGINT")) and vd["distinct"] > 0:
                    def one(v):
                        m = self.domain.meaning(name, c["name"], v["value"]); return _j(_clip(v["value"], 40)) + (f" = {m}" if m else "")
                    bits.append("values: " + ", ".join(one(v) for v in vd["values"]))
                else:
                    top = [v for v, _ in (pr.get("top") or [])[:3]]
                    if top: bits.append("e.g. " + _j([_clip(x, 40) for x in top]))
                line += " [" + ", ".join(bits) + "]"
            L.append(line)
            declared = [(l, pc) for l, pc in self.by_child.get((name, c["name"]), []) if self.shown is None or l["parent"] in self.shown]
            for l, pc in declared: L.append(f"  link: -> {l['parent']}.{pc} ({l['cardinality']}, {l['provenance']})")
            if not declared and name in self.matched and c["type"].upper().startswith(("VARCHAR", "TEXT")):
                ov = self.overlaps(name, c["name"])
                if ov is None: L.append("  overlap not computed")
                for lr, lc, ex, ci in ov or []: L.append(f"  overlaps {lr}.{lc}: exact {ex:.2f}, case-insensitive {ci:.2f}")
        return "\n".join(L) + "\n"

    # ---- domain knowledge section
    def constraint_sentences(self, table, fields):
        out = []
        for col in self.pkg.target.table(table)["columns"]:
            if col["name"] not in fields: continue
            d = self.field_docs.get(f"{table}.{col['name']}") or {}
            for s in keyword_sentences(d.get("guidance")) + keyword_sentences(d.get("conventions")):
                out.append((col["name"], s))
        return out

    def domain_section(self, table, fields):
        if not self.use_domain: return "", []
        cs = self.constraint_sentences(table, fields); parts = [self.domain.text] if self.domain.text else []
        if cs: parts.append("Target column constraints:\n" + "\n".join(f"- {c}: {s}" for c, s in cs))
        return "\n\n".join(parts), sorted({c for c, _ in cs})

def build_step1_task_v3(pkg, view, table, depth=1):
    """build_step1_task with the V3 view; the source tables are rendered a second time once the shown and matched sets are known."""
    view._lazy = True
    try: task = build_step1_task(pkg, view, table, depth)
    finally: view._lazy = False
    sg = task["source_graph"]; e1 = task["e1"]
    view.matched = set(sg["matched_tables"]); view.shown = set(e1["relation_text"]); view.shown |= set(e1["bridges"])
    e1["relation_text"] = {r: view.relation_text(r) for r in e1["relation_text"]}
    matched_fields = list(dict.fromkeys(m["field"] for m in task["matched_sources"]))
    e1["domain_knowledge"], e1["constraint_columns"] = view.domain_section(table, matched_fields)
    return task
