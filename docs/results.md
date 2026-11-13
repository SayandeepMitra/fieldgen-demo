# How to read the results

## What a run writes

`fieldgen generate` and `fieldgen execute` write one folder, the run folder `run/` next to your package folder:

| file or folder | what it is |
|---|---|
| `report.md` | start here: settings used, model id served, tables built (after `execute`), errors, calls and tokens, test result (after `test`) |
| `summary.json` | the same facts for programs |
| `settings.json` | the settings of the run (the key is never written) |
| `recipes/<table>.json` and `.txt` | the recipe of each target table: JSON, and the same in plain words |
| `formulas/<table>.json` | the SQL expression of each column |
| `sql/<table>.sql` | the final SQL of each table (the recipe and the formulas together) |
| `tables.duckdb`, `execute.json` | all built tables in one DuckDB file, and what `execute` did (written by `execute`) |
| `recipes.jsonl`, `formulas.jsonl` | full records: every attempt, retry and guardrail round |
| `calls.jsonl` | every model call: the full prompt, the raw answer, model id, settings, tokens, time (no request headers, no key) |
| `scores.json` | the scores (written by `test`) |
| `reference_built/` | reference tables built from reference recipes (only when `test` had to build them) |
| `work/` | derived files (field cards, link facts); safe to delete |

`generate` can be resumed: run it again and finished tables and columns are not asked again. To start over, delete the run folder.

## The measures

`fieldgen test` compares your run with a reference (`docs/reference_format.md`).

- **Tables with correct rows** (recipe level): the tool's table has the same rows as the reference, each once. This is the first thing to look at.
- **L2: columns correct end to end** (**the headline**): the values of the column equal the reference values, row by row, matched through the row identifiers of the reference. The report gives L2 for all scored columns, and again for the columns of tables whose rows are correct.
- L0, L1, L3: the SQL runs; the rows are found; the type is right. They explain a failure. They are not results.
- **L4 (additional)**: the same expressions on perturbed copies of the data (random NULLs, unusual strings, boundary values, lookup misses, upper-case ids). It asks whether the SQL still agrees with the reference expression when the data changes.
  We report it as an additional result only. A recipe is written for the data it saw, so it may break on a perturbation that the reference expression survives.

On the example (formulas written on the first passing recipe of each of the 12 tables that were correct): **54 of 60 scored columns correct at L2**, and 27 of 60 at L4.
With the correct (reference) recipe given, the same formula step gets 92 to 93 of 95 columns. Our earlier headline for recipes: 12 of 18 tables with correct rows.

## Read with care

- **Results fit the dataset they were generated from.** The recipes and formulas were made from the profiled data and its documentation. For new data, run again.
- **One run varies.** With temperature 0 the model still answers a little differently from run to run. We saw single tables move between 0 and 3 passes out of 5 with no change to the prompt. Do not read one table's change as an effect.
- **Tables built from other target tables are out of scope.** A column that must hold a key of another target table (a person id in the visit table, a visit id in the condition table) is numbered by the tool on its own. It cannot match a reference that numbered the keys differently. Such columns are normally excluded from scoring.
- A wrong table can still contain right columns (and the reverse). Read the table and the column numbers together.
- `report.md` lists every error. Check a sample of rows yourself, even when the score is high.

## Data protection

The default endpoint is free to use and **records the inputs and the outputs** of the calls. The prompts contain descriptions of your tables, statistics and **samples of your source values**.
Before you run on real data, check the licence and the privacy rules of the dataset. If in doubt, use synthetic or public data, or an endpoint you control (`base_url` in `config.yaml`).
`calls.jsonl` and `tables.duckdb` contain your data. Do not share them unless you are allowed to.

## About the +05:30 in the example data

The example source files carry timestamps as text with an offset, for example `1994-12-12 09:31:15+05:30`. That text comes from the data files (they were written on a machine in that zone); the instants are the same as in the original UTC data.
The tool reads this text as it is and runs all SQL in UTC, so the prompts and the results do not depend on the time zone of your machine (a test checks this).
