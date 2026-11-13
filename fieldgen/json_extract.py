"""Parse and validate model output."""
import json, re
import jsonschema, sqlglot
from sqlglot import exp
from fieldgen.llm import strip_think
SCHEMA = None

def extract_json(text):
    text = strip_think(text)
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        try: return json.loads(m.group(1))
        except Exception: pass
    start = text.find("{")
    while start != -1:
        depth, instr, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if instr:
                if esc: esc = False
                elif ch == "\\": esc = True
                elif ch == '"': instr = False
            elif ch == '"': instr = True
            elif ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try: return json.loads(text[start:i + 1])
                    except Exception: break
        start = text.find("{", start + 1)
    return None

def _check_sql(sql, branch, task, errors):
    if ";" in sql: errors.append(f"{branch['id']}: semicolon in sql"); return
    try: tree = sqlglot.parse_one(sql, read="duckdb")
    except Exception as e: errors.append(f"{branch['id']}: sql does not parse ({str(e)[:80]})"); return
    if tree.find(exp.Select) or tree.find(exp.From): errors.append(f"{branch['id']}: SELECT/FROM not allowed"); return
    cols = {a: {c.lower() for c in task["relations"][t]["columns"]} for a, t in branch["aliases"].items() if t in task["relations"]}
    allcols = set().union(*cols.values()) if cols else set()
    for c in tree.find_all(exp.Column):
        if c.table:
            if c.table not in cols: errors.append(f"{branch['id']}: unknown alias {c.table}")
            elif c.name.lower() not in cols[c.table]: errors.append(f"{branch['id']}: column {c.table}.{c.name} not in relation")
        elif c.name.lower() not in allcols: errors.append(f"{branch['id']}: unknown column {c.name}")

def _check_exprs(exprs, task, errors, where=""):
    branches = {b["id"]: b for b in task["row_source"]["branches"]}
    seen = [e["branch"] for e in exprs]
    for b in branches:
        if seen.count(b) != 1: errors.append(f"{where}branch {b} covered {seen.count(b)} times")
    for e in exprs:
        if e["branch"] not in branches: errors.append(f"{where}unknown branch {e['branch']}")
        else: _check_sql(e["sql"], branches[e["branch"]], task, errors)

def parse_response(text, task):
    obj = extract_json(text)
    if obj is None: return None, ["no JSON object found"]
    errors = [f"schema: {e.message[:120]}" for e in jsonschema.Draft7Validator(SCHEMA).iter_errors(obj)]
    if errors: return None, errors
    if obj["task_id"] != task["task_id"]: errors.append("task_id mismatch")
    if obj["status"] == "answer": _check_exprs(obj["expressions"], task, errors)
    else:
        for i, c in enumerate(obj["candidates"]): _check_exprs(c["expressions"], task, errors, f"candidate {i}: ")
        if obj["default"] >= len(obj["candidates"]): errors.append("default index out of range")
    return (None if errors else obj), errors
