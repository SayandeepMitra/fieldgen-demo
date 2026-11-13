# fieldgen: SQL for database conversion, written by a language model

fieldgen writes SQL that turns the tables of a source database into the tables of a target schema.
A language model writes the SQL. The tool checks every answer on the real data and asks again when an answer is wrong.
It ran on two datasets: the Synthea sample data converted to the OMOP common data model, and TPC-DI data converted to a data warehouse schema.
This folder holds the tool, the dataset setup scripts, the saved model answers of three runs, and the results.

Authors: [Names]. Course: [Course]. Year: [Year].

## How it works

1. Prepare a package: source data, target schema, matched columns, target documentation, and optional expert text (`init`, `check`).
2. Recipe step (model): for each target table, the model chooses the source tables, the joins and the grouping.
3. Formula step (model): for each target column, the model writes one SQL expression.
4. Build: the tool joins the recipe and the formulas into one query per table and runs it on DuckDB (`execute`).
5. Score: the tables are compared with the answer key, the reference data that only the scorer reads (`test`).

The checks run in steps 2 and 3. A recipe that does not run, or a formula that fails a check on the data, goes back to the model with the error text.
A recipe gets up to two such follow-ups. A formula gets one for a wrong answer and up to two for failed checks.
The tool never reads the answer key while it generates.

## Results

Every number is a single run of one model. Details of all runs are in `results/RESULTS.md`.

Synthea to OMOP (18 scored tables). Column knowledge means that each formula prompt shows the documented rules of its column.

| version | tables with correct rows | columns correct (in those tables) |
|---|---|---|
| stable version (v1.2-demo) | 11 of 18 | 54 |
| with column knowledge | 13 of 18 | 57 |

TPC-DI, table DimCustomer (28 columns):

| run | what changed | columns correct |
|---|---|---|
| 1 | stable version, documentation only | 10 of 28 |
| 6 | the package names the key and the order of the event records; the tool takes the latest non-empty value per column | 22 of 28 |
| 9 | source prepared with one row per customer action, new expert text | 19 of 28 |
| 10 | run 9 plus column knowledge | 23 of 28 |

## Setup

You need Python 3.10 or newer.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running

Commands are run from this folder.

**a) Tests (offline, about 1 minute).**
```
pytest tests/
```

**b) Replay of saved model answers (no API key, no network).**
`run_demo.py` gives the saved answers to the tool's own generate, execute and test steps. It prints a score table and compares it with the recorded run.
It needs the dataset once. For Synthea, set up the data (see below), then:
```
python run_demo.py --dataset synthea
```
This takes about 2 minutes and should print 13 of 18 tables and 57 columns. For TPC-DI, build the packages first (see below), then:
```
python run_demo.py --dataset tpcdi --run run10 --work WORK     # 23 of 28 columns
python run_demo.py --dataset tpcdi --run run6  --work WORK     # 22 of 28 columns
```
Each TPC-DI replay takes about 10 minutes. `WORK` is the folder you gave to `make_package.py`.

**c) Live run with your own key.**
The default endpoint is the NVIDIA API. The key is read only from the environment variable `NVIDIA_API_KEY`.
That endpoint records inputs and outputs. Your prompts contain samples of the source data, so check the rules for your data first.
```
export NVIDIA_API_KEY=...
python -m fieldgen generate --package datasets/synthea_omop/package
python -m fieldgen execute  --package datasets/synthea_omop/package
python -m fieldgen test     --package datasets/synthea_omop/package
```
`generate` takes about 20 to 25 minutes for Synthea (19 tables) and about 8 to 13 minutes for DimCustomer alone.
The other commands are `init` (create a package) and `check` (validate a package without model calls).
Settings are in `config.yaml` and explained in `docs/config.md`.

## Datasets

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
`OUT` is the DIGen output folder and `SCHEMA_REPO` is the TPC-DI-MS-SQL-Benchmark folder that contains `Helpers/`. The four commands take about 1 minute.
The result is in `WORK/packages/run6` and `WORK/packages/run10`. Go back to the project folder before you run `run_demo.py`, and use an absolute path for `WORK` so that both folders find it.

## Folder layout

- `fieldgen/`: the tool (a Python package).
- `tests/`: offline tests.
- `docs/`: tool documentation (the config options are in `docs/config.md`).
- `config.yaml`: the shipped settings. Column knowledge is on; the history options are off.
- `datasets/synthea_omop/`: the Synthea to OMOP package, the answer-key scripts, `SETUP.md`.
- `datasets/tpcdi/`: scripts that build the TPC-DI data, the gold tables and the packages; expert text and gold SQL.
- `replay/`: the saved model answers (recipes and formulas, no prompts) and the recorded scores.
- `results/`: `RESULTS.md` and the `config.yaml` of each run.
- `run_demo.py`: the replay script.
- `requirements.txt`, `pytest.ini`, `LICENSES.md`, `NOTICE`.

## Known limits

- Each result is a single run of one model. A difference of one or two columns is within the variation between runs.
- The recipes and formulas fit the dataset they were made for. A new dataset needs a new run.
- `history_tables` (off by default) needs the package to name the key, the order and the tiebreak column of the event records. The tool does not find them.
- Some lookups cannot be written. TPC-DI matches Prospect records on the customer's current values, which needs a subquery. The formula checker rejects subqueries, so these columns stay wrong (agencyid, creditrating, networth).
- `history_auto` (off by default) expects `column` or `table.column` names. Alias forms such as `c.C_ID` are not resolved.
- Rules that are not in the documentation or the expert text are not applied (for example the marketing nameplate tags in TPC-DI).
- In the saved TPC-DI answers in `replay/answers/`, the free-text `assumptions` lists are emptied, because they may quote the TPC-DI specification. Recipes, expressions and all other fields are unchanged, and the replays still match the recorded scores.
- The default endpoint is free and records inputs and outputs.

## Licences

See `LICENSES.md` and `NOTICE`. Data and vocabularies that the licences leave out are not in this folder.
