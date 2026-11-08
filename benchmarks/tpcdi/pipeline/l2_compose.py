"""Build an L2 submission from L1 answers: the gold query of each table with EVERY column's defining expression replaced by
one model's L1 expression (frozen prompt run). Expressions that did not execute at L1 are replaced by NULL.
This is not a pipeline a model wrote - it is the L1 results composed into whole tables - so it answers: how do per-column
L1 scores translate into table-level end-to-end correctness? (A real model-written pipeline goes through the same
l2_run.py / l2_grade.py path.)   usage: python l2_compose.py RUN MODEL [--repeat 0]   -> runs/l2/_subs/compose_RUN_MODEL/"""
import argparse, json, os, subprocess, sys
import duckdb, sqlglot
from sqlglot import exp
import grade_swap as g

HERE = os.path.dirname(os.path.abspath(__file__))


def compose_query(gold, table, swaps, types):
    ins = gold[table]["insert"].copy()
    cols = gold[table]["cols"]
    sel = ins.expression
    for col, expr_sql in swaps.items():
        found = g.defining_select(ins, col)
        if found is None:
            continue
        cur, i, name = found
        new = sqlglot.parse_one(g.requalify(expr_sql.strip().rstrip(";"), cur), read="duckdb")
        cur.expressions[i] = exp.Alias(this=g._strip_alias(g._strip_alias(new)), alias=exp.to_identifier(name))
    items = [exp.Alias(this=exp.cast(g._strip_alias(it), exp.DataType.build(types[n], dialect="duckdb")), alias=exp.to_identifier(n))
             for n, it in zip(cols, sel.expressions)]
    sel.set("expressions", items)
    wk = g._with_key(ins)
    if wk:
        sel.set(wk, ins.args[wk])
    return sel.sql(dialect="duckdb")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("run"); ap.add_argument("model"); ap.add_argument("--repeat", type=int, default=0)
    a = ap.parse_args()
    graded = [r for r in json.load(open(os.path.join(HERE, __import__("gold_version").RUNS_SUBDIR, a.run, "graded.json"))) if r["model"] == a.model and r["repeat"] == a.repeat]
    by = {}
    for r in graded:
        t, c = r["key"].split(".", 1)
        by.setdefault(t, {})[c] = r["expr"] if r["status"] == "EXECUTED" else "NULL"
    gold = g.load_gold(); con = duckdb.connect(g.DB_PATH, read_only=True)
    d = os.path.join(HERE, __import__("gold_version").RUNS_SUBDIR, "l2", "_subs", f"compose_{a.run}_{a.model}_r{a.repeat}")
    os.makedirs(d, exist_ok=True)
    for t, v in gold.items():
        if t not in by:
            continue
        q = compose_query(gold, t, by[t], g.column_types(con, t))
        open(os.path.join(d, f"{t}.sql"), "w").write(f"INSERT INTO {t} ({', '.join(v['cols'])}) {q};\n")
    print(d)


if __name__ == "__main__":
    main()
