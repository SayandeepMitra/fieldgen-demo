"""Build deliverables/tpcdi_column_mapping_v2.csv from the v1 mapping + the repaired gold.

Changes against v1 (populated columns only; unpopulated tables keep their rows untouched):
  * rule_sql        <- the column's defining expression in ported_historical_load_v2.sql (v1 rows held hand-written text of R1's logic)
  * rule_reliable   <- 'yes' (every populated v1 'no' referred to a defect the v2 gold repairs: placeholder constants, non-exhaustive CASE,
                       varchar join, daily-net Cash, unfiltered DimTrade join; IsCustomer's COUNT(*)>0 is a legitimate boolean test)
  * rule_issue / table_caution <- cleared
  * v2_changed      <- 'yes' when the defining expression text differs from the v1 gold's (after whitespace normalisation)
usage: python build_mapping_v2.py   (independent of TPCDI_GOLD)
"""
import csv, os, re
import grade_swap as g

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(os.path.dirname(HERE), "deliverables")


def gold_exprs(sql_path):
    g.GOLD_SQL = sql_path
    gold = g.load_gold()
    out = {}
    for t, spec in gold.items():
        for c in spec["cols"]:
            found = g.defining_select(spec["insert"].copy(), c)
            out[(t, c)] = re.sub(r"\s+", " ", g._strip_alias(found[0].expressions[found[1]]).sql(dialect="duckdb")) if found else None
    return out


v1 = gold_exprs(os.path.join(D, "ported_historical_load.sql"))
v2 = gold_exprs(os.path.join(D, "ported_historical_load_v2.sql"))
rows = list(csv.DictReader(open(os.path.join(D, "tpcdi_column_mapping.csv"))))
fields = list(rows[0].keys()) + ["v2_changed"]
n_changed = n_unrel = 0
for r in rows:
    k = (r["target_table"], r["target_column"])
    r["v2_changed"] = ""
    if r["table_status"] != "populated" or k not in v2:
        continue
    if r["rule_reliable"] == "no":
        n_unrel += 1
    r["v2_changed"] = "yes" if v1.get(k) != v2[k] else "no"
    n_changed += r["v2_changed"] == "yes"
    r["rule_sql"] = v2[k][:400]
    r["rule_reliable"], r["rule_issue"], r["table_caution"] = "yes", "", ""
with open(os.path.join(D, "tpcdi_column_mapping_v2.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader(); w.writerows(rows)
print(f"{len(rows)} rows; populated columns whose defining expression text changed in v2: {n_changed}; v1 rule_reliable=no cleared: {n_unrel}")
