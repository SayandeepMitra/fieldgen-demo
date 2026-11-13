"""config.yaml: options, defaults, validation, and the "untested setting" warnings. The defaults are the tested default path (Standard v4 recipe step + frozen formula step)."""
import yaml
from pathlib import Path

DEFAULTS = {
    "model": "nvidia/nemotron-3.5-super-vl-120b-a12b",
    "reasoning_effort": "low",
    "stages": "recipes_and_formulas",
    "timeout_s": 900,
    "requests_per_minute": 20,
    "concurrency": 2,
    "domain_knowledge": "required",
    "reference": "auto",
    "data_profiling": True,
    "computed_facts": True,
    "measured_links": True,
    "min_coverage": 0.5,
    "documentation_conventions": True,
    "documentation_first": True,
    "source_labels": True,
    "join_rules_in_prompt": True,
    "retry_on_error": "errors_and_invalid",
    "max_retries": 2,
    "text_data_check": "warn",
    "score_levels": "L2",
    "robustness_check": False,
    "formula_docs": True,             # on: the formula prompt also shows the documented rules (conventions) of the column (measured on Synthea and TPC-DI). off: only the field card (v1.2-demo)
    "history_pattern": False,         # off: no generic history guidance. on: tool instruction for sources with several records per key (recipe prompt, and formula prompt when grouped)
    "history_tables": {},             # tables built from events (see docs/config.md): {table: {key: ..., order: ..., tiebreak: ...}}; empty = no table is treated this way
    "history_auto": False,            # true: the recipe prompt asks the model to decide whether the table is built from partial-update events (recipe field "history")
    "formula_length_retry": False,    # true: a formula call that ends "length" or empty is asked once more with double max_tokens
    "execute": {"sample_rows": "all"},
    # endpoint (advanced; the key itself is only ever read from the environment variable named here)
    "base_url": "https://integrate.api.nvidia.com/v1",
    "api_key_env": "NVIDIA_API_KEY",
}
CHOICES = {"reasoning_effort": ["low", "high", "off"], "stages": ["recipes", "recipes_and_formulas"], "domain_knowledge": ["required", "optional", "off"], "reference": ["auto", "off"],
           "retry_on_error": ["off", "errors", "errors_and_invalid"], "text_data_check": ["warn", "off"], "score_levels": ["L2", "L2_and_L4"]}
BOOLS = ["robustness_check", "data_profiling", "computed_facts", "measured_links", "documentation_conventions", "documentation_first", "source_labels", "join_rules_in_prompt", "formula_docs", "history_pattern", "formula_length_retry", "history_auto"]
# values that were run and measured in our experiments (see docs/config.md); everything else prints "untested setting"
TESTED = {"model": [DEFAULTS["model"]], "reasoning_effort": ["low"], "stages": ["recipes", "recipes_and_formulas"], "timeout_s": [900, 1800], "requests_per_minute": [20], "concurrency": [2],
          "domain_knowledge": ["required", "optional"], "reference": ["auto", "off"], "data_profiling": [True], "computed_facts": [True, False], "measured_links": [True], "min_coverage": [0.5],
          "documentation_conventions": [True, False], "documentation_first": [True], "source_labels": [True], "join_rules_in_prompt": [True, False],
          "formula_docs": [True, False], "history_pattern": [False], "formula_length_retry": [False], "history_auto": [False], "history_tables": [{}], "retry_on_error": ["off", "errors", "errors_and_invalid"], "max_retries": [2], "text_data_check": ["warn", "off"], "score_levels": ["L2", "L2_and_L4"], "robustness_check": [True, False], "execute.sample_rows": ["all"],
          "base_url": [DEFAULTS["base_url"]], "api_key_env": [DEFAULTS["api_key_env"]]}

class ConfigError(ValueError): pass

class Settings:
    def __init__(self, values): self.__dict__["_v"] = dict(values)
    def flat(self):
        v = dict(self._v); ex = v.pop("execute"); v.update({f"execute.{k}": x for k, x in ex.items()}); return v
    def __getattr__(self, k):
        try: return self._v[k]
        except KeyError: raise AttributeError(k)
    def as_dict(self): return dict(self._v)

def load_settings(path=None, overrides=None):
    user = {}
    if path:
        user = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(user, dict): raise ConfigError("config file must be a mapping of option: value")
    user.update({k: v for k, v in (overrides or {}).items() if v is not None})
    for k in [k for k in user if isinstance(k, str) and k.startswith("execute.")]: user.setdefault("execute", {})[k.split(".", 1)[1]] = user.pop(k)      # execute.sample_rows may be written flat
    unknown = sorted(set(user) - set(DEFAULTS))
    if unknown: raise ConfigError("unknown option(s): " + ", ".join(unknown) + " (see docs/config.md)")
    if "execute" in user:
        if not isinstance(user["execute"], dict) or set(user["execute"]) - {"sample_rows"}: raise ConfigError("execute: only sample_rows is known (all or a number of rows)")
    v = {**DEFAULTS, **user}; v["execute"] = {**DEFAULTS["execute"], **(user.get("execute") or {})}
    sr = v["execute"]["sample_rows"]
    if sr != "all" and not (isinstance(sr, int) and not isinstance(sr, bool) and sr >= 1): raise ConfigError("execute.sample_rows: must be all or a whole number of rows (1 or more)")
    for k, allowed in CHOICES.items():
        if v[k] is False and "off" in allowed: v[k] = "off"        # YAML reads an unquoted off as false
        if v[k] not in allowed: raise ConfigError(f"{k}: {v[k]!r} is not one of {allowed}")
    for k in BOOLS:
        if not isinstance(v[k], bool): raise ConfigError(f"{k}: must be true or false")
    ht = v["history_tables"]
    if not isinstance(ht, dict): raise ConfigError("history_tables: must be a mapping table: {key, order, tiebreak}")
    for t, c in ht.items():
        if not isinstance(c, dict) or set(c) != {"key", "order", "tiebreak"} or not all(isinstance(x, str) and x for x in c.values()): raise ConfigError(f"history_tables.{t}: needs key, order and tiebreak (column names)")
    v["history_tables"] = {str(t).lower(): dict(c) for t, c in ht.items()}
    if not isinstance(v["model"], str) or not v["model"]: raise ConfigError("model: must be a model id")
    for k, lo in (("timeout_s", 1), ("requests_per_minute", 1), ("concurrency", 1)):
        if not isinstance(v[k], (int, float)) or v[k] < lo: raise ConfigError(f"{k}: must be a number >= {lo}")
    if not isinstance(v["min_coverage"], (int, float)) or not 0 < v["min_coverage"] <= 1: raise ConfigError("min_coverage: must be in (0, 1]")
    if v["score_levels"] == "L2_and_L4": v["robustness_check"] = True       # the older option score_levels still works: L2_and_L4 switches the robustness check on
    if not isinstance(v["max_retries"], int) or not 0 <= v["max_retries"] <= 2: raise ConfigError("max_retries: must be 0, 1 or 2")
    return Settings(v)

def find_config(package=None):
    """The config file to use: config.yaml in the package folder first, then config.yaml in the current folder, else None (the built-in defaults are used)."""
    for p in ([Path(package) / "config.yaml"] if package else []) + [Path("config.yaml")]:
        if p.is_file(): return p
    return None

def untested(s):
    """['option = value', ...] for every option whose value was not run in our experiments."""
    out = []
    for k, ok in TESTED.items():
        val = s.flat()[k]
        if val not in ok: out.append(f"{k} = {val!r}")
    if s.measured_links is False or s.data_profiling is False or s.source_labels is False or s.documentation_first is False: pass
    return out

def extra_body(s):
    """Reasoning switches of the endpoint (chat template arguments)."""
    return {"low": {"chat_template_kwargs": {"enable_thinking": True, "low_effort": True}}, "high": {"chat_template_kwargs": {"enable_thinking": True, "low_effort": False}},
            "off": {"chat_template_kwargs": {"enable_thinking": False}}}[s.reasoning_effort]
