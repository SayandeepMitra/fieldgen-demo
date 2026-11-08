# Licences of the items in this repository

Nothing here is legal advice. Each line says what an item is, where it comes from, its licence, and how we know. Items whose licence was unclear are **left out** (second table).

## Included

| item | source | licence | how checked |
|---|---|---|---|
| `src/`, `tests/`, `docs/`, `README.md`, `config.yaml`, `examples/synthea_omop/package/domain/`, `.../source/links.json`, `.../target/reference_tables.json` | written for this project | **not chosen yet** (see BUILD_NOTES.md, open issues): until the owner picks a licence, all rights are reserved | |
| `examples/synthea_omop/package/target/tables.json` | table and column definitions of the OMOP CDM v5.4, from the DDL of the OHDSI CommonDataModel project (https://github.com/OHDSI/CommonDataModel, tag v5.5.0) | Apache-2.0 | the `DESCRIPTION` file of a local clone of the project says "License: Apache License 2.0". A `LICENSE` file could not be fetched from GitHub in this session (404 for the path tried) |
| `.../target/field_docs.json`, `.../target/field_domains.json`, `.../target/provenance.json` | text of `OMOP_CDMv5.4_Field_Level.csv` and the table-level CSV of the same project and tag (user guidance, ETL conventions, foreign-key domains), reformatted; word for word | Apache-2.0, attribution to the OHDSI CommonDataModel project | as above |
| `.../source/tables.json` | table and column names of the Synthea CSV files; the column descriptions are copied from `models/staging/synthea/_synthea__models.yml` of dbt-synthea (https://github.com/OHDSI/dbt-synthea) | Apache-2.0 | `LICENSE` of a local clone of dbt-synthea is the Apache License 2.0 |
| `.../matches/matches.json` | matches of source columns to target columns, derived from the SQL lineage of dbt-synthea (and made noisy on purpose where marked in the matcher) | Apache-2.0 (derived from dbt-synthea) | as above |
| `examples/synthea_omop/reference/recipes/`, `.../fields/` | the reference conversion, derived from the compiled SQL of dbt-synthea, split per table and column, with alignment data added by us. Modified from the original | Apache-2.0 (derived from dbt-synthea); modified | as above |
| `examples/synthea_omop/tools/*.py` | written for this project; they only read files that **you** supply | as the project code | |

Apache-2.0 requires that we keep the licence text and mark changes. The full text of the Apache License 2.0 is at http://www.apache.org/licenses/LICENSE-2.0 . The files above carry changes (reformatting, splitting, additions).
Python packages used (not included in this repository): duckdb (MIT), httpx (BSD-3), Jinja2 (BSD-3), jsonschema (MIT), PyYAML (MIT), sqlglot (MIT), pytz (MIT), pytest (MIT).

## Left out (unclear or restricted), and why

| item | why it is not here | what to do |
|---|---|---|
| Synthea sample data (the 18 Synthea tables and `states`, as CSV) | The Synthea software is Apache-2.0 (its README). A Synthea FAQ is said to call the generated data public domain, but we could not confirm that on a primary page (the FAQ and the downloads page could not be read in this session). The files also contain SNOMED CT, LOINC and RxNorm codes and display names, whose terminology licences the Synthea licence does not cover | copy the files from your own dbt-synthea clone with `examples/synthea_omop/tools/fill_source_data.py` |
| OMOP vocabulary seed files (`concept_seed`, `concept_relationship_seed`, `concept_ancestor_seed`, `vocabulary_seed`, ... 10 files) | They contain SNOMED CT (distributed under licence by SNOMED International), LOINC (terms of use to accept), RxNorm and other vocabulary content. OHDSI says the copyright of the OHDSI vocabularies excludes source codes and descriptions of other content owners, and some sources restrict their use. We found no clear statement that this content may be redistributed | same script (the files come with the dbt-synthea seeds; you are responsible for the terms of the vocabularies you copy) |
| Reference tables (`reference_data/*.csv`, the OMOP tables built by dbt-synthea) | built from the Synthea data and the vocabulary seeds above; they contain OMOP concept ids and source codes | run dbt-synthea yourself and export with `examples/synthea_omop/tools/export_reference.py` |
| Column profiles and dependencies of the source data (`source/profiles/`, `source/dependencies.json`) | they hold sample values and statistics of the left-out data | not needed: the tool computes the profiles itself |
| Run outputs of our experiments (prompts, answers, built tables) | prompts contain samples of the data above | not shared |

## TPC-DI benchmark (`benchmarks/tpcdi`)

Same rules as above. **Status of this section: written by the benchmark's authors, not legal advice; two items are unclear and are the reason this repository should stay private until they are settled.**

### Included

| item | source | licence | how checked |
|---|---|---|---|
| `benchmarks/tpcdi/` code (`pipeline/`, `fieldgen_run/`, `tpcdi/work/`, `gold_crosscheck/*.py`), docs, result files (graded JSON/CSV, generated SQL) | written for this project | as the project code | |
| `deliverables/ported_historical_load_v2.sql`, `ported_historical_load.sql` (gold SQL v2 / v1), `tpcdi/work/ported_historical_load.sql` | **derived from `historical_load.sql` of https://github.com/abroniewski/TPC-DI-MS-SQL-Benchmark** (ported to DuckDB; v2 repairs it against the specification) | **unclear: the repository has no licence file** | looked for LICENSE/COPYING: none. **Ask the author, or rebuild the gold from the specification, before this repository is public** |
| `gold_crosscheck/dbt_port.sql`, `normalize.sql` | derived from the dbt models of https://github.com/rlsalcido24/dbtpcdi (see `NOTICE`) | Apache-2.0 | `LICENSE.md` of that repository |
| `deliverables/tpcdi_spec_target_descriptions.json`, `FROZEN_PROMPT.json`, `tpcdi_column_mapping*.csv`, `tpcdi_transformations.csv` (excerpts: Clause 3.2 column descriptions, Clause 4.4.1/4.4.2 conventions, per-table rules) | excerpts and paraphrase of the TPC-DI specification v1.1.0, https://www.tpc.org/tpc_documents_current_versions/pdf/tpc-di_v1.1.0.pdf | **unclear: TPC document, freely downloadable; we did not find permission to excerpt** | `benchmarks/tpcdi/spec/SOURCE.md` records where it was fetched. Same action as above if the repository goes public |
| `deliverables/tpcdi_source_schema.sql`, `tpcdi_target_schema*.sql` | table and column definitions of TPC-DI | as the specification above | |

### Left out

| item | why it is not here | what to do |
|---|---|---|
| TPC-DI kit and DIGen (`tpcdi/tpcdi-kit`, `Tools/DIGen.jar`, PDGF) | governed by the TPC licence and the bankmark UG end-user licence (accepted interactively at first run, see `FINDINGS.md`); the kit clone has no licence file | obtain it from tpc.org and generate SF=3 yourself |
| Generated TPC-DI data, the DuckDB databases built from it, sandboxes | same licences; several GB | rebuild with `benchmarks/tpcdi/README.md` |
| `sample_data/` (excerpts of the generated files) | generated data, same licences | |
| Prompts and raw model calls (`pipeline/runs/**/prompts.json`, `fieldgen_run/rep1/run/calls.jsonl`) | they contain samples of the generated data | `run_v4.py --prompts-only` rebuilds the prompts |
| The specification PDF (`spec/tpc-di_v1.1.0.pdf`) | TPC document | download it (`spec/SOURCE.md`) |
| Third-party clones (`dbtpcdi`, `TPC-DI-MS-SQL-Benchmark`, `tpcdi-kit`) | their own repositories and licences | clone them next to `benchmarks/tpcdi/tpcdi/` |
