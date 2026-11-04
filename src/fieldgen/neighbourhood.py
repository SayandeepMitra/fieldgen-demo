"""Source neighbourhood view over a package (generator side, schema independent).
Matched tables get full detail; parents are followed up to `depth` (0, 1, 2 or "all"); children are one line each.
Weak links (support == value_only) are excluded unless include_weak is set."""

def visible_links(links, include_weak=False):
    return [l for l in links if include_weak or not l.get("weak")]

def digest(profile_col):
    if not profile_col: return None
    d = {"distinct": profile_col.get("distinct"), "null_rate": profile_col.get("null_rate"),
         "top": [v for v, _ in (profile_col.get("top") or [])[:3]]}
    if "min" in profile_col: d["min"], d["max"] = profile_col["min"], profile_col["max"]
    return d

def table_detail(pkg, name):
    t = next(x for x in pkg.source.tables if x["name"] == name)
    prof = (pkg.source.profile(name) or {}).get("columns", {})
    cols = {c["name"]: {k: v for k, v in {"type": c["type"], "description": c.get("description"), "profile": digest(prof.get(c["name"]))}.items() if v is not None}
            for c in t["columns"]}
    return {"pk": t["pk"], "business_ids": t["business_ids"], "rows": (pkg.manifest["source_row_counts"].get(name)), "columns": cols,
            **({"description": t["description"]} if t.get("description") else {})}

def source_graph(pkg, matched_tables, depth=1, include_weak=False):
    links = visible_links(pkg.source.links, include_weak)
    matched = list(dict.fromkeys(matched_tables)); connected, frontier = [], set(matched)
    limit = 10 ** 6 if depth == "all" else int(depth)
    for _ in range(limit):
        nxt = []
        for l in links:
            if l["child"] in frontier and l["parent"] not in matched and l["parent"] not in connected and l["parent"] not in nxt: nxt.append(l["parent"])
        if not nxt: break
        connected += nxt; frontier = set(nxt)
    shown = set(matched) | set(connected)
    return {"matched_tables": {n: table_detail(pkg, n) for n in matched}, "connected_tables": {n: table_detail(pkg, n) for n in connected},
            "children": [{"table": l["child"], "points_to": l["parent"], "via": l["child_columns"][0], "cardinality": l["cardinality"]}
                         for l in links if l["parent"] in shown and l["child"] not in shown],
            "links": [{k: l[k] for k in ("child", "child_columns", "parent", "parent_columns", "cardinality", "provenance")} for l in links
                      if l["child"] in shown and l["parent"] in shown]}

def sizes(graph):
    return {"matched": len(graph["matched_tables"]), "connected": len(graph["connected_tables"]), "children": len(graph["children"]), "links": len(graph["links"])}
