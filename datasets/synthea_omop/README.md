# Example: Synthea sample data to the OMOP CDM v5.4

The source is the small Synthea sample data set (27 patients, 18 tables) plus the OMOP vocabulary seed tables and a state list.
The target is the OMOP common data model, version 5.4 (39 tables). The tool builds 19 of them: the ones that have matched source columns and are not plain copies of a vocabulary table. Our reference covers 18 of these.

```
package/      the input package (what the tool reads)
reference/    the reference conversion (what only the scorer reads)
tools/        two scripts that fill in the files that are not in this repository
```

## Why the data is not here

The Synthea sample data, the vocabulary seed files and the reference tables are **left out** because their licences are unclear or restricted (see `../../LICENSES.md`).
The package is complete without them, except `package/source/data/` (empty). `reference/reference_data/` is missing too, but `fieldgen test` can build the reference from the reference recipes.

## How to run the example

Run the commands from the repository root (so that `config.yaml` is found). You need a clone of dbt-synthea (https://github.com/OHDSI/dbt-synthea, Apache-2.0); it carries the Synthea sample data and the vocabulary seeds.
You are responsible for the terms of the data and the vocabularies you copy.

1. Copy the source data into the package:
   ```bash
   python examples/synthea_omop/tools/fill_source_data.py /path/to/dbt-synthea
   ```
   It writes 29 CSV files into `package/source/data/` and checks the row counts against the manifest.
   (It writes timestamps with the offset +05:30, the zone the example was built in. The instants are the same as in the seeds. `docs/results.md` explains this.)
2. `fieldgen generate --package examples/synthea_omop/package` checks the package (no problems and no TODOs are left in the example; warnings about primary keys of target tables are normal), then writes the recipes, formulas and SQL into `examples/synthea_omop/run/`. About 25 minutes with the default settings and the free NVIDIA endpoint.
3. `fieldgen execute --package examples/synthea_omop/package` builds the 19 target tables into `run/tables.duckdb`.
4. `fieldgen test --package examples/synthea_omop/package`. The folder `reference/` holds the reference **recipes** (no tables), so `test` first runs them on your data to build the reference tables, then compares.
   Such a reference can differ from the tables of the original program (on this example 10 of 26 tables are identical; see `docs/reference_format.md`).
   For the exact reference, build the tables with dbt-synthea (`dbt seed` and `dbt run`, see its README) and export them:
   ```bash
   python examples/synthea_omop/tools/export_reference.py /path/to/dbt-synthea/synthea_omop_etl.duckdb
   ```
   This writes `reference/reference_data/*.csv` (26 tables, in UTC; cost and measurement differ from ours only in trailing zeros of decimals). With the tables present, `test` compares with them and does not rebuild anything.

## What we got on this example

See `../../BUILD_NOTES.md` (reproduction run) and `../../docs/results.md`.
