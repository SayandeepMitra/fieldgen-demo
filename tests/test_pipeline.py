"""Run stages on the synthetic package with a fake endpoint: recipes, formulas, built tables, resume, stop rules, domain-knowledge modes."""
import json, duckdb, pytest
from fieldgen.settings import load_settings
from fieldgen.pipeline import run, PipelineError

def settings(**ov):
    s = load_settings(None, ov); s._v["api_key_env"] = "FIELDGEN_TEST_KEY"; return s

def test_full_run_writes_recipes_formulas_sql_tables_and_report(tmp_path, package, fake_endpoint):
    out = tmp_path / "run"; summ = run(package, settings(), out)
    assert summ["recipes_valid"] == ["client", "purchase"] and [b["ok"] for b in summ["built"]] == [True, True] and summ["served_models"] == ["fake/served"]
    for t in ("client", "purchase"):
        assert (out / "recipes" / f"{t}.json").exists() and "Grain:" in (out / "recipes" / f"{t}.txt").read_text(encoding="utf-8") and (out / "sql" / f"{t}.sql").exists() and (out / "formulas" / f"{t}.json").exists()
    con = duckdb.connect(str(out / "tables.duckdb"), read_only=True)
    assert con.execute("select client_name, client_id from client order by client_id").fetchall()[0] == ("Ann Lee", 1)       # generated key numbered in the order of client_name
    assert con.execute("select count(*), sum(amount) from purchase").fetchone() == (6, 152.74); con.close()
    rep = (out / "report.md").read_text(encoding="utf-8"); assert "fake/served" in rep and "Tables built" in rep and "Not tested" in rep

def test_recipes_only_stage_builds_no_tables(tmp_path, package, fake_endpoint):
    out = tmp_path / "run"; summ = run(package, settings(stages="recipes"), out)
    assert summ["recipes_valid"] == ["client", "purchase"] and not (out / "tables.duckdb").exists() and not (out / "formulas.jsonl").exists()

def test_lookup_copies_are_not_built(tmp_path, package, fake_endpoint):
    assert run(package, settings(stages="recipes"), tmp_path / "run")["tables_to_build"] == ["client", "purchase"]      # `state` is a copy of the source lookup table state_codes

def test_resume_makes_no_new_calls(tmp_path, package, fake_endpoint):
    out = tmp_path / "run"; run(package, settings(), out); n = len(fake_endpoint); run(package, settings(), out); assert len(fake_endpoint) == n

def test_http_400_stops_and_records_the_input_size(tmp_path, package, monkeypatch):
    import fieldgen.llm as llm
    monkeypatch.setenv("FIELDGEN_TEST_KEY", "dummy-not-a-key"); monkeypatch.setattr(llm.Client, "_http", lambda self, body: (400, {"error": "too long"}, {}))
    orig = llm.Client.__init__; monkeypatch.setattr(llm.Client, "__init__", lambda self, cfg, calls_path=None, transport=None, sleep=None: orig(self, cfg, calls_path=calls_path, transport=transport, sleep=lambda s: None))
    out = tmp_path / "run"; summ = run(package, settings(stages="recipes"), out)
    assert "HTTP 400" in summ["stopped"] and json.loads((out / "stop_400.json").read_text(encoding="utf-8"))["input_chars"] > 100 and "stopped early" in (out / "report.md").read_text(encoding="utf-8")

def test_missing_key_stops_before_any_call(tmp_path, package, monkeypatch):
    monkeypatch.delenv("FIELDGEN_TEST_KEY", raising=False)
    with pytest.raises(PipelineError, match="FIELDGEN_TEST_KEY"): run(package, settings(), tmp_path / "run")

def test_domain_knowledge_required_optional_off(tmp_path, package, fake_endpoint):
    import shutil; shutil.rmtree(package / "domain")
    with pytest.raises(PipelineError, match="no domain knowledge"): run(package, settings(), tmp_path / "a")
    summ = run(package, settings(domain_knowledge="optional", stages="recipes"), tmp_path / "b"); assert any("optional" in w for w in summ["warnings"]) and summ["recipes_valid"]
    summ = run(package, settings(domain_knowledge="off", stages="recipes"), tmp_path / "c"); assert summ["recipes_valid"]

def test_invalid_package_is_refused(tmp_path, package):
    (package / "source/data/orders.csv").unlink()
    with pytest.raises(PipelineError, match="not ready"): run(package, settings(), tmp_path / "run")

def test_prompt_carries_documentation_and_labels(tmp_path, package, fake_endpoint):
    run(package, settings(stages="recipes"), tmp_path / "run"); users = [b["messages"][1]["content"] for b in fake_endpoint]       # the two tables are asked in parallel: look at both
    assert any("[Target documentation:" in u for u in users) and any("Convention text." in u for u in users) and all("state_codes" in u for u in users)

def test_source_labels_off_removes_the_labels(tmp_path, package, fake_endpoint):
    run(package, settings(stages="recipes", source_labels=False), tmp_path / "run"); assert not any("[Target documentation:" in b["messages"][1]["content"] for b in fake_endpoint)


def test_execute_sample_rows_uses_the_first_rows_of_each_source_table(tmp_path, package, fake_endpoint):
    from fieldgen.pipeline import generate, execute
    out = tmp_path / "run"; generate(package, settings(), out); s = settings(); s._v["execute"] = {"sample_rows": 2}; res = execute(package, s, out)
    assert [t["rows"] for t in res["tables"]] == [2, 2] and res["sample_rows"] == 2
    s2 = settings(); assert [t["rows"] for t in execute(package, s2, out)["tables"]] == [4, 6]

def test_generate_alone_writes_sql_but_runs_no_sql(tmp_path, package, fake_endpoint):
    from fieldgen.pipeline import generate
    out = tmp_path / "run"; generate(package, settings(), out)
    assert (out / "sql" / "purchase.sql").read_text(encoding="utf-8").startswith("SELECT") and not (out / "tables.duckdb").exists() and "Not executed yet" in (out / "report.md").read_text(encoding="utf-8")

def test_execute_needs_a_generated_run_and_formulas(tmp_path, package, fake_endpoint):
    from fieldgen.pipeline import execute
    with pytest.raises(PipelineError, match="nothing to execute"): execute(package, settings(), tmp_path / "none")
