"""Assemble a runnable query for one branch: SELECT <alignment key as _k0.._kn>, (<expr>) AS value <FROM clause>."""

def assemble(task, key_exprs, branch_id, expr):
    branch = next(b for b in task["row_source"]["branches"] if b["id"] == branch_id)
    ks = ", ".join(f"{k} AS _k{i}" for i, k in enumerate(key_exprs))
    return f"SELECT {ks}, ({expr}) AS value {branch['from']}"

def placeholder_key(task):
    return ["1"]
