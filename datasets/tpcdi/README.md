# TPC-DI dataset (scale 3) for fieldgen

Source: the TPC-DI historical load (DIGen scale factor 3, Batch1). Target: 9 warehouse tables (DimDate, DimTime, StatusType, TaxRate, TradeType, Industry, DimBroker, DimCompany, DimCustomer).
The experiments in `results/` build **DimCustomer** (28 columns). **No TPC-DI data and no specification text is stored in this folder**; you fetch both and run four scripts.

## What you need

1. **The data.** Generate it with DIGen from tpc.org (https://www.tpc.org/tpcdi/, "TPC-DI tools", DIGen). Scale factor 3, for example `java -jar DIGen.jar -o OUT -sf 3`.
   You need the folder `OUT/Batch1` (Date.txt, Time.txt, HR.csv, Prospect.csv, CustomerMgmt.xml, FINWIRE*, ...).
2. **The schema repo** (pass the folder that contains `Helpers/` as `--repo`). The GitHub repository "TPC-DI-MS-SQL-Benchmark" (its README links the reference repository https://github.com/detobel36/tpc-di). `build_source.py` reads `Helpers/Scripts/schema.sql` and `Helpers/Datasets/CMP_Records_Schema.csv` from it; give the folder that holds `Helpers/`.
3. **The specification** (TPC-DI v1.1.0 PDF, tpc.org). `make_package.py` needs its text as one file: one text block per page, each page starting with a line `=====PAGE n=====`
   (extract with any PDF tool, e.g. pypdf: `"\n".join(f"=====PAGE {i+1}=====\n" + p.extract_text() for i, p in enumerate(PdfReader(f).pages))`).
   The script looks for the section headings 3.2.x and 4.5.x; if your extraction differs in layout it stops with a `KeyError` naming the heading it did not find.
   The text is read at run time and only used to write `target/field_docs.json` inside the work folder. Do not publish that file or the spec.
4. Python 3.10+ with `duckdb lxml` (and the fieldgen requirements) installed.

## The four commands (run in this order, from this folder; WORK is any empty folder)

```bash
python build_source.py  --data OUT/Batch1 --repo TPC-DI-MS-SQL-Benchmark-main --out WORK/source
python build_gold.py    --source-db WORK/source/tpcdi_source.duckdb --target-ddl WORK/source/target_ddl.sql --out WORK/gold
python build_history.py --source-db WORK/source/tpcdi_source.duckdb --out WORK/source_hist.duckdb
python make_package.py  --work WORK --spec spec_pages.txt
```

| script | what it does | takes about |
|---|---|---|
| `build_source.py` | loads the 19 source tables into `tpcdi_source.duckdb`; writes `source_ddl.sql`, `target_ddl.sql`, `results.json` | 15 s |
| `build_gold.py` | runs `gold_sql/*.sql` (spec rules applied; clause numbers in the headers) and writes `gold.duckdb` and `gold_csv/` | 3 s |
| `build_history.py` | one table `CustomerHistory` (one row per customer action, empty fields filled from the previous action) for run 10 | 3 s |
| `make_package.py` | `fieldgen init`, then keys, links, documentation (from the spec), matches (`column_map.csv`), expert text, config and the reference | 30 s |

Result: `WORK/packages/run6/{package,reference}` and `WORK/packages/run10/{package,reference}`; the `package` folder is what `fieldgen` reads, `reference` is read only by `fieldgen test`.
Our rebuild gives files identical to the ones used in the recorded runs (checked byte by byte for data, matches, links, keys, documentation, config; JSON compared as data).

## Expected row counts

| source table | rows | | gold table | rows |
|---|---|---|---|---|
| Date | 25933 | | DimDate | 25933 |
| Time | 86400 | | DimTime | 86400 |
| StatusType | 6 | | StatusType | 6 |
| TaxRate | 320 | | TaxRate | 320 |
| TradeType | 5 | | TradeType | 5 |
| Industry | 102 | | Industry | 102 |
| HR | 15000 | | DimBroker | 4293 |
| Prospect | 14982 | | DimCompany | 1096 |
| FinwireCMP | 1500 | | DimCustomer | 4728 |
| BatchDate | 1 | | | |
| ActionXML | 6440 (NEW 4728, UPDCUST 1284, INACT 428) | | | |
| CustomerXML | 6440 | | | |
| NameXML / AddressXML | 4728 / 6011 | | | |
| ContactInfoXML, C_PHONE_1/2/3_XML | 6012 each | | | |
| TaxInfoXML | 4728 | | | |

`CustomerHistory` (run 10): 6440 rows, 4728 customers. `build_gold.py` prints the gold counts and says if one differs.

## Files

- `gold_sql/` the nine SQL files of the reference (version B: the spec's rules applied). Headers name the clause numbers; the wording stays in the specification.
- `column_map.csv` which source columns feed each target column (no specification text); used for the package matches.
- `expert_text/` the generic expert text (`run6_flow_text.md`, `run10_flow_text.md`) and the package `config.yaml` of each run.
