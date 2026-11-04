"""No key anywhere: a scan of the repository, and a run whose logs and reports must not contain the key or request headers."""
import json, re
from pathlib import Path
from fieldgen.settings import load_settings
from fieldgen.pipeline import run

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = [re.compile(p) for p in (r"nvapi-[A-Za-z0-9_\-]{16,}", r"\bsk-[A-Za-z0-9]{20,}", r"Bearer\s+[A-Za-z0-9._\-]{20,}", r"AKIA[0-9A-Z]{16}", r"ghp_[A-Za-z0-9]{30,}", r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}['\"]")]
SKIP_DIRS = {".git", ".venv", "__pycache__", "runs", ".pytest_cache", "source"}

def test_no_key_in_the_repository():
    hits = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts) or p.suffix in {".csv", ".duckdb", ".zip", ".pyc"}: continue
        if p.stat().st_size > 5_000_000: continue
        try: txt = p.read_text(encoding="utf-8")
        except Exception: continue
        for pat in PATTERNS:
            m = pat.search(txt)
            if m and Path(__file__).resolve() != p.resolve(): hits.append(f"{p.relative_to(ROOT)}: {m.group(0)[:12]}...")
    assert not hits, hits

def test_gitignore_covers_secrets_and_runs():
    g = (ROOT / ".gitignore").read_text().split()
    for x in (".env", "runs/", "*.key", "*.duckdb"): assert x in g

def test_run_outputs_contain_no_key_or_headers(tmp_path, package, fake_endpoint):
    s = load_settings(None); s._v["api_key_env"] = "FIELDGEN_TEST_KEY"; out = tmp_path / "run"; run(package, s, out)
    for p in out.rglob("*"):
        if p.is_file() and p.suffix in {".jsonl", ".json", ".md", ".txt", ".sql"}:
            txt = p.read_text(encoding="utf-8"); assert "dummy-not-a-key" not in txt and "Authorization" not in txt and "Bearer" not in txt, p.name
    assert all(b.get("model") for b in fake_endpoint)
