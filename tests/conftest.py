"""Test fixtures: a small synthetic package (a shop: customers, orders, state codes -> client, purchase, state), a reference folder in both formats, and a fake HTTP transport for the model endpoint.
No network, no key. The names are invented on purpose: nothing in src/ may depend on the example dataset."""
import csv, json, os, re, shutil, threading
from pathlib import Path
import pytest

def _w(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(obj, indent=1), encoding="utf-8")
def _csv(p, header, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as f: w = csv.writer(f); w.writerow(header); w.writerows(rows)

SRC = {"customers": ([("cust_id", "VARCHAR"), ("full_name", "VARCHAR"), ("joined_on", "DATE"), ("city", "VARCHAR"), ("status_code", "VARCHAR")], ["cust_id"],
                     [["c1", "Ann Lee", "2020-01-05", "Paris", "A"], ["c2", "Bob Roy", "2021-03-10", "Rome", "A"], ["c3", "Cy Dee", "2019-07-21", "Oslo", "B"], ["c4", "Di Fox", "2022-11-30", "Riga", "B"]]),
       "orders": ([("order_id", "VARCHAR"), ("cust_id", "VARCHAR"), ("order_date", "DATE"), ("amount", "DOUBLE"), ("state_code", "VARCHAR"), ("placed_at", "TIMESTAMP WITH TIME ZONE")], ["order_id"],
                  [["o1", "c1", "2023-01-02", "10.5", "TX", "2023-01-02 09:30:00+05:30"], ["o2", "c1", "2023-02-03", "20.0", "CA", "2023-02-03 09:30:00+05:30"], ["o3", "c2", "2023-03-04", "5.25", "TX", "2023-03-04 09:30:00+05:30"], ["o4", "c3", "2023-04-05", "7.0", "NY", "2023-04-05 09:30:00+05:30"],
                   ["o5", "c3", "2023-05-06", "9.99", "NY", "2023-05-06 09:30:00+05:30"], ["o6", "c4", "2023-06-07", "100.0", "CA", "2023-06-07 09:30:00+05:30"]]),
       "state_codes": ([("code", "VARCHAR"), ("label", "VARCHAR")], ["code"], [["TX", "Texas"], ["CA", "California"], ["NY", "New York"]])}
TGT = {"client": [("client_id", "integer"), ("client_name", "varchar(50)"), ("joined_date", "date"), ("city", "varchar(30)"), ("client_source_value", "varchar(20)")],
       "purchase": [("purchase_id", "integer"), ("client_id", "integer"), ("purchase_date", "date"), ("amount", "double"), ("state_label", "varchar(20)"), ("purchase_source_value", "varchar(20)")],
       "state": [("code", "varchar(5)"), ("label", "varchar(20)")]}
TPK = {"client": "client_id", "purchase": "purchase_id", "state": "code"}
MATCH = {"client.client_name": ["customers.full_name"], "client.joined_date": ["customers.joined_on"], "client.city": ["customers.city"], "client.client_source_value": ["customers.cust_id"],
         "purchase.purchase_date": ["orders.order_date"], "purchase.amount": ["orders.amount"], "purchase.state_label": ["state_codes.label"], "purchase.purchase_source_value": ["orders.order_id"],
         "state.code": ["state_codes.code"], "state.label": ["state_codes.label"]}
RECIPES = {"client": {"task_id": "client", "step": "recipe", "grain": "one row per customer", "branches": [{"id": "b1", "from": "FROM customers c"}], "combine": "none", "group_by": None,
                      "keys": [{"column": "client_id", "order_by": ["client_name"]}], "decisions": {"joins": [], "stacked": False, "deduplicated": False, "aggregated": False}, "assumptions": []},
           "purchase": {"task_id": "purchase", "step": "recipe", "grain": "one row per order", "branches": [{"id": "b1", "from": "FROM orders o JOIN state_codes s ON o.state_code = s.code"}], "combine": "none", "group_by": None,
                        "keys": [{"column": "purchase_id", "order_by": ["purchase_date", "purchase_source_value"]}], "decisions": {"joins": ["orders to state_codes"], "stacked": False, "deduplicated": False, "aggregated": False}, "assumptions": []}}
FORMULAS = {"client.client_name": "c.full_name", "client.joined_date": "c.joined_on", "client.city": "c.city", "client.client_source_value": "c.cust_id",
            "purchase.purchase_date": "o.order_date", "purchase.amount": "o.amount", "purchase.state_label": "s.label", "purchase.purchase_source_value": "o.order_id"}

def make_package(root):
    root = Path(root)
    _w(root / "manifest.json", {"name": "shop", "version": "1.0", "source_row_counts": {t: len(v[2]) for t, v in SRC.items()}, "target_tables": len(TGT)})
    _w(root / "source/tables.json", [{"name": t, "columns": [{"name": c, "type": ty, "nullable": True} for c, ty in v[0]], "pk": v[1], "business_ids": v[1], "description": f"The {t} table of the shop system."} for t, v in SRC.items()])
    for t, v in SRC.items(): _csv(root / f"source/data/{t}.csv", [c for c, _ in v[0]], v[2])
    _w(root / "source/links.json", [{"child": "orders", "child_columns": ["cust_id"], "parent": "customers", "parent_columns": ["cust_id"], "cardinality": "many_to_one", "provenance": "declared", "support": "dictionary", "weak": False},
                                    {"child": "orders", "child_columns": ["state_code"], "parent": "state_codes", "parent_columns": ["code"], "cardinality": "many_to_one", "provenance": "declared", "support": "dictionary", "weak": False}])
    _w(root / "target/tables.json", [{"name": t, "columns": [{"name": c, "type": ty, "nullable": c != TPK[t], "constraints": ["primary key"] if c == TPK[t] else [], "description": f"{c} of {t}"} for c, ty in cols], "pk": [TPK[t]],
                                      "fks": [{"columns": ["client_id"], "ref_table": "client", "ref_columns": ["client_id"]}] if t == "purchase" else [], "business_ids": [], "description": f"The {t} table."} for t, cols in TGT.items()])
    _w(root / "matches/matches.json", {f"{t}.{c}": [{"relation": x.split(".")[0], "column": x.split(".")[1]} for x in MATCH.get(f"{t}.{c}", [])] for t, cols in TGT.items() for c, _ in cols})
    _w(root / "target/field_docs.json", {"tables": {t: {"description": f"The {t} table.", "guidance": None, "conventions": None} for t in TGT},
                                         "fields": {f"{t}.{c}": {"guidance": f"{c} of {t}, as documented.", "conventions": "Convention text." if c == "city" else None, "ddl": {"type": ty, "default": None, "check_constraints": [], "unique": False}} for t, cols in TGT.items() for c, ty in cols}})
    _w(root / "target/reference_tables.json", {"reference_tables": [{"target_table": "state", "source_relation": "state_codes", "id_column": "code", "label_column": "label", "default_filters": []}], "field_filters": {}})
    d = root / "domain"; d.mkdir(parents=True, exist_ok=True)
    (d / "domain_knowledge.md").write_text("A client is a customer of the shop. A purchase is one order.\n", encoding="utf-8"); (d / "flow_text.md").write_text("Orders become purchases; the state label comes from state_codes.\n", encoding="utf-8")
    _w(d / "domain_text.json", {"doc_label": "Target documentation", "rule_table": "state", "empty_markers": ["", "NA"]})
    _w(d / "descriptions_supplement.json", [{"table": "state_codes", "column": None, "text": "Codes of the states an order is shipped to.", "provenance": "test"}]); _w(d / "value_meanings.json", [])
    return root

def make_reference(root, full=True):
    """Reference folder: reference_data/*.csv plus either the full format (recipes/, fields/) or the minimum format (alignment.json)."""
    root = Path(root); ids = {"c1": 1, "c2": 2, "c3": 3, "c4": 4}
    _csv(root / "reference_data/client.csv", [c for c, _ in TGT["client"]], [[ids[r[0]], r[1], r[2], r[3], r[0]] for r in SRC["customers"][2]])
    names = {r[0]: r[1] for r in SRC["customers"][2]}; states = {r[0]: r[1] for r in SRC["state_codes"][2]}
    order = sorted(SRC["orders"][2], key=lambda r: (r[2], r[0]))
    _csv(root / "reference_data/purchase.csv", [c for c, _ in TGT["purchase"]], [[i + 1, "", r[2], r[3], states[r[4]], r[0]] for i, r in enumerate(order)])
    _csv(root / "reference_data/state.csv", ["code", "label"], SRC["state_codes"][2])
    if full:
        for t, r in RECIPES.items(): _w(root / f"recipes/{t}.json", {"table": t, "grain": r["grain"], "branches": r["branches"], "combine": "none", "group_by": None})
        for t, cols in (("client", TGT["client"]), ("purchase", TGT["purchase"])):
            for c, _ in cols:
                src = "customers.cust_id" if t == "client" else "orders.order_id"; ref = "r.client_source_value" if t == "client" else "r.purchase_source_value"
                kind = "keygen" if c == TPK[t] else ("excluded" if c == "client_id" else "value")
                _w(root / f"fields/{t}.{c}.json", {"task_id": f"{t}.{c}", "table": t, "column": c, "kind": kind, "reference": {"table": t, "column": c}, "expressions": [{"branch": "b1", "expr": FORMULAS.get(f"{t}.{c}", "1")}],
                                                  "alignment": {"source": [f"b1:{src}"], "reference": [ref]}, "alignment_quality": "strong", "ambiguity": {"ambiguous": False, "reason": "test", "source": "pending"}, "exclusion_reason": None})
    else:
        _w(root / "alignment.json", {"client": {"source": ["customers.cust_id"], "reference": ["client_source_value"], "exclude": ["client_id"]}, "purchase": {"source": ["orders.order_id"], "reference": ["purchase_source_value"], "exclude": ["purchase_id", "client_id"]}})
    return root

@pytest.fixture()
def package(tmp_path): return make_package(tmp_path / "package")
@pytest.fixture()
def reference_full(tmp_path): return make_reference(tmp_path / "reference", True)
@pytest.fixture()
def reference_min(tmp_path): return make_reference(tmp_path / "reference_min", False)

def _formula_answer(tid): return json.dumps({"task_id": tid, "status": "answer", "expressions": [{"branch": "b1", "sql": FORMULAS[tid]}], "uses": [], "class": "copy_or_rename", "assumptions": []})

@pytest.fixture()
def fake_endpoint(monkeypatch):
    """Patches the HTTP call of the model client: answers recipes and formulas of the synthetic package. Returns the list of request bodies seen (for assertions)."""
    import fieldgen.llm as llm
    monkeypatch.setenv("FIELDGEN_TEST_KEY", "dummy-not-a-key"); seen = []; lock = threading.Lock()
    def fake(self, body):
        with lock: seen.append(body)
        u = body["messages"][-1]["content"]; m1 = re.search(r"## Target table: (\w+)", u); m2 = re.search(r'Return the JSON object for task_id "([\w.]+)"', u)
        text = json.dumps(RECIPES[m1.group(1)]) if m1 else (_formula_answer(m2.group(1)) if m2 and m2.group(1) in FORMULAS else "{}")
        return 200, {"model": "fake/served", "choices": [{"message": {"content": text}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 7, "completion_tokens": 5}}, {"x-ratelimit-remaining": "9"}
    monkeypatch.setattr(llm.Client, "_http", fake)
    orig = llm.Client.__init__
    monkeypatch.setattr(llm.Client, "__init__", lambda self, cfg, calls_path=None, transport=None, sleep=None: orig(self, cfg, calls_path=calls_path, transport=transport, sleep=lambda s: None))
    return seen
