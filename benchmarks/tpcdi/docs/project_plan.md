> **Framing (2026-11):** fieldgen is the name of the project; TPC-DI is a benchmark used inside it, next to Synthea→OMOP. This plan predates that framing and says "we"/"the pipeline" for the query generator; read that as fieldgen plus the per-column prompt baselines.

# Project Plan — Database Transformation for a Target Schema

Living plan. Update the status column as tasks close instead of rewriting this file from
scratch. Detailed run-by-run notes stay in `benchmark/FINDINGS.md`; this file tracks the
*shape* of the project and where we are in it.

## 1. The actual research goal

Build a system that, given a source database `D` (schema `S`) and a target schema `S′`
describing the *same* real-world entities, automatically generates a query `Q` per target
table `T′` such that `Q(D)` correctly populates `T′` — and can verify that `Q` is correct.

## 2. The four-stage pipeline (from `Course_Projects-23-33.pdf`)

| # | Stage | What it does | Status |
|---|---|---|---|
| 0 | **Benchmark sourcing** *(not one of the official 4, but a hard prerequisite)* | Find/prepare real `(S, D, T, transformation)` examples to build and test against | **In progress** — see §3 |
| 1 | Ground Truth Generation | Given `S`, use a strong model (or, for real benchmarks, an existing human-written transformation) to get `S′` + ground-truth queries `{Q̂}` | **Done for one benchmark** (TPC-DI SF3, real target, gold v2 repaired + audited); no second benchmark / no LLM-generated `S′` |
| 2 | Query Synthesis (= **fieldgen**, the project) | Given `D, S, S′`, generate candidate queries `{Q}` (this is the actual system under development) | **fieldgen run once on TPC-DI** (untuned, 88/210); per-column L1 prompts (matching given, 2 free models) serve as baselines. No matching-not-given variant yet |
| 3 | Equivalence Check | Test `{Q} ≡ {Q̂}` via execution similarity | **Done on our graders** (L1 swap-in, L2 table-level, official audit, controls); not yet via fieldgen's own `fieldgen test` / L4 / leak test (needs gold v2 exported in fieldgen's reference format) |
| 4 | Reverse Execution | On recoverable examples, invert `D′ → S` and measure distance from original `D` | **Not started** |

Stages 1–4 can't start until Stage 0 delivers at least one usable benchmark example (all four
of `S`, `D`, `T`, transformation present). That is the entire current focus.

## 3. Stage 0 — Benchmark sourcing status

Two candidates are being evaluated in parallel per `files/benchmark_evaluation.pdf`:
**TPC-DI** (financial, currently active) and **MIMIC-IV → OMOP** (hospital, not started).

Decision rule once a benchmark is classified (Task A3 / B4):

| Plain-copy % | Verdict |
|---|---|
| < 30% (and tables read from 2+ sources) | Excellent — use it |
| 30–70% | Usable — select an interesting subset of tables |
| > 70% | Too easy alone — combine with another source |
| Blocked by registration/licensing | Report it, supervisor decides |

### 3a. TPC-DI

| Task | What | Status | Notes |
|---|---|---|---|
| **A1** | Clone repo(s), survey contents | **Done** (R1 only) | `benchmark/tpcdi/TPC-DI-MS-SQL-Benchmark/`. Full findings in `benchmark/FINDINGS.md`. |
| **A2** | Read the source schema file, confirm it gives us `S` | **Done** | Correction to the original doc: `CreateDBTableSchema.sql` is actually a second copy of `T`, not `S`. The real `S` (31 `Source.*` tables) is in `Helpers/Scripts/schema.sql`, fully tabulated in FINDINGS.md. Standalone portable `tpcdi_source_schema.sql` extraction + DuckDB load test deferred to A5 (mechanical, low-risk, grouped with the other DuckDB load check). |
| **A3** | Classify every transformation column (copy/rename/retype/.../SCD history/constant) for `DimCustomer`, `DimAccount`, `FactMarketHistory` | **Done** | `DimCustomer` (33 cols) and `DimAccount` (11 cols) fully classified from live SQL. **`FactMarketHistory` (14 cols) turned out to be commented-out/abandoned in R1** — classified anyway from the dead code, flagged `NOT IMPLEMENTED` per row. Deliverable: `benchmark/deliverables/tpcdi_transformations.csv`. Plain-copy rate on this 3-table sample: 10.3% (or 37.9% if `rename` is folded in) — materially more complex than the doc's whole-schema 60/40 estimate, explained in FINDINGS.md as a sample-selection effect (these 3 tables were deliberately the hard ones), not a contradiction. |
| **A4** | Determine whether `D` can be generated without registering with TPC | **Done — `D` generated successfully** | R2 bundles the real `DIGen.jar` v1.1.0 + PDGF framework in `Tools.zip`; no tpc.org registration needed. User reviewed and approved: (1) using this bundled copy, (2) accepting PDGF's own end-user licence (bankmark UG — separate from TPC's). Technical hurdles hit and fixed along the way: jar-in-jar classloader failure (worked around with an explicit classpath), PDGF requiring an actual Java 8 JVM (user installed `temurin@8` via Homebrew, needed their own sudo), Apple Silicon incompatibility (fixed with `softwareupdate --install-rosetta`, no sudo needed), and a console-flooding bug from closing stdin too early (fixed by keeping the input pipe open). **Result: SF=3 dataset generated, 4,579,717 rows across 3 batches, 267.1 MiB**, structurally cross-checked against the `S` tables from A2 (`Trade.txt`, `Customer.txt`, `CustomerMgmt.xml` all match). Full data at `benchmark/tpcdi/tpcdi-kit/staging/3/`; a 108 KB representative sample at `benchmark/sample_data/tpcdi_sf3/`. |
| **A5** | Load `tpcdi_target_schema.sql` (`T`) into DuckDB, confirm 20 tables; also extract + load the new `tpcdi_source_schema.sql` (`S`) | **Done** | Extracted `tpcdi_source_schema.sql` (31 tables) from `schema.sql`'s `Source.*` block via a paren-aware parser, with dialect fixes (`NVARCHAR→VARCHAR`, `DATETIME→TIMESTAMP`, trailing commas stripped). Both `S` (31 tables) and `T` (20 tables) load cleanly into DuckDB — 51 tables total, matching every count from A2/the doc exactly. **Bonus:** loaded 3 of the SF=3 generated `D` files (`Trade.txt`, `HR.csv`, `DailyMarket.txt` — ~1.7M rows combined) straight into the extracted `S` tables with no casting/reordering needed — genuine proof `S` and `D` are a matched, consistent pair, not just independently plausible. Corrected an A2 counting error along the way (31 source tables, not 30). |

**Current verdict: Stage 0 for TPC-DI is complete.** All four pieces (`S`, `D`, `T`,
transformation) are in hand, portable, and cross-validated against each other — deliverables at
`benchmark/deliverables/` (`tpcdi_source_schema.sql`, `tpcdi_target_schema.sql`,
`tpcdi_transformations.csv`, `load_schemas.py`, `tpcdi.duckdb`) and `benchmark/sample_data/`.
`FactMarketHistory` remains the one known gap in the transformation (R1 abandoned it mid-write;
R3/`dbtpcdi` has a working reference implementation if needed later, not yet ported) — worth
noting in the final report per the doc's "negative findings are results" guidance, but not a
blocker for adopting TPC-DI as a benchmark.

**Next decision point (not yet started): the A3/B4 "deciding task" outcome.** On our 3-table
TPC-DI sample, plain-copy rate was ~10% (or ~38% folding in `rename`) — well under the doc's
<30% "excellent" threshold, suggesting TPC-DI is a strong benchmark candidate. But that sample
was deliberately the hard tables; the doc's §4.2 questions want this measured across the *whole*
20-table warehouse before a final verdict, and MIMIC (B1–B5) hasn't been started at all yet for
comparison.

### 3b. MIMIC-IV → OMOP

| Task | What | Status |
|---|---|---|
| B1 | Clone `mimic-iv-demo-omop`, survey `.sql`/`.md` files | Not started |
| B2 | Locate and download `D` from PhysioNet demo subset; check OMOP vocabulary requirement | Not started |
| B3 | Sort files into `S` / `T` / transformation / helper buckets | Not started |
| B4 | Classify transformations for `person`, `visit_occurrence`, `measurement` (+ vocabulary-lookup category) | Not started — **deciding task for MIMIC** |
| B5 (optional) | Try running the conversion end to end | Not started |

Not being worked yet — TPC-DI is the current priority per direction.

### 3c. Deliverables checklist (from the evaluation doc, §4.1)

| # | File | From task | Status |
|---|---|---|---|
| 1 | `benchmark/FINDINGS.md` | all | **In progress**, being kept current |
| 2 | `benchmark/deliverables/tpcdi_transformations.csv` | A3 | **Done** (58 rows across 3 tables) |
| 3 | `mimic_transformations.csv` | B4 | Not started |
| 4 | `benchmark/deliverables/tpcdi_source_schema.sql` | A2/A5 | **Done** (31 tables, DuckDB-verified) |
| 5 | `benchmark/sample_data/tpcdi_sf3/` | A4, B2 | **Done for TPC-DI** (108 KB); MIMIC half (B2) not started |

## 4. Known open questions / blockers

- **D for TPC-DI**: official generator requires TPC registration + licence agreement — a
  licensing decision, not ours to make unilaterally if it comes to that. Task A4 will tell us
  whether a no-registration alternative (R2, R4) actually works.
- **MIMIC-III vs MIMIC-IV-demo**: MIMIC-III needs credentialing (ethics course + application,
  weeks-long) — explicitly deferred. Only the open MIMIC-IV demo subset is in scope for now.
- **OMOP vocabulary size**: large reference table, free-account gated (athena.ohdsi.org) —
  account decision sits with supervisor, to be confirmed in Task B2 if/when we get there.
- **R2–R5 (TPC-DI) unopened**: everything the evaluation doc says about them is an unverified
  expectation from README text, same caveat the doc itself flags.

## 5. Revised plan (supersedes the old "immediate next step") — as of 2026-10-02

Trigger: the user supplied `column_mapping_flagged.csv` — a column-level ground-truth mapping
for an existing **Synthea → OMOP** dbt pipeline (432 rows, 39 tables). This is the format Stage 1
("Ground Truth Generation") is actually supposed to produce, and it's far richer than our
`tpcdi_transformations.csv` (which only has `category` + a free-text snippet for 58 of 241
columns). The plan below formalizes TPC-DI's ground truth in that same structured format, then
moves into the real system: LLM-based query synthesis against `S`/`S′`, graded against that
formalized ground truth.

### 5.1 What `column_mapping_flagged.csv` actually is (reverse-engineered from the file itself)

One row per **target column**, 17 fields:
`target_table, target_column, target_type, table_status, producing_models, source_tables,
value_columns, key_columns, joins, rule_sql, combination, lineage_path, column_kind, notes,
rule_reliable, rule_issue, table_caution`.

Measured distributions (432 rows / 39 OMOP tables):

| Field | Values (count) |
|---|---|
| `table_status` | populated 278, empty_stub 82, vocabulary_passthrough 46, empty_due_to_empty_seed 15, not_built 11 |
| `column_kind` | null_placeholder 175, passthrough_copy 112, value 51, copies_generated_key 36, constant 30, generated_key 17 |
| `combination` | none 350, union_all 55, union_distinct 7, case 6, union_all+case 3 |
| `rule_reliable` | yes 268, n/a 154 (constants/placeholders), **no 10** |
| `table_caution` | yes 20 (flagged tables), blank 412 |

The 10 `rule_reliable=no` rows are explicitly flagged as **non-deterministic** — e.g.
`visit_occurrence.visit_occurrence_id`'s note: *"ROW_NUMBER... TIES in reference (largest tie
group 64 rows): tied rows get an arbitrary order... observed UNSTABLE across two rebuilds."*
This is the critical design insight: **surrogate/generated keys can't be checked by literal
value equality** — the mapping format exists precisely so an equivalence checker knows, per
column, whether to compare values directly (`value`, `passthrough_copy`, `constant`) or compare
*structurally* (`generated_key`, `copies_generated_key` — check relational consistency, not the
literal number).

### 5.2 Phase A — Build `tpcdi_column_mapping.csv` (the TPC-DI equivalent)

Same 17-column schema, scoped to TPC-DI's 20 tables / 241 columns (vs. OMOP's 432/39 — a much
smaller, fully-tractable task). `producing_models` has no dbt equivalent for TPC-DI — repurpose
that field for the CTE name inside `historical_load.sql` that produces the column (TPC-DI has no
model layering, just one script with CTEs).

**New research done while planning this** (full read of `historical_load.sql`'s remaining ~550
lines not covered by Task A3's 3-table sample) — gives the `table_status` column for all 20
tables up front, numbers below are exact column counts from `tpcdi_target_schema.sql` (sums to
241):

| Status | Tables | Columns |
|---|---|---|
| **Reliable, fully populated** | `DimDate`(18), `DimTime`(10), `StatusType`(2), `TaxRate`(3), `TradeType`(4), `Industry`(3), `DimBroker`(13), `DimCompany`(20), `DimCustomer`(33), `DimAccount`(11), `Financial`(14) | **131** |
| **Populated but flagged** (author's own TODO/FIXME comments, or a real bug) | `DimSecurity`(15, varchar-join TODO), `DimTrade`(21, **5 FK surrogate columns hardcoded to literal `1`** — `SK_BrokerID`/`SK_SecurityID`/`SK_CompanyID`/`SK_CustomerID`/`SK_AccountID` all have a `-- FIX SK` comment, never actually looked up), `FactCashBalances`(5, no running balance, TODO), `FactHoldings`(11, author questions own `CurrentPrice` choice), `Prospect`(27, `IsCustomer` is declared `BOOLEAN` but the query returns `COUNT(*)` — a real type-mismatch bug) | **79** |
| **Not built at all** | `FactMarketHistory`(14, fully commented out), `FactWatches`(5, fully commented out), `DImessages`(6, only a `-- TODO` comment, no code), `AuditTable`(6, populated by a separate audit process, not this ETL) | **31** |

This means our *actual*, whole-schema-honest reliability picture is **54.4% fully reliable /
32.8% populated-but-flagged / 12.9% not built** — a cleaner three-way split than the doc's
original 60/40 copy/complex framing, and directly comparable to the OMOP example's own
`table_status` spread (which also has real `not_built`/`empty_stub` tables — TPC-DI isn't
uniquely incomplete, every real transformation example has gaps; the point is to *record* them,
not hide them).

**How to build it:** semi-automated, not fully scripted — a regex/paren-aware parser (reusing
the technique from Tasks A2/A5) can mechanically pull each INSERT block's column list + raw
expression text and the `Source.*`/`dbo.*` identifiers it touches (`source_tables`,
`value_columns`, `joins` columns), but `column_kind`, `rule_reliable`, `rule_issue`, and
`lineage_path` need a human/LLM pass per table — exactly the close-reading work already done
manually for `DimCustomer`/`DimAccount`/`FactMarketHistory` in Task A3, now extended to the
other 17 tables using the findings above as a head start.

**Deliverable:** `benchmark/deliverables/tpcdi_column_mapping.csv`, 241 rows. This **replaces**
`tpcdi_transformations.csv` as the authoritative mapping (that file stays as an A3-era artifact,
superseded, not deleted).

### 5.3 Phase B — Execute the ground truth for real rows

Unchanged from the previous plan version: port `historical_load.sql`'s dialect to DuckDB
(`GO` splitting, `IDENTITY`→explicit surrogate-key generation, `TOP n`→`LIMIT n`, bracketed
identifiers, string `+`→`||` — full list already in chat history/FINDINGS), fully load all 31
`Source.*` tables from the generated `D` (currently only 3 of 31 are loaded), and run it. Produces
real `{Q̂}(D)` rows for the 16 reliable-or-flagged tables; the 4 not-built tables stay empty
(expected, documented in Phase A's mapping, not a bug in our work).

Phase A and Phase B are complementary, not sequential — Phase A's per-column `rule_sql` extraction
*is* most of the work needed for Phase B's port, so they should be done together, table by table.

### 5.4 Phase C — LLM-based query synthesis (Stage 2 proper) — detailed design, 2026-10-03

Revised and made concrete, per direction. Scope decision up front: **schema matching is assumed
solved and given to the model** (i.e. which source table(s)/column(s) feed a given target
column — the `source_tables`/`value_columns`/`key_columns`/`joins` fields of
`tpcdi_column_mapping.csv`). **The LLM's job is only to find the transformation** — the actual
SQL expression/rule — not to discover correspondences. This narrows Stage 2 from "schema
matching + rule synthesis" down to just "rule synthesis given a resolved match," which is both
more tractable and more realistic as a controlled experiment (it isolates transformation-writing
skill from schema-matching skill).

**Models: 3-way comparison.**
- **NVIDIA Nemotron** (e.g. `Llama-3.1-Nemotron-70B-Instruct` or the newer
  `Llama-3.3-Nemotron-Super-49B`, both openly released) — reachable without local GPU hosting via
  NVIDIA's free NIM API (build.nvidia.com) or Hugging Face Inference. Given our hardware (16 GB
  unified memory, no dedicated GPU — see the earlier hardware-requirements discussion), API access
  is the practical route, not local hosting.
- **Two other open-weight LLMs**, run through the identical prompts/harness for comparison.
  Reasonable candidates: **Llama 3.3 70B** and **Qwen 2.5 72B** (or DeepSeek-V3) — picking the
  exact two is an open decision, not locked in here; any should be reachable via the same kind of
  free/low-cost inference API (Together AI, Fireworks, OpenRouter, Groq) to avoid local hosting
  entirely, matching the Nemotron access plan.

**Answering the clarification: how field-by-field prompting handles multi-source-column
matches.** "Field by field" means one **target** column per call, not one **source** column per
call — the resolved match for a single target column can (and often does) span multiple source
tables, already captured in `tpcdi_column_mapping.csv`'s `source_tables`/`value_columns`/
`key_columns`/`joins` fields (e.g. `DimCustomer.NationalTaxRateDesc` matches to
`Source.TaxInfoXML.C_NAT_TX_ID` joined through `Source.TaxRate.TX_NAME` — two tables, one join,
one target column). The LLM is handed that pre-resolved match and only has to write the
expression combining it — it never has to (re)discover a join.

**Refinement to avoid redundant/inconsistent joins within one table.** Problem: several columns
of the same target table typically share one join context (all 33 `DimCustomer` columns come
from the same 9-table join). Resolving that shared context independently, 33 separate times,
risks the LLM reconstructing 33 slightly different (and possibly inconsistent) `FROM`/`JOIN`
clauses. Fix — a **two-level prompting strategy**:
1. **Table level (once per target table):** derive the shared `FROM`/`JOIN` skeleton directly
   from the matching metadata (`source_tables` + `joins` columns already list every table and
   join condition involved) — this step is close to mechanical, possibly not even needing an LLM
   call, since the join graph is already fully specified by the (given) matching.
2. **Column level ("field by field," the actual LLM-synthesis step):** for each target column,
   given the shared skeleton from step 1 + that column's own matched source field(s) + the inputs
   below, ask only for the `SELECT`-list expression — never the `FROM`/`JOIN` again.

The harness then assembles one full `INSERT ... SELECT` per table from (shared skeleton + every
column's synthesized expression), which is also exactly the form needed to actually execute the
candidate query in DuckDB for Phase D.

**Per-call input, concretely (target-field-by-target-field, per the direction given):**

| Input | Source |
|---|---|
| Target table name, target field name, target type | `tpcdi_target_schema.sql` / `tpcdi_column_mapping.csv` (`target_table`,`target_column`,`target_type`) |
| Target field description (if available) | Need to write these ourselves — no official TPC-DI spec PDF with per-column prose is in hand (checked; not present locally). Draw from our own accumulated understanding (A3/C5 analysis) rather than blocking on sourcing the official spec. |
| Matched source field(s) + their table name(s) | `tpcdi_column_mapping.csv`'s `source_tables`/`value_columns` — this is the "matching assumed given" |
| Source table PK / FK / business key, if available | From `tpcdi_source_schema.sql`'s DDL (most `Source.*` staging tables have no declared PK/FK at all — itself a fact worth giving the model, since it explains why surrogate/business keys need deriving rather than reading off a constraint) |
| Source sample data | A handful of real rows from `tpcdi_populated.duckdb`'s `Source.*` tables (already loaded, SF=3) |
| **Data profiling** (see below) | Computed fresh per column from the loaded `Source.*` data |
| Dependency / constraints | Target column's `NOT NULL`/`CHECK`/FK, from `tpcdi_target_schema.sql` |
| *(held out, never shown)* | `rule_sql`, `combination`, `column_kind`, `rule_reliable`, `rule_issue` — these are the answer key |

**Data profiling approach** — compute per matched source column before prompting: row count,
null %, distinct count, min/max (numeric/date columns), top-k most frequent values (low-cardinality
text), a handful of sample distinct values (to surface format patterns). This isn't speculative —
it would have caught, cheaply and automatically, two real problems we only found by debugging
failed casts during Phase B: `HolidayFlag`/`CashFlag`/etc. storing literal text `'true'/'false'`
rather than `0/1`, and `FoundingDate`/`FirstTradeDate`/`QtrStartDate` being fixed-width `YYYYMMDD`
text rather than ISO dates. Profiling-informed prompting should let the LLM infer the correct
`CASE`/`strptime` handling up front instead of us finding it via a failed `NOT NULL` constraint
after the fact.

**Output, per call:** one SQL expression (the `SELECT`-list formula) for that target column.

### 5.5 Phase D — Equivalence checking (Stage 3 proper)

Execute the LLM's `{Q}` and the ported ground truth `{Q̂}` (Phase B) against the same loaded `D`
in DuckDB, per table. Compare using `column_kind` from the Phase A mapping to decide *how*:
- `value` / `passthrough_copy` / `constant` → direct value equality per row (after matching rows
  by a stable natural key, not row order)
- `generated_key` / `copies_generated_key` → **never** compare literal surrogate values; check
  structural equivalence instead (e.g., does the candidate's key column define the same
  equivalence classes / join consistency as the ground truth's), exactly the distinction the
  Synthea/OMOP file's own `rule_reliable=no` rows exist to warn about
- Tables flagged `rule_reliable=no` or `table_caution=yes` in Phase A (e.g. `DimTrade`'s stubbed
  FK columns, `Prospect.IsCustomer`'s type bug) → exclude from strict grading, or grade against a
  *corrected* rule, not the buggy reference-implementation one — otherwise we'd be penalizing a
  correct LLM answer for not reproducing R1's bug

### 5.2b / 5.3 — Executed (2026-10-02 → 2026-10-03)

C1–C6 all done: persistent venv, full `D` (Batch1) loaded into all 28 `Source.*` tables
`historical_load.sql` actually uses (15 simple + 3 FINWIRE fixed-width + 10 XML-derived),
`historical_load.sql` ported to DuckDB and executed end-to-end. **16 of 20 target tables now
hold real, referentially-consistent rows** (the other 4 — `FactMarketHistory`, `FactWatches`,
`DImessages`, `AuditTable` — correctly stayed empty, as expected from the `table_status` survey
in §5.2). Two genuine bugs in R1's original `DimTrade`/`FactHoldings` logic were found and
patched with clearly-flagged (not silent) `COALESCE` fallbacks — full detail in
`benchmark/FINDINGS.md`'s "Tasks C1–C6" section.

**`tpcdi_column_mapping.csv` (241 rows) is now built and complete** —
`benchmark/deliverables/tpcdi_column_mapping.csv`. Final breakdown: `table_status` 210
populated / 31 not_built; `rule_reliable` 193 yes / 42 no / 6 n/a; `column_kind` spans all of
passthrough_copy(70), rename(41), lookup join(25), retype(18), constant(16), SCD history(12),
conditional(7), copies_generated_key(6), value(9), generated_key(5), aggregate(1); 6 tables carry
a table-level caution (`DimSecurity`, `DimTrade`, `FactHoldings`, `FactMarketHistory`,
`FactWatches`, `DImessages`).

Deliverables: `benchmark/deliverables/ported_historical_load.sql`,
`benchmark/deliverables/tpcdi_populated.duckdb` (342 MB),
`benchmark/deliverables/tpcdi_column_mapping.csv` (241 rows).

**Deferred, not blocking:** deeper row-count verification against `Generator_audit.csv` (turned
out not to have per-table oracles, only generator config params — our referential/SCD sanity
checks already done serve as the practical verification instead).

**Everything needed for Phase C is now in place.** Next concrete step: pick the exact 2
non-Nemotron models and the inference-access method, write the data-profiling script, and build
the two-level (table-skeleton + per-column) prompting harness described in §5.4.

### Phase C harness — built and demo'd end-to-end (2026-10-03)

**Models + access, decided.** Checked live (the "usual" Nemotron names from pretraining —
Llama-3.1/3.3-Nemotron — turned out superseded by a newer "Nemotron 3" family on OpenRouter by
now, good thing this was verified rather than assumed):
- **Nemotron:** `nvidia/nemotron-3-super-120b-a12b:free` (reasoning-oriented MoE, free tier)
- **Llama:** `meta-llama/llama-3.3-70b-instruct:free` (strong generalist baseline, free tier)
- **Qwen:** `qwen/qwen-2.5-coder-32b-instruct` (code/SQL-specialized — deliberately one
  reasoning model, one generalist, one code-specialist, not three similar chat models)
- **Access:** OpenRouter, one OpenAI-compatible endpoint/API key for all three (avoids 3 separate
  vendor SDKs, avoids local hosting entirely — consistent with the earlier hardware read: 16 GB
  unified memory, no dedicated GPU, so API access is the practical route at this model scale).

**Built, in `benchmark/pipeline/`:**
- `profiling.py` — computes null%/distinct/min-max/top-k/sample-values per source column, run for
  real against `tpcdi_populated.duckdb`. Worked example: `Source.FinwireCMP.FoundingDate` profiles
  as `numeric range 18500101.0–20140816.0` + `string length always ≤8` — exactly the signal that
  should let a model infer "this is YYYYMMDD text, not an ISO date" **before** writing a query,
  rather than us finding it via a failed `NOT NULL` constraint after the fact (which is literally
  how we found it, in Phase B).
- `table_skeleton.py` — Level 1: resolves the shared `FROM`/`JOIN` skeleton for a target table
  once, straight from `tpcdi_column_mapping.csv`'s `source_tables`/`joins` fields (no LLM call).
  **Found and worked around a real inconsistency while building this**: ~10 of 20 tables in the
  mapping CSV (notably `DimCustomer`) have full `table.column` paths stuffed into `source_tables`
  instead of bare table names, because of how the CSV-building scripts were written — the parser
  was made tolerant of both forms rather than silently misreading one. **Tracked as a follow-up**:
  clean up `tpcdi_column_mapping.csv`'s `source_tables`/`value_columns`/`joins` separation
  properly (the semantic content is all there, just not uniformly split into the right fields).
- `build_prompt.py` — Level 2: builds the full per-column prompt (target field + description +
  constraints + resolved join context + matched source field(s) + source PK/FK info + sample
  rows + profile), explicitly withholding `rule_sql`/`column_kind`/`rule_reliable`/etc.
- `call_llm.py` — unified OpenRouter caller for all 3 models; falls back to a dry run (prints what
  would be sent) when `OPENROUTER_API_KEY` isn't set, which is the case in this environment.
- `run_demo.py` — ties it together end to end for `DimCompany.Industry` and
  `DimCompany.FoundingDate`: prompt → (dry-run) model call → held-out ground truth from
  `tpcdi_column_mapping.csv` shown for comparison.

**Still needed before running this for real:** an `OPENROUTER_API_KEY`; a fuller
`FIELD_DESCRIPTIONS` pass (only a handful of columns have hand-written descriptions so far, as a
placeholder — no official TPC-DI spec PDF with per-column prose was found locally, per §5.4); the
`tpcdi_column_mapping.csv` field-separation cleanup noted above; and Phase D's actual grading
logic (execute each model's expression inside the resolved skeleton against `D`, compare per
`column_kind`).

### First live run, 2026-10-03 — no-paid-budget revision + real findings

**Model roster revised**: no paid budget available, so the paid Qwen-Coder pick had to go.
Verified live against OpenRouter's actual `/api/v1/models` API (far more reliable than scraped
model pages, several of which 404'd inconsistently and turned out to reflect stale/removed
listings) — **Llama 3.3 70B has dropped off the free tier entirely** since it was first proposed.
Final roster, all three confirmed `$0`/`$0` pricing live:
- `nvidia/nemotron-3-super-120b-a12b:free` (unchanged)
- `cohere/north-mini-code:free` (replaces paid Qwen-Coder — code-specialist, genuinely free)
- `qwen/qwen3.8-27b:free` (replaces Llama 3.3 — generalist)

**Consequence for the rate-limit math**: all 3 models are now `:free`, so the 50/day cap is
shared across all three (not 2 of 3 as in the original paid-Qwen design). Subset trimmed from 15
to 12 columns (36 calls, vs. the original 30) to keep safe margin.

**Real results from the first live run** (12 columns × 3 models = 36 calls, +1 diagnostic +10
retry = 47 of today's 50 used):

| Model | Success rate | Failure mode |
|---|---|---|
| `nvidia/nemotron-3-super-120b-a12b:free` | 11/12 (92%) | 1 null-content |
| `cohere/north-mini-code:free` | 2/12 (17%) | mostly `finish_reason=max_tokens`: exhausted budget on internal reasoning before emitting final content |
| `qwen/qwen3.8-27b:free` | 2/12 (17%) | mix of `finish_reason=length` (same reasoning-exhaustion pattern as Cohere) and `HTTP 429` (hit mid-run even at an 8s/call throttle — the documented 20/min account limit doesn't fully explain this; more likely each free backend has its own capacity-based throttling on top of the account quota) |

**Root cause, confirmed via the raw API response, not guessed**: both Cohere and Qwen's picks
are reasoning models with a separate internal `"reasoning"` field ahead of the final `"content"`.
On our real multi-section column prompts (far longer than a quick test prompt), they were
spending the entire token budget on internal reasoning and never reaching a final answer —
`content: null`. Diagnosed by capturing and reading the *full* raw API response for one call,
not just the extracted message content (the bug `expected string or bytes-like object, got
'NoneType'` was `extract_sql()` choking on that null, not a real network/auth failure).

**Fix applied for next run**: `max_tokens` raised `600 → 2000 → 6000`. This costs nothing extra
against the call-count-based daily cap (max_tokens isn't billed/limited the same way on `:free`
models), so there's no reason not to set it generously. Also bumped the inter-call throttle
`4s → 8s` after Qwen's 429s appeared even under the original delay, and made `run_subset.py`
retry previously-*failed* (not just missing) entries, and support an explicit `max_calls` cap so
a run stops cleanly instead of blindly burning through a scarce remaining daily budget.

**15 of 36 slots now have usable SQL** (see `benchmark/pipeline/subset_results.json`); the rest
are queued to retry tomorrow once the daily quota resets, with the `max_tokens=6000` fix in
place and not yet validated at scale (only validated conceptually from the diagnostic call so
far — today's remaining 3-call budget wasn't enough to confirm it fixes Cohere/Qwen for real on
the actual subset).

### Phase D, first real pass — `benchmark/pipeline/grade_subset.py`, 2026-10-03

Built an actual grader rather than eyeballing the 15 successful responses: execute each
candidate expression for real against `Source.*` data, compare to the already-verified-correct
value sitting in the populated `T`. Only implemented so far for "value-like" columns with a clean
natural key to join back on (5 of the 12 test columns — `generated_key`/`SCD history`/
`aggregate`/`copies_generated_key` need a different, structural grading approach, not built yet).

**Real results, 7 gradable (column, model) pairs:**

| Column | Model | Result |
|---|---|---|
| `Industry.IN_NAME` | nemotron | **100% match** |
| `Industry.IN_NAME` | cohere | **100% match** |
| `DimCompany.CEO` | nemotron | **100% match** |
| `DimCompany.CEO` | cohere | **100% match** |
| `DimCompany.isLowGrade` | nemotron | **99.9% match** (1 mismatch / ~1500 rows — model used real investment-grade rating thresholds instead of the reference's cruder `LIKE 'A%'/'BBB%'` pattern; nearly identical, diverges on one edge case) |
| `DimCompany.FoundingDate` | nemotron | **EXECUTION FAILED** — used `TO_DATE(...)`, a Postgres/Oracle function that doesn't exist in DuckDB (we never told the model which SQL dialect to target) |
| `DimCompany.Industry` | nemotron | **EXECUTION FAILED** — referenced `I.IndustryName`, a column that doesn't exist (the real one is `I.IN_NAME`) — a hallucination |

**Important confound found while building this**: 7 of the original 12 test columns were not
fairly tested. Their mapping-CSV `value_columns` field was empty (the same data-quality gap
flagged when building `table_skeleton.py`), which meant `build_prompt.py`'s "MATCHED SOURCE
FIELD(S)" section — the whole point of which is "matching assumed given" — was rendering
**blank** for those columns. The models weren't failing at the transformation task there; they
were reasoning from nothing (e.g. `DimTrade.SK_BrokerID`'s model invented `-1` out of thin air,
`Prospect.IsCustomer`'s model hallucinated a `DimCustomer.CustomerKey` column that doesn't exist).
One column (`DimCustomer.Phone1`) had a `*` wildcard in `value_columns` that never got expanded
to the actual 4 phone sub-fields.

**Three fixes applied (free — code only, no API cost) for tomorrow's retry:**
1. Prompt now explicitly says *"write portable, DuckDB-compatible SQL... do not use T-SQL/Oracle/
   Postgres-specific functions"* and *"do not invent column or table names."*
2. `build_prompt.py` now expands a `*` wildcard in `value_columns` to the table's real columns
   (fixes `DimCustomer.Phone1` and similar).
3. `build_prompt.py` now falls back to the resolved join skeleton's actual table columns when
   `value_columns` is empty, instead of silently rendering a blank "matched source field" section.

**Honest verdict on "is this working with decent accuracy":** on the columns that were actually
given fair, complete context (5 of 12), results are strong — 4 of 5 exactly correct, 1 of 5
99.9% correct with a defensible alternative rule. The 2 real failures are both mechanical and
fixable (missing dialect instruction, no anti-hallucination guardrail) rather than a
transformation-reasoning failure — both fixes are now in place. The other 7 columns (generated
keys, SCD history, aggregates, deliberately-flagged bugs) have not yet had a fair test or a
working grading methodology — that's the next real gap, not today's rate-limit logistics.

### Contamination concern raised, subset revised (round 2) — 2026-10-03

Reasonable concern: TPC-DI is a decade-old, heavily-documented public benchmark (spec PDF freely
downloadable, 4+ full reference implementations on public GitHub). The 5 columns graded so far
are all simple, textbook `FinwireCMP → DimCompany` mappings — exactly what a model could plausibly
know from pretraining rather than from reasoning over the matching we handed it. One data point
cuts against *pure* memorization though: `isLowGrade`'s answer used real S&P rating tiers, not
R1's actual (cruder) `LIKE 'A%'` pattern — diverging from the literal reference while landing on
defensible domain logic, which looks more like "knows the TPC-DI *spec's intent*" than "copied
R1's GitHub code." Contamination at the schema/spec level looks plausible; at the literal-code
level, less so — but this is not resolved, just one weak data point.

**Subset revised** (`select_subset.py`) to 13 columns, prioritizing contamination-resistant
targets over easy/memorizable ones: kept `DimCompany.FoundingDate`/`Industry` (need dialect-fix
retest), `IsCurrent`/`SK_CompanyID`/`FactCashBalances.*` (no clear signal yet either way), the 2
existing flagged-bug columns, and added **5 new harder targets** — a second flagged-fragile
column (`DimSecurity.SK_CompanyID`), a 2-hop lookup (`DimCustomer.NationalTaxRateDesc`), an
idiosyncratic R1-invented business rule with no spec-mandated answer
(`DimCustomer.MarketingNameplate`'s 6-branch CASE), and two temporal/correlated-subquery lookups
(`DimAccount.SK_CustomerID`, `Financial.SK_CompanyID`). Rationale: R1's own bugs/rough edges and
idiosyncratic logic are a cleaner contamination test than its correct, spec-standard code, since
memorized "I know TPC-DI" knowledge would reproduce the *spec's* intended behavior, not one
obscure student repo's specific mistakes. 39 calls, still safely under the 50/day shared cap.

**Further option, not yet built, highest rigor**: identifier obfuscation. Rename
`tpcdi_source_schema.sql`/`tpcdi_target_schema.sql` tables/columns to meaningless synthetic names
(`Source.FinwireCMP` → `Source.Tbl_A7`, etc.), keeping structure and data identical, and re-run
the same prompts. If accuracy holds, that's strong evidence of genuine reasoning (no training-data
pattern to match against); if it drops sharply, that confirms memorization was propping up the
earlier results. Not attempted yet — meaningfully more work (new schema variant, new mapping CSV,
new prompts) — flagged as the gold-standard follow-up if the harder-column results are still
ambiguous.

### Full 13-column run, 2026-10-04 — pre-fix results, a real bug found, and a clean fix validation

**Pre-fix run (30 calls)**: Nemotron 13/13 raw success, Cohere 11/13, **Qwen 3/13** (still our
weakest model — mostly token-exhaustion on its own internal reasoning, plus intermittent 429s
and one connection reset; no fix found for this yet, may just be an unreliable free backend).

**A real prompt bug, found and fixed, not a model capability gap.** All 4 of the 5 new "harder"
contamination-test columns that depend on a two-step lookup (`DimSecurity.SK_CompanyID`,
`DimAccount.SK_CustomerID`, `Financial.SK_CompanyID`, `DimCustomer.NationalTaxRateDesc`) came back
with the *same* wrong pattern from both working models: casting the raw business key to an
integer instead of looking up the target dimension's surrogate key. Traced to the actual prompt
sent — `tpcdi_column_mapping.csv`'s `" -> "` lookup-arrow notation (e.g.
`Source.TaxInfoXML.C_NAT_TX_ID -> Source.TaxRate.TX_NAME`) was being mis-parsed by
`build_prompt.py`, which only split on `.` and never looked for `" -> "` first — for that example
it rendered `Source.TaxInfoXML.C_NAT_TX_ID -> Source` in the prompt (truncated, `TaxRate.TX_NAME`
lost entirely). `table_skeleton.py` had the identical bug's sibling: `_table_ref` treated
`DimBroker.SK_BrokerID` (a column reference on an already-populated TARGET table, from the arrow
notation's right-hand side) as if the whole string were itself a table name, producing garbage
like `Source tables involved: ..., DimBroker.SK_BrokerID, DimCustomer.SK_CustomerID, ...` in the
"resolved join context" every column of `DimAccount` was shown.

**Both fixed** (`build_prompt.py`, `table_skeleton.py`): arrow notation is now split first, each
side resolved separately, and a reference to an already-populated target table now renders as an
explicit `LOOKUP:` line (e.g. *"use `Source.CustomerXML.C_ID` to find the matching row in
`DimCustomer` (an ALREADY-POPULATED target table), then take its `DimCustomer.SK_CustomerID`
column"*) instead of being silently absorbed into the wrong field. Also had to re-patch 4 of the
5 CSV rows fixed on 2026-10-03 — yesterday's quick patch only recorded the raw source column
(e.g. `Source.CustomerXML.C_ID`), not the full lookup chain, so even with the parser fixed there
was nothing on the right side of the arrow to parse. Correct chains now in place for
`FactCashBalances.SK_CustomerID`, `DimSecurity.SK_CompanyID`, `DimAccount.SK_CustomerID`,
`Financial.SK_CompanyID`.

**Retest, clean before/after validation (15 more calls, 45/50 used today)**:
- `DimCustomer.NationalTaxRateDesc`: **0/2 correct → 3/3 correct.** All three models now
  reference `TaxRate.TX_NAME` directly instead of the raw tax code. Clean evidence the bug, not
  model capability, was the cause.
- `DimAccount.SK_CustomerID`: 2/2 successful calls now correctly reference
  `DimCustomer.SK_CustomerID` (qwen errored again, separately, on token exhaustion).
- `DimSecurity.SK_CompanyID`: **a narrower, new problem surfaced.** All 3 models now correctly
  identify the right table to look up (`DimCompany`) — real progress — but all 3 guessed a join
  column, `DimCompany.CoNameOrCIK`, that doesn't exist (the real columns are `CompanyID`/`Name`;
  the actual logic needs a `CASE` on whether the source value is numeric). Root cause: we tell the
  model a target table is "available to join against" but never show *its schema*, unlike
  `Source.*` tables which get a `DESCRIBE` + profile. **Next fix, not yet done**: expose the
  target table's real columns (at least a `DESCRIBE`) whenever it's offered as a lookup target.
- `Financial.SK_CompanyID` — not retested, budget ran out (45/50 used) right before reaching it.
  Carries over to the next run.

**Budget status**: 45 of 50 used today (2026-10-04). 5 remain; deliberately held in reserve rather
than spent chasing the `DimSecurity.SK_CompanyID` schema-exposure fix same-day.

### Grading extended to cover the fixed columns — real accuracy numbers

Extended `grade_subset.py` with `DimCustomer.NationalTaxRateDesc` (keyed by `CustomerID`,
matching the pattern already used for `DimCompany`/`Industry`); also fixed two bugs in the
grader itself found while doing this: (1) it crashed on the `_prompt` key now stored alongside
model results (missing a skip-guard), (2) the ground-truth query was hardcoded to
`FROM DimCompany WHERE IsCurrent` regardless of which table `GRADABLE` actually specified,
which would have silently graded `DimCustomer` columns against the wrong table.

**`DimCustomer.NationalTaxRateDesc`: 3/3 models, 4,728/4,728 rows, 100% match** — clean,
full-scale confirmation that the lookup-arrow prompt fix produces fully correct output, not just
syntactically-plausible output.

**`DimCompany.FoundingDate` re-examined: cohere/qwen's new `make_date`/`CAST(...AS DATE)`
answers execute successfully (confirms the dialect fix) but only show 75.3% match** — traced
this to a grading-methodology artifact, not a model error: company `CIK=2` (and others) have
**multiple historical `FinwireCMP` records** (a restatement — `FoundingDate` corrected from
1921-03-28 to 1923-09-06 in a later record), each with its own `DimCompany` SCD row, but our
grader only keeps the single *current* row as ground truth and checks every raw source row
(including the outdated one) against it. The outdated record's row will always look like a
"mismatch" even though the candidate SQL computed exactly the right value for that row's own
point in time. Same underlying phenomenon as the earlier 1,500-rows/1,096-distinct-companies
note — not yet fixed in the grader (would need to compare against the SCD-row whose
effective-date window actually contains that source record's `PTS`, not just "the current one").
### Nemotron retest + grader fix — final confirmation on `FoundingDate`/`Industry`

Used the last of today's budget (50/50) to retest nemotron's stale `FoundingDate`/`Industry`
answers directly (cleared and re-called rather than waiting for an error-triggered retry, since
neither had errored before — they'd just graded wrong).

- **`FoundingDate`**: nemotron now also produces valid DuckDB (`STRPTIME(FoundingDate,
  '%Y%m%d')`), confirming the dialect fix works across all 3 models, not just cohere/qwen.
  Grading it hit a second grader bug: `STRPTIME` returns `TIMESTAMP`, not `DATE`, so
  `"1886-07-22 00:00:00"` vs ground truth's `"1886-07-22"` compared as a false mismatch —
  fixed (`grade_subset.py` now strips a trailing `00:00:00`). With that fixed: **75.3% match,
  same exact rowkeys mismatching as cohere/qwen's run (2, 3, 5...)** — confirms this is entirely
  the duplicate-FinwireCMP-record grading artifact already diagnosed, not a model error. **True
  verdict: all 3 models produce correct `FoundingDate` logic.**
- **`Industry`**: nemotron still fails — now guesses `I.Industry` (previously `I.IndustryName`),
  still not the real column (`I.IN_NAME`). The anti-hallucination instruction reduced but did not
  eliminate this specific failure mode — model keeps assuming a source column shares the
  *target* column's name rather than using what was actually shown. Unresolved.
- **`Financial.SK_CompanyID`**: still not attempted — the daily cap (50/50) was reached one call
  short of it. Carries into the round-3 batch below.

### Round 3 — genuine column-count expansion, prepared 2026-10-04

User flagged (correctly) that "expand the number of columns" had only gone from 12→13 so far —
a swap, not a real expansion, since most of the day's effort went into diagnosing/fixing bugs.
Built a real expansion: **13 → 25 columns**, prioritizing tables never touched before
(`DimBroker`, `FactHoldings`) and deliberate repeats of categories in a different table (second
`MarketingNameplate`-style idiosyncratic-CASE test on `Prospect`, second YYYYMMDD-retype test on
`DimSecurity`) to see if a model makes the identical mistake twice independently.

**9 of the 12 new columns needed the same `value_columns` CSV patch** as round 2's — confirms
the 86-row gap is systemic across the mapping file, not a handful of unlucky rows. Patched
directly in `tpcdi_column_mapping.csv`. Also fixed a related notation bug found while doing
this: `DimCustomer.MarketingNameplate`'s `value_columns` used an unparsed `"{A,B,C}"`
curly-brace list (never handled by `build_prompt.py`'s parser) — switched to clean
`;`-separated entries, applied consistently to the new `Prospect.MarketingNameplate` too.

**Budget for tomorrow**: 36 new calls needed (12 new columns × 3 models), well under 50/day.
`select_subset.py` now has the full 25-column list ready to run.

### 5.6 Not in this plan (deliberately deferred)
- MIMIC-IV → OMOP (B1–B5) — still untouched; revisit once the TPC-DI pipeline (A→D above) proves
  the approach works end to end on one benchmark first.
- Reverse Execution (Stage 4) — comes after Stage 3 is working.

**Order of work: 5.1 (done, this section) → 5.2 and 5.3 together, table by table → 5.4 → 5.5.**

### Transformation-type breakdown: gold standard vs. what the LLMs generated (2026-10-04)

**Gold standard (`tpcdi_column_mapping.csv`, 210 populated columns):** passthrough_copy 70 (33.3%),
rename 41 (19.5%), lookup join 25 (11.9%), retype 18 (8.6%), constant 16 (7.6%), SCD history 12
(5.7%), value 9 (4.3%), conditional 7 (3.3%), copies_generated_key 6 (2.9%), generated_key 5
(2.4%), aggregate 1 (0.5%). 31 more columns are not_built (no gold answer). 193 of the 210 are
rule_reliable=yes.

**Caveat on any accuracy claim:** the current 13-column test subset is hand-picked and heavily
skewed toward hard types (lookup join 5, conditional 2, retype/SCD/generated_key/copies_
generated_key/aggregate/constant 1 each) and contains **zero** passthrough_copy/rename columns --
the two types that make up 53% of the gold standard. Round 3 (not yet run) adds those. Results
below are therefore NOT an estimate of overall accuracy.

**Generated vs. gold, 32 (column, model) pairs that produced SQL** (only FoundingDate, Industry,
NationalTaxRateDesc were execution-graded; the rest are a manual read against gold rule_sql):
- Verified correct (executed, matches): 6 -- FoundingDate x3 (retype), NationalTaxRateDesc x3 (lookup join, 4,728/4,728 rows)
- Correct by reading, not executed: 2 -- qwen's ROW_NUMBER() for DimCompany.SK_CompanyID (generated_key), nemotron's DimAccount.SK_CustomerID lookup for FactCashBalances.SK_CustomerID (copies_generated_key)
- Right approach, broken/unverified details: 10 -- DimSecurity.SK_CompanyID x3 (right table, nonexistent join column), DimAccount.SK_CustomerID x2 (no SCD-window gating shown), Prospect.IsCustomer x2 (existence-flag idea right, hallucinated column / no join), Industry nemotron (hallucinated I.Industry), SK_CompanyID nemotron (NEXT VALUE FOR, wrong dialect), DimTrade.SK_BrokerID nemotron (constant -1 vs gold 1)
- Wrong approach: 14 -- SCD history 0/3 (constant TRUE or an invented 'Delete' status; gold needs LEAD() window), aggregate 0/3 (row-level cast, no SUM/GROUP BY), MarketingNameplate 0/2 (concatenated raw values instead of a CASE label), plus assorted key-copy errors (cast of an account/name column used as a surrogate/broker key)

**By gold type:** retype and name-based lookup join work; window (SCD), aggregate, and
multi-branch CASE-label types are 0 for N so far; generated/surrogate keys are mixed. Note
FactCashBalances.SK_CustomerID cohere/qwen answers predate the lookup-chain CSV patch and would
likely change on a re-run.

## Run 3 status (prompt v3-2026-10-05, 25 columns, temp 0.0) — 2026-10-05
- **Nemotron** (NVIDIA hosted NIM, `nvidia/nemotron-3-super-120b-a12b`): 25/25 cells at v3. Not subject to the OpenRouter 50/day cap.
- **Cohere north-mini-code** (OpenRouter free): 24/25 at v3 or valid; DimCompany.Industry still failing with null content (max_tokens). 7 older cells predate v3 (not re-run, to save OpenRouter quota).
- **Qwen3.8-27B** (OpenRouter free): INCOMPLETE — 2 cells at v3, 6 older valid, 5 errors (429/length), 12 not attempted. OpenRouter's 50/day cap is nearly spent; Qwen was deliberately deprioritised because it fails most often. Re-run tomorrow (`RUN_MODELS=qwen run_subset.py <cap>`).
- `run_subset.py` gained a `RUN_MODELS=a,b` env filter so single providers/models can be run alone.
- Graded so far (only 6 columns are gradable): NationalTaxRateDesc 100% for all three models (v3 prompt fix validated). FoundingDate: cohere/qwen 75.3% (remaining gap = FinwireCMP duplicate-CIK grader artifact, not a model error); Nemotron fails execution (`CAST('18860722' AS DATE)` — wrong date format for DuckDB). DimCompany.Industry: Nemotron execution fails again (hallucinated `I.Industry`; real column is `IN_NAME`).
- Still to do: extend GRADABLE / structural grading for the 19 other columns, fix SCD-duplicate grader artifact, finish Qwen cells.

### Run 3 addendum — NVIDIA-hosted replacement model (2026-10-05)
- Probed NVIDIA's hosted catalog (81 listed): only `openai/gpt-oss-20b` answers promptly (~4s). deepseek-v4.1-flash timed out >280s, glm-5.3-flash ~260s, kimi-k3 timed out; codestral, mistral-large, kimi-k2.6, nemotron-70b/ultra, codellama, granite, mixtral are listed but 404. Catalog listing is not a reliable indicator of availability.
- Added `gpt_oss` to `call_llm.py` (NVIDIA-routed, uncapped by OpenRouter). Ran all 25 columns at v3 with zero errors.
- Graded: NationalTaxRateDesc 100%; DimCompany.Industry 86.9% (first model to execute successfully with the correct `IN_NAME`); FoundingDate 75.3% (same SCD-duplicate artifact as Cohere/Qwen).
- Model set now: Nemotron (25/25), gpt-oss-20b (25/25) via NVIDIA; Cohere (24/25) and Qwen (partial) via OpenRouter, to finish when quota resets.

## Pending after the mid-semester presentation (added 2026-10-06)
- **Grader wiring (TPC-DI):** only 3 of the 25 subset columns are graded by value today. About 10 more have a clean natural key and only need `GRADABLE` specs in `benchmark/pipeline/grade_subset.py`: DimBroker.FirstName/Branch, DimTrade.Status/CashFlag, DimSecurity.FirstTrade, FactHoldings.CurrentPrice, DimAccount.Status, Financial.FI_REVENUE, DimCompany.AddressLine1, DimCustomer.Email1. The 7 surrogate/copied-key columns (SK_*, FactHoldings.TradeID) need structural grading; IsCurrent, FactCashBalances.Cash, Prospect.IsCustomer and the two MarketingNameplate columns need other logic.
- Fix the FinwireCMP duplicate-CIK grader artifact (affects DimCompany.FoundingDate 75.3%).
- Finish Cohere/Qwen cells once the OpenRouter quota resets.
- Slide 2 wording: "can be graded" should read "graded so far".

## Step 1 done: generic swap-in grader + gold self-test (2026-10-26)
Files: `benchmark/pipeline/grade_swap.py` (grader), `grade_subset_swap.py` (grades subset_results.json), `run_gold_swap_test.py`, `run_null_control.py`; outputs `gold_swap_results.json`, `null_control_results.json`, `grade_swap_results.json`. Needs `sqlglot` (installed in .venv).
- **Method.** The executable gold per table is its INSERT...SELECT in `ported_historical_load.sql`. The grader keeps the gold query unchanged, swaps ONE candidate expression in at the SELECT that actually computes the column (descends through derived tables/CTEs while a column is a plain pass-through), runs it, and compares with the populated T as a multiset keyed by all other output columns (no hand-picked keys). Outer select items are CAST to T's declared types (mimics INSERT). One comparator for every column; replaces the hand-written GRADABLE specs.
- **Gold self-test: 16/16 tables reproduce exactly; 210/210 columns reproduce exactly** when their own gold expression is swapped back in. So the grader is validated before touching any model.
- **NULL control:** swapping NULL into each column. 11 of 210 columns score >=20% for NULL alone (AddressLine2 88%, Phone3 67%, MiddleInitial x3 ~56-65%, DimTrade.SK_CloseDateID/TimeID 61%, Prospect.Gender 53%, Email2 46%, Prospect.AddressLine2 32%, Phone2 21%): on these a score is only meaningful above that baseline.
- **Old grader artifacts confirmed:** FoundingDate 75.3% -> 100% for gpt-oss/cohere/qwen; Industry gpt-oss 86.9% -> 100%.
- **Subset re-graded (82 cells, 4 models):** 29 exact, 11 partial, 4 wrong (0%), 26 unresolved-name/scope failures, ~12 other execution errors.
- **Root cause of the scope failures (data/prompt contract, not model weakness):** the prompt shows a CSV-derived informal skeleton, but the grader (like the gold) evaluates the expression in a specific executable scope (aliases, derived tables, CTE chain). Columns computed in an outer SELECT (surrogate-key ROW_NUMBER, lookups) or in CTE chains (DimCustomer, DimAccount, DimSecurity, DimTrade; UNION branches) cannot see the raw Source.* names the model was told to use.
- **Step 2 (next):** make the scope a contract. For each column derive from the gold the executable FROM/JOIN/WHERE of its defining SELECT (and per-branch for UNIONs), show it in the prompt (recipe-given), and grade in exactly that scope. Then re-derive `value_columns` automatically from the same lineage, flag the 17 defective-gold columns, and parallelise the runner.

## Step 2 done: scope-contract prompt (v4), gold-lineage audit, parallel runner (2026-11-04)
New files in `benchmark/pipeline/`: `scope_prompt.py` (prompt v4 + `derive_scope`), `audit_scope.py` -> `scope_audit.csv`, `llm_parallel.py`, `run_v4.py` (parallel, resumable, per-model pools, `--run NAME --subset --models ... --repeats N --temp T`), `grade_run.py` (-> `runs/NAME/graded.json`). Runs live in `runs/NAME/{prompts.json,results.jsonl,graded.json}`.
- **Scope contract.** For each column the SELECT that computes it is derived from the gold (`grade_swap.defining_select`, now also descending through UNION branches and `SELECT *`). The prompt shows that SELECT's FROM/JOIN/WHERE/GROUP BY with a `<YOUR_EXPRESSION>` placeholder, the relations/aliases/columns visible in it (derived relations as name + columns only, never their bodies), the columns the gold expression reads (matching, given), sample rows and a profile computed in that scope. The grader swaps the model's expression into the same SELECT, so prompt and grader cannot disagree. Gold self-test still 210/210 columns, 16/16 tables.
- **Controlled comparison (same model = nemotron-3.5-super, same grader, same data, 25-col subset, temp 0):** v3 prompt 11 exact / 3 partial / 8 fail-to-run / 3 no-answer -> v4 prompt **21 exact / 2 partial / 2 wrong / 0 fail-to-run**. Remaining misses: both MarketingNameplate columns (R1's invented thresholds), Prospect.IsCustomer (71.7%), DimTrade.SK_BrokerID (gold is a hardcoded 1).
- **Answer-key bug found and fixed:** `DimTrade.CashFlag` was all FALSE (982,180 rows) because OUR port tested `UPPER(T_IS_CASH)='TRUE'` but the source holds '0'/'1' (the original T-SQL just copies it). Three LLMs all scored 79.97% = share of '0' rows, which exposed it. Fixed in `ported_historical_load.sql`; DimTrade rebuilt in `tpcdi_populated.duckdb` (196,751 TRUE / 785,429 FALSE; row count unchanged; backup `tpcdi_populated.duckdb.bak_before_cashflag_fix`). The other text flags (HolidayFlag, MarketHoursFlag, OfficeHoursFlag) verified genuinely 'true'/'false'. Gold self-test 16/16 after the fix.
- **value_columns audit (`scope_audit.csv`):** the 104 populated columns with an empty CSV `value_columns` are now filled from gold lineage (prompt v4 no longer reads the CSV field). Of the 106 non-empty rows, 94 agree with the gold lineage, 2 differ in a consistent way (DimCompany.Status/Industry: CSV names the raw code, gold reads the joined lookup output), 10 are lookups into already-populated tables. Gold-quality flags: 17 `rule_reliable=no` (13 of them the hardcoded-1 foreign keys in DimTrade/FactHoldings).
- **Model availability drift (important for provenance).** `nvidia/nemotron-3-super-120b-a12b` is still listed by NVIDIA but now returns 404 on invocation. `nemotron` now = `nvidia/nemotron-3.5-super-vl-120b-a12b` (same size class). Probed 2026-11-04: working = nemotron-3-ultra-550b (3s), 3.5-lightning-30b, 3-nano-omni-30b, 3.5-bolt-e4b, 3.5-super-vl-120b (9s), mistral-large-4-1t-a52b (10s but 140s average under real prompts, many timeouts), poolside/laguna-xs-2.1 (2s), meta/muse-glimmer-30b (37s); gpt-oss-20b answers intermittently (22 of 25 timed out); deepseek-v4.1-flash, glm-5.3-flash, gemma-4-31b, step-5-preview time out; kimi-k2.6, codestral, nemotron-nano-3-30b, palmyra-fin return 404. Old v3 results keep their original `model_slug` per cell.
- **v4 subset run coverage:** nemotron 25/25; mistral-large 14/25 (rest timeouts); gpt-oss 3/25. Mistral/gpt-oss need a retry pass or a different second/third model (laguna and nemotron-3-ultra are the fast candidates).
- **Next:** pick the 2nd/3rd model (decision needed), full 210-column run with 3 repeats at temp 0.7, fresh-subagent Claude sample, profiling-off ablation; handle columns whose value depends on UNION-branch logic (DimCustomer/DimAccount.Status) as "branch-logic" flagged.

### Step 2 addendum — model speed fix and 4-model subset comparison (2026-11-04)
- Mistral Large 4 is a reasoning model: by default ~5,700 reasoning tokens (~200s) per ~600-token prompt (1 of 3 sequential calls succeeded; others timed out / hit max_tokens). Request param `reasoning_effort: "low"` -> ~13-28s, ~400 tokens, 24/25 answered. Set per model in `llm_parallel.MODEL_EXTRA`. (`enable_thinking=false` did not help; `reasoning_effort=none` is rejected with HTTP 400.) gpt-oss-20b still times out even at low effort (12/12) -> dropped.
- v4 prompt, 25-column subset, temp 0, graded with the swap grader: nemotron-3.5-super 21 exact | mistral-large-4 (low) 19 exact (+1 no answer) | nemotron-3-ultra 18 exact | laguna-xs-2.1 13 exact (6 fail to run). Avg latency: laguna 1.6s, nemotron 11s, ultra 14s, mistral 28s. The models separate, so the benchmark discriminates. All four miss the two MarketingNameplate columns (R1's invented thresholds).
- Full-run estimate (210 cols x 3 repeats x 3-4 models, per-model pools): roughly 1 hour wall clock. Real risk is NVIDIA's free credit pool (unverified ~1000 credits, no headers expose it): proposed phase A = 1 repeat x 3 models (630 calls), phase B repeats only if credits allow; user should check the credit balance on build.nvidia.com first.

## Step 3 — Phase A full run (2026-11-05)
Run `runs/v4_full_t0` (prompt v4, temp 0, 210 cols x 3 models, 630 calls, 0 API errors; spacing 1.6s ~ 37 RPM vs the 40 RPM limit).
Exact-match (100% of T rows) on all 210 columns: nemotron-3.5-super 170 (81.0%), mistral-large-4(low) 174 (82.9%), laguna 134 (63.8%; 28 fail to run).
Reliable-gold only (193 cols): 159 / 162 / 122. Gold-defective (17 cols) reported separately. >=1 model exact: 174/193 reliable.
Summary table: `benchmark/pipeline/runs/v4_full_t0/summary.txt`; per-cell: `graded.json`.
Systematic misses (identical across models, so not model noise): DimCustomer address/phone columns (~95% = union-branch rows),
BatchID constants (gold = 1, prompt never says historical load = batch 1), SCD EndDate/IsCurrent windows, both MarketingNameplate columns, SK_BrokerID.
Not yet done: repeats at temp 0.7 (noise), fresh-Claude 40-col run, matching-not-given variant.

## Step 4 — Error analysis of Phase A and the v5 prompt (2026-11-05)

### 4.0 What we are building, and the rule for changing the prompt
Goal of the pipeline: given source schema S + source data D + target schema T', synthesise migration queries Q so that Q(D)
populates T'. The benchmark measures how well a method does that WITHOUT being told the answer. So the prompt may contain
only what a real migration engineer would have: the target schema (+ its documentation), the source schema and data profile,
and the matching (given in this mode). It must never contain the gold expression, hints derived from a specific column's gold,
or per-column special cases.
A change to the prompt is allowed only if ALL hold:
 (a) it is a rule applied mechanically to every prompt (or to every prompt that meets a structural condition), not a per-column patch;
 (b) its content comes from a source independent of the gold SQL (the public TPC-DI spec, the DDL, or the structure of the scope
     query that the prompt already shows) -- never from the gold expression of the column being asked about;
 (c) it is validated by re-running ALL 210 columns and reporting wins AND regressions, with the old prompt version kept as the baseline;
 (d) the final report states that v5 was designed after looking at v4 failures on this benchmark (so v5 is a development-set number);
     unbiased numbers come from (i) the fresh-agent run, (ii) the temp-0.7 repeats, (iii) Synthea->OMOP where no prompt tuning was done.
Distinction used throughout: benchmark-validity fix (prompt and grader disagree about what is being asked) vs. missing documentation
(information a real engineer would have) vs. answer hint (not allowed).

### 4.1 Item analysed first: "DimCustomer address/phone columns at ~95%" -- my earlier explanation was WRONG
Earlier hypothesis: the missing rows come from the gold's UNION branch for updated customers, which the prompt does not show. Checked:
the swapped expression lives in Customers_Preproc, and CustomersNew / CustomersUpd / the UNION branches are all built FROM it, so the
swap reaches every branch. Actual cause (measured on DimCustomer.City, 282 of 6,440 rows): the model wrote
LEFT(COALESCE(NULLIF(TRIM(C_CITY),''),''),25); the gold keeps NULL, and a later step does COALESCE(UC.City, NC.City) so an UPDCUST
record with no address falls back to the NEW record's city. Returning '' instead of NULL blocks the fallback.
Swapping in LEFT(NULLIF(TRIM(C_CITY),''),25) or TRIM(C_CITY) gives 100.0%. So: a scope-framing problem (the prompt said "populate the
NOT NULL column" while the scope is an intermediate step), plus the model not knowing what happens downstream.
Phone1..3 are a different cause: the gold appends the extension (Phone1_V1 || C_EXT1); the models used COALESCE(...) instead. The column
description ("Phone number 1") does not say so; the spec's per-table transformation text (Clause 4.5) does. Left as a genuine miss in
the no-transformation-docs mode.

### 4.2 TPC-DI spec found: field descriptions DO exist (earlier belief was wrong)
Public spec v1.1.0, https://www.tpc.org/tpc_documents_current_versions/pdf/tpc-di_v1.1.0.pdf (copy in benchmark/spec/).
 - Clause 3.2: a description row for every target column -> deliverables/tpcdi_spec_target_descriptions.json (233 of 241 columns; the 8 missing are
   AuditTable / FactMarketHistory, not among our 210). Parser: pipeline/extract_spec_descriptions.py (anchored on our DDL column names).
 - Clause 4.4.1 (history-tracking dimensions: IsCurrent / EffectiveDate / EndDate semantics) and 4.4.2 (BatchID: Historical Load = 1) are
   GENERIC conventions, not per-column rules.
 - Clause 4.5 holds the per-table transformation rules in prose (e.g. EffectiveDate = date portion of ActionTS). NOT used in the main
   benchmark: with it the task becomes "translate English spec to SQL". Planned as a separate ablation ("spec-docs arm").
 - Side finding: spec 4.4.1.5 says at most ONE row per natural key per day; the ported gold does not enforce this (DimAccount has 1,284
   (AccountID, EffectiveDate) groups with >1 row, caused by the duplicated last row for closed accounts). Gold-quality note, not fixed.

### 4.3 v5 prompt = v4 prompt text + three additions (nothing else changes; paired comparison)
 1. Target description from spec Clause 3.2 (replaces "(no description available)").
 2. LOAD CONTEXT (Clause 4.4.2, every prompt) and, for the five spec-listed history-tracking tables (Clause 4.4.1.1: DimAccount, DimBroker,
    DimCompany, DimCustomer, DimSecurity), the SCD2 conventions of 4.4.1.2/4.4.1.3. Fixes BatchID and gives EndDate/IsCurrent their meaning.
    Selection principle: include the clauses that DEFINE what the target columns mean; exclude processing rules (e.g. 4.4.1.5 granularity).
 3. NOTE ON THIS SCOPE, added when the defining SELECT is not the outermost SELECT of the gold INSERT (93 prompts): states that the scope is an
    intermediate step and that target constraints apply to the final result. It does NOT say "keep NULL".
Frozen text: v5 prompts are built from runs/v4_full_t0/prompts.json (profile "top values"/"sample distinct values" were nondeterministic
under ties; profiling.py now sorts ties, but the v4 text is reused so v4 vs v5 differ only in the three additions).
Run names: v4_full_t0 (baseline), v5_full_t0 (temp 0), v5_t07 (3 repeats, temp 0.7), v5_fresh (fresh Claude agents, 40 sampled columns).

### 4.4 Results of v5 vs v4 (temp 0, 210 cols; `runs/v5_full_t0/compare_vs_v4.txt`)
Exact (reliable-gold 193): nemotron 159->157, mistral 162->163, laguna 122->120. Net ~0, but it hides two opposite effects:
 + WINS that are the intended ones: BatchID exact for every model (spec 4.4.2); SCD EndDate exact on all 4 SCD tables for both big models
   (nemotron 0-2 of 4 -> 4 of 4). So the generic spec conventions work.
 - REGRESSIONS (13 per big model): columns that were 100% in v4 now ~78-95% or fail. Pattern: v5 ADDS a default where v4 left NULL alone,
   e.g. COALESCE(C_TIER,'0'), COALESCE(MaritalStatus,'U'), COALESCE(C_DOB, DATE '1900-01-01'). Seen also on columns with NO scope note
   (Prospect.*), so the note is not the only cause; the spec rows add "Not NULL" (and "'M' or 'F' or 'U'" for Gender).
 Conceptual finding: the spec says these columns are Not NULL / M-F-U, the ported gold (R1's historical_load.sql) leaves NULLs in them.
 When the gold deviates from the spec, adding the documentation makes a spec-correct answer score LOWER. Gold-vs-spec fidelity is a data
 quality issue in its own right (to audit: columns where T contains NULLs although the spec says Not NULL).
 - DimAccount.IsCurrent 89.6 -> 79.7 for both: model now writes ROW_NUMBER() ... ORDER BY ActionTS DESC = 1 (spec-correct, exactly one
   current), but closed accounts have two rows with identical ActionTS (ACTIVE copy + INACTIVE copy), so which one is "current" is
   decided by arbitrary tie order in the gold. Gold-ambiguous column -> propose grading SCD flags structurally (one current per natural
   key, and it is a latest-EffectiveDate row) instead of exact row identity.
 Some regressions are format/noise (prose without SQL, TRIM() on a DECIMAL). Run-to-run drift at temp 0 is NOT yet measured.
Fresh Claude agents (2 agents x 20 columns, v5 prompts, `runs/v5_fresh`): 35/40 exact (87.5%), all 40 executed. Misses: DimAccount.IsCurrent 81.5
 (tie issue), DimCompany.AddressLine2 9.9 and DimCustomer.LastName 78.6 (NULL-defaulting, same pattern as above), DimCompany.isLowGrade 89.7,
 DimSecurity.SK_SecurityID 0.2. Agents reported opening only their own prompt file (not independently verifiable).
 Sample = seeded proportional draw (so only 2 SCD, 1 conditional): small n, wide interval (~87% +/- ~10 pts).

### 4.5 Ablation in progress (decide the final prompt BEFORE spending calls on repeats)
temp-0.7 repeats started on v5 were stopped (partial data kept in runs/v5_t07_partial_abandoned). Running nemotron + mistral only:
 v4_rerun (control: unchanged v4 prompts, measures temp-0 drift) | ab_v5b (spec descriptions only) | ab_v5a (BatchID/SCD conventions only) |
 ab_v5c (intermediate-scope note only, 93 changed columns). Driver: pipeline/run_ablation.sh; compare with compare_runs.py OLD NEW.

## Step 5 — Gold audit against the official TPC-DI validation (2026-11-05)
**Why:** the gold is R1's port, a single unaudited implementation. Before calling the benchmark research-usable, its output was checked against two oracles that do not come from R1's ETL: (a) DIGen's own `*_audit.csv` files (238 files → an `Audit` table, Batch 1 only, because the gold is the historical load) and (b) the official `tpcdi_audit.sql` (spec Clause 7), run verbatim except the portability substitution the script header prescribes (`FROM DUMMY TABLE`, DB2 date arithmetic) and one disclosed column alias (`Type`→`DT_Type`, R1's DDL name).
**Code:** `pipeline/gold_audit.py` (-> `deliverables/gold_audit_results.csv`), `pipeline/build_clean_subset.py` (-> `deliverables/gold_audit_findings.csv`, `deliverables/tpcdi_clean_subset.csv`).
**Result:** 130 audit test queries; 35 not applicable to a Batch-1-only load (need batches 2/3, the ETL's DImessages log, or touch the empty FactMarketHistory/FactWatches, which pass vacuously); of the **89 applicable, 72 pass and 17 fail**. First pass of the harness reported 26 fails; 9 were harness artefacts (3-batch coverage checks, Audit rows from batches 2/3, a column alias) and were fixed before anything was reported.
Findings (all numbers computed live, see findings CSV):
- DimTrade has one row per TradeHistory *event* (982,180 = TH_Records) not per trade (390,978 distinct TradeID); Canceled rows 45,560 vs audit 22,780. FactHoldings inherits it: 930,764 rows vs audit HH_RECORDS 362,342 (join multiplication; CurrentTradeID values themselves are all valid).
- DimAccount: same-day versions not consolidated (2,568 rows), row set below the audit minimum (12,339 < 14,573: no account versions following customer updates).
- DimCustomer prospect-derived fields (AgencyID, CreditRating, NetWorth, MarketingNameplate) carried onto new versions: 966 of 4,721 prospect-matched current rows no longer match, all multi-version customers (not a NULL-concatenation artefact: tested).
- Prospect.MarketingNameplate: 94.1% of rows violate the spec's published rules (gold emits one tag, spec concatenates tags). DimCompany.SPrating: 154 invalid ratings kept (generator injects 10%; spec says NULL them). DimAccount/DimCustomer.Status written ACTIVE/INACTIVE, spec Active/Inactive.
- Version-level FKs (audit date-range join): DimSecurity.SK_CompanyID 27.5%, DimAccount.SK_CustomerID 21.4%, FactCashBalances.SK_CustomerID 43.5% point at a date-invalid version of the right entity.
- Hardcoded entity FKs: an independent constant-column detector finds 9 (DimTrade.SK_{Broker,Security,Company,Customer,Account}ID, FactHoldings.SK_{Customer,Account,Security,Company}ID), all already in the manual `rule_reliable=no` list (0 false positives). The audit's date-range test does NOT catch these (FactHoldings FK checks pass because SK 1's range covers all dates): the audit alone is not sufficient.
**Clean subset (210 populated columns):** clean 147 | clean_column 22 (column ok, its TABLE's row set deviates: DimAccount/DimTrade/FactHoldings) | fk_entity_only 2 | weak 11 (NULL control >=20%) | audit_flagged 11 | known_defect 17. Headline "core" = clean + clean_column + fk_entity_only = 171 (expression-level); 147 clean are the only ones valid for table-level/end-to-end targets. 3 of 20 tables (DimAccount, DimTrade, FactHoldings) have defective row sets, so end-to-end grading must exclude them until the gold is repaired (repair list: F10-F12 + DimTrade event->trade collapse).
**Deliberately not done:** the gold was not edited. Every number in earlier runs is still "vs R1's gold"; the clean subset is a filter on top, not a new gold.

### 5.1 Corrections found while auditing (read before citing earlier statements)
- **Earlier claim retracted:** "the gold keeps NULLs where the spec says Not NULL, so spec-correct answers can mismatch the gold" is wrong at the output level. Checked on all 210 populated columns: 150 have a spec "Not NULL" description and **0** contain NULLs in the gold (`DimCustomer.City`: spec Not NULL, 0 NULLs). The NULLs I had measured live in the *intermediate* CTE (`Customers_Preproc`) where the expression is swapped in; the gold needs them there for its later `COALESCE(UC.x, NC.x)` merges. So the description-induced regressions are a swap-point/NULL-propagation effect (the spec text is true of the final column, misleading for the intermediate expression), not gold defects. Recorded as finding N01 (0/150).
- **Noise floor measured (control = identical v4 prompt, temp 0, complete data):** Mistral 162->160, Nemotron 159->160 exact on the 193 reliable columns, with 4-6 columns flipping each way. Treat |net change| <= ~4 exact columns as noise. (First control attempt was invalid: HTTP 429s left 61-202 cells without an answer; fixed in llm_parallel.py with a shared cooldown + adaptive spacing + 8 tries, and gap-filling driver run_ablation2.sh.)
- **Independent held-out data is not available from DIGen:** changing `<seed>` in PDGF's tpc-di-schema.xml produces byte-identical output (0 differing files, verified); larger SF is a superset of the same rows. A dev/test *column* split is therefore the only held-out mechanism available inside this benchmark (see tpcdi_split.csv); data-level held-out has to come from the other benchmarks (Synthea->OMOP, MIMIC).

### 5.2 Design: end-to-end (table-level) grading — Level 2 (not yet implemented)
Levels: **L1** expression swap-in (current; scope shown, matching given) -> **L1b** scope not shown -> **L2** pipeline emits one INSERT..SELECT per target table and is graded on the tables it produces.
L2 protocol: run the pipeline's SQL in a sandbox copy holding only `Source.*` (targets empty; timeout; no gold access). Per target table: (1) *row set* — match on the natural key (DimBroker.BrokerID, DimCustomer.(CustomerID,EffectiveDate), ...), report key precision/recall and row-count ratio; (2) *columns* — on key-matched rows, per-column agreement using the same exact/partial/wrong classes as L1, with surrogate keys judged by entity identity (map through the referenced dimension's natural key), so L1 and L2 numbers are comparable; (3) *official audit* — run `gold_audit.py --db <sandbox.duckdb>` on the pipeline's output (model-independent validity oracle). Headline = columns exact on matched rows over the clean columns of tables whose gold row set passes the audit (`tpcdi_clean_subset.csv`: table_rowset_ok). DimAccount, DimTrade, FactHoldings are excluded from L2 until the gold is repaired (F10-F12).

### 5.3 Ablation result and prompt freeze (2026-11-05)
Nemotron / Mistral-large exact columns, temp 0, same grader. core171 = audited core (clean + clean_column + fk_entity_only); noise floor |net| ~4.
| arm | core171 (M/N) | core-dev | core-test |
|---|---|---|---|
| v4 (original) | 147 / 144 | 77 / 75 | 70 / 69 |
| v4 rerun (control) | 144 / 145 | 74 / 73 | 70 / 72 |
| v5b descriptions only | 147 / 145 | 73 / 69 | 74 / 76 |
| **v5a conventions only** | **153 / 152** | 81 / 77 | 72 / 75 |
| v5c intermediate note only | 143 / 139 | 75 / 73 | 68 / 66 |
v5a is +6/+8 over v4 and +9/+7 over the rerun: above the noise floor, and the wins are mechanical (BatchID = 1 constant columns, SCD EndDate = 9999-12-31, both stated in spec 4.4.1/4.4.2). Regressions (5 per model) look like ordinary flip noise. Descriptions are neutral; the note is harmful (-4/-6) and is dropped.
**Frozen prompt = v5a** (`deliverables/FROZEN_PROMPT.json`, prompts hash recorded). Provenance: v4 is the untuned baseline; v5a was chosen using failure categories seen on all 210 columns, so the dev/test split does not make v5a's test number independent. Only future changes are protected by the split. Descriptions are not in the frozen prompt (no measurable effect); the user's earlier "do not strip descriptions" applied to the v5 bundle, and this arm-level ablation is the evidence for leaving them out.
Next: step 4 = 3 repeats at temp 0.7 on v5a (`runs/frozen_v5a_t07`), step 5 = non-LLM baselines (`baseline_trivial.py`) and a schema-only recall probe (`contam_probe.py`).

### 5.4 Step 4 and 5 results (2026-11-06) — frozen prompt v5a
**Step 4 (3 repeats, temp 0.7, runs/frozen_v5a_t07, exact columns; mean (min-max)):** core171 Mistral 153.0 (150-157), Nemotron 150.3 (149-152); dev 80.0 / 75.3; test 73.0 / 75.0; unstable columns (exact in some repeats only) 14 / 20. Temp-0.7 spread is about +/-3-4 columns, the same size as the temp-0 noise floor, so differences under ~4 columns between systems are not resolvable on this benchmark.
**Trivial baselines (same task, same given matching; baseline_trivial.py):** `trivial_name` (closest-named matched field, unchanged) = 134/171 core exact; `trivial_mode` (most frequent target value as a constant) = 14/171. The name matcher solves 0 constants, 0 generated keys, 0 SCD-history, 0 conditionals. => the discriminating part of the L1 task is the 37 core columns it cannot solve: Mistral 28-29, Nemotron 29-32 of 37 per repeat. On the 134 easy columns the LLMs still miss ~6-14 per repeat. Report headline results on the 37-column hard subset AND the full 171; never the 171 alone.
**Schema-only recall probe (contam_probe.py; no data, no scope, only target column + bare Source schema; 155 columns with base-table sources):** exact field-set recovered: Nemotron 123/152, Mistral 126/155, name matcher (oracle k) 94/155. On the 61 columns where the name matcher fails: 31/58 and 33/61. Correct answers there are mostly semantic synonyms (EmployeeFirstName->FirstName) plus a few non-obvious ones (isLowGrade<-SPrating, EffectiveDate<-PTS). Failures concentrate where benchmark-specific conventions matter (SK_BrokerID, Status via StatusType, DimCustomer name/tax fields, where Prospect also has the same column names). **Reading:** no evidence of verbatim or benchmark-specific recall, but this probe cannot separate memorisation from semantic inference (no control schema the models cannot have seen). Consequence: matching is ~80% inferable from names alone, so "matching given" is a mild handicap removal, and the clean contamination control must come from Synthea->OMOP / MIMIC.

### 5.5 L2 grader built (2026-11-06) — `benchmark/pipeline/l2_run.py`, `l2_grade.py`, `l2_controls.py`, `l2_compose.py`, `L2_README.md`
Table-level end-to-end grading, reusing fieldgen's row-identity idea: a submission is one SQL file per target table run in a sandbox holding only `Source.*`; rows are matched on natural keys, foreign surrogate keys are translated per side through its own dimension to the entity they point to, a table's own SK is only checked for uniqueness. SCD2 versions / event rows pair k-th with k-th ordered by EffectiveDate (so a wrong date costs the column, not the table). Reports L0 ran, row recall/precision/duplicates, per-column strict agreement (missing rows count wrong), NOT NULL / dangling-FK counts, and optionally the official audit. Sandbox defaults to declared types without constraints (`--constraints strict` enforces them).
**Validation:** C1 gold-as-pipeline = 16/16 tables, 210/210 columns, 0 violations, audit 72/89 (identical to auditing the gold). C2 empty = 0/210. C3 L1<->L2 consistency: 17/18 ordinary columns agree to +/-0.01 pt; the one miss is DimAccount.IsCurrent on the defective same-day-version grain (79.69 vs 79.95); FK columns differ by design (number vs entity).
**First real use — L1 answers composed into whole tables (v5a, temp 0; NOT model-written pipelines):** core171 exact L1 -> L2: Mistral 153 -> 125, Nemotron 152 -> 122; hard-37 28-32 -> 20; tables with correct rows (13 sound-reference) 11/13 for both. Cause: errors cascade through dependent tables — e.g. one failed DimCompany.EffectiveDate expression breaks DimSecurity's date-range join (0 rows) and Financial's company link (0% recall), plus 0.1-2.0M NOT NULL and 3.8-6.7M dangling-FK cells. L1 per-column scores therefore overstate end-to-end correctness by ~28 core columns; end-to-end claims must come from L2.
Not yet done: a pipeline actually written by an LLM end to end (needs a generate-pipeline prompt/harness); repairing the gold; L2 on temp-0.7 repeats.
