"""Fill the fieldgen package for TPC-DI (after `fieldgen init`). Inputs: Source tables (already in pkg), the target DDL (already in pkg),
the GIVEN matching (tpcdi_column_mapping.csv: value_columns + skeleton source tables only; rule_sql/lineage/combination are never read),
spec target descriptions (Clause 3.2), spec load/SCD2 conventions (Clause 4.4.1/4.4.2, same text as frozen prompt v5a).
Never reads the gold SQL or any target-table data."""
import csv, json, re, sys
from pathlib import Path
from collections import defaultdict, OrderedDict
HERE = Path(__file__).resolve().parent; PKG = HERE / ("pkg" if len(sys.argv) < 2 else sys.argv[1])
DELIV = HERE.parent / "deliverables"
TARGETS = {"DimDate","DimTime","DimBroker","DimCompany","DimCustomer","DimAccount","DimSecurity","DimTrade","FactCashBalances","FactHoldings","FactMarketHistory","FactWatches","Industry","StatusType","TaxRate","TradeType","Financial","Prospect","DImessages","AuditTable"}
src_tabs = {t["name"]: [c["name"] for c in t["columns"]] for t in json.load(open(PKG / "source/tables.json"))}
tgt_tabs = json.load(open(PKG / "target/tables.json"))
rows = [r for r in csv.DictReader(open(DELIV / "tpcdi_column_mapping.csv")) if r["table_status"] == "populated"]

def refs(s):
    """'Source.T.C' items of a value_columns string; both sides of 'A -> B'; target-table refs and unknown names are dropped."""
    out = []
    for item in [x.strip() for x in s.split(";") if x.strip()]:
        for side in item.split(" -> "):
            p = side.strip().split(".")
            if p[0] == "Source" and len(p) >= 3 and p[1] in src_tabs:
                cols = src_tabs[p[1]] if p[2] == "*" else [p[2]]
                out += [(p[1], c) for c in cols if c in src_tabs[p[1]]]
    return list(OrderedDict.fromkeys(out))

def skeleton_tables(table_rows):
    """tables named in the CSV's source_tables column (a table-level matching artefact); target tables dropped."""
    seen = OrderedDict()
    for r in table_rows:
        for raw in r["source_tables"].split(";"):
            for side in raw.split(" -> "):
                side = re.sub(r"\(.*?\)", "", side).strip(); p = side.split(".")
                if p[0] == "Source" and len(p) >= 2 and p[1] in src_tabs: seen[p[1]] = True
    return list(seen)

by = defaultdict(list)
for r in rows: by[r["target_table"]].append(r)
matches = {}; stats = {"given": 0, "skeleton_fallback": 0, "none": 0}
for t in tgt_tabs:
    tn = t["name"]; orig = next((k for k in by if k.lower() == tn), None); trs = by.get(orig, [])
    sk = skeleton_tables(trs); rmap = {r["target_column"].lower(): r for r in trs}
    for c in t["columns"]:
        key = f"{tn}.{c['name']}"; r = rmap.get(c["name"])
        if r is None: matches[key] = []; stats["none"] += 1; continue
        m = refs(r["value_columns"])
        if m: stats["given"] += 1
        elif sk: m = [(s, col) for s in sk for col in src_tabs[s]]; stats["skeleton_fallback"] += 1
        else: stats["none"] += 1
        matches[key] = [{"relation": a, "column": b} for a, b in m]
json.dump(matches, open(PKG / "matches/matches.json", "w"), indent=1)
print("matches:", stats, "| columns with a match:", sum(1 for v in matches.values() if v))

# keys for the four source tables init could not key (3 are empty in SF3, WatchHistory has no unique column set)
tabs = json.load(open(PKG / "source/tables.json"))
for t in tabs:
    if not t["pk"]:
        t["pk"] = [t["columns"][0]["name"]] if t["name"] != "WatchHistory" else [c["name"] for c in t["columns"]]
        t["business_ids"] = list(t["pk"]); t["pk_provenance"] = {"source": "packager: init found no unique column; not a real key"}
json.dump(tabs, open(PKG / "source/tables.json", "w"), indent=1)

# target documentation = spec Clause 3.2 descriptions (guidance), as fieldgen's native 'target documentation'
spec = json.load(open(DELIV / "tpcdi_spec_target_descriptions.json")); fd = json.load(open(PKG / "target/field_docs.json")); n = 0
low = {k.lower(): v for k, v in spec.items()}
for key in fd["fields"]:
    if key in low and low[key]: fd["fields"][key]["guidance"] = low[key]; n += 1
json.dump(fd, open(PKG / "target/field_docs.json", "w"), indent=1, ensure_ascii=False); print("spec descriptions attached:", n, "of", len(fd["fields"]))

# domain knowledge = frozen v5a conventions (same text as scope_prompt.LOAD_CONTEXT / SCD2_CONTEXT, spec Clause 4.4.1/4.4.2)
dom = PKG / "domain"
(dom / "flow_text.md").unlink(missing_ok=True)
(dom / "domain_knowledge.md").write_text("""You are writing the Historical Load of the TPC-DI data warehouse: the first load of an empty warehouse from the Batch 1 source files.
The spec fixes BatchID per execution phase: Initialization = 0, Historical Load = 1, Incremental Update 1 = 2, Incremental Update 2 = 3.
DimAccount, DimBroker, DimCompany, DimCustomer and DimSecurity are history-tracking ("type 2") dimensions: a source record's natural key stays constant, each recorded change becomes a new row.
A row for a natural key that is not yet in the table gets IsCurrent = TRUE, EffectiveDate = the value given by the transformation, and EndDate = 9999-12-31.
When a later record for the same natural key arrives, the earlier row is expired: IsCurrent = FALSE and EndDate = the EffectiveDate of the new record.
So per natural key the rows form one consecutive chain and exactly one row is current.
""", encoding="utf-8")
(dom / "domain_text.json").write_text(json.dumps({"doc_label": "TPC-DI specification", "empty_markers": ["", "NA"]}), encoding="utf-8")
