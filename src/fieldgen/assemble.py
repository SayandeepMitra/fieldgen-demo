"""Build runnable queries from a recipe branch: aliases come from the recipe's FROM clause; GROUP BY from the recipe."""

def _keys(key_exprs, group_by):
    gb = [g.strip() for g in (group_by or [])]
    return ", ".join((f"{k} AS _k{i}" if (not gb or k in gb) else f"ANY_VALUE({k}) AS _k{i}") for i, k in enumerate(key_exprs))

def _tail(recipe):
    return f" GROUP BY {', '.join(recipe['group_by'])}" if recipe.get("group_by") else ""

def assemble_expr(recipe, branch_id, key_exprs, expr):
    b = next(x for x in recipe["branches"] if x["id"] == branch_id)
    ks = _keys(key_exprs, recipe.get("group_by"))
    return f"SELECT {ks + ', ' if ks else ''}({expr}) AS value {b['from']}{_tail(recipe)}"

def assemble_keys(recipe, branch_id, key_exprs):
    b = next(x for x in recipe["branches"] if x["id"] == branch_id)
    return f"SELECT {_keys(key_exprs, recipe.get('group_by'))} {b['from']}{_tail(recipe)}"

def combine_sql(recipe, sqls):
    glue = " UNION " if recipe["combine"] == "union_distinct" else " UNION ALL "
    return glue.join(f"({s})" for s in sqls)

def assemble_table(recipe, columns, exprs, types, key_exprs=None):
    """One query per target table. columns: target columns in order; exprs: {column: {branch: sql}}; types: {column: type}.
    Each branch selects every field (NULL of the target type when a field has no expression); branches are combined by the
    recipe rule; generated keys (recipe `keys`) are numbered over the combined rows. key_exprs ({branch: [exprs]}) adds the
    alignment key columns _k0.. (harness use)."""
    gen = {k["column"]: k for k in recipe.get("keys") or []}
    parts = []
    for b in recipe["branches"]:
        sel = []
        for i, k in enumerate((key_exprs or {}).get(b["id"], [])): sel.append(_keys([k], recipe.get("group_by")).replace("_k0", f"_k{i}"))
        for c in columns:
            if c in gen: continue
            e = (exprs.get(c) or {}).get(b["id"])
            sel.append(f'TRY_CAST(({e}) AS {types[c]}) AS "{c}"' if e else f'CAST(NULL AS {types[c]}) AS "{c}"')
        parts.append(f"SELECT {', '.join(sel)} {b['from']}{_tail(recipe)}")
    inner = combine_sql(recipe, parts) if len(parts) > 1 else (f"SELECT DISTINCT * FROM ({parts[0]})" if recipe["combine"] == "union_distinct" else parts[0])
    extra = "".join(f', CAST(ROW_NUMBER() OVER (ORDER BY {", ".join(k["order_by"])}) AS {types[c]}) AS "{c}"' for c, k in gen.items() if c in columns)
    ks = "".join(f"_k{i}, " for i in range(len((key_exprs or {}).get(recipe["branches"][0]["id"], []))))
    return f'SELECT {ks}{", ".join(chr(34) + c + chr(34) for c in columns if c not in gen)}{extra} FROM ({inner})'
