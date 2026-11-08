# L2 grader: table-level, end-to-end (TPC-DI)

L1 (`grade_swap.py`) swaps ONE expression into the gold query and asks if that column is right. L2 asks the question a
pipeline author cares about: **run the pipeline's SQL from `Source.*` alone; are the tables it builds right?**

## Submission
A directory with one file per target table, `<Table>.sql`: either one `SELECT`/`WITH` query (its output columns loaded by name)
or any SQL script (own `INSERT INTO <Table> ...`, `TEMP` helpers). Optional `order.txt` = execution order (default: gold order,
dimensions before facts). A later table may read earlier *target* tables and any `Source.*` table.

```
python l2_run.py SUBMISSION_DIR --name NAME [--audit] [--timeout 900] [--constraints off|strict]
python l2_grade.py --cand runs/l2/NAME/sandbox.duckdb --out runs/l2/NAME      # re-grade only
```
Outputs in `runs/l2/NAME/`: `l2_exec.json` (L0: per-table status/rows/seconds), `l2_scores.json`, `l2_report.md`, `audit.csv` (with `--audit`).

## Sandbox (what the candidate can see)
Copy of the benchmark DB with **only `Source.*` filled** and empty target tables (declared types). `--constraints off` (default) drops
NOT NULL/PK/FK/CHECK so one bad column does not discard the table; violations are counted separately
(`not_null_cells`, `dangling_fk_cells`). `strict` enforces them at load. External access is disabled on the candidate connection (no
`ATTACH` of the reference, no file reads), per-table timeout, reference opened only by the grader afterwards.

## Row identity (the fieldgen idea, adapted)
Candidate and reference rows are matched on the **natural key** (`l2_grade.IDENTITY`), never on surrogate numbers:
DimCustomer = CustomerID, DimAccount = AccountID, DimSecurity = Symbol, DimCompany = CompanyID, DimBroker = BrokerID, DimTrade = TradeID,
FactCashBalances = (account, date), FactHoldings = (TradeID, CurrentTradeID), Financial = (company, year, quarter), Prospect = AgencyID, ...
- **Several rows per identity** (SCD2 versions, a trade's events): paired k-th with k-th, ordered by `VERSION_ORDER` (e.g. EffectiveDate)
  then the whole row. A wrong EffectiveDate therefore costs that column, not the table.
- **Foreign surrogate keys are translated, on each side through its own dimension, to the natural key of the entity they point to**
  ("right = same entity"). A table's own generated SK is only checked for unique + not NULL. Number-for-number SK equality is never required.

## What is reported (per table, then headline)
| level | meaning |
|---|---|
| L0 | the SQL ran (status, rows, seconds) |
| L1 rows | recall, precision, repeated identities, `rows_correct` (same row set, each once) |
| L2 columns | `pct_ref` = agreement over ALL reference rows (missing rows count wrong); `pct_matched` = over matched rows. Exact = pct_ref >= 99.995 |
| constraints | NULLs in declared NOT NULL columns; FK SKs pointing at no dimension row |
| audit | `--audit`: the official TPC-DI `tpcdi_audit.sql` on the candidate (Batch-1 applicable checks) |
Headline: tables with correct rows (13 "sound-reference" tables; DimAccount/DimTrade/FactHoldings have a defective gold grain, reported but not in the headline),
columns exact over all 210 / core 171 / hard 37 (same column sets as L1, so L1 and L2 numbers are directly comparable).
Empty gold tables (FactMarketHistory, FactWatches, ...) are not graded.

## Validation (run before trusting a number; `l2_controls.py`, results in `runs/l2/ctrl_results.json`)
- **C1 gold-as-pipeline**: the gold's own table SQL run from scratch in the sandbox: 16/16 tables, 210/210 columns exact, 0 constraint violations, official audit 72/89 (identical to auditing the gold).
- **C2 empty pipeline**: every table missing, 0/210.
- **C3 L1 <-> L2 consistency**: an LLM expression put into the gold's table query and run through the L2 path scores the same as its L1 match_pct (see report).
- `l2_compose.py RUN MODEL`: composes one model's L1 answers into whole tables (not a model-written pipeline; shows how per-column L1 scores translate into end-to-end results).

## Known limits
- The reference is R1's gold: 17 audit failures remain (DimTrade event grain etc.). Tables with a defective grain are flagged, not hidden.
- Identity choices are ours (`IDENTITY`); `l2_controls.py` C1/C3 are the guard that they are consistent with L1.
- Comparison is text-normalised (trim, lower-case) like L1; types already agree because the sandbox targets carry the declared types.
- Batch-1 historical load only; incremental batches are not exercised.
