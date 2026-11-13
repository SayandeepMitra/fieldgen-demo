"""`fieldgen check`: good and broken packages. No model calls."""
import csv, json, shutil
from fieldgen.check import check_package
from fieldgen import cli

def test_good_package_is_valid(package):
    r = check_package(package); assert r["ok"], r["errors"]; assert r["checks"]["source_tables"] == 3 and r["checks"]["target_tables"] == 3

def _edit(package, rel, fn):
    p = package / rel; obj = json.loads(p.read_text()); fn(obj); p.write_text(json.dumps(obj))

def test_missing_data_file(package):
    (package / "source/data/orders.csv").unlink(); assert any("missing data file" in e for e in check_package(package)["errors"])

def test_wrong_header_and_row_count(package):
    p = package / "source/data/state_codes.csv"; rows = list(csv.reader(open(p))); rows[0][1] = "name"; csv.writer(open(p, "w", newline="")).writerows(rows)
    errs = check_package(package)["errors"]; assert any("header" in e for e in errs)
    p.write_text("code,label\nTX,Texas\n"); assert any("row count" in e for e in check_package(package)["errors"])

def test_unknown_link_column(package):
    _edit(package, "source/links.json", lambda o: o[0].update(child_columns=["nope"])); assert any("nope" in e for e in check_package(package)["errors"])

def test_matches_must_cover_every_target_field_and_name_real_columns(package):
    _edit(package, "matches/matches.json", lambda o: o.pop("client.city")); assert any("matches/matches.json" in e for e in check_package(package)["errors"])

def test_matches_unknown_source_column(package):
    _edit(package, "matches/matches.json", lambda o: o.update({"client.city": [{"relation": "customers", "column": "nope"}]})); assert any("nope" in e for e in check_package(package)["errors"])

def test_manifest_must_not_describe_the_reference(package):
    _edit(package, "manifest.json", lambda o: o.update(gold={"target_tables": []})); assert any("reference" in e for e in check_package(package)["errors"])

def test_missing_target_documentation_and_lookup_list(package):
    (package / "target/field_docs.json").unlink(); (package / "target/reference_tables.json").unlink()
    errs = check_package(package)["errors"]; assert any("field_docs" in e for e in errs) and any("reference_tables" in e for e in errs)

def test_missing_domain_folder_is_a_warning_not_an_error(package):
    shutil.rmtree(package / "domain"); r = check_package(package); assert r["ok"] and any("domain" in w for w in r["warnings"])

def test_profiles_are_optional(package):
    r = check_package(package); assert r["ok"] and any("profile" in w for w in r["warnings"])

def test_cli_exit_codes(package, tmp_path, capsys):      # `fieldgen check` is the validation behind `generate`
    assert cli.main(["check", "--package", str(package)]) == 0
    (package / "source/data/orders.csv").unlink(); assert cli.main(["check", "--package", str(package)]) == 1
    assert "NOT valid" in capsys.readouterr().out

def test_reference_leak_is_found(package, reference_full):
    from fieldgen.check_reference import leak_check
    assert leak_check(package, reference_full) == []
    p = reference_full / "recipes/purchase.json"; g = json.loads(p.read_text()); g["branches"][0]["from"] = "FROM orders o JOIN state_codes s ON o.state_code = s.code AND o.amount > 1"; p.write_text(json.dumps(g))
    _edit(package, "source/links.json", lambda o: o[0].update(evidence=g["branches"][0]["from"]))
    assert any("reference string" in h for h in leak_check(package, reference_full))
