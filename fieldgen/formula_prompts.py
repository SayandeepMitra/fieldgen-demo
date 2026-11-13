"""Messages for step 1 (recipe) and step 2 (field); field-task builder. Generator side."""
import jinja2
from fieldgen.parse import recipe_info
from fieldgen.paths import PROMPTS_DIR
P = str(PROMPTS_DIR) + "/"
_env = jinja2.Environment(loader=jinja2.FileSystemLoader(P), keep_trailing_newline=True, undefined=jinja2.Undefined)

def _msgs(system, template, **kw):
    return [{"role": "system", "content": open(P + system).read().strip()}, {"role": "user", "content": _env.get_template(template).render(**kw)}]

def step1_messages(task): return _msgs("v2_step1_system.md", "v2_step1_user.md", task=task)
def step2_messages(ftask): return _msgs("v2_step2_system.md", "v2_step2_user.md", task=ftask)

def field_task(task, recipe, column, dump=None, conventions=False, rules=None, history=""):
    """Step 2 input: table task + chosen recipe + one target field + full detail of the tables the recipe uses."""
    view = task.get("recipe_view") if recipe is task.get("recipe") else None     # compact form of a given recipe whose FROM clauses carry large derived relations
    recipe = view or recipe
    info = recipe_info(recipe)
    used = list(dict.fromkeys(t for b in info.values() for t in b["tables"]))
    detail = {**task["source_graph"]["matched_tables"], **task["source_graph"]["connected_tables"]}
    f = next(x for x in task["target_table"]["fields"] if x["column"] == column)
    matched = []
    for m in task["matched_sources"]:
        if m["field"] == column:
            al = {bid: [a for a, t in i["aliases"].items() if t == m["relation"]] for bid, i in info.items()}
            matched.append({"relation": m["relation"], "column": m["column"], "aliases": {b: a[0] for b, a in al.items() if a}})
    tt = task["target_table"]
    ft = {"task_id": f'{tt["name"]}.{column}', "step": "formula", "recipe": recipe, "aliases": {b: i["aliases"] for b, i in info.items()},
            "target": {"table": tt["name"], "column": column, "type": f["type"], "nullable": f["nullable"], "description": f.get("description"),
                       "constraints": f.get("constraints"), "value_hints": f.get("value_hints"), "table_keys": {"pk": tt["pk"], "fks": tt["fks"], "business_ids": tt["business_ids"]}},
            "matched": matched, "relations": {t: detail[t] for t in used if t in detail}}
    if rules: ft["rules"] = rules
    if history: ft["history"] = history
    if dump is not None: ft["dump"] = dump.field_view(tt["name"], column, matched, conventions=conventions, description=f.get("description"), scope=used)
    return ft
