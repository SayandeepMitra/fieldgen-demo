# Setup for this folder (added by the project submission; the other files are as in fieldgen-demo v1.2-demo)

The package is shipped as in fieldgen-demo, under the same terms (`LICENSES.md` in the project root; items it lists under "Left out" are NOT here).
The Synthea sample data, the vocabulary seeds and the reference tables are not included, so you add them once. Run from the project root:

1. Get dbt-synthea (Apache-2.0): `git clone https://github.com/OHDSI/dbt-synthea` (it carries the Synthea sample data and vocabulary seeds). You are responsible for the terms of the data you copy.
2. Source data: `python datasets/synthea_omop/tools/fill_source_data.py /path/to/dbt-synthea` writes 29 CSV files into `package/source/data/` and checks the row counts.
3. Reference tables (needed for the exact scores in `results/RESULTS.md`): build dbt-synthea (`dbt seed`, `dbt run`; see its README), then
   `python datasets/synthea_omop/tools/export_reference.py /path/to/dbt-synthea/synthea_omop_etl.duckdb` writes `reference/reference_data/*.csv`.
   Without this step `fieldgen test` builds the reference from the reference recipes; it differs from the dbt tables in part of the tables, so the scores can differ.
4. Check: `python run_demo.py --dataset synthea` (replay, no key) should print 13 of 18 tables and 57 L2 columns.

Paths in `README.md` and `LICENSES.md` of the demo say `examples/synthea_omop/...`; in this project that folder is `datasets/synthea_omop/`.
