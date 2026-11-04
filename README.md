# fieldgen (demo release v1.0-demo)

fieldgen writes SQL that converts the tables of one database (the **source**) into the tables of another data model (the **target**).
It uses a language model, the documentation of the target, and facts it measures on your data.

It works in two steps:

1. **Recipe.** For each target table the model decides which source tables to read, how to join them, and how to combine the rows.
2. **Formulas.** For each target column the model writes one SQL expression.

Then fieldgen runs the SQL on your source data and builds the target tables in one DuckDB file.
If you also give it a **reference** (tables or a conversion you already trust), it tests the result against it.

The example in this repository is the move from the Synthea sample data to the OMOP common data model (version 5.4).

## Quick start

You need Python 3.10 or newer and an API key for an OpenAI-compatible endpoint (the default is the NVIDIA endpoint).
Install once (`pip install -e .`) and set the key in your shell: `export NVIDIA_API_KEY=...` (it is read from this variable only, never written anywhere).
Four commands, in this order. Each takes `--package DIR`; every other setting comes from `config.yaml`. The file is looked for in this order: **1. the package folder** (`DIR/config.yaml`), **2. the current folder**, **3. the built-in defaults** (the first one found is used, the command prints which). Each command ends by printing the next one.

1. `fieldgen init --package DIR --source SRC --target DDL` builds the package from your data (a folder of CSV files or a DuckDB file) and your target schema (a `.sql` DDL file, a folder of `.sql` files, or a DuckDB file); it leaves a `TODO.md`.
2. `fieldgen generate --package DIR` checks the package (it stops with the problems and TODOs), then writes recipes, formulas and the final SQL into the run folder `DIR/../run/`.
3. `fieldgen execute --package DIR` runs the SQL and writes all target tables into `run/tables.duckdb` (`execute.sample_rows` in `config.yaml` limits the rows).
4. `fieldgen test --package DIR` compares with the reference in `DIR/../reference/`, if there is one; if not it says "no reference, nothing to test".

`fieldgen check --package DIR` only validates the package (generate runs it first).
The example package does not contain the Synthea data or the vocabulary files (see `LICENSES.md`). Add them first: `examples/synthea_omop/README.md`. For your own data, read `docs/input_package.md`.

## What to read

| file | what it tells you |
|---|---|
| `docs/input_package.md` | every file of an input package, what `init` fills and what stays TODO |
| `docs/reference_format.md` | what a reference must contain (minimum and full) |
| `docs/domain_knowledge.md` | how to write the expert text, and what the tool adds itself |
| `docs/config.md` | every option of `config.yaml`, which values we tested, what we measured |
| `docs/results.md` | how to read the output; what the numbers do and do not mean |
| `docs/send_back.md` | the exact list of files to send back after a test |

## Limits (read this before you trust a result)

- The recipes and formulas fit **the dataset they were generated from**. A new dataset needs a new run.
- **Headline from our experiments** (Synthea to OMOP, headline measure L2): the recipe step built **12 of 18** target tables with the correct rows. Formulas written on the first passing recipe of those 12 tables gave **54 of 60** scored columns correct end to end. Those two numbers come from separate experiments. `BUILD_NOTES.md` has the result of one full default run of this release next to them. One run varies by a few tables or columns.
- Target tables that need keys from other target tables (for example a person id taken from the person table) are **out of scope**. The tool numbers such keys itself, so they do not match a reference.
- Only one model was tested in full (see `docs/config.md`). Every setting that was not tested prints "untested setting" when a run starts.
- The default endpoint is free to use and **records the inputs and outputs**. Your prompts contain samples of your source data. Check the licence and the privacy rules of your data first.
- This is a demo release. `fieldgen init` proposes keys and links and fills the technical parts of a package. Matches, descriptions, target documentation and domain knowledge stay yours to write.
