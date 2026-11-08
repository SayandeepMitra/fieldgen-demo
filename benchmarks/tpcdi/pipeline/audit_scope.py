"""Audit of the mapping CSV against the gold-derived scope, for all 210 populated columns.
Writes scope_audit.csv:  derived matched fields vs CSV value_columns, and gold-quality flags."""
import csv, collections
import duckdb
from sqlglot import exp
import grade_swap as g
from scope_prompt import derive_scope, matched_fields, DB_PATH

MAPPING_CSV = f"{g.BASE}/deliverables/tpcdi_column_mapping.csv"


def csv_fields(vc):
    out = set()
    for part in vc.split(";"):
        for tok in part.split(" -> "):
            tok = tok.strip()
            if tok:
                out.add(tok.lower().removeprefix("source."))
    return out


def main():
    con = duckdb.connect(DB_PATH, read_only=True)
    gold = g.load_gold()
    rows = {(r["target_table"], r["target_column"]): r for r in csv.DictReader(open(MAPPING_CSV))}
    out, stat = [], collections.Counter()
    for table, spec in gold.items():
        for col in spec["cols"]:
            r = rows.get((table, col), {})
            sc = derive_scope(gold, con, table, col)
            cur = sc["cur"]
            item = g._strip_alias(cur.expressions[sc["item_index"]])
            literal = isinstance(item, exp.Literal)
            derived = matched_fields(sc)
            dset = {d.lower().removeprefix("source.") for d in derived if d.lower().startswith("source.")}
            cset = csv_fields(r.get("value_columns", ""))
            if not cset:
                st = "csv_empty"
            elif not dset:
                st = "derived_none"
            elif dset <= cset:
                st = "covered"
            elif dset & cset:
                st = "partial"
            else:
                st = "disjoint"
            kind = r.get("column_kind", "")
            quality = "ok"
            if r.get("rule_reliable") == "no":
                quality = "gold_defective(csv)"
            if literal and kind != "constant":
                quality = "gold_placeholder_constant"
            stat[st] += 1
            out.append({"table": table, "column": col, "csv_kind": kind, "relations": "|".join(x["alias"] for x in sc["relations"]),
                        "grouped": sc["grouped"], "derived_fields": "; ".join(derived), "csv_value_columns": r.get("value_columns", ""),
                        "value_columns_status": st, "gold_literal": literal, "csv_rule_reliable": r.get("rule_reliable", ""),
                        "gold_quality": quality})
    with open("scope_audit.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    print("value_columns status:", dict(stat))
    print("gold_quality:", dict(collections.Counter(o["gold_quality"] for o in out)))
    print("placeholder constants:", [(o["table"], o["column"]) for o in out if o["gold_quality"] == "gold_placeholder_constant"])

main()
