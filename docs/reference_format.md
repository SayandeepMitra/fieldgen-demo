# The reference (for scoring)

A **reference** is the right answer for a move you already trust: the target tables as they should look, and a way to tell which source row each target row came from.
fieldgen uses it only to **test** a generated run (`fieldgen test`). The tool never reads it while it generates (a test checks this).
No reference means no testing (`fieldgen test` says "no reference, nothing to test"). Everything else still works.

The reference sits in a folder of its own, next to the package folder by default:

```
examples/synthea_omop/
  package/       the input package (what the tool reads)
  reference/     the reference (what only the scorer reads)
```

The folder is always `reference/` next to the package folder. In `config.yaml`, `reference: off` makes `fieldgen test` skip even if the folder exists.

## Minimum format: reference tables and row identity

Enough to score the **rows** of every table and the **values** of every column (levels L0 to L3, headline L2).

```
reference/
  reference_data/<target table>.csv     the reference rows, one file per target table
  alignment.json                        which source columns identify each row
```

`reference_data/<table>.csv`: UTF-8 CSV with a header. The columns are the columns of the target table, in the order of `target/tables.json`. A missing value is an empty cell.

`alignment.json` says, per target table, which source column(s) identify the source row of each reference row, and which reference column holds the same identifier:

```json
{"purchase": {"source": ["orders.order_id"], "reference": ["purchase_source_value"], "exclude": ["purchase_id", "client_id"]},
 "client":   {"source": ["customers.cust_id"], "reference": ["client_source_value"], "exclude": ["client_id"]}}
```

- `source`: the source columns that identify a row (`table.column`). If a table can be built from two different sources, give a list of lists: `[["a.id"], ["b.id"]]`.
- `reference`: the column(s) of the reference table that carry the same identifier. In the OMOP example these are the `*_source_value` columns.
- `exclude` (optional): columns that are not scored (for example numbered keys, which no tool can reproduce).

How a column is scored: the tool's value for each source row is compared with the reference value of the row that has the same identifier.
A table has the **correct rows** when the identifiers of the tool's rows are the same as the reference's (the same rows, once each).

With this format `L4` is skipped (it needs the full format).

## Full format: the reference conversion as runnable SQL

Add the reference conversion itself, written in the same recipe format the tool uses. This allows level **L4**, which runs the reference expressions on perturbed copies of the data.

```
reference/
  recipes/<table>.json                  one recipe per target table
  fields/<table>.<column>.json          one file per target column
  reference_data/<table>.csv            as in the minimum format
```

`recipes/<table>.json`:

```json
{"table": "purchase", "grain": "one row per order",
 "branches": [{"id": "b1", "from": "FROM orders o JOIN state_codes s ON o.state_code = s.code"}],
 "combine": "none", "group_by": null}
```

`fields/<table>.<column>.json`:

```json
{"task_id": "purchase.amount", "table": "purchase", "column": "amount", "kind": "value",
 "reference": {"table": "purchase", "column": "amount"},
 "expressions": [{"branch": "b1", "expr": "o.amount"}],
 "alignment": {"source": ["b1:orders.order_id"], "reference": ["r.purchase_source_value"]},
 "alignment_quality": "strong",
 "ambiguity": {"ambiguous": false, "reason": "", "source": "pending"},
 "exclusion_reason": null}
```

- `kind`: `value` (scored), `keygen` (a numbered key: checked for being unique and not NULL), `placeholder` (must be NULL) or `excluded` (not scored).
- `expressions`: the reference SQL for the column, one per branch of the recipe. The `from` of the recipe and the expressions must run on your source tables.
- `alignment`: as in `alignment.json`, with the branch id in front of the source column (`b1:orders.order_id`) and `r.` in front of the reference column.

Both formats can be mixed: if `alignment.json` exists, it fills in every column that has no file in `fields/`.

## What `fieldgen test` does with each kind

- **The folder holds reference tables** (`reference_data/*.csv`) and the row identities (`alignment.json` or `fields/`): it compares.
- **The folder holds recipes and fields but no tables:** it first **runs the reference recipes on your source data** to build the reference tables (into `run/reference_built/`; your reference folder is not changed), then compares.
  The built tables are exact for every scored column and for the row identities (on the OMOP example: 26 of 26 tables, 152 of 152 scored columns, and the same test result as with the tables of the original program). Numbered ids and keys that the original program took from the output of another target table cannot be rebuilt from source tables and may differ or stay empty; they are not scored. A foreign key of that kind is filled from the referenced reference table when both tables identify their rows by the same source column.
- **Neither:** it prints "no reference, nothing to test" and stops.

`test` also checks that no reference expression appears in the package files, and stops if one does.
`L4` runs only when `robustness_check: true` (and needs the full format).

## How to build a reference for your own move

- You already have a trusted conversion (a program, an ETL, a hand-checked set of tables): export its output tables to `reference_data/` and write `alignment.json`.
- You also have its SQL: write the recipe and field files as above to get L4.
- You have nothing: skip scoring. Read `report.md` and check a sample of rows yourself.

## The OMOP example

`examples/synthea_omop/reference/` has the full format (recipes and fields) for the Synthea to OMOP move.
It was derived from the SQL of the dbt-synthea project (see `LICENSES.md`).
The reference tables (`reference_data/`) are **not** in the repository. `examples/synthea_omop/tools/export_reference.py` writes them from your own dbt-synthea run.
