"""reference = auto / off, the two reference formats, scoring and its limits."""
import json, os
from fieldgen.settings import load_settings
from fieldgen.pipeline import run
from fieldgen.score_run import score_run

def settings(**ov):
    s = load_settings(None, ov); s._v["api_key_env"] = "FIELDGEN_TEST_KEY"; return s

def test_score_full_reference(tmp_path, package, reference_full, fake_endpoint):
    s = settings(); run(package, s, tmp_path / "run"); sc = score_run(package, reference_full, tmp_path / "run", s)
    assert "tables with correct rows: 2 of 2" in sc["headline"] and "L2 columns correct: 8 of 8" in sc["headline"] and "L4" not in sc["headline"]
    assert "Scoring" in (tmp_path / "run" / "report.md").read_text() and (tmp_path / "run" / "scores.json").exists()

def test_score_minimum_reference_skips_l4(tmp_path, package, reference_min, fake_endpoint):
    s = settings(score_levels="L2_and_L4"); run(package, s, tmp_path / "run"); sc = score_run(package, reference_min, tmp_path / "run", s)
    assert "L2 columns correct: 8 of 8" in sc["headline"] and "L4 skipped" in sc["headline"]

def test_score_l4_on_full_reference(tmp_path, package, reference_full, fake_endpoint):
    s = settings(score_levels="L2_and_L4"); run(package, s, tmp_path / "run"); sc = score_run(package, reference_full, tmp_path / "run", s)
    assert "additional, L4:" in sc["headline"] and sc["fields"]["client.city"]["L4"] is True

def test_wrong_formula_is_counted_wrong(tmp_path, package, reference_full, fake_endpoint):
    s = settings(); run(package, s, tmp_path / "run")
    p = tmp_path / "run" / "formulas.jsonl"; rows = [json.loads(l) for l in open(p)]
    for r in rows:
        if r["task_id"] == "purchase.amount": r["final"]["expressions"][0]["sql"] = "o.amount * 2"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n"); sc = score_run(package, reference_full, tmp_path / "run", s)
    assert "L2 columns correct: 7 of 8" in sc["headline"] and sc["fields"]["purchase.amount"]["L2"] is False

def test_wrong_recipe_rows_are_counted_wrong(tmp_path, package, reference_full, fake_endpoint):
    s = settings(stages="recipes"); run(package, s, tmp_path / "run")
    p = tmp_path / "run" / "recipes.jsonl"; rows = [json.loads(l) for l in open(p)]
    for r in rows:
        if r["table"] == "purchase": r["recipe"]["branches"][0]["from"] = "FROM orders o JOIN state_codes s ON o.state_code = s.code WHERE o.amount > 8"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n"); sc = score_run(package, reference_full, tmp_path / "run", s)
    assert "tables with correct rows: 1 of 2" in sc["headline"]


def test_reference_build_fills_a_foreign_key_from_the_referenced_table(tmp_path, package, reference_full):
    """purchase is identified by the customer id (like client), and purchase.client_id is a key the reference program took from another table."""
    import csv, glob
    from fieldgen.reference_build import build_reference_tables
    shutil_rm = __import__("shutil").rmtree; shutil_rm(reference_full / "reference_data")
    rec = json.loads((reference_full / "recipes/purchase.json").read_text())
    rec["branches"][0]["from"] = "FROM orders JOIN customers ON orders.cust_id = customers.cust_id JOIN state_codes ON orders.state_code = state_codes.code"; (reference_full / "recipes/purchase.json").write_text(json.dumps(rec))
    expr = {"purchase_date": "orders.order_date", "amount": "orders.amount", "state_label": "state_codes.label", "purchase_source_value": "customers.cust_id"}
    for f in glob.glob(str(reference_full / "fields/purchase.*.json")):
        g = json.loads(open(f).read()); c = g["column"]
        g["alignment"] = {"source": ["b1:customers.cust_id"], "reference": ["r.purchase_source_value"]}
        if c in expr: g["expressions"] = [{"branch": "b1", "expr": expr[c]}]
        if c == "client_id": g["kind"] = "excluded"; g["expressions"] = [{"branch": "reference", "expr": "FROM orders: int__orders.client_id"}]; g["exclusion_reason"] = "reference takes the key from another target table's output; not expressible in source tables"
        open(f, "w").write(json.dumps(g))
    built, errs = build_reference_tables(package, reference_full, tmp_path / "built"); assert not errs and built["purchase"] == 6
    rows = list(csv.DictReader(open(tmp_path / "built/reference_data/purchase.csv"))); clients = {r["client_source_value"]: r["client_id"] for r in csv.DictReader(open(tmp_path / "built/reference_data/client.csv"))}
    assert all(r["client_id"] for r in rows) and all(r["client_id"] == clients[r["purchase_source_value"]] for r in rows)
