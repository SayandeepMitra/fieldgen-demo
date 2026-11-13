"""Step-1 view with the domain-text v2 switch (generic; generator side). Source relations that are copies of a target table get the target documentation
(verbatim) as column descriptions; measured links go on the column card; the Domain knowledge section is built by src/domain_text_v2.py. Every added line is labelled."""
import re
from fieldgen.view_nulls import Step1ViewV5
from fieldgen.view_cards import whole_sentences, NO_DESC
from fieldgen.view_base import _j, _clip
from fieldgen.link_facts_nulls import fact_line
from fieldgen.domain_text import MEASURED, EXPERT, lab, DomainTextV2

_OV = re.compile(r"^  overlaps (\S+?)\.(\S+): exact [\d.]+, case-insensitive [\d.]+(.*)$")

class Step1ViewV6(Step1ViewV5):
    def __init__(self, *a, dt=None, **kw):
        super().__init__(*a, **kw)
        self.dt = dt; self.dt.use_flow = bool(self.flow)

    def domain_section(self, table, fields): return self.dt.domain_section(table, fields)

    def _facts(self, name, col, links):
        out = []
        if self.link_profile and self.profiles is not None:
            for lr, lc in links:
                if lr not in self.lookups: continue
                p = self.profiles.get(name, col, lr, lc)
                if p is not None and p["distinct"]: out.append("  " + fact_line(lr, lc, p, self.null_label) + lab(MEASURED))
        return out

    def relation_text(self, name):
        if self._lazy: return ""
        t = self.src[name]; limit = 30 if name in self.parents else 12; dt = self.dt; copy = name in dt.copies
        rows = self.pkg.manifest["source_row_counts"].get(name); L = [f"#### {name} ({rows} rows)"]
        txt, label = dt.table_description(name, t.get("description")); td = txt if label and label.startswith(dt.doc_label) else whole_sentences(txt)
        if td: L.append(td + (lab(label) if label else ""))
        L.append(f"PK: {', '.join(t['pk']) or 'none'}; business ids: {', '.join(t['business_ids']) or 'none'}")
        for c in t["columns"]:
            card = self.sf.get((name, c["name"])) if self.profiling else None
            if copy:
                d, label = dt.column_description(name, c["name"], c.get("description")); line = f"- {c['name']} ({c['type']}): {d or NO_DESC}{lab(label)}"
            else: line = f"- {c['name']} ({c['type']}): {whole_sentences(self.domain.column_text(name, c['name'], c.get('description'))) or NO_DESC}"
            if card:
                vd, pr = card["value_domain"], card.get("profile") or {}; bits = [f"distinct {vd['distinct']}", f"null rate {pr.get('null_rate')}"]
                if vd["kind"] == "list" and vd["distinct"] <= limit and c["type"].upper().startswith(("VARCHAR", "TEXT", "INT", "BIGINT")) and vd["distinct"] > 0:
                    def one(v):
                        m = dt.meaning(name, c["name"], v["value"]) if copy else self.domain.meaning(name, c["name"], v["value"])
                        return _j(_clip(v["value"], 40)) + (f" = {m}" if m else "")
                    bits.append("values: " + ", ".join(one(v) for v in vd["values"]))
                else:
                    top = [v for v, _ in (pr.get("top") or [])[:3]]
                    if top: bits.append("e.g. " + _j([_clip(x, 40) for x in top]))
                line += " [" + ", ".join(bits) + "]"
            L.append(line)
            links = []
            for l, pc in self.by_child.get((name, c["name"]), []):
                if self.shown is None or l["parent"] in self.shown:
                    L.append(f"  link: -> {l['parent']}.{pc} ({l['cardinality']}, {l['provenance']})"); links.append((l["parent"], pc))
            for m in dt.measured_for(name, c["name"]):
                if self.shown is None or m["lookup"] in self.shown:
                    L.append(dt.measured_line(m)); links.append((m["lookup"], m["lookup_column"]))
            L += self._facts(name, c["name"], links)
        return "\n".join(L) + "\n"

    def source_text(self, relation, column):
        text = super().source_text(relation, column)
        if not text: return text
        ms = {(m["lookup"], m["lookup_column"]): m for m in self.dt.measured_for(relation, column)}; out, seen = [], set()
        for line in text.split("\n"):
            m = _OV.match(line)
            if m and (m.group(1), m.group(2)) in ms:
                x = ms[(m.group(1), m.group(2))]; seen.add((m.group(1), m.group(2)))
                out.append(f"  link: -> {x['lookup']}.{x['lookup_column']} (measured, {x['found']} of {x['distinct']} distinct values found){m.group(3)}" + lab(MEASURED))
            elif m: out.append(line + lab(MEASURED))
            else: out.append(line)
        for k, x in ms.items():
            if k not in seen: out.append(self.dt.measured_line(x))
        return "\n".join(out)
