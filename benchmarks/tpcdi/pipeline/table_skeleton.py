"""
Level 1 of the two-level prompting strategy (project_plan.md Sec 5.4): resolve the shared
FROM/JOIN skeleton for a target table ONCE, directly from tpcdi_column_mapping.csv's
source_tables/joins columns -- mechanical, no LLM call needed, since the matching (which source
tables/columns feed this target table, and how they join) is assumed already solved.

This exists so that e.g. all 33 DimCustomer columns share ONE resolved join graph instead of the
LLM reconstructing a slightly different 9-table join 33 times over.
"""
import csv
from collections import OrderedDict

MAPPING_CSV = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))), "deliverables/tpcdi_column_mapping.csv")


def load_mapping(table_filter=None):
    with open(MAPPING_CSV, newline="") as f:
        rows = list(csv.DictReader(f))
    if table_filter:
        rows = [r for r in rows if r["target_table"] == table_filter]
    return rows


TARGET_TABLE_NAMES = {"DimDate", "DimTime", "DimBroker", "DimCompany", "DimCustomer", "DimAccount",
                       "DimSecurity", "DimTrade", "FactCashBalances", "FactHoldings",
                       "FactMarketHistory", "FactWatches", "Industry", "StatusType", "TaxRate",
                       "TradeType", "Financial", "Prospect", "DImessages", "AuditTable"}


def _table_ref(fragment):
    """
    Normalize one source_tables fragment down to just its table reference. Defensive against
    an inconsistency in tpcdi_column_mapping.csv found while building this: some rows (e.g.
    DimCustomer's) put the full "Source.Table.Column" path here instead of just "Source.Table"
    -- tracked as a follow-up cleanup (see project_plan.md), not fixed in the CSV yet, so this
    parser tolerates both forms rather than silently mis-reading one of them.

    Fixed 2026-10-04: previously treated "DimBroker.SK_BrokerID" (a column REFERENCE on an
    already-populated TARGET table, from the " -> " lookup-arrow notation) the same as
    "Source.CustomerXML.C_ID" and returned "DimBroker.SK_BrokerID" as if that whole string were
    itself a table name -- it isn't; "DimBroker" is the table, "SK_BrokerID" is its column. This
    produced garbage like "Source tables involved: ..., DimBroker.SK_BrokerID, ..." in the
    resolved skeleton shown to the LLM. Now a single-segment TARGET_TABLE_NAMES match returns
    just the table name.
    """
    fragment = fragment.strip()
    parts = fragment.split(".")
    if not parts:
        return fragment
    if parts[0] == "Source" and len(parts) >= 2:
        return "Source." + parts[1]  # "Source.CustomerXML.C_ID" -> "Source.CustomerXML"
    if parts[0] in TARGET_TABLE_NAMES:
        return parts[0]  # "DimBroker.SK_BrokerID" -> "DimBroker" (not "DimBroker.SK_BrokerID")
    return fragment


def resolve_table_skeleton(target_table):
    """
    Returns {source_tables: [...], joins: [...]} for a target table -- the union of every
    column's source_tables/joins fields, deduplicated, in first-seen order.
    """
    rows = load_mapping(target_table)
    source_tables = OrderedDict()
    joins = OrderedDict()
    for r in rows:
        for raw in r["source_tables"].split(";"):
            raw = raw.strip()
            if not raw:
                continue
            for side in raw.split(" -> "):  # "A.col -> B.col" lookup notation: take both sides
                t = _table_ref(side)
                if t:
                    source_tables[t] = True
        if r["joins"]:
            joins[r["joins"].strip()] = True
    return {
        "target_table": target_table,
        "source_tables": list(source_tables.keys()),
        "joins": list(joins.keys()),
    }


def format_skeleton_for_prompt(skeleton):
    lines = [f"Resolved join skeleton for target table {skeleton['target_table']} (from the matching step, already solved -- do not re-derive):"]
    lines.append("  Source tables involved: " + ", ".join(skeleton["source_tables"]))
    if skeleton["joins"]:
        lines.append("  Join conditions:")
        for j in skeleton["joins"]:
            lines.append(f"    - {j}")
    else:
        lines.append("  Join conditions: none (single-table or no join needed)")
    return "\n".join(lines)


if __name__ == "__main__":
    for t in ["DimCustomer", "DimCompany", "Industry"]:
        print(format_skeleton_for_prompt(resolve_table_skeleton(t)))
        print()
