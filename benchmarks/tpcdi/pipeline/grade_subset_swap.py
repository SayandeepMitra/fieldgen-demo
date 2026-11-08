"""Grade every cell in subset_results.json with the generic swap-in grader (grade_swap.py)."""
import json, sys
import duckdb, sqlglot
from sqlglot import exp
import grade_swap as g
from grade_subset import clean_sql, RESULTS_PATH

MODELS = ("nemotron", "gpt_oss", "cohere_code", "qwen")


def requalify(expr_sql, gold, table):
    """Rewrite table qualifiers the model used (Source.FinwireCMP.x / FinwireCMP.x) to the alias
    the gold final SELECT gives that table, so a correct column reference resolves in scope."""
    tree = sqlglot.parse_one(expr_sql, read="duckdb")
    sel = gold[table]["insert"].expression
    alias_of = {}
    for t in sel.find_all(exp.Table):
        alias_of[t.name.lower()] = t.alias_or_name
    for c in tree.find_all(exp.Column):
        q = c.table
        if q and q.lower() in alias_of and alias_of[q.lower()] != q:
            c.set("table", exp.to_identifier(alias_of[q.lower()]))
            c.set("db", None)
    return tree.sql(dialect="duckdb")


def main():
    con = duckdb.connect(g.DB_PATH, read_only=True)
    gold = g.load_gold()
    res = json.load(open(RESULTS_PATH))
    rows = []
    for key, cells in res.items():
        table, col = key.split(".", 1)
        if table not in gold or col not in gold[table]["cols"]:
            continue
        for m in MODELS:
            d = cells.get(m)
            if not isinstance(d, dict) or not d.get("sql"):
                continue
            try:
                e = clean_sql(d["sql"])
            except Exception as ex:
                rows.append((key, m, "PARSE_FAILED", None, str(ex)[:80])); continue
            r = g.grade_candidate(con, gold, table, col, e)
            rows.append((key, m, r["status"], r.get("match_pct"), (r.get("error") or "")[:110].replace("\n", " ")))
            print(f"{key:34s} {m:12s} {r['status']:17s} {str(r.get('match_pct')):>7s}  {(r.get('error') or '')[:110]}".replace("\n"," "), flush=True)
    json.dump(rows, open("grade_swap_results.json", "w"), indent=1)

main()
