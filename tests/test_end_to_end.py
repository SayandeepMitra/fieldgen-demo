"""init -> generate -> execute -> test on the synthetic shop, with the fake endpoint: reference as tables, reference as recipes, and no reference."""
import json, shutil, duckdb, pytest
from pathlib import Path
from fieldgen import cli
from conftest import make_package, make_reference, MATCH
from test_init import DDL

@pytest.fixture()
def project(tmp_path, monkeypatch, fake_endpoint):
    """A folder with package/ made by `fieldgen init` and the blocking TODOs filled in; the current folder is tmp_path (no config.yaml: defaults)."""
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("NVIDIA_API_KEY", "dummy-not-a-key")
    src = tmp_path / "src"; src.mkdir(); ref_pkg = make_package(tmp_path / "ref_pkg")
    for f in (ref_pkg / "source/data").glob("*.csv"): shutil.copy(f, src / f.name)
    (tmp_path / "target.sql").write_text(DDL, encoding="utf-8"); root = tmp_path / "project"; root.mkdir(); package = root / "package"
    assert cli.main(["init", "--package", str(package), "--source", str(src), "--target", str(tmp_path / "target.sql")]) == 0
    m = json.loads((package / "matches/matches.json").read_text(encoding="utf-8")); m.update({k: [{"relation": x.split(".")[0], "column": x.split(".")[1]} for x in v] for k, v in MATCH.items()}); (package / "matches/matches.json").write_text(json.dumps(m), encoding="utf-8")
    (package / "domain/domain_knowledge.md").write_text("A client is a customer of the shop. A purchase is one order.\n", encoding="utf-8"); (package / "domain/flow_text.md").write_text("Orders become purchases.\n", encoding="utf-8")
    return root

def four_commands(root, capsys):
    pkg = str(root / "package"); out = {}
    for cmd in ("generate", "execute", "test"):
        assert cli.main([cmd, "--package", pkg]) == 0, cmd; out[cmd] = capsys.readouterr().out
    return out

def check_the_chain(root, out):
    assert out["generate"].strip().endswith(f"next: fieldgen execute --package {root / 'package'}") and out["execute"].strip().endswith(f"next: fieldgen test --package {root / 'package'}")
    run = root / "run"; assert (run / "sql/purchase.sql").exists() and (run / "recipes/client.json").exists()
    con = duckdb.connect(str(run / "tables.duckdb"), read_only=True); assert con.execute("select count(*) from client").fetchone()[0] == 4 and con.execute("select count(*) from purchase").fetchone()[0] == 6; con.close()

def test_reference_as_tables(project, capsys):
    make_reference(project / "reference", full=False); out = four_commands(project, capsys); check_the_chain(project, out)
    assert "tables with correct rows: 2 of 2" in out["test"] and "L2 columns correct: 8 of 8" in out["test"] and "building" not in out["test"]
    assert not (project / "run/reference_built").exists() and "Scoring" in (project / "run/report.md").read_text(encoding="utf-8")

def test_reference_as_recipes_is_built_first(project, capsys):
    make_reference(project / "reference", full=True); shutil.rmtree(project / "reference/reference_data"); out = four_commands(project, capsys); check_the_chain(project, out)
    assert "reference tables built from the reference recipes" in out["test"] and "tables with correct rows: 2 of 2" in out["test"] and "L2 columns correct: 8 of 8" in out["test"]
    assert (project / "run/reference_built/reference_data/purchase.csv").exists() and not (project / "reference/reference_data").exists()      # the reference folder itself is not changed

def test_no_reference_says_so_and_stops(project, capsys):
    out = four_commands(project, capsys); check_the_chain(project, out)
    assert out["test"].strip().splitlines()[-1] == "no reference, nothing to test" and not (project / "run/scores.json").exists()

def test_empty_reference_folder_is_no_reference(project, capsys):
    (project / "reference").mkdir(); out = four_commands(project, capsys); assert out["test"].strip().splitlines()[-1] == "no reference, nothing to test"

def test_reference_off_in_config(project, capsys, tmp_path):
    make_reference(project / "reference", full=False); (tmp_path / "config.yaml").write_text("reference: off\n", encoding="utf-8"); out = four_commands(project, capsys)
    assert out["test"].strip().splitlines()[-1] == "reference: off in config.yaml, nothing to test"

def test_tables_without_alignment_are_reported(project, capsys):
    ref = make_reference(project / "reference", full=False); (ref / "alignment.json").unlink()
    four = [cli.main([c, "--package", str(project / "package")]) for c in ("generate", "execute")]; capsys.readouterr()
    assert four == [0, 0] and cli.main(["test", "--package", str(project / "package")]) == 1 and "alignment.json" in capsys.readouterr().out

def test_robustness_check_runs_l4_only_when_true(project, capsys, tmp_path):
    make_reference(project / "reference", full=True); out = four_commands(project, capsys); assert "L4" not in out["test"]
    (tmp_path / "config.yaml").write_text("robustness_check: true\n", encoding="utf-8"); assert cli.main(["test", "--package", str(project / "package")]) == 0
    assert "additional, L4:" in capsys.readouterr().out

def test_robustness_check_with_tables_only_is_skipped_with_a_message(project, capsys, tmp_path):
    make_reference(project / "reference", full=False); (tmp_path / "config.yaml").write_text("robustness_check: true\n", encoding="utf-8"); out = four_commands(project, capsys)
    assert "L4 skipped" in out["test"]

def test_execute_sample_rows_from_config(project, capsys, tmp_path):
    (tmp_path / "config.yaml").write_text("execute:\n  sample_rows: 2\n", encoding="utf-8"); out = four_commands(project, capsys)
    con = duckdb.connect(str(project / "run/tables.duckdb"), read_only=True); assert con.execute("select count(*) from client").fetchone()[0] == 2 and "first 2 rows" in out["execute"]; con.close()

def test_generate_stops_while_todos_are_open(tmp_path, monkeypatch, fake_endpoint, capsys):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("NVIDIA_API_KEY", "dummy-not-a-key"); src = tmp_path / "src"; src.mkdir(); ref_pkg = make_package(tmp_path / "ref_pkg")
    for f in (ref_pkg / "source/data").glob("*.csv"): shutil.copy(f, src / f.name)
    (tmp_path / "target.sql").write_text(DDL, encoding="utf-8"); cli.main(["init", "--package", str(tmp_path / "p" / "package"), "--source", str(src), "--target", str(tmp_path / "target.sql")]); capsys.readouterr()
    assert cli.main(["generate", "--package", str(tmp_path / "p" / "package")]) == 1 and not fake_endpoint

def test_test_stops_when_reference_text_is_in_the_package(project, capsys):
    ref = make_reference(project / "reference", full=True); frm = json.loads((ref / "recipes/purchase.json").read_text(encoding="utf-8"))["branches"][0]["from"]
    p = project / "package/source/links.json"; links = json.loads(p.read_text(encoding="utf-8")); links[0]["evidence"] = frm; p.write_text(json.dumps(links), encoding="utf-8")
    for c in ("generate", "execute"): assert cli.main([c, "--package", str(project / "package")]) == 0
    capsys.readouterr(); assert cli.main(["test", "--package", str(project / "package")]) == 1 and "LEAK" in capsys.readouterr().out


def test_config_is_read_from_the_package_folder_first_then_the_current_folder(project, capsys, tmp_path):
    pkg = str(project / "package")
    (tmp_path / "config.yaml").write_text("execute:\n  sample_rows: 3\n", encoding="utf-8"); cli.main(["generate", "--package", pkg]); out = capsys.readouterr().out
    assert f"config: {tmp_path / 'config.yaml'}" in out                                           # the current folder (tmp_path)
    (project / "package" / "config.yaml").write_text("execute:\n  sample_rows: 2\n", encoding="utf-8"); cli.main(["execute", "--package", pkg]); out = capsys.readouterr().out
    assert f"config: {project / 'package' / 'config.yaml'}" in out and "first 2 rows" in out       # the package folder wins over the current folder
    (project / "package" / "config.yaml").unlink(); (tmp_path / "config.yaml").unlink(); cli.main(["execute", "--package", pkg]); out = capsys.readouterr().out
    assert "built-in defaults" in out and "all rows" in out


def test_execute_names_a_table_that_fails(project, capsys):
    pkg = str(project / "package"); assert cli.main(["generate", "--package", pkg]) == 0; capsys.readouterr()
    p = project / "run/formulas.jsonl"; rows = [json.loads(l) for l in open(p, encoding="utf-8")]
    for r in rows:
        if r["task_id"] == "purchase.amount": r["final"]["expressions"][0]["sql"] = "o.amount + nonexistent_column"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert cli.main(["execute", "--package", pkg]) == 1          # the other table is built and written; the exit code says that one failed
    out = capsys.readouterr().out; assert "FAILED  purchase:" in out and "nonexistent_column" in out and "1 of 2 tables built" in out and "1 failed table(s): purchase" in out

def test_config_line_shows_the_full_path(project, capsys, tmp_path):
    (tmp_path / "config.yaml").write_text("execute:\n  sample_rows: all\n", encoding="utf-8"); cli.main(["generate", "--package", str(project / "package")])
    assert f"config: {tmp_path / 'config.yaml'}" in capsys.readouterr().out
