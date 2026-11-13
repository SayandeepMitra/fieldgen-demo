"""Formula step (generic; generator side): one answer per matched target column of a table, frozen setup (field cards in the prompt, guardrail v2, at most two guardrail retries)."""
from fieldgen.formula_stage import step2_guarded
from fieldgen.final_expr import final_expressions

def formula_columns(task, recipe):
    """Matched target columns of the table, without the columns the recipe generates as keys."""
    gen = {k["column"] for k in recipe.get("keys") or []}
    return [c for c in dict.fromkeys(m["field"] for m in task["matched_sources"]) if c not in gen]

def generate_formula(task, recipe, column, client, dump, pool, source_tables, ov, max_guard_retries=2, rules=None, history="", length_retry=False):
    return step2_guarded(task, recipe, column, client, dump, pool, source_tables, max_guard_retries=max_guard_retries, conventions=False, guard_version=2, rules=rules, history=history, length_retry=length_retry, **ov)

def expressions(result):
    """{branch: sql} of a formula answer, or None."""
    ex = final_expressions(result.get("final")) if result else None
    return {e["branch"]: e["sql"] for e in ex} if ex else None
