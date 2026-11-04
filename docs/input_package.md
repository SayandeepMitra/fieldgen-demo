# The input package

An input package is one folder. It describes your source data, your target model, and (optionally) what an expert knows about the move.
`fieldgen init` creates it from your data and your target schema. You then fill in what is left (the TODOs). `fieldgen check --package DIR` tells you what is wrong with a package, and `fieldgen generate` runs the same check first. Neither makes model calls.

```
package/                                          init fills                                   you fill (TODO)
  manifest.json                  required         name, version, row counts, table count       nothing
  TODO.md                        written by init  the list of what is left                     delete when done
  source/
    tables.json                  required         tables, columns, types, PROPOSED keys        descriptions; confirm the keys
    links.json                   required         PROPOSED links (inferred from the data)      confirm, delete, or add the ones you know
    data/<table>.csv             required         copied from your source                      nothing
    profiles/<table>.json        optional         computed from the data                       nothing
    dependencies.json            optional         not written; not used by the default prompts nothing
  target/
    tables.json                  required         tables, columns, types, keys from the schema  business ids (optional)
    field_docs.json              required         empty template (all columns, no text)         the target documentation
    reference_tables.json        required         empty list                                    the lookup tables, if any
    field_domains.json           optional         not written                                   optional
  matches/matches.json           required         every target column with an EMPTY list        the matched source columns (blocks generate)
  domain/                        required if domain_knowledge is "required" (the default)
    domain_knowledge.md          optional         template with TODO lines                      the general rules (blocks generate until done)
    flow_text.md                 optional         template with TODO lines                      how a source value becomes a target value
    descriptions_supplement.json optional         empty list                                    expert descriptions
    value_meanings.json          optional         empty list                                    meaning of coded values
    domain_text.json             optional         default labels                                nothing (see docs/domain_knowledge.md)
```

Two TODOs **block** `fieldgen generate`: no matched columns at all, and (while `domain_knowledge: required`) no domain knowledge file without TODO lines.
Everything else is a hint that `generate` prints and then continues.

Names of tables and columns are kept exactly as you write them. Use lower case names for target tables and columns (the matches file requires it).

## manifest.json

```json
{"name": "shop", "version": "1.0",
 "source_row_counts": {"customers": 4, "orders": 6, "state_codes": 3},
 "target_tables": 3}
```

`source_row_counts` must equal the number of data rows in each CSV file. `target_tables` is the number of target tables.
Do not add anything that describes the reference. `check` rejects a manifest with a `gold` section.

## source/tables.json

One entry per source table. Every table needs a primary key.

```json
[{"name": "orders",
  "description": "One row per order.",
  "columns": [{"name": "order_id", "type": "VARCHAR", "nullable": false, "description": "Unique id of the order."},
              {"name": "cust_id", "type": "VARCHAR", "nullable": true},
              {"name": "order_date", "type": "DATE", "nullable": true},
              {"name": "amount", "type": "DOUBLE", "nullable": true}],
  "pk": ["order_id"], "business_ids": ["order_id"]}]
```

Types are DuckDB types (`VARCHAR`, `INTEGER`, `DOUBLE`, `DATE`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE`, ...).
`description` is optional but helps the model. Use the text of your own data dictionary.
`business_ids` are the columns people use to identify a row (can be empty).

## source/data/<table>.csv

UTF-8, comma separated, a header row with the column names, quotes as in RFC 4180. A missing value (NULL) is an empty cell.
The header must equal the declared columns, in the same order.

## source/links.json

How source tables join. Give the links you know. Leave out the ones you do not know.

```json
[{"child": "orders", "child_columns": ["cust_id"], "parent": "customers", "parent_columns": ["cust_id"],
  "cardinality": "many_to_one", "provenance": "declared", "support": "dictionary", "weak": false}]
```

- `cardinality`: `one_to_one`, `many_to_one`, `one_to_many` or `many_to_many`.
- `provenance`: `declared` (from a data dictionary or foreign key), `supplemented` (added by an expert), or `inferred` (found in the data; it must point to the parent's primary key).
- `support`: `dictionary` (a declared link needs this), `name` (the column names say so) or `value_only` (only the values match).
- `weak` must be `true` exactly when `support` is `value_only`. Weak links are not shown to the model.
- Optional: `coverage` (a number from 0 to 1), `evidence` (text), `note`.

## source/profiles/<table>.json and source/dependencies.json (optional)

If you do not give profiles, fieldgen computes them from the CSV files (count, null rate, distinct values, most frequent values, shapes).
In our tests the prompts were identical with and without these two files. A file with a wrong table or column name makes `check` fail, so only add them if you can generate them correctly.

## target/tables.json

The target tables, as a database definition would give them.

```json
[{"name": "purchase",
  "description": "One row per purchase.",
  "columns": [{"name": "purchase_id", "type": "integer", "nullable": false, "constraints": ["primary key", "not null"]},
              {"name": "client_id", "type": "integer", "nullable": true, "constraints": []},
              {"name": "amount", "type": "double", "nullable": true, "constraints": [], "value_hints": {"format": "decimal number"}}],
  "pk": ["purchase_id"],
  "fks": [{"columns": ["client_id"], "ref_table": "client", "ref_columns": ["client_id"]}],
  "business_ids": []}]
```

Use lower case names. `type` is the DuckDB type the finished column gets (for example `varchar(50)`, `date`).
`value_hints` is optional.

## target/field_docs.json: the target documentation

The text that explains the target model. fieldgen shows it to the model, word for word.

```json
{"tables": {"purchase": {"description": "A purchase is one order.", "guidance": null, "conventions": null}},
 "fields": {"purchase.amount": {"guidance": "The total price of the order.",
                                "conventions": "Use two decimals.",
                                "ddl": {"type": "double", "default": null, "check_constraints": [], "unique": false}}}}
```

- `guidance` says what the column means. `conventions` says how to fill it. Both can be `null`.
- Give an entry for every target column you have text for.
- For the OMOP model we built this file from the field-level documentation of the OHDSI CommonDataModel project (see `LICENSES.md`).
  The columns of its CSV file are `userGuidance` (our `guidance`) and `etlConventions` (our `conventions`). The value `NA` means empty.

## target/reference_tables.json: the lookup tables

Some source tables are lookups: code lists, vocabularies, domains. List them here. The tool treats a source table as a copy of a target table when all columns of the target table are in it.

```json
{"reference_tables": [{"target_table": "state", "source_relation": "state_codes",
                       "id_column": "code", "label_column": "label", "default_filters": []}],
 "field_filters": {}}
```

`group_column` is optional. `default_filters` is a list of `{"column": ..., "equals": ...}` for rows that count by default
(for OMOP vocabularies: only rows with `standard_concept = 'S'`). If you have no lookup tables, use `{"reference_tables": [], "field_filters": {}}`.

## target/field_domains.json (optional)

For columns that point to a lookup row: the domain that row must belong to.

```json
{"purchase.state_label": {"fkTableName": "state", "fkFieldName": "label", "fkDomain": "State", "fkClass": ""}}
```

Use an empty text or `NA` when there is none. For OMOP this comes from the same CSV as the documentation (columns `fkTableName`, `fkFieldName`, `fkDomain`, `fkClass`).

## matches/matches.json

Which source columns are likely sources of each target column. It comes from a matcher (a tool, a person, or both). It may be incomplete or wrong. The model is told so.

```json
{"purchase.amount": [{"relation": "orders", "column": "amount"}],
 "purchase.client_id": []}
```

Give **every** target column as a key, in the form `table.column`, with an empty list when nothing matches.
The target tables that fieldgen builds are the ones that have at least one match and are not plain copies of a source lookup table.
Columns without a match get no formula (they stay NULL).

## domain/ (the expert text)

Optional files that carry what an expert knows. See `docs/domain_knowledge.md` for the templates and for what the tool adds itself.
If you do not have any, set `domain_knowledge: optional` or `off` in `config.yaml` (untested, see `docs/config.md`).

## How to create a package from your own data

1. Put your source data in one folder as CSV files (UTF-8, header, empty cell = NULL), or in a DuckDB file. Write the target schema as a `.sql` DDL file (`CREATE TABLE ...`) or put the target tables in a DuckDB file.
2. Run `fieldgen init --package DIR --source SRC --target DDL`. It copies the data, reads the types and row counts, computes the profiles, **proposes** a primary key for every source table and links between tables (marked `proposed`), and reads the target tables, columns, types and keys.
   It refuses to write into a folder that already holds a package.
3. Open `TODO.md` and work through it:
   - **Matches** (blocking): list the source columns that probably feed each target column. A matcher or a person can do this.
   - **Domain knowledge** (blocking while `domain_knowledge` is `required`): follow `docs/domain_knowledge.md`, or set `domain_knowledge: optional` (or `off`) in `config.yaml`.
   - **Confirm the proposals**: keys and links. A table for which no key could be found needs one by hand.
   - **Descriptions and target documentation**: add your data dictionary to `source/tables.json` and the target documentation to `target/field_docs.json`. This makes the result better.
   - **Lookup tables**: list code lists and vocabularies in `target/reference_tables.json`.
4. Run `fieldgen check --package DIR` and fix every error. Warnings are hints.

Never put the reference into the package. The reference lives in a separate folder next to it (`docs/reference_format.md`).
