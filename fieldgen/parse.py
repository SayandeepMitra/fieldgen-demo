"""Parse and check model output for step 1 (recipe) and step 2 (field expressions). Generator side."""
import json, re
import jsonschema, sqlglot
from sqlglot import exp
from fieldgen.json_extract import extract_json
from fieldgen.paths import SCHEMAS_DIR
D = str(SCHEMAS_DIR / "v2") + "/"
RECIPE_SCHEMA = json.load(open(D + "recipe.schema.json"))
OUTPUT_SCHEMA = json.load(open(D + "output.schema.json"))
# the optional recipe field `history` is accepted only with history_auto on; with it off the recipe schema is exactly the v1.2-demo schema
RECIPE_SCHEMA_HISTORY = {**RECIPE_SCHEMA, "properties": {**RECIPE_SCHEMA["properties"], "history": {"anyOf": [{"type": "null"}, {"type": "object", "required": ["key", "order", "tiebreak"], "additionalProperties": False,
                         "properties": {"key": {"type": "string", "minLength": 1}, "order": {"type": "string", "minLength": 1}, "tiebreak": {"type": "string", "minLength": 1}}}]}}}

def branch_tables(from_sql):
    """({alias: table}, [tables]) of a FROM clause. Aliases are those of the top-level sources only (a derived source maps to
    "(derived)"); tables lists every table read, including inside subqueries. Raises ValueError when it does not parse or a top-level alias clashes."""
    tree = sqlglot.parse_one("SELECT 1 " + from_sql.strip(), read="duckdb")
    fr = tree.args.get("from_") or tree.args.get("from")
    if fr is None: raise ValueError("no FROM clause")
    aliases = {}
    for n in [fr.this] + [j.this for j in tree.args.get("joins") or []]:
        a = n.alias_or_name
        v = n.name if isinstance(n, exp.Table) else "(derived)"
        if a in aliases and aliases[a] != v: raise ValueError(f"alias {a} used for two tables")
        aliases[a] = v
    tabs = []
    for t in tree.find_all(exp.Table):
        if t.name not in tabs: tabs.append(t.name)
    return aliases, tabs

def recipe_info(recipe):
    return {b["id"]: dict(zip(("aliases", "tables"), branch_tables(b["from"]))) for b in recipe["branches"]}

def _cols(task):
    return {t: {c.lower() for c in d["columns"]} for t, d in {**task["source_graph"]["matched_tables"], **task["source_graph"]["connected_tables"]}.items()}

def check_recipe(recipe, task, shown_only=True):
    errs, cols = [], _cols(task)
    ids = [b["id"] for b in recipe["branches"]]
    if len(set(ids)) != len(ids): errs.append("duplicate branch ids")
    if recipe["combine"] == "none" and len(ids) > 1: errs.append("combine is none but several branches are given")
    for b in recipe["branches"]:
        try: al, tabs = branch_tables(b["from"])
        except Exception as e: errs.append(f"{b['id']}: from clause invalid ({str(e)[:80]})"); continue
        for t in tabs:
            if t not in cols: errs.append(f"{b['id']}: table {t} is not in the provided source tables")
        try: tree = sqlglot.parse_one("SELECT 1 " + b["from"], read="duckdb")
        except Exception: continue
        for c in tree.find_all(exp.Column):
            if c.table and c.table in al and al[c.table] in cols and c.name.lower() not in cols[al[c.table]]: errs.append(f"{b['id']}: column {c.table}.{c.name} not in {al[c.table]}")
            elif c.table and c.table not in al: errs.append(f"{b['id']}: unknown alias {c.table}")
    fields = {f["column"] for f in task["target_table"]["fields"]}
    for k in recipe.get("keys") or []:
        if k["column"] not in fields: errs.append(f"keys: {k['column']} is not a field of the target table")
        for o in k["order_by"]:
            try: refs = {c.name for c in sqlglot.parse_one(o, read="duckdb").find_all(exp.Column)}
            except Exception: errs.append(f"keys: order_by item does not parse: {o[:40]}"); continue
            for r in refs:
                if r not in fields: errs.append(f"keys: order_by uses {r}, which is not a field of the target table")
                if r == k["column"]: errs.append(f"keys: {k['column']} cannot be ordered by itself")
    for g in recipe.get("group_by") or []:
        try: sqlglot.parse_one(g, read="duckdb")
        except Exception: errs.append(f"group_by item does not parse: {g[:40]}")
    return errs

def parse_recipe(text, task, allow_history=False):
    obj = extract_json(text)
    if obj is None: return None, ["no JSON object found"]
    errs = [f"schema: {e.message[:120]}" for e in jsonschema.Draft7Validator(RECIPE_SCHEMA_HISTORY if allow_history else RECIPE_SCHEMA).iter_errors(obj)]
    if errs: return None, errs
    if obj["task_id"] != task["task_id"]: errs.append("task_id mismatch")
    errs += check_recipe(obj, task)
    return (None if errs else obj), errs

AGG = (exp.AggFunc,)
def _check_expr(sql, branch_id, info, recipe, cols, errs, keygen_ok):
    if ";" in sql: errs.append(f"{branch_id}: semicolon in sql"); return
    try: tree = sqlglot.parse_one(sql, read="duckdb")
    except Exception as e: errs.append(f"{branch_id}: sql does not parse ({str(e)[:80]})"); return
    if tree.find(exp.Select) or tree.find(exp.From): errs.append(f"{branch_id}: SELECT/FROM not allowed"); return
    al = info[branch_id]["aliases"]
    allc = set().union(*[cols.get(t, set()) for t in al.values()]) if al else set()
    for c in tree.find_all(exp.Column):
        if c.table:
            if c.table not in al: errs.append(f"{branch_id}: unknown alias {c.table}")
            elif al[c.table] == "(derived)": pass
            elif c.name.lower() not in cols.get(al[c.table], set()): errs.append(f"{branch_id}: column {c.table}.{c.name} not in relation")
        elif c.name.lower() not in allc: errs.append(f"{branch_id}: unknown column {c.name}")
    if tree.find(*AGG) and not recipe.get("group_by") and not tree.find(exp.Window): errs.append(f"{branch_id}: aggregate used but the recipe has no group_by")

def _exprs(exprs, recipe, info, cols, errs, where=""):
    ids = [b["id"] for b in recipe["branches"]]; seen = [e["branch"] for e in exprs]
    for b in ids:
        if seen.count(b) != 1: errs.append(f"{where}branch {b} covered {seen.count(b)} times")
    for e in exprs:
        if e["branch"] in info: _check_expr(e["sql"], e["branch"], info, recipe, cols, errs, True)
        else: errs.append(f"{where}unknown branch {e['branch']}")

def parse_field(text, ftask):
    obj = extract_json(text)
    if obj is None: return None, ["no JSON object found"]
    errs = [f"schema: {e.message[:120]}" for e in jsonschema.Draft7Validator(OUTPUT_SCHEMA).iter_errors(obj)]
    if errs: return None, errs
    if obj["task_id"] != ftask["task_id"]: errs.append("task_id mismatch")
    info = recipe_info(ftask["recipe"]); cols = {t: {c.lower() for c in d["columns"]} for t, d in ftask["relations"].items()}
    if obj["status"] == "answer": _exprs(obj["expressions"], ftask["recipe"], info, cols, errs)
    else:
        for i, c in enumerate(obj["candidates"]): _exprs(c["expressions"], ftask["recipe"], info, cols, errs, f"candidate {i}: ")
        if obj["default"] >= len(obj["candidates"]): errs.append("default index out of range")
    return (None if errs else obj), errs
