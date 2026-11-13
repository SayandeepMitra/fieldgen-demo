"""The tool never reads the reference folder. Static scan of the generator modules plus a run in which any open() of a reference path fails."""
import builtins, io, re
from pathlib import Path
from fieldgen.settings import load_settings
from fieldgen.pipeline import run

SRC = Path(__file__).resolve().parent.parent / "fieldgen"
SCORING = {"harness", "harness_fix", "harness_keys", "scorer", "score_run", "compare", "l4", "assemble_v1", "check_reference", "reference_build", "testing", "cli"}
FORBIDDEN_IMPORT = re.compile(r"from fieldgen(\.| import )(harness|harness_fix|harness_keys|scorer|score_run|compare|l4|assemble_v1|check_reference)\b|import fieldgen\.(harness|scorer|score_run|compare|l4)")
FORBIDDEN_TEXT = re.compile(r"(?<!reads_)reference_data|alignment\.json|reference_dir|reference/|gold/")

def test_generator_modules_do_not_import_or_name_the_reference_side():
    gen = [p for p in SRC.glob("*.py") if p.stem not in SCORING and p.stem != "__init__"]; assert len(gen) > 20
    for p in gen:
        txt = p.read_text(); assert not FORBIDDEN_IMPORT.search(txt), (p.name, FORBIDDEN_IMPORT.search(txt).group(0))
        assert not FORBIDDEN_TEXT.search(txt), (p.name, FORBIDDEN_TEXT.search(txt).group(0))

def test_run_never_opens_a_reference_path(tmp_path, package, reference_full, fake_endpoint, monkeypatch):
    real = io.open; ref = str(reference_full)
    def guard(file, *a, **k):
        if isinstance(file, (str, Path)) and str(file).startswith(ref): raise AssertionError(f"reference path opened by the generator: {file}")
        return real(file, *a, **k)
    monkeypatch.setattr(builtins, "open", guard); monkeypatch.setattr(io, "open", guard)
    s = load_settings(None, {"stages": "recipes"}); s._v["api_key_env"] = "FIELDGEN_TEST_KEY"
    summ = run(package, s, tmp_path / "run"); assert summ["recipes_valid"] == ["client", "purchase"]
