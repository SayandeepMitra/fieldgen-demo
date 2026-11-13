"""`fieldgen init`: package from source data and target schema; proposals marked; TODO templates; what `generate` does with them."""
import json, shutil, duckdb, pytest
from pathlib import Path
from fieldgen import cli
from fieldgen.check import check_package
from fieldgen.init_package import init_package, InitError
from fieldgen.settings import load_settings
from fieldgen.todo import package_todos
from conftest import make_package

DDL = """CREATE TABLE @cdmDatabaseSchema.client (client_id integer NOT NULL, client_name varchar(50) NULL, joined_date date NULL, city varchar(30) NULL, client_source_value varchar(20) NULL, PRIMARY KEY (client_id));
CREATE TABLE @cdmDatabaseSchema.purchase (purchase_id integer NOT NULL PRIMARY KEY, client_id integer NULL REFERENCES client (client_id), purchase_date date NULL, amount double precision NULL, state_label varchar(20) NULL, purchase_source_value varchar(20) NULL);
CREATE TABLE @cdmDatabaseSchema.state (code varchar(5) NOT NULL, label varchar(20) NULL);
"""

@pytest.fixture()
def inputs(tmp_path):
    src = tmp_path / "src"; src.mkdir(); ref = make_package(tmp_path / "ref_pkg")
    for f in (ref / "source/data").glob("*.csv"): shutil.copy(f, src / f.name)
    (tmp_path / "target.sql").write_text(DDL, encoding="utf-8"); return src, tmp_path / "target.sql"

def test_init_from_csv_folder_and_ddl(tmp_path, inputs):
    src, ddl = inputs; res = init_package(tmp_path / "pk", src, ddl, log=lambda *a: None); root = tmp_path / "pk"
    assert res["source_tables"] == 3 and res["target_tables"] == 3 and res["no_key"] == []
    tabs = {t["name"]: t for t in json.loads((root / "source/tables.json").read_text(encoding="utf-8"))}
    assert tabs["orders"]["pk"] == ["order_id"] and tabs["orders"]["pk_provenance"]["source"] == "proposed" and tabs["customers"]["pk"] == ["cust_id"]
    types = {c["name"]: c["type"] for c in tabs["orders"]["columns"]}; assert types["amount"] == "DOUBLE" and types["order_date"] == "DATE" and types["placed_at"].startswith("TIMESTAMP")
    man = json.loads((root / "manifest.json").read_text(encoding="utf-8")); assert man["source_row_counts"] == {"customers": 4, "orders": 6, "state_codes": 3} and man["target_tables"] == 3
    links = json.loads((root / "source/links.json").read_text(encoding="utf-8")); assert {(l["child"], l["parent"]) for l in links} == {("orders", "customers"), ("orders", "state_codes")}
    assert all(l["provenance"] == "inferred" and "proposed" in l["note"] for l in links)
    t = {x["name"]: x for x in json.loads((root / "target/tables.json").read_text(encoding="utf-8"))}
    assert t["client"]["pk"] == ["client_id"] and t["purchase"]["fks"] == [{"columns": ["client_id"], "ref_table": "client", "ref_columns": ["client_id"]}] and t["purchase"]["columns"][3]["type"] == "double"
    m = json.loads((root / "matches/matches.json").read_text(encoding="utf-8")); assert len(m) == 5 + 6 + 2 and not any(m.values())
    assert (root / "source/profiles/orders.json").exists() and (root / "TODO.md").exists() and "TODO" in (root / "domain/flow_text.md").read_text(encoding="utf-8")
    r = check_package(root); assert r["ok"], r["errors"]               # a fresh package is valid, only incomplete

def test_fresh_package_has_blocking_todos_that_stop_generate(tmp_path, inputs, capsys, monkeypatch):
    src, ddl = inputs; root = tmp_path / "pk"; init_package(root, src, ddl, log=lambda *a: None); monkeypatch.chdir(tmp_path)
    blocking, notes = package_todos(root, load_settings(None)); assert len(blocking) == 2 and any("matches" in b for b in blocking) and any("domain" in b for b in blocking)
    assert any("proposed" in n for n in notes) and any("descriptions" in n for n in notes)
    assert cli.main(["generate", "--package", str(root)]) == 1
    out = capsys.readouterr().out; assert "TODO" in out and "generate stops" in out
    (tmp_path / "config.yaml").write_text("domain_knowledge: off\n", encoding="utf-8"); blocking, _ = package_todos(root, load_settings(tmp_path / "config.yaml")); assert len(blocking) == 1

def test_init_from_duckdb_source_and_target(tmp_path, inputs):
    src, ddl = inputs; db = tmp_path / "s.duckdb"; con = duckdb.connect(str(db))
    for f in src.glob("*.csv"): con.execute(f'CREATE TABLE "{f.stem}" AS SELECT * FROM read_csv(\'{f}\', header=true)')
    con.close(); tdb = tmp_path / "t.duckdb"; tc = duckdb.connect(str(tdb)); tc.execute("CREATE TABLE client (client_id INTEGER PRIMARY KEY, client_name VARCHAR(50))"); tc.close()
    init_package(tmp_path / "pk", db, tdb, log=lambda *a: None); t = json.loads((tmp_path / "pk/target/tables.json").read_text(encoding="utf-8"))[0]
    assert t["name"] == "client" and t["pk"] == ["client_id"] and t["columns"][0]["nullable"] is False
    assert json.loads((tmp_path / "pk/manifest.json").read_text(encoding="utf-8"))["source_row_counts"]["orders"] == 6 and check_package(tmp_path / "pk")["ok"]

def test_init_refuses_to_overwrite_and_bad_inputs(tmp_path, inputs):
    src, ddl = inputs; init_package(tmp_path / "pk", src, ddl, log=lambda *a: None)
    with pytest.raises(InitError, match="already holds a package"): init_package(tmp_path / "pk", src, ddl)
    with pytest.raises(InitError, match="neither a folder"): init_package(tmp_path / "pk2", tmp_path / "missing", ddl)
    (tmp_path / "bad.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(InitError, match="no CREATE TABLE"): init_package(tmp_path / "pk3", src, tmp_path / "bad.sql")

def test_table_without_a_unique_column_gets_no_key(tmp_path, inputs):
    src, ddl = inputs; (src / "log.csv").write_text("a,b\n1,x\n1,x\n", encoding="utf-8"); init_package(tmp_path / "pk", src, ddl, log=lambda *a: None)
    t = {x["name"]: x for x in json.loads((tmp_path / "pk/source/tables.json").read_text(encoding="utf-8"))}; assert t["log"]["pk"] == [] and "TODO" in t["log"]["pk_provenance"]["source"]
    assert any("log" in e for e in check_package(tmp_path / "pk")["errors"])      # check names the table: it needs a key

def test_cli_init_prints_the_next_command(tmp_path, inputs, capsys):
    src, ddl = inputs; assert cli.main(["init", "--package", str(tmp_path / "pk"), "--source", str(src), "--target", str(ddl)]) == 0
    assert capsys.readouterr().out.strip().endswith(f"next: fieldgen generate --package {tmp_path / 'pk'}")


def test_ddl_in_a_folder_with_constraints_first_and_timestamp_type(tmp_path, inputs):
    src, _ = inputs; d = tmp_path / "ddl"; d.mkdir()
    (d / "a_constraints.sql").write_text("ALTER TABLE @s.purchase ADD CONSTRAINT fpk FOREIGN KEY (client_id) REFERENCES @s.client (client_id);", encoding="utf-8")       # sorts before the CREATE statements
    (d / "b_ddl.sql").write_text("CREATE TABLE @s.client (client_id integer NOT NULL, born TIMESTAMP NULL, name varchar(50) NULL);\nCREATE TABLE @s.purchase (purchase_id integer NOT NULL, client_id integer NULL, paid timestamp with time zone NULL);", encoding="utf-8")
    (d / "c_pk.sql").write_text("ALTER TABLE @s.client ADD CONSTRAINT xpk_client PRIMARY KEY (client_id);\nALTER TABLE @s.purchase ADD CONSTRAINT xpk_purchase PRIMARY KEY (purchase_id);", encoding="utf-8")
    init_package(tmp_path / "pk", src, d, log=lambda *a: None); t = {x["name"]: x for x in json.loads((tmp_path / "pk/target/tables.json").read_text(encoding="utf-8"))}
    assert t["client"]["pk"] == ["client_id"] and t["purchase"]["pk"] == ["purchase_id"] and t["purchase"]["fks"] == [{"columns": ["client_id"], "ref_table": "client", "ref_columns": ["client_id"]}]
    types = {c["name"]: c["type"] for x in t.values() for c in x["columns"]}; assert types["born"] == "timestamp" and types["name"] == "varchar(50)" and "timestamptz" in types["paid"].replace(" ", "")
    con = duckdb.connect(":memory:")
    for ty in types.values(): con.execute(f"SELECT CAST(NULL AS {ty})")        # every type is a type DuckDB knows
