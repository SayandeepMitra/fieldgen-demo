# Two benchmarks for fieldgen: Synthea → OMOP and TPC-DI

**fieldgen** is the project (a tool that writes SQL converting a source database into a target data model). Synthea → OMOP is its first example and benchmark
(`examples/synthea_omop`); **TPC-DI is a second benchmark for it** (this folder, `benchmarks/tpcdi`). This note compares the two benchmarks, then reports
fieldgen's first result on TPC-DI. Numbers for Synthea → OMOP are the ones fieldgen's own documents report (`docs/results.md`, `docs/config.md`); I read them but did not
re-run that side. Numbers for TPC-DI are ours. Where a comparison needs a number neither side measured, it says so.

## A. What each benchmark is

| | Synthea → OMOP (existing example) | TPC-DI (new benchmark) |
|---|---|---|
| What is shipped | an example package, a reference and the scorer (`fieldgen test`, levels L0–L4) | package builder, gold SQL (v2), graders (L1 per column, L2 per table), official audit, controls and per-column prompt baselines; fieldgen is the system under test |
| Task | write SQL that converts the source DB to the target DB, table by table | same; per column (L1) and per table (L2) |
| Source | Synthea sample data: 18 tables, **27 patients**, plus OMOP vocabulary seeds | DIGen SF=3: **31 `Source.*` tables, 4.6M rows** (trades, holdings, cash, finwire, customer-management XML) |
| Target | OMOP CDM v5.4, 39 tables; tool builds 19, **18 scored, 95 columns** | TPC-DI warehouse, 20 tables; **16 populated, 210 columns** |
| Reference | rebuilt from reference recipes (dbt-synthea derived) or exported from a dbt-synthea DuckDB; 26 tables | gold SQL (R1's `historical_load.sql`, ported) **repaired to v2**, validated by the official TPC-DI audit (89/89) and an independent dbt implementation |
| Reference is public? | yes (dbt-synthea, OHDSI docs) → contamination likely | yes (TPC-DI spec, several public ETLs) → contamination probed, not excluded |
| Matching | matches given (`matches.json`) | matches given (headline); matching-not-given is a planned variant |
| Models | Nemotron-120B in full; Ultra-550B recipe step only | fieldgen with Nemotron-120B (one run); per-column baselines with Nemotron-120B and Mistral-Large (L1 ×3 repeats) |

## B. How each one scores

| | Synthea → OMOP scoring (`fieldgen test`) | TPC-DI scoring (our L1/L2) |
|---|---|---|
| Row identity | `*_source_value` columns link target rows to source rows (`alignment.json`) | natural keys per table (`l2_grade.IDENTITY`), k-th-with-k-th pairing inside repeated keys (SCD versions) — the idea is fieldgen's, adapted |
| Cross-table keys | **out of scope** (tool numbers them itself; such columns excluded from scoring) | **in scope**: foreign surrogate keys translated through the referenced dimension to the entity (and its version) they point to |
| Headline | L2 = columns correct end to end (54/60 on the 12 tables with correct rows); tables with correct rows (12/18) | L1: columns exact, reported as **core 171 AND hard 37** (hard = what a name-matcher cannot do); L2: tables with correct rows + columns exact + constraint violations + official audit |
| Table-level correctness | "correct rows" (same ids, once each) | `rows_correct` (same row set, each once) + recall/precision + duplicates |
| Robustness | **L4**: same SQL on perturbed data (27/60 at L4 vs 54/60 at L2) | not yet (TODO: adopt L4) |
| Leak test | tests that the tool never opens the reference folder | L2 sandbox: candidate connection has no external access, only `Source.*` filled; reference opened by the grader afterwards |
| Controls | reference-recipe replay (92–93/95 with the correct recipe) | gold-as-pipeline (210/210 + audit 89/89), empty pipeline (0/210), L1↔L2 consistency, NULL-swap control per column, constant-mode and name-matcher baselines |
| Noise | "single tables move 0–3 of 5 with no change"; no repeat statistics beyond that | ±~4 net columns (temp-0 rerun and temp-0.7 spread agree), 3 repeats at temp 0.7 |
| Independent validity oracle | none for the reference beyond its construction | **official audit (89 checks) + dbtpcdi cross-check** |
| Contamination | not controlled (public data, public docs) | schema-only recall probe; trivial baselines; no clean control yet |

## C. fieldgen on TPC-DI: the system's first result

**What was run.** The fieldgen CLI as shipped (`init` → fill package → `generate`, recipe step + formula step) with Nemotron-3.5-super-120B through the NVIDIA
free endpoint (4 requests/min, concurrency 1). Code and prompts untouched; two mechanical overrides only (`fieldgen_run/run_fieldgen.py`): the 20 MB
source-CSV cap raised (our `Source.*` tables go to 74 MB) and `/proc/meminfo` served from `sysctl` on macOS.
Package (`fieldgen_run/build_package.py`): all 31 `Source.*` tables, the target DDL, the **given matching** as `matches.json`
(never `rule_sql`/lineage), spec Clause 3.2 descriptions as target `guidance`, and the Clause 4.4.1/4.4.2 history-tracking conventions
(same text as our frozen prompt v5a) as `domain_knowledge.md`. The gold SQL and any target data were never read.
Run: 383 calls (33 failed, 10 cut at the output limit), 1.42 M tokens in / 0.76 M out, ~2 h 20 min wall clock (rate-limit bound);
16/16 recipes valid, 204 of 205 formulas answered (`DimSecurity.IsCurrent`: "SELECT/FROM not allowed").
A second replicate was started and **stopped at 54/205 formulas after a network stall**, so run-to-run noise of fieldgen on TPC-DI is **not measured**.

**Results** (single run, graded by our L2 against **gold v2**; numbers are the same grader as every other TPC-DI L2 row):

| | fieldgen's SQL run in our L2 sandbox (Source-only, strict) | tables fieldgen built itself (`fieldgen_to_l2.py built`) |
|---|---|---|
| tables with correct rows | 9 / 16 | 10 / 16 |
| columns exact, all 210 | 88 | 103 |
| core (196) / hard (70) | 85 / 5 | 99 / 10 |
| official audit (Batch-1 applicable) | 34 / 78 ok | 41 / 89 ok |
| NOT NULL cells violated / dangling FK cells | 2.75 M / 0.86 M | 2.75 M / 0.86 M |

The two columns differ only in DimCompany: our sandbox runs fieldgen's SQL as emitted and it **fails** there (`strptime(FoundingDate,'%Y%m%d')` on an empty string
is an error in DuckDB, not a NULL), while fieldgen's own executor builds the table (1,500 rows, 14/20 columns exact). The strict number is the one comparable with
the other pipelines in this repository.

**Where it succeeds and where it does not** (per table, gold v2, strict sandbox run):

| table group | fieldgen | cause (read from the generated SQL) |
|---|---|---|
| DimDate, DimTime, StatusType, TaxRate, TradeType, Industry, Prospect | rows correct, 61/67 columns exact | single-source, conversion-only tables |
| DimBroker | 15,000 rows vs 4,293 | no filter to `EmployeeJobCode = 314` (a spec rule, not in the package) |
| DimCustomer / DimAccount / DimSecurity | 14,572 / 12,860 / 2,400 rows vs 6,440 / 16,110 / 3,147 | one row per source record: no per-day consolidation, no forward fill of updates |
| DimCompany | does not run (strict) | non-TRY date parse of `''` |
| FactCashBalances | 361,856 rows vs 330,461, 0/5 | net amount per day, not a running balance per account |
| Financial | 0/14, even rows match 0% | `SK_CompanyID = hash(CoNameOrCIK)`: foreign surrogate keys are not resolved through the dimension |
| DimTrade, FactHoldings | right row count (390,978 / 362,342), 10/21 and 4/11 columns | foreign SKs again; close keys |

**Against per-column baselines (gold v2, same grader, both on the given matching).** Our frozen-v5a L1 answers (one SQL expression per column, prompted with the
gold-derived scope) composed into whole tables by `l2_compose.py`: Nemotron **132/210** columns (core 129/196, hard 25/70), Mistral-Large **136/210** (131/196, 26/70),
14/16 tables with correct rows, official audit 65/78 and 64/78, 0 dangling foreign keys. fieldgen (strict): 88/210 (85/196, 5/70), 9/16 tables, audit 34/78, 0.86 M dangling
foreign-key cells. On the earlier v1 gold the same comparison was 78 vs 147/145 of 210.
These baselines are **not a competing system and not a fair target**: they are given the gold's table skeleton (row set, joins, grain), their prompt was tuned on the dev
columns (disclosed elsewhere), and the composer is ours. They show how far per-column prompting gets when the table structure is handed over; the distance to fieldgen is the
value of getting the recipe and the cross-table keys right on its own. The hard-column gap (5/70 vs 25–26/70) is the informative part: fieldgen's correct columns are almost
all ones a name-matcher could also get.

**What the run shows about transfer.** fieldgen's pieces work on a second domain without code changes: the package builder, the formula step and
its SQL guards (casts, alias rules) all ran; 100 % of recipes were valid. The failures cluster in the three places the tool's own docs mark as out of
scope or leave to the package: cross-table surrogate keys, history/SCD consolidation, and spec filter rules that live in prose.

## D. What each benchmark is good for, and what TPC-DI asks of fieldgen

**Synthea → OMOP is the better benchmark for**
- *Fast iteration*: 27 patients, 18 tables, 95 columns, minutes per run. TPC-DI is 4.6 M source rows and a ~2 h rate-limited run.
- *Robustness and leak checks that already exist*: **L4** (the same SQL on perturbed data, which catches hard-coded values) and the test that the tool never opens the reference folder.
- *A reference built the way the tool consumes it* (recipes and fields with `*_source_value` alignment), so `fieldgen test` works without any adapter.

**TPC-DI is the better benchmark for**
- *Validity of the reference*: gold v2 passes the official 89-check audit and agrees with an independent dbt implementation on all key sets (131/148 columns identical, the rest traced). Synthea → OMOP's reference is its construction (dbt-synthea), with no independent oracle that I saw.
- *What the Synthea scoring leaves out*: cross-table surrogate keys and SCD2 versions are scored here, and they are where fieldgen loses most of its columns.
- *Measured difficulty*: core and hard sets, a name-matcher baseline (126/196 core, 70 hard it cannot do), constant-mode, NULL-swap and gold-as-pipeline controls, noise from repeats, constraint counts.
- *Semantics that live in a specification*: filters, ordering, versioning and consolidation rules, so a pipeline that only converts types cannot pass.

**Both share** public references (contamination possible), matching given for the headline, and Nemotron as the main model. Neither has a contamination-clean control.

**What the first TPC-DI run asks of fieldgen** (from the generated SQL, section C): (1) resolve foreign surrogate keys through the dimension they point to (fieldgen's docs declare this out of scope; here it costs most of Financial, DimTrade and FactHoldings);
(2) consolidate history (one row per entity and day, forward-fill updates) for the SCD2 dimensions; (3) carry spec filter rules that live in prose (DimBroker's job-code filter) into the package's domain knowledge; (4) guard date parsing (`strptime` of `''` made DimCompany fail in strict DuckDB; a `TRY_` form would have given NULL).

**Next steps inside fieldgen.** (1) Export gold v2 in fieldgen's reference format so `fieldgen test`, **L4** and the leak test apply to TPC-DI natively, instead of our own L2 only. (2) Add the spec filter rules and a key-resolution hint to the TPC-DI package and rerun, to separate "what the tool can do" from "what the package knows". (3) Run the second replicate to get fieldgen's noise on TPC-DI.
