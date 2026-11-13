"""config.yaml: parsing, defaults, validation and the "untested setting" warnings."""
import pytest, yaml
from pathlib import Path
from fieldgen.settings import load_settings, untested, ConfigError, DEFAULTS, TESTED
from fieldgen.pipeline import run
ROOT = Path(__file__).resolve().parent.parent

def test_defaults_are_the_tested_default_path():
    s = load_settings(None)
    assert (s.stages, s.domain_knowledge, s.retry_on_error, s.max_retries, s.score_levels, s.reference) == ("recipes_and_formulas", "required", "errors_and_invalid", 2, "L2", "auto")
    assert s.timeout_s == 900 and s.requests_per_minute == 20 and s.concurrency == 2 and s.min_coverage == 0.5
    assert all(getattr(s, k) is True for k in ("data_profiling", "computed_facts", "measured_links", "documentation_conventions", "documentation_first", "source_labels", "join_rules_in_prompt"))
    assert untested(s) == []

def test_shipped_config_file_equals_defaults():
    assert load_settings(ROOT / "config.yaml").as_dict() == DEFAULTS

def test_execute_sample_rows_nested_flat_and_invalid(tmp_path):
    assert load_settings(None).execute == {"sample_rows": "all"}
    for text, want in (("execute:\n  sample_rows: 5\n", 5), ("execute.sample_rows: 7\n", 7), ("execute:\n  sample_rows: all\n", "all")):
        p = tmp_path / "c.yaml"; p.write_text(text, encoding="utf-8"); assert load_settings(p).execute["sample_rows"] == want
    for bad in ("execute:\n  sample_rows: 0\n", "execute:\n  sample_rows: some\n", "execute:\n  rows: 5\n", "execute: 5\n"):
        p.write_text(bad, encoding="utf-8")
        with pytest.raises(ConfigError): load_settings(p)

def test_robustness_check_and_the_older_score_levels(tmp_path):
    assert load_settings(None).robustness_check is False
    p = tmp_path / "c.yaml"; p.write_text("robustness_check: true\n", encoding="utf-8"); assert load_settings(p).robustness_check is True
    p.write_text("score_levels: L2_and_L4\n", encoding="utf-8"); assert load_settings(p).robustness_check is True and untested(load_settings(p)) == []

def test_option_names_are_the_documented_ones():
    names = {"model", "reasoning_effort", "stages", "timeout_s", "requests_per_minute", "concurrency", "domain_knowledge", "reference", "data_profiling", "computed_facts", "measured_links", "min_coverage",
             "documentation_conventions", "documentation_first", "source_labels", "join_rules_in_prompt", "retry_on_error", "max_retries", "text_data_check", "score_levels", "robustness_check", "execute"}
    assert names <= set(DEFAULTS)

@pytest.mark.parametrize("bad", [{"nonsense": 1}, {"stages": "formulas"}, {"domain_knowledge": "maybe"}, {"data_profiling": "yes"}, {"min_coverage": 0}, {"max_retries": 3}, {"retry_on_error": "always"}, {"concurrency": 0}])
def test_invalid_config_is_rejected(tmp_path, bad):
    p = tmp_path / "c.yaml"; p.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ConfigError): load_settings(p)

@pytest.mark.parametrize("opt,val", [("data_profiling", False), ("source_labels", False), ("documentation_first", False), ("measured_links", False), ("min_coverage", 0.7), ("reasoning_effort", "high"),
                                     ("concurrency", 4), ("model", "other/model"), ("requests_per_minute", 40), ("max_retries", 1), ("execute.sample_rows", 5)])
def test_untested_values_warn(tmp_path, opt, val):
    p = tmp_path / "c.yaml"; p.write_text(yaml.safe_dump({opt: val}), encoding="utf-8"); w = untested(load_settings(p))
    assert any(x.startswith(opt) for x in w), w

@pytest.mark.parametrize("opt,val", [("stages", "recipes"), ("documentation_conventions", False), ("retry_on_error", "off"), ("computed_facts", False), ("join_rules_in_prompt", False), ("score_levels", "L2_and_L4"), ("text_data_check", "off")])
def test_tested_values_do_not_warn(tmp_path, opt, val):
    p = tmp_path / "c.yaml"; p.write_text(yaml.safe_dump({opt: val}), encoding="utf-8"); assert untested(load_settings(p)) == []

def test_warning_is_printed_at_run_start(tmp_path, package, fake_endpoint):
    s = load_settings(None, {"stages": "recipes"}); s._v.update(api_key_env="FIELDGEN_TEST_KEY", data_profiling=False, source_labels=False); lines = []
    run(package, s, tmp_path / "run", log=lines.append)
    assert "WARNING untested setting: data_profiling = False" in lines and "WARNING untested setting: source_labels = False" in lines


def test_unquoted_off_in_yaml_means_off(tmp_path):
    p = tmp_path / "c.yaml"; p.write_text("domain_knowledge: off\nreference: off\nreasoning_effort: off\ntext_data_check: off\nretry_on_error: off\n", encoding="utf-8")
    s = load_settings(p); assert (s.domain_knowledge, s.reference, s.reasoning_effort, s.text_data_check, s.retry_on_error) == ("off",) * 5
