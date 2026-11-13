"""Render dump cards as prompt text (generic). Generator side: reads only the dump files of the package."""
import json
from fieldgen import cards as D

def _j(v): return json.dumps(v, ensure_ascii=False)

class DumpView:
    def __init__(self, pkg_root):
        d = D.load_dump(pkg_root); self.tf = {(r["table"], r["column"]): r for r in d["target_fields"]}
        self.sf = {(r["relation"], r["column"]): r for r in d["source_fields"]}; self.links = d["links"]

    # ---- target field card
    def target_text(self, table, column, conventions=False, description=None):
        r = self.tf.get((table, column))
        if not r: return ""
        L = []; k = r["keys"]
        if k["foreign_key"]: L.append(f"- foreign key to {k['foreign_key']['table']}.{k['foreign_key']['column']}")
        g = (r["description"]["guidance"] or "").strip()
        if g and g != (description or "").strip(): L.append(f"- guidance: {g}")
        av = r["allowed_values"]
        if av["kind"] == "pairs": L.append("- allowed values (id = label): " + "; ".join(f"{e['value']} = {e.get('label', '')}" for e in av["entries"]))
        elif av["kind"] == "values": L.append("- allowed values: " + ", ".join(_j(e["value"]) for e in av["entries"]))
        elif av["omitted_count"]: L.append(f"- allowed values: a reference list of {av['omitted_count']} entries (not listed)")
        sv = r["special_values"]
        if sv: L.append("- special values: " + "; ".join(f"{e['value']} = {e.get('label', '')}" if e.get("label") else str(e["value"]) for e in sv))
        ru = r["rules"]; parts = []
        if ru.get("max_length") is not None: parts.append(f"max length {ru['max_length']}")
        if ru.get("min_length") is not None: parts.append(f"min length {ru['min_length']}")
        if ru.get("pattern"): parts.append("digits only" if ru["pattern"] == "^[0-9]+$" else f"pattern {ru['pattern']}")
        if ru.get("lengths"): parts.append("length is one of " + ", ".join(map(str, ru["lengths"])))
        if ru.get("range"): parts.append(f"range {ru['range']}")
        if parts: L.append("- rules: " + "; ".join(parts))
        if r["format_notes"]: L.append("- format notes: " + " ".join(_j(n) for n in r["format_notes"]))
        if r["sample_values"]: L.append("- documentation examples: " + ", ".join(_j(e["value"]) for e in r["sample_values"]))
        c = (r["description"]["conventions"] or "").strip()
        if conventions and c: L.append(f"- conventions: {c}")
        return "Field card (from the documentation and the target schema):\n" + "\n".join(L) + "\n" if L else ""

    # ---- source column card
    def source_text(self, relation, column):
        if not getattr(self, "profiling", True): return ""
        r = self.sf.get((relation, column))
        if not r: return ""
        vd, fo = r["value_domain"], r["format_observations"]; L = []
        L.append(f"  card: {r['type']}, length {r['observed_min_length']}-{r['observed_max_length']}, {vd['distinct']} distinct")
        if vd["kind"] == "list": L.append("  values: " + ", ".join(f"{_j(v['value'])} x{v['count']}" for v in vd["values"]))
        by = {}
        for s in r["samples"]: by.setdefault(s["kind"], []).append(s["value"])
        rnd = by.get("random", [])
        if vd["kind"] != "list" and rnd: L.append("  samples: " + ", ".join(_j(v) for v in rnd))
        edge = [f"{k} {_j(by[k][0])}" for k in ("shortest", "longest", "rarest", "leading_zero") if k in by]
        if "mixed_case" in by: edge.append("mixed-case pair " + " / ".join(_j(v) for v in by["mixed_case"]))
        if "null" in by: edge.append("has NULLs")
        if edge: L.append("  edge cases: " + "; ".join(edge))
        f = []
        if fo["top_shapes"]: f.append("shapes " + ", ".join(f"{s['shape']} x{s['count']}" for s in fo["top_shapes"]))
        if fo["separators"]: f.append("separators " + ", ".join(f"{_j(k)} in {v}" for k, v in fo["separators"].items()))
        if fo["case_variants"]: f.append(f"{fo['case_variants']} values differ only by case")
        w = fo["whitespace"]
        if w["leading_trailing"] or w["double_internal"]: f.append(f"whitespace: {w['leading_trailing']} padded, {w['double_internal']} doubled")
        if f: L.append("  format: " + "; ".join(f))
        for o in r["reference_overlap"]:
            g = ", ".join(f"{v['value']} x{v['count']}" for v in o["group_values"])
            L.append(f"  overlaps {o['relation']}.{o['column']}: exact {o['exact_coverage']:.2f}, case-insensitive {o['ci_coverage']:.2f}" + (f" (matched rows by {o.get('group_column')}: {g})" if g else ""))
        return "\n".join(L) + "\n"

    def links_text(self, relations, limit=12):
        rel = set(relations); out = []
        for l in self.links:
            if l["side"] != "source" or l.get("weak") or l["child"] not in rel or l["parent"] not in rel: continue
            out.append(f"- {l['child']}.{'+'.join(l['child_columns'])} -> {l['parent']}.{'+'.join(l['parent_columns'])} ({l['cardinality']}, {l['provenance']})")
        return "\n".join(out[:limit]) + ("\n" if out else "")

    def field_view(self, table, column, matched, conventions=False, description=None, scope=()):
        rels = sorted({m["relation"] for m in matched} | set(scope))
        return {"target": self.target_text(table, column, conventions, description),
                "sources": {f"{m['relation']}.{m['column']}": self.source_text(m["relation"], m["column"]) for m in matched},
                "links": self.links_text(rels)}
