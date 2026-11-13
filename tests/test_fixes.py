"""formula_docs and history_pattern: both off by default, prompts unchanged when off; the added sections when on."""
import json
from fieldgen.settings import load_settings, untested, DEFAULTS
from fieldgen.pipeline import prepare, run
from fieldgen.recipe_prompts import recipe_messages
from fieldgen.formula_prompts import field_task, step2_messages
from fieldgen.rules_history import HISTORY_TEXT, column_rules
from conftest import RECIPES

def settings(**ov):
    s = load_settings(None, ov); s._v["api_key_env"] = "FIELDGEN_TEST_KEY"; return s

def test_both_switches_default_to_off_and_warn_when_on():
    assert DEFAULTS["formula_docs"] is True and DEFAULTS["history_pattern"] is False and DEFAULTS["history_auto"] is False and DEFAULTS["history_tables"] == {} and untested(load_settings(None)) == []
    assert untested(load_settings(None, {"formula_docs": False})) == []                              # both values of formula_docs were measured
    s = load_settings(None, {"history_pattern": True, "history_auto": True}); assert len(untested(s)) == 2

def test_recipe_prompt_with_the_switch_off_has_no_tool_instructions_and_on_has_the_text(tmp_path, package, fake_endpoint):
    off = prepare(package, settings(), tmp_path / "a"); on = prepare(package, settings(history_pattern=True), tmp_path / "b")
    u_off = recipe_messages(off.tasks["client"], off.s)[1]["content"]; u_on = recipe_messages(on.tasks["client"], on.s)[1]["content"]
    assert "Tool instructions" not in u_off and HISTORY_TEXT not in u_off
    assert HISTORY_TEXT in u_on and u_on.replace("## Tool instructions\n" + HISTORY_TEXT + "\n", "") == u_off      # the only difference is the added section

def test_formula_prompt_sections(tmp_path, package, fake_endpoint):
    c = prepare(package, settings(formula_docs=True), tmp_path / "a")
    rules = column_rules(c.view, "client", "city"); assert rules and rules.startswith("conventions: Convention text.") and "[Target documentation: client.city, conventions]" in rules
    plain = step2_messages(field_task(c.tasks["client"], RECIPES["client"], "city"))[1]["content"]
    ft = field_task(c.tasks["client"], RECIPES["client"], "city", rules=rules, history=HISTORY_TEXT); u = step2_messages(ft)[1]["content"]
    assert "Documented rules for this column" not in plain and "Tool instructions" not in plain
    assert "## Documented rules for this column\n" + rules + "\n## Recipe (fixed)" in u and "## Tool instructions\n" + HISTORY_TEXT in u
    assert column_rules(c.view, "client", "client_name") is None            # no conventions text: nothing is added

def test_run_with_both_switches_on_puts_the_rules_in_the_formula_request(tmp_path, package, fake_endpoint):
    run(package, settings(formula_docs=True, history_pattern=True), tmp_path / "run")
    city = [b["messages"][-1]["content"] for b in fake_endpoint if 'task_id "client.city"' in b["messages"][-1]["content"]]
    assert city and "Documented rules for this column" in city[0] and "Tool instructions" not in city[0]       # the fixture recipe of `client` is not grouped
    rec = [b["messages"][-1]["content"] for b in fake_endpoint if "## Target table: client" in b["messages"][-1]["content"]]
    assert rec and "## Tool instructions" in rec[0]

# ---- history_tables (wrapper) and formula_length_retry
from fieldgen.assemble import assemble_expr, wrap_history
from fieldgen.history import apply_history, HistoryError, recipe_text, formula_text
from fieldgen.package import load_package
from fieldgen.settings import ConfigError
import pytest

HT = {"client": {"key": "cust_id", "order": "order_date", "tiebreak": "order_id"}}

def test_history_tables_config_validation():
    assert load_settings(None).history_tables == {} and load_settings(None, {"history_tables": {"Client": HT["client"]}}).history_tables == HT
    with pytest.raises(ConfigError): load_settings(None, {"history_tables": {"client": {"key": "x"}}})
    with pytest.raises(ConfigError): load_settings(None, {"history_tables": ["client"]})

def test_wrapper_is_added_by_the_tool_and_not_to_the_key():
    rec = {"branches": [{"id": "b1", "from": "FROM orders o"}], "combine": "none", "group_by": ["o.cust_id"], "history": {"key": "o.cust_id", "order": "o.order_date", "tiebreak": "o.order_id", "unwrapped": ["client_id"]}}
    w = wrap_history(rec, "o.amount")
    assert w == "arg_max((o.amount), (o.order_date, o.order_id)) FILTER (WHERE NULLIF(CAST((o.amount) AS VARCHAR), '') IS NOT NULL)"
    assert wrap_history(rec, "o.cust_id", column="client_id") == "o.cust_id" and wrap_history({"branches": []}, "o.amount") == "o.amount"
    assert assemble_expr(rec, "b1", [], "o.amount").startswith("SELECT (arg_max((o.amount)") and assemble_expr(rec, "b1", [], "o.amount").endswith("GROUP BY o.cust_id")

def test_apply_history_resolves_aliases_and_sets_the_grouping(package):
    pkg = load_package(package); rec = {**RECIPES["purchase"], "branches": [{"id": "b1", "from": "FROM orders o JOIN customers c ON o.cust_id = c.cust_id"}], "group_by": None}
    out = apply_history(rec, {"key": "cust_id", "order": "order_date", "tiebreak": "order_id"}, pkg, ["purchase_id"])
    assert out["group_by"] == ["o.cust_id"] and out["history"] == {"key": "o.cust_id", "order": "o.order_date", "tiebreak": "o.order_id", "unwrapped": ["purchase_id"]} and rec["group_by"] is None
    with pytest.raises(HistoryError): apply_history(rec, {"key": "nope", "order": "order_date", "tiebreak": "order_id"}, pkg, [])

def test_listed_table_prompts_use_the_history_text_and_not_the_pattern_text(tmp_path, package, fake_endpoint):
    s = settings(history_tables=HT, history_pattern=True); c = prepare(package, s, tmp_path / "a")
    u = recipe_messages(c.tasks["client"], s)[1]["content"]; assert recipe_text(HT["client"]) in u and HISTORY_TEXT not in u
    u2 = recipe_messages(c.tasks["purchase"], s)[1]["content"]; assert HISTORY_TEXT in u2 and "This table is built from events" not in u2       # not listed: unchanged behaviour

def test_length_retry_asks_once_more_with_double_max_tokens(tmp_path, package, monkeypatch):
    import fieldgen.llm as llm, re
    seen = []
    def fake(self, body):
        seen.append(body); u = body["messages"][-1]["content"]; m1 = re.search(r"## Target table: (\w+)", u); m2 = re.search(r'Return the JSON object for task_id "([\w.]+)"', u)
        from conftest import _formula_answer, FORMULAS
        long_ = bool(m2) and m2.group(1) == "client.city" and body.get("max_tokens") == 8192
        text = json.dumps(RECIPES[m1.group(1)]) if m1 else ("" if long_ else (_formula_answer(m2.group(1)) if m2 and m2.group(1) in FORMULAS else "{}"))
        return 200, {"model": "fake/served", "choices": [{"message": {"content": text}, "finish_reason": "length" if long_ else "stop"}], "usage": {"prompt_tokens": 7, "completion_tokens": 8192 if long_ else 5}}, {"x-ratelimit-remaining": "9"}
    monkeypatch.setenv("FIELDGEN_TEST_KEY", "dummy-not-a-key"); monkeypatch.setattr(llm.Client, "_http", fake)
    orig = llm.Client.__init__; monkeypatch.setattr(llm.Client, "__init__", lambda self, cfg, calls_path=None, transport=None, sleep=None: orig(self, cfg, calls_path=calls_path, transport=transport, sleep=lambda s: None))
    out = tmp_path / "run"; summ = run(package, settings(formula_length_retry=True), out)
    city = [b for b in seen if 'task_id "client.city"' in b["messages"][-1]["content"]]
    assert [b.get("max_tokens") for b in city] == [8192, 16384] and summ["stats"]["formula_length_retries"] == 1

def test_history_auto_adds_the_decision_text_only_when_on_and_the_schema_accepts_the_field(tmp_path, package, fake_endpoint):
    from fieldgen.history import AUTO_TEXT
    from fieldgen.parse import RECIPE_SCHEMA_HISTORY as RECIPE_SCHEMA
    import jsonschema
    off = prepare(package, settings(), tmp_path / "a"); on = prepare(package, settings(history_auto=True), tmp_path / "b")
    u_off = recipe_messages(off.tasks["client"], off.s)[1]["content"]; u_on = recipe_messages(on.tasks["client"], on.s)[1]["content"]
    assert AUTO_TEXT not in u_off and AUTO_TEXT in u_on and u_on.replace("## Tool instructions\n" + AUTO_TEXT + "\n", "") == u_off
    ok = {**RECIPES["client"], "history": {"key": "cust_id", "order": "joined_on", "tiebreak": "cust_id"}}; assert not list(jsonschema.Draft7Validator(RECIPE_SCHEMA).iter_errors(ok))
    assert not list(jsonschema.Draft7Validator(RECIPE_SCHEMA).iter_errors({**RECIPES["client"], "history": None}))
    assert list(jsonschema.Draft7Validator(RECIPE_SCHEMA).iter_errors({**RECIPES["client"], "history": {"key": "x"}}))

TASK = {"task_id": "client", "source_graph": {"matched_tables": {}, "connected_tables": {}}}

def test_history_field_is_rejected_unless_history_auto_is_on():
    from fieldgen.parse import parse_recipe
    rec = {**RECIPES["client"], "history": None}
    r, errs = parse_recipe(json.dumps(rec), TASK); assert r is None and any("history" in e for e in errs)          # v1.2-demo behaviour
    import jsonschema
    from fieldgen.parse import RECIPE_SCHEMA_HISTORY
    assert not list(jsonschema.Draft7Validator(RECIPE_SCHEMA_HISTORY).iter_errors(rec))      # accepted only through allow_history (history_auto on)
