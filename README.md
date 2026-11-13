# fieldgen: SQL for database conversion, written by a language model

Authors: [Names]. Course: [Course]. Year: [Year].

## 1. What it does

fieldgen writes SQL that turns the tables of a source database into the tables of a target schema.
A language model writes the SQL. The tool runs it on DuckDB, checks it on the real data, and compares the result with an answer key.
It ran on two datasets: Synthea to OMOP, and TPC-DI.

The five steps. Each one is a command: `python -m fieldgen COMMAND --package DIR`.

1. Prepare the package: `init` builds it from your data, `check` tests it. No model call.
2. Recipe step: `generate`. For each target table, the model chooses the source tables, the joins and the grouping. One call per table.
3. Formula step: `generate` (the same command). For each target column, the model writes one SQL expression. One call per column.
4. Build: `execute` joins recipe and formulas into one query per table and writes the tables to `run/tables.duckdb`.
5. Score: `test` compares the tables with the answer key, the reference data that only the scorer reads. The tool never reads it while it generates.

Wrong answers are sent back to the model with the error text:

| step | reason | follow-up calls |
|---|---|---|
| recipe | answer is cut at the output limit | asked again with a larger limit (up to 3 times) |
| recipe | answer is invalid or does not run | up to 2, with the error text |
| formula | answer is invalid or does not run | 1, with the error text |
| formula | answer fails a check on the data (letter case, type, allowed values, declared length) | up to 2, with the offending values |

A table gets at most 8 recipe calls. A formula gets at most 4 calls. If every try fails, the table has no recipe, or the column stays NULL.

## 2. Setup

You need Python 3.10 or newer.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Running

Run all commands from this folder.

**Tests (offline, about 1 minute).**
```
pytest tests/
```

**Replay of saved model answers (no API key, no network).**
`run_demo.py` gives the saved answers to the tool's own generate, execute and test steps. It prints a score table and the recorded scores.
It needs the dataset first (section 5). Expected result in the last lines:

| command | time | expected |
|---|---|---|
| `python run_demo.py --dataset synthea` | about 2 min | 13 of 18 tables with correct rows, 57 columns correct |
| `python run_demo.py --dataset tpcdi --run run10 --work WORK` | about 10 min | 23 of 28 columns correct |
| `python run_demo.py --dataset tpcdi --run run6 --work WORK` | about 10 min | 22 of 28 columns correct |

The last line says "identical to the recorded run: YES" when it worked. `WORK` is the folder you gave to `make_package.py`; use an absolute path.

**Live run with your own key.**
The default endpoint is the NVIDIA API. The key is read only from the environment variable `NVIDIA_API_KEY`.
That endpoint records inputs and outputs. Your prompts contain samples of the source data, so check the rules for your data first.
```
export NVIDIA_API_KEY=...
python -m fieldgen generate --package datasets/synthea_omop/package
python -m fieldgen execute  --package datasets/synthea_omop/package
python -m fieldgen test     --package datasets/synthea_omop/package
```
`generate` takes about 20 to 25 minutes for Synthea (19 tables built, 18 scored) and about 8 to 13 minutes for the TPC-DI table DimCustomer alone.
Settings are in `config.yaml`; see `docs/config.md`.

## 4. The package

A package is one folder. `python -m fieldgen init --package DIR --source SRC --target DDL` creates it from a folder of CSV files (or a DuckDB file) and a DDL file.
`python -m fieldgen check --package DIR` lists what is wrong. Names of target tables and columns are lower case. The examples below come from `datasets/synthea_omop/package`.

| file | status | holds |
|---|---|---|
| `manifest.json` | required | name, version, row counts |
| `source/tables.json` | required | source tables and columns |
| `source/links.json` | required | how source tables join |
| `source/data/<table>.csv` | required | source rows |
| `source/profiles/<table>.json` | optional | column statistics |
| `source/dependencies.json` | optional | column dependencies |
| `target/tables.json` | required | target tables and columns |
| `target/field_docs.json` | required | column documentation (the source of column knowledge) |
| `target/reference_tables.json` | required | lookup tables |
| `target/field_domains.json` | optional | domain of a lookup column |
| `target/provenance.json` | optional | not read by the tool; records which OMOP documentation version the column texts come from |
| `matches/matches.json` | required | matches: source columns for each target column |
| `domain/` | required while `domain_knowledge: required` (the default) | expert text |
| `config.yaml` | optional | settings, including the history settings |
| `TODO.md` | written by `init` | list of what is left to fill in; not read by the tool |

**`manifest.json`.** Keys: `name`, `version`, `source_row_counts` (table to number of rows), `target_tables` (a number). `check` rejects a `gold` key.
```json
{"name": "synthea_omop", "version": "1.0", "source_row_counts": {"allergies": 40, "careplans": 49}, "target_tables": 39}
```

**`source/tables.json`.** A list with one entry per source table. Keys: `name`, `columns` (each with `name`, `type`, `nullable`, optional `description`), `pk` (required, not empty), `business_ids`, optional `description`. Types are DuckDB types.
```json
{"name": "patients", "columns": [{"name": "Id", "type": "VARCHAR", "nullable": true, "description": "Primary Key. Unique Identifier of the patient."}, ...], "pk": ["Id"], "business_ids": ["Id"]}
```

**`source/links.json`.** A list of links. Keys: `child`, `child_columns`, `parent`, `parent_columns`, `cardinality` (`one_to_one`, `many_to_one`, `one_to_many`, `many_to_many`), `provenance` (`declared`, `supplemented`, `inferred`), `support` (`dictionary`, `name`, `value_only`), `weak` (true exactly when `support` is `value_only`). Optional: `coverage`, `evidence`, `note`.
```json
{"child": "patients", "child_columns": ["STATE"], "parent": "states", "parent_columns": ["state_name"], "cardinality": "many_to_one", "provenance": "supplemented", "support": "name", "weak": false}
```

**`source/data/<table>.csv`.** UTF-8, comma separated, one file per source table. The header row equals the columns in `tables.json`, in the same order. An empty cell is NULL. The row count must equal `source_row_counts`.
```
Id,BIRTHDATE,DEATHDATE,SSN,DRIVERS,PASSPORT,PREFIX,FIRST,...
```

**`source/profiles/<table>.json`.** Optional. If missing, the tool computes it from the CSV file. Keys: `relation`, `rows`, `columns`. Each column has `type`, `rows`, `nulls`, `null_rate`, `distinct`, `top` (most frequent values with counts), `min`/`max` or `min_len`/`max_len`, `shapes`.
**`source/dependencies.json`.** Optional. A list of `{"table", "lhs": [columns], "rhs": [columns]}`. The default prompts do not use it.

**`target/tables.json`.** A list with one entry per target table. Keys: `name`, `columns` (each with `name`, `type`, `nullable`, `constraints`, optional `value_hints` and `description`), `pk`, `fks` (each with `columns`, `ref_table`, `ref_columns`), `business_ids`.
```json
{"name": "person", "columns": [{"name": "person_id", "type": "integer", "nullable": false, "constraints": ["primary key", "not null"]}, ...], "pk": ["person_id"], ...}
```

**`target/field_docs.json`.** The column documentation. Keys: `tables` (table to `description`, `guidance`, `conventions`) and `fields` (`table.column` to `guidance`, `conventions`, `ddl`). `guidance` says what a column means. `conventions` says how to fill it. The tool shows this text to the model word for word. With column knowledge on, the `conventions` of a column are also in its formula prompt.
```json
"person.gender_concept_id": {"guidance": "This field is meant to capture the biological sex at birth of the Person. ...", "conventions": "Use the gender or sex value present in the data ...", "ddl": {...}}
```

**`target/reference_tables.json`.** Keys: `reference_tables` (each with `target_table`, `source_relation`, `id_column`, `label_column`, optional `group_column`, `default_filters` as a list of `{column, equals}`) and `field_filters`. With no lookup tables use `{"reference_tables": [], "field_filters": {}}`. (This is the list of lookup tables, not the answer key.)
```json
{"target_table": "concept", "source_relation": "concept_seed", "id_column": "concept_id", "label_column": "concept_name", "group_column": "domain_id", "default_filters": [{"column": "standard_concept", "equals": "S"}]}
```

**`target/field_domains.json`.** Optional. `table.column` to `fkTableName`, `fkFieldName`, `fkDomain`, `fkClass`. Use `NA` when there is none.
```json
{"person.person_id": {"fkTableName": "NA", "fkFieldName": "NA", "fkDomain": "NA", "fkClass": "NA"}}
```

**`matches/matches.json`.** The matches. Every target column is a key (`table.column`); the value is a list of source columns, empty when nothing matches. A matcher or a person can write it. It may be wrong, and the model is told so. A target table is built when at least one of its columns has a match. A column without a match stays NULL.
```json
{"person.gender_source_value": [{"relation": "patients", "column": "GENDER"}], "person.person_id": []}
```

**`domain/`.** The expert text. Every file is optional, but with `domain_knowledge: required` the folder needs one `.md` file without TODO lines, or a non-empty `descriptions_supplement.json` or `value_meanings.json`.
- `domain_knowledge.md`: free text with the general rules for the move.
- `flow_text.md`: free text on how a source value becomes a target value. Example: "How a code in a source table becomes a target concept: 1. Find the concept_seed row whose concept_code equals the code ..."
- `descriptions_supplement.json`: a list of `{"table", "column" (or null), "text", "provenance"}`.
- `value_meanings.json`: a list of `{"table", "column", "value", "meaning"}`.
- `domain_text.json`: labels, `{"doc_label", "rule_table", "rule_label", "empty_markers"}`.
```json
{"table": "concept_seed", "column": "standard_concept", "value": "S", "meaning": "Standard concept."}
```

**`config.yaml`.** Optional settings for this package. The tool looks in the package folder first, then the current folder, then uses the built-in defaults (the same values as the shipped `config.yaml`). Each option is explained in `docs/config.md`. The history settings are:
- `history_tables`: the package names the table, the key, the order column and the tiebreak column of an event table. The tool then takes the latest non-empty value of each column per key.
- `history_auto`: the model decides in the recipe whether a table is built from events.
- `history_pattern`: adds guidance text to the prompts only.
```yaml
formula_docs: true          # column knowledge (default on)
history_tables:             # example with invented names
  customer: {key: cust_id, order: event_time, tiebreak: event_seq}
```

**Next to the package (not inside it).** `reference/` is the answer key: `reference_data/<table>.csv` and `alignment.json` (which source columns identify each row), or the reference recipes in `recipes/` and `fields/`. Only `test` reads it. `run/` is the output of `generate` and `execute`. Details are in `docs/input_package.md` and `docs/reference_format.md`.

## 5. Datasets

**Synthea to OMOP** (`datasets/synthea_omop/`). The package is included. The data and the answer key are not (see `LICENSES.md`).
`datasets/synthea_omop/SETUP.md` has the steps. In short: clone dbt-synthea, then run
```
python datasets/synthea_omop/tools/fill_source_data.py /path/to/dbt-synthea
python datasets/synthea_omop/tools/export_reference.py /path/to/dbt-synthea/synthea_omop_etl.duckdb
```
The first command copies the source data (a few seconds). The second needs the dbt-synthea tables, which you build with `dbt seed` and `dbt run` (see the dbt-synthea README).

**TPC-DI** (`datasets/tpcdi/`). No TPC-DI data and no specification text are included.
Get the data yourself: generate it with DIGen from tpc.org at scale factor 3. Get the TPC-DI specification (PDF) from tpc.org and extract its text to one file.
`datasets/tpcdi/README.md` explains both, the expected row counts, and the text format of the specification file.
Then run the four build commands in this order:
```
cd datasets/tpcdi
python build_source.py  --data OUT/Batch1 --repo SCHEMA_REPO --out WORK/source
python build_gold.py    --source-db WORK/source/tpcdi_source.duckdb --target-ddl WORK/source/target_ddl.sql --out WORK/gold
python build_history.py --source-db WORK/source/tpcdi_source.duckdb --out WORK/source_hist.duckdb
python make_package.py  --work WORK --spec SPEC_TEXT_FILE
```
`make_package.py` has more options (`--column-map`, `--expert-text`, `--fieldgen`); see `--help`.
`OUT` is the DIGen output folder and `SCHEMA_REPO` is the TPC-DI-MS-SQL-Benchmark folder that contains `Helpers/`. The four commands take about 1 minute.
The result is in `WORK/packages/run6` and `WORK/packages/run10`. Go back to the project folder before you run `run_demo.py`.

## 6. Files

Top level:
- `fieldgen/`: the tool (a Python package; run it with `python -m fieldgen`).
- `tests/`: offline tests (`pytest tests/`).
- `docs/`: tool documentation: `config.md`, `input_package.md`, `reference_format.md`, `domain_knowledge.md`, `results.md`, `send_back.md`.
- `datasets/`: the two datasets (below).
- `replay/`: saved model answers and recorded scores (below).
- `results/`: `RESULTS.md` (results and limits) and `configs/` (the `config.yaml` of each run).
- `config.yaml`: the shipped settings. Column knowledge is on; the history options are off.
- `run_demo.py`: replays saved answers through generate, execute and test, and prints the score table.
- `requirements.txt`: pinned Python packages.
- `pytest.ini`: test settings.
- `LICENSES.md`, `NOTICE`: licence notes.

`datasets/synthea_omop/`:
- `package/`: the Synthea to OMOP input package (no data).
- `reference/`: reference recipes for the answer key.
- `tools/fill_source_data.py`: copies the Synthea data from a dbt-synthea clone into the package.
- `tools/export_reference.py`: writes the answer-key tables from the dbt-synthea database.
- `README.md`, `SETUP.md`: description and setup steps.

`datasets/tpcdi/`:
- `build_source.py`: loads the TPC-DI source files into one DuckDB file and writes the DDL.
- `build_gold.py`: runs the gold SQL and writes the gold tables, the answer key.
- `build_history.py`: builds the table with one row per customer action for run 10.
- `make_package.py`: writes the packages and references for run 6 and run 10 (reads the specification text you give it).
- `gold_sql/`: the nine gold SQL files, with clause numbers instead of specification text.
- `expert_text/`: the expert text and `config.yaml` of run 6 and run 10.
- `column_map.csv`: which source columns feed each target column (used for the matches).
- `README.md`: how to get the data and the specification, and the expected row counts.

`replay/`:
- `answers/`: the model's saved recipes and formulas of three runs (no prompts).
- `recorded/`: the scores of the live runs, used for the comparison.
- `extract_answers.py`: copies the answers out of a finished run folder (only needed to make new answer files).

## 7. More

Results and limits are in `results/RESULTS.md`. Licences are in `LICENSES.md` and `NOTICE`.
