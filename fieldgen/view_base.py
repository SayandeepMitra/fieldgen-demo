"""Step 1 (recipe) prompt content from the field-knowledge dump (generic; generator side). Reads the package and the dump only."""
import json
from fieldgen import cards as D
from fieldgen.cards_view import DumpView
from fieldgen.neighbourhood import visible_links, table_detail
from fieldgen.tasks import build_task_b

PARENT_LIMIT, OTHER_LIMIT = 30, 12
def _j(v): return json.dumps(v, ensure_ascii=False)
def _clip(s, n): s = " ".join(str(s).split()); return s if len(s) <= n else s[:n - 3] + "..."

class Step1View(DumpView):
    profiling = True      # data_profiling switch: False hides value lists, null rates and source column cards
    def __init__(self, pkg, pkg_root):
        super().__init__(pkg_root); self.pkg = pkg; d = D.load_dump(pkg_root)
        self.tt = {t["name"]: t for t in d["tables"] if t["side"] == "target"}
        self.links = visible_links(pkg.source.links); self.parents = {l["parent"] for l in self.links}
        self.src = {t["name"]: t for t in pkg.source.tables}

    # ---- target
    def table_card(self, table):
        t = self.pkg.target.table(table); c = self.tt.get(table, {}); L = []
        if t.get("description"): L.append(t["description"])
        L.append(f"Primary key: {', '.join(t['pk']) or 'none'}; grain candidates: " + ("; ".join(f"{', '.join(g['columns'])} ({g['kind']})" for g in c.get("grain_candidates", [])) or "none") + f"; business ids: {', '.join(t['business_ids']) or 'none'}")
        L.append("Foreign keys: " + ("; ".join(f"{','.join(f['columns'])} -> {f['ref_table']}.{','.join(f['ref_columns'])} (parent table {f['ref_table']})" for f in t["fks"]) or "none"))
        return "\n".join(L)

    def field_cards(self, table, fields):
        t = self.pkg.target.table(table); out = []
        for col in t["columns"]:
            if col["name"] not in fields: continue
            r = self.tf.get((table, col["name"]))
            if not r: continue
            g = (r["description"]["guidance"] or r["description"]["conventions"] or "").strip()
            L = [f"- {col['name']} ({col['type']}, {'nullable' if col['nullable'] else 'not null'})" + (f": {_clip(g, 250)}" if g else "")]
            av = r["allowed_values"]
            if av["kind"] == "pairs": L.append("  allowed values (id = label): " + "; ".join(f"{e['value']} = {e.get('label', '')}" for e in av["entries"]))
            elif av["kind"] == "values": L.append("  allowed values: " + ", ".join(_j(e["value"]) for e in av["entries"]))
            if r["special_values"]: L.append("  special values: " + "; ".join(f"{e['value']} = {e.get('label', '')}" for e in r["special_values"]))
            ru = r["rules"]; p = []
            if ru.get("max_length") is not None: p.append(f"max length {ru['max_length']}")
            if ru.get("pattern"): p.append("digits only" if ru["pattern"] == "^[0-9]+$" else f"pattern {ru['pattern']}")
            if ru.get("lengths"): p.append("length is one of " + ", ".join(map(str, ru["lengths"])))
            if p: L.append("  rules: " + "; ".join(p))
            if r["format_notes"]: L.append("  format notes: " + _clip(" ".join(r["format_notes"]), 200))
            out.append("\n".join(L))
        return "\n".join(out)

    # ---- source relations
    def relation_text(self, name):
        t = self.src[name]; limit = PARENT_LIMIT if name in self.parents else OTHER_LIMIT
        rows = self.pkg.manifest["source_row_counts"].get(name); L = [f"#### {name} ({rows} rows)"]
        if t.get("description"): L.append(_clip(t["description"], 200))
        L.append(f"PK: {', '.join(t['pk']) or 'none'}; business ids: {', '.join(t['business_ids']) or 'none'}")
        for c in t["columns"]:
            card = self.sf.get((name, c["name"])); line = f"- {c['name']} ({c['type']})" + (f": {_clip(c['description'], 100)}" if c.get("description") else "")
            if card:
                vd, pr = card["value_domain"], card.get("profile") or {}; bits = [f"distinct {vd['distinct']}", f"null rate {pr.get('null_rate')}"]
                if vd["kind"] == "list" and vd["distinct"] <= limit and c["type"].upper().startswith(("VARCHAR", "TEXT", "INT", "BIGINT")) and vd["distinct"] > 0:
                    bits.append("values: " + ", ".join(f"{_j(_clip(v['value'], 40))} x{v['count']}" for v in vd["values"]))
                else:
                    top = [v for v, _ in (pr.get("top") or [])[:3]]
                    if top: bits.append("e.g. " + _j([_clip(x, 40) for x in top]))
                line += " [" + ", ".join(bits) + "]"
            L.append(line)
        return "\n".join(L) + "\n"

    def link_lines(self, shown):
        out = []
        for l in self.links:
            if l["child"] in shown and l["parent"] in shown:
                out.append(f"- {l['child']}.{','.join(l['child_columns'])} -> {l['parent']}.{','.join(l['parent_columns'])} ({l['cardinality']}, {l['provenance']}"
                           + (f", support {l['support']}" if l.get("support") else "") + (", evidence: " + _clip(l["evidence"], 60) if l.get("evidence") else "") + ")")
        return "\n".join(out)

    def bridges(self, shown):
        n = {}
        for l in self.links:
            if l["parent"] in shown and l["child"] not in shown: n[l["child"]] = n.get(l["child"], 0) + 1
        return sorted(c for c, k in n.items() if k >= 2)

def build_step1_task(pkg, view, table, depth=1):
    task = build_task_b(pkg, table, depth, "metadata_aware", False); sg = task["source_graph"]
    shown = set(sg["matched_tables"]) | set(sg["connected_tables"]); bridges = view.bridges(shown)
    for b in bridges: sg["connected_tables"][b] = {**table_detail(pkg, b), "bridge": True}
    allshown = shown | set(bridges)
    sg["children"] = [{"table": l["child"], "points_to": l["parent"], "via": l["child_columns"][0], "cardinality": l["cardinality"]} for l in view.links if l["parent"] in allshown and l["child"] not in allshown]
    sg["links"] = [{k: l[k] for k in ("child", "child_columns", "parent", "parent_columns", "cardinality", "provenance")} for l in view.links if l["child"] in allshown and l["parent"] in allshown]
    matched_fields = list(dict.fromkeys(m["field"] for m in task["matched_sources"]))
    cards = []; seen = set()
    for m in task["matched_sources"]:
        k = (m["relation"], m["column"])
        if k in seen: continue
        seen.add(k); tx = view.source_text(*k)
        if tx: cards.append(f"- {k[0]}.{k[1]}\n{tx}")
    task["e1"] = {"table_card": view.table_card(table), "field_cards": view.field_cards(table, matched_fields),
                  "matched_cards": "\n".join(cards), "matched_relations": [r for r in sg["matched_tables"]], "connected_relations": [r for r in sg["connected_tables"] if r not in bridges],
                  "bridges": bridges, "relation_text": {r: view.relation_text(r) for r in list(sg["matched_tables"]) + list(sg["connected_tables"])},
                  "links": view.link_lines(allshown)}
    return task
