# fieldgen: LLM-written SQL for database conversion (student project)

fieldgen asks a language model to write SQL that converts the tables of one database (source) into the tables of another data model (target). Step 1: a **recipe** per target table (which source tables, joins, grouping). Step 2: one SQL **formula** per target column. The tool runs the SQL on DuckDB and scores the result against a reference.
This folder holds the tool (fieldgen-fix, commit d8acdbf: v1.2-demo plus the changes below), two datasets (Synthea to OMOP, TPC-DI to a warehouse), the saved model answers of the runs, and the results.

1. Tool = fieldgen-demo v1.2-demo + one new default and four off-by-default options. **Column knowledge** (`formula_docs`, on): each formula prompt shows the documented rules of its column.
2. Off by default: `history_pattern`, `history_tables`, `history_auto` (ways to tell the tool to build a current state from event records) and `formula_length_retry`.
3. Synthea to OMOP: column knowledge raised the correct tables from 11 to 13 of 18 and the correct columns from 54 to 57.
4. TPC-DI DimCustomer (28 columns): 10 correct with the plain tool, 22 with a package-given history wrapper, 23 with a prepared source plus column knowledge.
5. Each result is one run of one model. Differences of one or two columns are within run-to-run variation.
6. The replays here reproduce the recorded scores exactly, without a key or network: the model's saved answers are fed through the tool's own pipeline.
7. No data, databases or TPC text are in this folder; the datasets need setup (below).
8. Licences: see `LICENSES.md` and `NOTICE` (from fieldgen-demo). The owner has not chosen a licence for our own code yet.
9. Details of every run: `results/RESULTS.md`; config of every run: `results/configs/`.
10. Python 3.10 or newer; `pip install -r requirements.txt`.

## Results

| experiment | what | result (single run) |
|---|---|---|
| Synthea to OMOP, v1.2-demo | default tool | 11 of 18 tables with correct rows, 54 L2 columns |
| Synthea to OMOP, column knowledge | `formula_docs` on | **13 of 18**, **57** L2 columns |
| TPC-DI DimCustomer, run 1 | default tool, documentation only | 10 of 28 columns |
| TPC-DI DimCustomer, run 6 | history wrapper given in the package config | 22 of 28 |
| TPC-DI DimCustomer, run 10 | prepared source + expert text + column knowledge | **23 of 28** |

All ten TPC-DI runs and what changed in each: `results/RESULTS.md`.

## Quick start

**Level 1: tests (offline, about 1 minute).**
```
pip install -r requirements.txt
pytest tests/
```

**Level 2: replay (no key, no network).** Feeds the saved answers through the tool's own generate, execute and test, prints the score table and compares it with the recorded run. Needs the data of the dataset once:
```
# Synthea: follow datasets/synthea_omop/SETUP.md (copy data from dbt-synthea), then
python run_demo.py --dataset synthea                       # expect 13 of 18 tables, 57 L2 columns
# TPC-DI: follow datasets/tpcdi/README.md (build the data and the packages into a work folder), then
python run_demo.py --dataset tpcdi --run run10 --work WORK # expect 23 of 28 columns
python run_demo.py --dataset tpcdi --run run6  --work WORK # expect 22 of 28 columns
```

**Level 3: live run with your own key.** The default endpoint is the free NVIDIA one; it records inputs and outputs, so check the licence of your data first. The key is read from the environment only.
```
export NVIDIA_API_KEY=...                                  # your NVIDIA API key
python -m fieldgen generate --package datasets/synthea_omop/package   # about 25 min; then execute, then test
python -m fieldgen execute  --package datasets/synthea_omop/package
python -m fieldgen test     --package datasets/synthea_omop/package
```
Settings come from `config.yaml` (package folder first, then the current folder); every option is explained in `docs/config.md`.

## Known limits

- Each result is one run of one model; differences of one or two columns are within run-to-run variation.
- `history_auto` (off by default) expects `column` or `table.column` names; alias forms such as `c.C_ID` are not resolved.
- The saved TPC-DI answers in `replay/answers/` have their free-text `assumptions` lists emptied (they may quote the TPC-DI specification); recipes, expressions and all other fields are unchanged, and the replays still reproduce the recorded scores.

## Folder layout

```
fieldgen/         the tool (Python package; run with python -m fieldgen)
tests/, pytest.ini, config.yaml, requirements.txt, docs/   tests, shipped settings, pinned packages, tool documentation
datasets/synthea_omop/   the Synthea to OMOP package as fieldgen-demo ships it (data not included; SETUP.md)
datasets/tpcdi/          scripts that build the TPC-DI data, gold tables and packages from DIGen output and the spec (nothing included)
replay/answers/          the model's saved answers (recipes, formulas) of three runs: no prompts
replay/recorded/         the scores of the live runs, for the comparison
run_demo.py              replay, execute, test, score table
results/                 RESULTS.md and the config of each run
LICENSES.md, NOTICE      licence notes from fieldgen-demo
```
