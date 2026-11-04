"""Mode B task builder: from the package only (manifest, source, target, matches). Schema independent."""
from fieldgen.neighbourhood import source_graph, table_detail

def target_table_view(pkg, table):
    t = pkg.target.table(table)
    return {"name": t["name"], **({"description": t["description"]} if t.get("description") else {}), "pk": t["pk"],
            "fks": [f'{",".join(f["columns"])} -> {f["ref_table"]}.{",".join(f["ref_columns"])}' for f in t["fks"]], "business_ids": t["business_ids"],
            "fields": [{k: v for k, v in {"column": c["name"], "type": c["type"], "nullable": c["nullable"], "description": c.get("description"),
                        "constraints": c["constraints"], "value_hints": c.get("value_hints")}.items() if v is not None} for c in t["columns"]]}

def matched_for(pkg, table, matcher):
    m = pkg.matches(matcher)
    return [{"field": c["name"], "relation": x["relation"], "column": x["column"]}
            for c in pkg.target.table(table)["columns"] for x in m.get(f'{table}.{c["name"]}', [])]

def build_task_b(pkg, table, depth=1, matcher="metadata_aware", include_weak=False, fields=None):
    ms = matched_for(pkg, table, matcher)
    g = source_graph(pkg, [m["relation"] for m in ms], depth, include_weak)
    tv = target_table_view(pkg, table)
    return {"task_id": table, "mode": "B", "settings": {"depth": depth, "matcher": matcher, "hints": "docs", "include_weak_links": include_weak},
            "target_table": tv, "fields": fields or [f["column"] for f in tv["fields"]], "matched_sources": ms, "source_graph": g}
