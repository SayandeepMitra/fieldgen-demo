# PROGRESS (living file: update after every milestone; details in project_plan.md §5)
_Last updated: 2026-11-06 (gold v2 repaired; fieldgen-on-TPC-DI done; L1 re-baseline on v2 done)_

## Where we are (TPC-DI, expression-level swap-in, matching given)
| Item | State |
|---|---|
| Gold v1 (R1 `historical_load.sql` → DuckDB) | 72/89 official audit checks; 17 failing + 9 untested defects. **All numbers below the "v1 gold" label were produced against it.** |
| **Gold v2 (repaired, 2026-11-06)** | `ported_historical_load_v2.sql`: **89/89** audit, 30/30 own invariants, cross-checked vs independent `dbtpcdi` port (identical keys on 9 tables, 131/148 columns; the 17 others = 1 v2 bug, fixed, + dbt deviations). Change log `deliverables/GOLD_V2_CHANGES.md`. Select with `TPCDI_GOLD=v2` (default still v1 until re-baseline is done). L2 gold-as-pipeline on v2: 210/210, audit 89/89. |
| Clean subset | 210 cols → clean 147, clean_column 22, fk_entity_only 2, weak 11, audit_flagged 11, known_defect 17. **Core = 171** (`tpcdi_clean_subset.csv`) |
| Dev/test split | Frozen (`tpcdi_split.csv`). DIGen cannot give held-out data (seed has no effect). Protects *future* changes only. |
| Frozen prompt | **v5a** = v4 + spec 4.4.1/4.4.2 conventions (`deliverables/FROZEN_PROMPT.json`). v4 = untuned baseline. v5a tuned after seeing all 210 cols → its test score is not independent. |
| Noise floor | ±~4 net columns (temp-0 rerun and temp-0.7 spread agree) |

## Headline numbers (exact cols on core 171; Mistral-L4 / Nemotron-120B)
| Run | Mistral | Nemotron |
|---|---|---|
| v4 | 147 | 144 |
| v5a t=0 | 153 | 152 |
| v5a t=0.7 ×3, mean (range) | 153.0 (150–157) | 150.3 (149–152) |
| Trivial name-matcher (no LLM) | 134 | 134 |
| Constant-mode baseline | 14 | 14 |
| **Hard 37** (trivial fails: constants, SKs, SCD, conditionals) | 28–29 | 29–32 |

Contamination probe (schema-only matching): Nemotron 123/152, Mistral 126/155 vs name matcher 94/155; no sign of benchmark-specific recall, but cannot separate memorisation from inference.
**Report on hard-37 AND core-171, never 171 alone.**

## L2 end-to-end grader (built 2026-11-06; `pipeline/L2_README.md`)
Sandbox (Source.* only) -> per-table SQL -> natural-key row identity, FK SKs compared as entities, constraint + official-audit counts. Controls: gold-as-pipeline 210/210 + audit 72/89; empty 0/210; L1↔L2 consistent on 17/18 columns.
First use (L1 answers composed into tables, not LLM-written pipelines): core171 **L1 → L2: Mistral 153 → 125, Nemotron 152 → 122**; hard-37 ≈30 → 20. Errors cascade (DimCompany dates → DimSecurity 0 rows, Financial 0% recall). **L1 overstates end-to-end correctness by ~28 core columns.**

## v2 gold: what is done / not done
- Clean subset v2: **196 clean + 14 weak, 0 known_defect** (v1: 171 core). Name-matcher baseline on v2: 126/196 core, **70 hard** (v1: 37 hard), constant-mode 14.
- Prompt scope text changed for 102/210 columns (DimCustomer, DimAccount, DimSecurity, DimTrade, FactCashBalances, FactHoldings + 5 others); 108 keep their v1 answers (`transplant_v1_to_v2.py`) and are regraded on v2.
- Regraded unchanged answers (temp 0, 108 columns): Mistral 101→100, Nemotron 103→100 exact; the losses are DimCompany.Country/SPrating/AddressLine2 (v1 gold rewarded passing blanks / invalid ratings through; spec 4.5.3 says NULL).
- **L1 re-baseline on v2 is done** (`score_clean.py`, now gold-aware; core = 196 columns, hard = 70 the name-matcher cannot do; name-matcher itself 126/196):

  | condition | Nemotron core / hard | Mistral-Large core / hard |
  |---|---|---|
  | v4 baseline, t=0 | 150 / 25 | 144 / 18 |
  | **v5a frozen, t=0** | **158 / 33** | **156 / 30** |
  | v5a, t=0.7 ×3 (mean, range) | 157.3 (156–158) / 32.7 | 154.0 (151–157) / 29.7 |

  v5a still beats v4 by +8 / +12 core. Not comparable with the v1 numbers (152/171, 153/171): the core grew 171 → 196 and the hard set 37 → 70. Tuned-on-dev disclosure unchanged. Default `TPCDI_GOLD` is now **v2** (`=v1` reproduces old results).
- **Controls on v2 (done):** gold-as-pipeline 210/210; empty pipeline 0/210; L1↔L2 consistency 14/14 plain columns agree. **Contamination probe on v2:** schema-only field-set recall, models 113/121 (Nemotron) and 114/123 (Mistral) vs name matcher 86/123 (v1: 123/152, 126/155 vs 94/155) — same gap; fewer columns scorable (123 vs 155) because v2 gold uses derived relations. Still no clean (non-public) control.
- **Project framing:** fieldgen is the project; TPC-DI is a benchmark inside it (next to Synthea→OMOP). Roadmap (slides' 4 stages): 1 ground truth done for TPC-DI; 2 query synthesis = fieldgen (first run below, untuned); 3 equivalence check done on our L1/L2 (not yet via fieldgen's own `fieldgen test`/L4/leak test); 4 reverse execution not started. See `docs/project_plan.md` §2.
- **fieldgen on TPC-DI = the system's first result (rep 1, gold v2, strict L2):** 9/16 tables correct, 88/210 columns (core 85/196, hard 5/70), audit 34/78; its own executor 103/210. Baseline (per-column v5a answers composed on the gold skeleton, not a competing tool): Nemotron 132/210, Mistral 136/210 (14/16 tables, audit 65/78 and 64/78). Failures = foreign SKs, SCD consolidation, spec filters, DimCompany date parse. Details: `BENCHMARKS_synthea_omop_vs_tpcdi.md` §C–D; files `benchmark/fieldgen_run/`.

## Corrections on record
- Gold has **0** NULLs in the 150 spec "Not NULL" columns (earlier NULL-vs-spec "defect" claim retracted).
- Synthea→OMOP is **not** a clean contamination control: dbt-synthea and OMOP docs are public (see fieldgen review). MIMIC / a private schema is better.

## TODO (priority order)
1. [x] L2 grader built + validated
1b. [ ] LLM-written end-to-end pipeline harness (prompt: all tables from Source.* schema + data profile; matching given/not) → run through `l2_run.py`; 3 repeats
2. [ ] Share fieldgen review with team; add its L4 perturbation + leak test to L2
3. [ ] Repair gold (DimTrade trade grain, DimAccount, F10–F12) → re-baseline everything vs new gold
4. [ ] Fresh Claude agent rerun on frozen v5a (unbiased check)
5. [ ] Scale replication at SF≥6 (superset of SF3 rows)
6. [ ] Matching-not-given and scope-not-shown variants (L1b)
7. [ ] Held-out dataset with no public ETL (MIMIC or private) → true test; laguna / more models optional
8. [ ] Update FINDINGS.md with §5.3–5.4 results

## Key paths
`pipeline/`: `run_v4.py` (runner), `grade_run.py`, `score_clean.py RUN[,RUN…] [--base B]`, `compare_runs.py`, `baseline_trivial.py`, `contam_probe.py`, `gold_audit.py`, `build_clean_subset.py`, `make_split.py`; runs in `runs/` (`ab_*` ablation, `frozen_v5a_t07`). Only ONE NVIDIA-key process at a time (40 RPM shared).
