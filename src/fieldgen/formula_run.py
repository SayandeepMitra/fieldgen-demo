"""Two-step generation with one retry: step 1 recipe (mode B) or given recipe (mode A), step 2 expressions per field. Generator side."""
from fieldgen.formula_prompts import step1_messages, step2_messages, field_task
from fieldgen.parse import parse_recipe, parse_field
from fieldgen.assemble import assemble_expr, assemble_table
from fieldgen.final_expr import final_expressions

def _usage(rs): return {"in": sum(r.usage.get("prompt_tokens", 0) for r in rs), "out": sum(r.usage.get("completion_tokens", 0) for r in rs)}
_CON = {}
def task_con(task): return _CON["con"].cursor()
def set_connection(con): _CON["con"] = con

def run_sql_ok(con, sqls):
    try:
        for q in sqls: con.execute(f"select count(*) from ({q})").fetchall()
        return True, None
    except Exception as e: return False, str(e)[:200]

RETRY = ("Your previous answer was rejected for this reason:\n{errs}\n\nThe failing answer was:\n{text}\n\n"
         "Return a corrected JSON object only, in the same format. Fix the problem without changing anything that was correct.")

def _attempt(client, msgs, tag, check, ov):
    r = client.chat(msgs, tag=tag, **ov)
    out = check(r.text); out.update({"text": r.text, "tokens": _usage([r]), "latency_s": r.latency_s}); return out

def _with_retry(client, msgs, tag, check, ov):
    first = _attempt(client, msgs, tag, check, ov)
    if not first["errors"]: return first, None, first
    m2 = msgs + [{"role": "assistant", "content": first["text"][:6000]}, {"role": "user", "content": RETRY.format(errs="; ".join(first["errors"][:4]), text=first["text"][:3000])}]
    second = _attempt(client, m2, tag + ":retry", check, ov)
    return first, second, second

def step1(task, client, retry=True, **ov):
    msgs = step1_messages(task)
    def check(text):
        recipe, errs = parse_recipe(text, task); runs = None
        if recipe:
            runs, err = run_sql_ok(task_con(task), [f"SELECT 1 {b['from']}" + (f" GROUP BY {', '.join(recipe['group_by'])}" if recipe.get("group_by") else "") for b in recipe["branches"]])
            if not runs: errs = errs + [f"recipe does not run: {err}"]
        return {"recipe": recipe, "errors": errs, "runs": runs}
    if retry: first, second, final = _with_retry(client, msgs, "step1:" + task["task_id"], check, ov)
    else: first = final = _attempt(client, msgs, "step1:" + task["task_id"], check, ov); second = None
    tok = {k: first["tokens"][k] + (second["tokens"][k] if second else 0) for k in ("in", "out")}
    return {"messages": msgs, "first": first, "retry": second, **{k: final[k] for k in ("text", "recipe", "errors", "runs")}, "tokens": tok,
            "retry_tokens": second["tokens"] if second else {"in": 0, "out": 0}, "latency_s": first["latency_s"] + (second["latency_s"] if second else 0)}

def step2(task, recipe, column, client, retry=True, **ov):
    ft = field_task(task, recipe, column); msgs = step2_messages(ft)
    def check(text):
        obj, errs = parse_field(text, ft); runs = None; asm = {}
        ex = final_expressions(obj)
        if ex:
            asm = {e["branch"]: assemble_expr(recipe, e["branch"], [], e["sql"]) for e in ex}
            runs, err = run_sql_ok(task_con(task), list(asm.values()))
            if not runs: errs = errs + [f"does not run: {err}"]
        return {"final": obj, "errors": errs, "runs": runs, "assembled_sql": asm}
    if retry: first, second, final = _with_retry(client, msgs, "step2:" + ft["task_id"], check, ov)
    else: first = final = _attempt(client, msgs, "step2:" + ft["task_id"], check, ov); second = None
    tok = {k: first["tokens"][k] + (second["tokens"][k] if second else 0) for k in ("in", "out")}
    return {"task_id": ft["task_id"], "messages": msgs, "first": first, "retry": second, **{k: final[k] for k in ("text", "final", "errors", "runs", "assembled_sql")},
            "tokens": tok, "retry_tokens": second["tokens"] if second else {"in": 0, "out": 0}, "latency_s": first["latency_s"] + (second["latency_s"] if second else 0)}

def table_sql(task, recipe, field_results):
    """Table-level query from the recipe and the final formulas (no alignment keys): generator-side build check."""
    cols = [f["column"] for f in task["target_table"]["fields"]]; types = {f["column"]: f["type"] for f in task["target_table"]["fields"]}
    exprs = {}
    for r in field_results:
        ex = final_expressions(r["final"])
        if ex: exprs[r["task_id"].split(".", 1)[1]] = {e["branch"]: e["sql"] for e in ex}
    return assemble_table(recipe, cols, exprs, types)
