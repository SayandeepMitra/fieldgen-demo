"""Load models.yaml and run.yaml. The API key is resolved from the env var named in the config and never logged."""
import os, yaml
from dataclasses import dataclass, field

class ConfigError(Exception): pass

@dataclass
class ModelCfg:
    name: str; provider: str; base_url: str; api_key_env: str; model: str
    temperature: float = 0.0; top_p: float = 1.0; max_tokens: int = 4096; timeout_s: float = 120
    requests_per_minute: float = 20; max_concurrency: int = 2; retries: int = 4
    json_mode: object = "unknown"; strip_thinking: bool = True; extra_body: dict = field(default_factory=dict)
    def api_key(self):
        k = os.environ.get(self.api_key_env)
        if not k: raise ConfigError(f"environment variable {self.api_key_env} is not set")
        return k
    def public(self):   # safe to log
        return {k: v for k, v in self.__dict__.items()}

def load_models(path):
    raw = yaml.safe_load(open(path, encoding="utf-8"))["models"]
    return {n: ModelCfg(name=n, **c) for n, c in raw.items()}

def load_run(path):
    return yaml.safe_load(open(path, encoding="utf-8"))
