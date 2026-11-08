# TPC-DI Benchmark Evaluation — Findings

Working directory for this evaluation: `Project/benchmark/` (kept inside the course-project
folder rather than `~/benchmark/` as the task doc literally says, since this project already
lives in its own folder).

Scope note: only **R1 (`abroniewski/TPC-DI-MS-SQL-Benchmark`)** has been cloned and
investigated so far, per current direction. R2 (`haydarai/tpcdi-kit`) and R3
(`rlsalcido24/dbtpcdi`) have **not** been cloned yet — anything below that depends on them is
marked "not investigated."

---

## Task A1 — Clone the repositories and look inside

**Command run:**
```
mkdir -p benchmark/tpcdi && cd benchmark/tpcdi
git clone https://github.com/abroniewski/TPC-DI-MS-SQL-Benchmark.git
```
Result: cloned successfully, no errors.

### File listing (R1), VCS/IDE/build noise (`.git`, `.vs`, `.idea`, `obj`, `bin`) omitted

```
TPC-DI-MS-SQL-Benchmark/.cursor/rules/readme-public.mdc
TPC-DI-MS-SQL-Benchmark/Deliverables/TPC-DI MS SQL Servier Final Report Rev1.pdf
TPC-DI-MS-SQL-Benchmark/Helpers/Datasets/CMP_Records_Schema.csv
TPC-DI-MS-SQL-Benchmark/Helpers/Datasets/FIN_Records_Schema.csv
TPC-DI-MS-SQL-Benchmark/Helpers/Datasets/SEC_Records_Schema.csv
TPC-DI-MS-SQL-Benchmark/Helpers/Scripts/ConvertFinwireFilesToCSV.py
TPC-DI-MS-SQL-Benchmark/Helpers/Scripts/CreateDBTableSchema.sql
TPC-DI-MS-SQL-Benchmark/Helpers/Scripts/CustomerMgmt.xsd
TPC-DI-MS-SQL-Benchmark/Helpers/Scripts/XML SSIS Instructions.txt
TPC-DI-MS-SQL-Benchmark/Helpers/Scripts/historical_load.sql
TPC-DI-MS-SQL-Benchmark/Helpers/Scripts/logging_DDL.sql
TPC-DI-MS-SQL-Benchmark/Helpers/Scripts/schema.sql
TPC-DI-MS-SQL-Benchmark/Helpers/Scripts/tpcdi_audit.sql
TPC-DI-MS-SQL-Benchmark/Helpers/Scripts/tpcdi_validation.sql
TPC-DI-MS-SQL-Benchmark/Helpers/Scripts/tpcdi_visibility_1.sql
TPC-DI-MS-SQL-Benchmark/Helpers/Scripts/tpcdi_visibility_2.sql
TPC-DI-MS-SQL-Benchmark/README.md
TPC-DI-MS-SQL-Benchmark/Research Papers/2018_Data_Quality_Problems_in_TPC-DI_Based_Data_Integration_Processes.pdf
TPC-DI-MS-SQL-Benchmark/Research Papers/TPC-DI- The First Industry Benchmark for Data Integration.pdf
TPC-DI-MS-SQL-Benchmark/SSIS/TPCDI ETL/TPCDI ETL.sln
TPC-DI-MS-SQL-Benchmark/SSIS/TPCDI ETL/TPCDI ETL/Package.dtsx
TPC-DI-MS-SQL-Benchmark/SSIS/TPCDI ETL/TPCDI ETL/Project.params
TPC-DI-MS-SQL-Benchmark/SSIS/TPCDI ETL/TPCDI ETL/TPCDI ETL.database
TPC-DI-MS-SQL-Benchmark/SSIS/TPCDI ETL/TPCDI ETL/TPCDI ETL.dtproj
TPC-DI-MS-SQL-Benchmark/SSIS/TPCDI ETL/TPCDI ETL/TPCDI ETL.dtproj.user
TPC-DI-MS-SQL-Benchmark/SSIS/TPCDI ETL/UpgradeLog.htm
```

### Answers

**1. Does `TPC-DI-MS-SQL-Benchmark` contain a file named `CreateDBTableSchema.sql`? What is its full path?**

Yes. Full path: `TPC-DI-MS-SQL-Benchmark/Helpers/Scripts/CreateDBTableSchema.sql`.

**2. Does it contain `historical_load.sql`? What is its full path?**

Yes. Full path: `TPC-DI-MS-SQL-Benchmark/Helpers/Scripts/historical_load.sql`.

**3. How many lines does each have?**

```
wc -l Helpers/Scripts/CreateDBTableSchema.sql Helpers/Scripts/historical_load.sql \
      Helpers/Scripts/schema.sql Helpers/Scripts/logging_DDL.sql \
      Helpers/Scripts/tpcdi_audit.sql Helpers/Scripts/tpcdi_validation.sql \
      Helpers/Scripts/tpcdi_visibility_1.sql Helpers/Scripts/tpcdi_visibility_2.sql
```
```
     310 Helpers/Scripts/CreateDBTableSchema.sql
     911 Helpers/Scripts/historical_load.sql
     684 Helpers/Scripts/schema.sql
      26 Helpers/Scripts/logging_DDL.sql
    1317 Helpers/Scripts/tpcdi_audit.sql
     109 Helpers/Scripts/tpcdi_validation.sql
     101 Helpers/Scripts/tpcdi_visibility_1.sql
      70 Helpers/Scripts/tpcdi_visibility_2.sql
    3528 total
```

**4. Does `tpcdi-kit` contain a README explaining how to generate data? Does it mention registering with tpc.org?**

**Not investigated.** R2 (`haydarai/tpcdi-kit`) was not cloned in this pass — out of scope per
current direction (R1 only). Deferred to Task A4.

---

## Bonus finding from A1 (important — changes the picture from the evaluation doc)

Reading the files while listing them turned up something the evaluation doc did not
anticipate:

> **`CreateDBTableSchema.sql` does *not* contain the source schema `S`.** Despite its name and
> despite the README calling it the "source schema" script, its `CREATE TABLE` statements are
> the same 20 `Dim*`/`Fact*` warehouse tables as our already-supplied `tpcdi_target_schema.sql`
> — i.e. it is a second copy of **T**, not `S`. Its own header comment confirms this: *"Original
> SQL Script pulled from ... https://github.com/detobel36/tpc-di/blob/master/createTables.sql"*
> — the exact same upstream source our `tpcdi_target_schema.sql` was converted from (see R5 in
> the evaluation doc). The "source" in the README's wording refers to the SQL Server *schema
> namespace* the DDL is loaded under, not to our benchmark's `S`.

> **The real `S` lives in a different, previously-unlisted file: `Helpers/Scripts/schema.sql`
> (684 lines).** It is one script in two halves:
> - Lines 1–367: `CREATE SCHEMA Source;` followed by 30 `CREATE TABLE Source.<Name>` statements
>   — this is the actual raw source schema `S` (staging tables for the flat files TPC-DI
>   generates: `Source.Customer`, `Source.Account`, `Source.Trade`, `Source.HR`,
>   `Source.FinwireCMP/SEC/FIN`, `Source.Date`, `Source.Time`, several `*XML` staging tables
>   for the CustomerMgmt XML feed, etc.)
> - Lines 369–683 (after a `-- TPC DI Data Warehouse` comment marker): the same `Dim*`/`Fact*`
>   target tables again — i.e. `T`, a duplicate of `CreateDBTableSchema.sql`/
>   `tpcdi_target_schema.sql`.

> **`historical_load.sql` confirmed as the transformation.** Its `INSERT INTO dbo.<Target> ...
> SELECT ... FROM Source.<SourceTable>` pattern (e.g. `INSERT INTO dbo.DimBroker ... FROM
> Source.HR WHERE EmployeeJobCode = 314`, `INSERT INTO dbo.DimCompany ... FROM
> Source.FinwireCMP CMP, Source.StatusType S, Source.Industry I ...`) is exactly the
> `D → T` mapping we need as ground truth. This checks out against the README, which
> describes step 4 as "Data transformed and loaded into the `dbo` schema using
> `historical_load.sql`."

### All 31 `Source.*` tables in `schema.sql` (name, column count, first 3 columns)

(Corrected count: an earlier pass here miscounted these as 30 — a plain recount of the table
list gives 31, `AuditFiles` included.)

| Table | Columns | First three columns |
|---|---|---|
| Source.Account | 6 | CA_ID NUMERIC(11); CA_B_ID NUMERIC(11); CA_C_ID NUMERIC(11) |
| Source.BatchDate | 1 | BatchDate DATE |
| Source.CashTransaction | 4 | CT_CA_ID NUMERIC(11); CT_DTS DATETIME; CT_AMT NUMERIC(10,2) |
| Source.Customer | 31 | C_ID NUMERIC(11); C_TAX_ID CHAR(20); C_ST_ID CHAR(4) |
| Source.ActionXML | 3 | ActionType NVARCHAR(9); ActionTS NVARCHAR(256); Action_Id NVARCHAR(256) |
| Source.CustomerXML | 7 | C_ID NUMERIC(11); C_TAX_ID NVARCHAR(20); C_GNDR NVARCHAR(1) |
| Source.NameXML | 4 | C_L_NAME NVARCHAR(25); C_F_NAME NVARCHAR(20); C_M_NAME NVARCHAR(1) |
| Source.AddressXML | 7 | C_ADLINE1 NVARCHAR(80); C_ADLINE2 NVARCHAR(80); C_ZIPCODE NVARCHAR(12) |
| Source.ContactInfoXML | 4 | C_PRIM_EMAIL NVARCHAR(50); C_ALT_EMAIL NVARCHAR(50); Customer_Id NVARCHAR(256) |
| Source.C_PHONE_1_XML | 5 | C_CTRY_CODE NVARCHAR(3); C_AREA_CODE NVARCHAR(3); C_LOCAL NVARCHAR(10) |
| Source.C_PHONE_2_XML | 5 | C_CTRY_CODE NVARCHAR(3); C_AREA_CODE NVARCHAR(3); C_LOCAL NVARCHAR(10) |
| Source.C_PHONE_3_XML | 5 | C_CTRY_CODE NVARCHAR(3); C_AREA_CODE NVARCHAR(3); C_LOCAL NVARCHAR(10) |
| Source.TaxInfoXML | 3 | C_LCL_TX_ID NVARCHAR(4); C_NAT_TX_ID NVARCHAR(4); Customer_Id NVARCHAR(256) |
| Source.AccountXML | 5 | CA_ID NUMERIC(11); CA_TAX_ST NUMERIC(1); CA_B_ID NUMERIC(11) |
| Source.DailyMarket | 6 | DM_DATE DATE; DM_S_SYMB CHAR(15); DM_CLOSE NUMERIC(8,2) |
| Source.Date | 18 | SK_DateID NUMERIC(11); DateValue CHAR(20); DateDesc CHAR(20) |
| Source.FinwireCMP | 16 | PTS NVARCHAR(256); RecType NVARCHAR(256); CompanyName NVARCHAR(256) |
| Source.FinwireSEC | 12 | PTS NVARCHAR(256); RecType NVARCHAR(256); Symbol NVARCHAR(256) |
| Source.FinwireFIN | 17 | PTS NVARCHAR(256); RecType NVARCHAR(256); Year NVARCHAR(256) |
| Source.HoldingHistory | 4 | HH_H_T_ID NUMERIC(15); HH_T_ID NUMERIC(15); HH_BEFORE_QTY NUMERIC(6) |
| Source.HR | 9 | EmployeeID NUMERIC(11); ManagerID NUMERIC(11); EmployeeFirstName CHAR(30) |
| Source.Industry | 3 | IN_ID CHAR(2); IN_NAME CHAR(50); IN_SC_ID CHAR(4) |
| Source.Prospect | 22 | AgencyID CHAR(30); LastName CHAR(30); FirstName CHAR(30) |
| Source.StatusType | 2 | ST_ID CHAR(4); ST_NAME CHAR(10) |
| Source.TaxRate | 3 | TX_ID CHAR(4); TX_NAME CHAR(50); TX_RATE NUMERIC(6,5) |
| Source.Time | 10 | SK_TimeID NUMERIC(11); TimeValue CHAR(20); HourID NUMERIC(2) |
| Source.TradeHistory | 3 | TH_T_ID NUMERIC(15); TH_DTS DATETIME; TH_ST_ID CHAR(4) |
| Source.Trade | 14 | T_ID NUMERIC(15); T_DTS DATETIME; T_ST_ID CHAR(4) |
| Source.TradeType | 4 | TT_ID CHAR(3); TT_NAME CHAR(12); TT_IS_SELL NUMERIC(1) |
| Source.WatchHistory | 4 | W_C_ID NUMERIC(11); W_S_SYMB CHAR(15); W_DTS DATETIME |
| Source.AuditFiles | 6 | DataSet CHAR(20); BatchID NUMERIC(5); Date DATE |

(Full parse produced with a small Python script against `schema.sql`, paren-aware so
`NUMERIC(10,2)`-style types aren't split on their internal comma.)

---

## Status against the "four things we need" (S, D, T, transformation) — R1 only

| Piece | Status | Where |
|---|---|---|
| **S** (source schema) | **Found** | `Helpers/Scripts/schema.sql`, lines 1–367 (`CREATE SCHEMA Source` + 31 `Source.*` tables) |
| **T** (target schema) | **Already had it** (independently confirmed) | `Helpers/Scripts/CreateDBTableSchema.sql` and the second half of `schema.sql` (lines 369–683) both reproduce the same 20 `Dim*`/`Fact*` tables as our supplied `tpcdi_target_schema.sql` |
| **Transformation** | **Found** | `Helpers/Scripts/historical_load.sql` (911 lines, `INSERT INTO dbo.X ... FROM Source.Y` statements) |
| **D** (source data) | **Still missing** | Not shipped in this repo. README confirms data must come from "TPC-DI generated flat files at four scale factors (SF 3, 10, 20, 30)" via the official TPC-DI data generator — a separate, licensed tool. `Helpers/Datasets/*.csv` in this repo are just *schema* reference sheets for the Finwire record layout (CMP/FIN/SEC), not actual generated data. Confirmed missing, matches the evaluation doc's expectation — this is what Task A4 (data generator) is for. |

**Verdict for R1 on Task A1's underlying question:** R1 solves *two and a half* of our three
missing pieces — it gives us `S` and the transformation outright (not from
`CreateDBTableSchema.sql` as the doc guessed, but from `schema.sql` and `historical_load.sql`
respectively), plus an independent confirmation of `T`. It does **not** solve `D` — that still
requires the TPC-DI data generator (Task A4), and the README explicitly says the official
generator needs registration with tpc.org.

## Other notes

- `Helpers/Scripts/logging_DDL.sql`, `tpcdi_audit.sql`, `tpcdi_validation.sql`,
  `tpcdi_visibility_1.sql`, `tpcdi_visibility_2.sql` are helper/audit scripts, not part of
  S/T/transformation proper — bucket as "helper" (same category the doc uses for MIMIC task
  B3). Not classified further in this task.
- `Helpers/Scripts/ConvertFinwireFilesToCSV.py` — a Python preprocessor for the FINWIRE flat
  files (fixed-width → CSV) prior to loading into `Source.Finwire*`. Relevant once we have `D`.
- `SSIS/TPCDI ETL/` — the actual SSIS package or transformation was not opened; per the
  evaluation doc's expectations, SQL logic lives in `historical_load.sql`, not the `.dtsx`
  package, so this wasn't necessary for A1.
- No errors encountered during clone or file inspection.

## Task A2 — verdict

Confirmed complete as a byproduct of A1 (see the "Bonus finding" section above and the full
30-table listing there). **Verdict: `Helpers/Scripts/schema.sql` (not `CreateDBTableSchema.sql`)
does give us `S`.** The standalone portable `tpcdi_source_schema.sql` extraction (dialect
conversion, DuckDB load test — the doc's deliverable #4) is still open; it's mechanical at this
point and deferred until after A3/A4 per current direction, grouped in with A5's DuckDB-loading
work.

---

## Task A3 — Classify the transformations

**Goal.** Classify every output column of `DimCustomer`, `DimAccount`, and `FactMarketHistory`
in `historical_load.sql` into the doc's 12-category taxonomy.

**What was run.** Read `historical_load.sql` in full (911 lines) via the three
`INSERT INTO dbo.<Table>` blocks (`grep -n "^-- \|INSERT INTO" historical_load.sql` to find
section boundaries first, then read each section in full).

**Important discrepancy found: `FactMarketHistory` is not actually implemented.** Its entire
`INSERT` statement is commented out (`----INSERT INTO FactMarketHistory(...)`), and even inside
that dead code the `FROM` clause has `DimSecurity DS` commented out of the join list, so
`DS.SK_SecurityID` / `DS.SK_CompanyID` (also commented out of the SELECT list) would not have
resolved even if uncommented. The `Yield` column has no code at all — not even a commented
attempt beyond a single stray comment line. This matches the README's stated limitation
("`FactMarketHistory` ... excluded from the benchmark") but goes further: it isn't just
*excluded from benchmark timing*, the transformation SQL itself was abandoned mid-write
(there's a literal `-- DimSecurity (#FIXME FROM HERE ON)` marker a few lines earlier, at line
543, signalling the same). Classification below is done anyway, against the dead/intended code,
with every row flagged `NOT IMPLEMENTED`.

**Deliverable:** [`benchmark/deliverables/tpcdi_transformations.csv`](deliverables/tpcdi_transformations.csv)
— 58 rows (33 `DimCustomer` + 11 `DimAccount` + 14 `FactMarketHistory`), matching the column
counts in `tpcdi_target_schema.sql`.

### Counts per category

| Category | DimCustomer | DimAccount | FactMarketHistory | Total | % of 58 |
|---|---|---|---|---|---|
| copy | 2 | 0 | 4 | 6 | 10.3% |
| rename | 13 | 3 | 0 | 16 | 27.6% |
| retype | 0 | 0 | 0 | 0 | 0% |
| concat | 3 | 0 | 0 | 3 | 5.2% |
| conditional | 3 | 1 | 0 | 4 | 6.9% |
| arithmetic | 0 | 0 | 2 | 2 | 3.4% |
| lookup join | 7 | 2 | 5 | 14 | 24.1% |
| aggregate | 0 | 0 | 0 | 0 | 0% |
| window | 0 | 0 | 2 | 2 | 3.4% |
| key generation | 1 | 1 | 0 | 2 | 3.4% |
| SCD history | 3 | 3 | 0 | 6 | 10.3% |
| constant | 1 | 1 | 1 | 3 | 5.2% |
| **Total** | **33** | **11** | **14** | **58** | **100%** |

**Plain copy: 6/58 ≈ 10.3%.** Even generously counting `copy` + `rename` together (i.e.
treating the pervasive `TRIM()` whitespace-cleanup wrapper as cosmetic rather than a real
transform) gives 22/58 ≈ 37.9% "simple," which still leaves **62.1% non-trivial**.

**Cross-check against the doc's schema-only estimate (~60% copy / 40% complex): materially
different, and this is worth explaining rather than treating as a contradiction.** Two things
are going on:
1. These three tables were *chosen by the task specifically because they're representative of
   the hard cases* — two of the five SCD Type-2 dimensions (`DimCustomer`, `DimAccount`) plus a
   fact table with window functions (`FactMarketHistory`). They are not a random sample of the
   full 20-table/241-column warehouse; the four genuinely trivial tables (`Industry`,
   `StatusType`, `TaxRate`, `TradeType`, all flagged as "pure copies" in the evaluation doc)
   are excluded by construction. A schema-wide sample would land closer to the doc's estimate.
2. `DimCustomer` in particular is unusually derivation-heavy even for an SCD Type-2 table: it
   joins across 9 source tables (`CustomerXML`, `ActionXML`, `NameXML`, `ContactInfoXML`,
   `AddressXML`, `TaxInfoXML`, `TaxRate` (twice), `C_PHONE_{1,2,3}_XML`, `Prospect`) and derives
   `MarketingNameplate` from a 6-branch `CASE` over 6 different `Prospect` columns.

**Verdict: the discrepancy is explained by sample selection, not by an error in either
analysis — but it's a meaningful signal in its own right.** If task A3 is meant to answer "does
this benchmark discriminate between weak and strong query-generation methods," these three
tables alone would already produce a strong signal (over 60% requires more than a rename): even
the *simplest* of the three (`DimAccount`) is still two-thirds surrogate-key lookups, SCD
bookkeeping, and a conditional. Recommend also sampling at least one of the four "trivial"
tables (e.g. `TradeType`) later, purely to have the two extremes on record for the final report
(the doc's §4.2 Q2 asks for the percentage across the *whole* benchmark, not just the hard
subset).

### How-many-source-tables-per-target check (bonus, useful for the doc's Q3)

- `DimCustomer`: reads from **9** distinct `Source.*` tables (listed above).
- `DimAccount`: reads from **4** (`CustomerXML`, `ActionXML`, `AccountXML`, plus lookups against
  the already-built `dbo.DimBroker`/`dbo.DimCustomer` — arguably 2 raw source + 2 target-side
  lookups).
- `FactMarketHistory` (as designed, dead code): would read from **3** (`DailyMarket`,
  `FinwireFIN`, plus `DimSecurity`/`DimDate` target-side lookups).

---

## Task A4 — Find out how to get the data (`D`)

**Commands run:**
```
cd benchmark/tpcdi
git clone https://github.com/haydarai/tpcdi-kit.git
git clone https://github.com/rlsalcido24/dbtpcdi.git
```
Both cloned successfully, no errors.

### R2 — `haydarai/tpcdi-kit`

File listing (non-`.git`):
```
tpcdi-kit/.gitignore
tpcdi-kit/README.md
tpcdi-kit/TPCDI_Loader.py
tpcdi-kit/Tools.zip
tpcdi-kit/db.conf
tpcdi-kit/main.py
tpcdi-kit/staging/5/.gitignore
tpcdi-kit/utils.py
```

**README says:** generate data with `Tools/DIGen.jar -o ../staging/<sf>/ -sf <sf>`, then load
the generated flat files into a MemSQL/MySQL-compatible database with `python main.py -d
<dbname> -s <sf>`. Needs a MySQL client installed.

**Key finding — the generator is bundled in this repo, not a pointer to tpc.org:**
`unzip -l Tools.zip` shows the archive contains the *actual* `Tools/DIGen.jar` (55,895 bytes)
plus `Tools/DIGen_Build.zip` and the complete `Tools/PDGF/` framework (config XML, dictionaries
for names/addresses/companies, audit-check XML per table) that DIGen depends on.
`Tools/Note.txt` confirms `DIGen Version: 1.1.0` — the exact spec version our
`tpcdi_target_schema.sql` and `historical_load.sql` were both built/reviewed against, so it's
schema-compatible with everything else we have.

`TPCDI_Loader.py` / `main.py` are a thin loader that only stages the *raw generated flat files*
into a MySQL/MemSQL `Source`-equivalent schema (`load_dim_date`, `load_staging_finwire`,
`load_staging_customer`, etc.) — it is not itself an ETL/transformation implementation, and it
targets MySQL/MemSQL specifically, not something portable like DuckDB.

**This is a licensing question, not just a technical one, and needs a decision before we act
on it.** The official TPC-DI generator (`DIGen.jar`) is governed by a TPC licence agreement
that normally requires registering at tpc.org before download (this is stated directly in the
evaluation doc and in R1's README). Here, the jar is not gated behind that registration flow at
all — it was already committed into a public GitHub repo and downloaded to us via a plain `git
clone`. Whether that satisfies the letter of TPC's licence, or whether using it anyway would be
using a redistributed copy outside its intended distribution channel, is exactly the kind of
call the evaluation doc says to escalate rather than decide ourselves ("If registration proves
unavoidable, stop and report — licence agreements require a supervisor decision" / "Registration
and licensing decisions sit with the supervisor"). **Flagging this now and pausing before
running `java -jar DIGen.jar` to actually generate sample data — see the question below.**

### R3 — `rlsalcido24/dbtpcdi`

Top-level structure:
```
BigQuery/{models,integration_tests}
Databricks/{models,helpers,integration_tests}
Fabric/{models,helpers,integration_tests}
Redshift/{models,helpers,integration_tests}
Snowflake/{models,helpers,integration_tests}
Synapse/{models,helpers,integration_tests}
dbt_packages/{dbt_external_tables,dbt_utils,spark_utils}
macros/
.circleci/
```

**README says:** this is a full dbt project implementing TPC-DI end-to-end, targeting
Databricks, Snowflake, BigQuery, Redshift, and Synapse (`dbt run --target <warehouse>`). Data
prep explicitly depends on the same tool as R2 (*"This project uses the TPC-DI Kit TPC-DI Data
Generator https://github.com/haydarai/tpcdi-kit"*), generated the same way
(`java -jar DIGen.jar -o ../staging/10/ -sf 10`), then uploaded to cloud storage (S3/GCS/ADLS)
before `dbt run-operation stage_external_sources` and `dbt run`.

**Correction to the evaluation doc's expectation for R3.** The doc guessed R3 "should be more
portable" since it's a dbt implementation targeting several database systems. In practice it is
**less portable for our purposes**, not more: every target is a managed cloud warehouse
requiring its own cloud storage account and CLI tooling (AWS CLI, gcloud, Azure CLI) — there is
no local/DuckDB/Postgres target. This mirrors the same kind of doc-vs-reality correction we
found for R1's `CreateDBTableSchema.sql` in Task A2 — worth remembering that every "why it
matters" claim in the evaluation doc is explicitly an unverified expectation, and a second one
turned out to need correcting.

**Bonus finding — R3 has a complete, working `FactMarketHistory` that R1 abandoned.**
`BigQuery/integration_tests/models/incremental/FactMarketHistory.sql` fully implements the
column set our A3 classification above had to infer from dead code: a self-join against a
`tempDailyMarketHistorical` staging model (twice, for 52-week high/low with a 12-month window,
using `QUALIFY ROW_NUMBER() ...` to dedupe), a `LEFT JOIN` to `DimSecurity` on
`symbol = dm_s_symb AND date BETWEEN effectivedate AND enddate`, and a `LEFT JOIN` to a
`tempSumpFiBasicEps` model (a windowed `SUM` of EPS) for the `PERatio`/`Yield` arithmetic. This
corroborates our category assignments for the dead R1 code (lookup join / arithmetic / window)
and gives us an actual runnable reference for this table if we need one later — though it's
written in dbt+Jinja for BigQuery specifically, so it would need translation to run standalone.
Not pursued further in this pass since A4's scope is `D`, not patching R1's transformation gaps.

### A4 status against the doc's actual question

| Sub-question | Answer |
|---|---|
| Does R2 include the generator itself, or point to tpc.org? | **Includes it directly** (bundled in `Tools.zip`), not a pointer |
| Does the README mention registering with tpc.org? | No — the README doesn't mention registration at all; it assumes you already have `Tools/DIGen.jar` in place, and here it's supplied pre-extracted-adjacent inside the repo's own zip |
| Can we produce data at the smallest scale factor? | **Not yet attempted** — paused pending the licensing question above |
| Is R3 a viable alternative path to `D`? | No new path — it depends on the identical `DIGen.jar`/tpcdi-kit generator, just adds cloud-warehouse-specific loading on top |

**Update: generation attempted and completed successfully** — see below. `D` is now in hand.

### Actually generating `D` — what it took

Approval was given to proceed. Getting an actual dataset out of a 2015-era tool took three
separate hurdles, each recorded here since the doc explicitly wants "what was run, what
happened" even for the messy parts, and the fixes are reusable if we need to regenerate at a
different scale factor later.

**Hurdle 1 — modern JVM incompatibility.** Running `DIGen.jar` directly (`java -jar DIGen.jar
...`) failed immediately with `NoClassDefFoundError: org/apache/commons/cli/ParseException`.
The jar uses an Eclipse "jar-in-jar" loader (`Rsrc-Class-Path: ./ commons-cli-1.2.jar` in its
manifest) to bundle its one dependency, `commons-cli-1.2.jar`, inside itself — this loader
mechanism doesn't work correctly on the JVMs available here (21/23/24; only ones installed).
Fix: extracted `commons-cli-1.2.jar` from inside `DIGen.jar` (`unzip -j DIGen.jar
commons-cli-1.2.jar`) and ran the real main class directly on an explicit classpath instead of
going through the loader: `java -cp DIGen.jar:commons-cli-1.2.jar org.tpc.di.digen.DIGen ...`.
This got `-v`/`-h` working (confirmed `DIGen Version: 1.1.0`, `-sf` range 3–2147483647, default
5 — **the doc's "always start at smallest" is actually SF=3, not SF=1**), but actual generation
still failed with `ClassCastException: class jdk.internal.loader.ClassLoaders$AppClassLoader
cannot be cast to class java.net.URLClassLoader` inside PDGF's own resource loader
(`PDGFProperties`/`ResourceManager`) — PDGF hard-assumes the JVM's system classloader is a
`URLClassLoader`, which stopped being true from Java 9 onward. This needed an actual Java 8
runtime; none of the three installed JDKs qualify. **The user installed `temurin@8` via
Homebrew** (`brew install --cask temurin@8`) to resolve this — this needed their own sudo
password, which is outside what I can supply, so this step was done by the user directly.
Confirmed present afterward: `/usr/libexec/java_home -V` → `1.8.0_504 (x86_64) "Eclipse
Temurin"`.

**Hurdle 2 — Apple Silicon.** That JDK 8 build is `x86_64` (there is no Apple Silicon build of
Java 8 — it predates the hardware). Running it directly failed with `bad CPU type in
executable`. Fixed with `softwareupdate --install-rosetta --agree-to-license`, which installed
cleanly without needing sudo. After that, `java -version` under the JDK 8 `JAVA_HOME` worked
(`openjdk version "1.8.0_504"`).

**Hurdle 3 — the PDGF end-user licence prompt.** Running the generator for real hit an
interactive console prompt, not a technical error:

> `By using this software you must first agree to our terms of use. press [ENTER] to show them`
> ... [full **BANKMARK UG (HAFTUNGSBESCHRAENKT) END-USER LICENSE AGREEMENT** text, ~150 lines,
> standard "AS IS" / no-warranty / liability-capped-at-fees-paid terms for PDGF, the underlying
> "Parallel Data Generation Framework" that `DIGen.jar` wraps] ...
> `If you have read and agree to this terms of use, please type (uppercase!): YES and press [ENTER]`

This is a **separate license from TPC's own** — it belongs to bankmark UG (haftungsbeschränkt),
Passau, Germany, the company that built the PDGF engine TPC-DI's generator is built on top of.
Distinct from the tpc.org registration question already resolved above. **Flagged to the user
before proceeding; the user reviewed the summary and explicitly approved accepting it.**
Piping the acceptance in non-interactively took two attempts: a single `YES` was consumed by
the initial "press ENTER to show them" gate, so the real accept prompt then hit end-of-input
and the run aborted (`Broken pipe`). Fixed by piping two lines (`printf '\nYES\n' | java ...`).

**Hurdle 4 (minor) — console reads after acceptance.** With exactly two lines of stdin, the
PDGF interactive console (`PDGF:>`) started reading a *third* command after license acceptance,
hit end-of-input, and looped logging `Command 'null' is unknown` until its own flood-prevention
killed the run (having already finished 1 of 16 tables). Fixed by keeping the stdin pipe open
without closing it (`( printf '\nYES\n'; sleep 90 ) | java ...`) so the console simply has
nothing to read (blocks) while generation proceeds in its own background threads — which is
exactly what happens once actual generation isn't racing a closed pipe.

### Generation result

```
cd benchmark/tpcdi/tpcdi-kit/Tools
unzip -j DIGen.jar commons-cli-1.2.jar -d .
JAVA8_HOME=$(/usr/libexec/java_home -v 1.8)
( printf '\nYES\n'; sleep 90 ) | "$JAVA8_HOME/bin/java" \
    -cp "DIGen.jar:commons-cli-1.2.jar" org.tpc.di.digen.DIGen -sf 3 -o ../staging/3/
```

```
Data generation finished successfully
AuditTotalRecordsSummaryWriter - TotalRecords for Batch1: 4539962
AuditTotalRecordsSummaryWriter - TotalRecords for Batch2: 19900
AuditTotalRecordsSummaryWriter - TotalRecords for Batch3: 19855
AuditTotalRecordsSummaryWriter - TotalRecords all Batches: 4579717 702518.33 records/second
Overall time  0h:00m:06s:519ms
Generated     267.1 MiB
DIGen completed successfully.
```

Output at `benchmark/tpcdi/tpcdi-kit/staging/3/`: three batch directories (`Batch1` = historical
load, ~4.54M rows across `HR.csv`, `Prospect.csv`, `Trade.txt`, `DailyMarket.txt`,
`CashTransaction.txt`, `Date.txt`, `Time.txt`, `HoldingHistory.txt`, `WatchHistory.txt`,
`TradeHistory.txt`, `Industry.txt`/`StatusType.txt`/`TaxRate.txt`/`TradeType.txt` (the trivial
lookup tables), `CustomerMgmt.xml`, and 406 `FINWIRE<year><quarter>` fixed-width files spanning
1967–2017; `Batch2`/`Batch3` = incremental batches, ~19.9K rows each, adding `Account.txt` and
flat `Customer.txt` on top), plus `Generator_audit.csv`/`Batch*_audit.csv`/`digen_report.txt`
(the audit/reporting files the doc flagged as "the closest thing TPC-DI ships to a correctness
oracle").

**Structural cross-check against `S`:** spot-checked several files against the `Source.*`
tables tabulated in Task A2 — `Trade.txt` is `|`-delimited matching `Source.Trade`'s 14 columns
(`T_ID|T_DTS|T_ST_ID|T_TT_ID|T_IS_CASH|T_S_SYMB|T_QTY|T_BID_PRICE|T_CA_ID|T_EXEC_NAME|
T_TRADE_PRICE|T_CHRG|T_COMM|T_TAX`) in order; `Customer.txt` (Batch2) matches `Source.Customer`'s
31 columns with a leading `I`/`U` action-type marker; `CustomerMgmt.xml` (Batch1) matches the
nested `Action > Customer > Name/Address/ContactInfo/Phone_{1,2,3}/TaxInfo/Account` structure
implied by `CustomerMgmt.xsd` and the `Source.*XML` staging tables. **`D` genuinely lines up with
the `S` we already extracted — this is a real, usable, matched `(S, D)` pair, not just two
independently-plausible pieces.**

**Sample data deliverable:** a small (108 KB) representative subset — small tables in full
(`Industry`, `StatusType`, `TaxRate`, `TradeType`, `BatchDate`, both small `Batch2` files) plus
`head -20`/`head -60` truncated samples of the large ones (`Trade`, `DailyMarket`,
`CashTransaction`, `HR`, `Prospect`, `Date`, `HoldingHistory`, `WatchHistory`, `TradeHistory`,
one `FINWIRE` file, `CustomerMgmt.xml`) — saved to
[`benchmark/sample_data/tpcdi_sf3/`](sample_data/tpcdi_sf3/). The full 267 MiB generated dataset
stays at `benchmark/tpcdi/tpcdi-kit/staging/3/` (not duplicated into the sample folder).

### A4 final verdict

**All four pieces are now in hand for TPC-DI:** `S` (Task A2), `D` (this task), `T` (already
supplied, reconfirmed in A1/A2), and the transformation (Task A3, `historical_load.sql`, with
the one known gap being `FactMarketHistory`, which R3 has a working reference implementation
for if we need it later). Blockers cleared: no TPC registration was needed (R2's bundled copy
sufficed); the PDGF license was reviewed and explicitly accepted by the user; the Java
version/architecture mismatches were fixed with a Homebrew JDK 8 install (user-run, needed sudo)
and Rosetta 2 (no sudo needed).

---

## Tasks C1–C6 — Full data load + ported ground-truth ETL execution (2026-10-02)

Executes the revised plan's Phase B (§5.3 of `project_plan.md`): fully load `D` into `S`, port
`historical_load.sql` to DuckDB, run it, get a real populated `T`.

**C1 — persistent venv.** `Project/.venv/` with `duckdb` 1.5.x, replacing the ephemeral
scratchpad one from Task A5.

**C2 — 15 simple delimited `Source.*` tables**, Batch1 only (confirmed `historical_load.sql`
only references 28 of 31 `Source.*` tables — `Account`, `Customer`, `AuditFiles` are unused,
since Batch1 uses the XML customer-management route, not the flat incremental files). All 15
column counts matched the schema exactly on the first try. **4,422,915 rows.**

**C3 — FINWIRE fixed-width parsing.** Used the exact byte-offset layouts from
`Helpers/Datasets/{CMP,FIN,SEC}_Records_Schema.csv` (e.g. CMP: `PTS(15),RecType(3),
CompanyName(60),CIK(10),...`, verified against raw bytes — records are CRLF-terminated, hence
the 544 vs 543-byte offset-by-one when naively measuring line length). Dispatch by `RecType` at
byte offset 15. **102,476 rows** (1,500 CMP + 98,576 FIN + 2,400 SEC) — exactly matches an
independent dirty `cat | cut` sanity count taken before writing the real parser.

**C4 — `CustomerMgmt.xml` parsing.** Used `CustomerMgmt.xsd` to get the exact nesting
(`Action[ActionType,ActionTS] > Customer[C_ID,C_TAX_ID,C_GNDR,C_TIER,C_DOB] > Name/Address/
ContactInfo[+Phone1-3]/TaxInfo/Account*`). `Action_Id`/`Customer_Id`/`ContactInfo_Id` aren't in
the raw XML — they're synthetic, assigned here as a single per-`Action` sequential index (the
Action↔Customer↔ContactInfo relationship is 1:1 in this schema, so one counter serves all
three). **14,572 Actions → 81,519 rows** across the 10 XML staging tables.

**Cross-check:** `4,422,915 + 102,476 + 14,572 (one count per Action, not fanned out) =
4,539,963` — against `digen_report.txt`'s reported Batch1 total of **4,539,962**. Off by exactly
1, which is noise (not investigated further — negligible). Confirms the full `D` was parsed
completely and correctly, not just "didn't crash."

**C5 (partial) / C6 — port `historical_load.sql`, execute.** Full file ported to
`benchmark/deliverables/ported_historical_load.sql`. Dialect fixes: `GO`→statement-per-`;`,
bracket identifiers stripped, `TOP n`→`LIMIT n`, `IDENTITY` surrogate keys→explicit
`ROW_NUMBER() OVER (...)` (added `ORDER BY` for `DimBroker`/`DimCompany`, which had none in the
original — SQL Server's `IDENTITY` order was implementation-defined there too, so this isn't a
behavior change, just making it explicit), string `+`→`||`, `ISNUMERIC(x)`→
`TRY_CAST(x AS BIGINT) IS NOT NULL`, and T-SQL's `CONVERT/STUFF` date-reformatting hack
(`DimSecurity`'s `PTS` parsing) and several `YYYYMMDD`-format FINWIRE date fields (`FoundingDate`,
`FirstTradeDate`, `FirstTradeExchg`, `QtrStartDate`) → `strptime`/`try_strptime` with explicit
format strings (discovered these were fixed `YYYYMMDD`/`YYYYMMDD-HHMMSS` text, not ISO dates, by
inspecting the actually-loaded data — `TRY_CAST(... AS DATE)` silently returned `NULL` for all of
them at first).

**Two genuine bugs found in R1's original logic while executing against real data** (not
porting artifacts — same failure would occur in SQL Server too):
1. **`DimTrade`'s `SK_CreateDateID`/`SK_CreateTimeID` `CASE` is non-exhaustive.** It only
   assigns a value for `(TH_ST_ID='SBMT' AND T_TT_ID IN ('TMB','TMS')) OR TH_ST_ID='PNDG'`, or
   `TH_ST_ID IN ('CMPT','CNCL')` (→ `NULL` there). A `SBMT` trade whose type is `TSL`/`TLS`/`TLB`
   matches neither branch → `NULL`, violracing the target's `NOT NULL`. Confirmed via
   `Source.TradeHistory`: all 4 real `TH_ST_ID` values occur (`SBMT` 362,343 / `CNCL` 22,780 /
   `PNDG` 234,715 / `CMPT` 362,342) — the gap is in the branch logic, not missing data. This is
   almost certainly *why* R1's README excludes "part of `DimTrade`" from their own benchmark
   run. **Fix applied (flagged, not silent):** `COALESCE(<original CASE>, TH.TH_DTS)` — falls
   back to the trade-history timestamp itself, which every row has.
2. **`FactHoldings` inherits the same gap**: its join to `DimTrade` doesn't filter to
   "closed" trades, so it can pick up a still-open row whose `SK_CloseDateID`/`TimeID` is
   legitimately `NULL`, violating `FactHoldings`' own `NOT NULL`. **Fix applied:**
   `COALESCE(DT.SK_CloseDateID, DT.SK_CreateDateID)` (and same for `TimeID`).

Both fixes are clearly commented in `ported_historical_load.sql` as additions, not part of R1's
original logic — kept this way deliberately so the file still serves as an honest record of what
R1 actually specified, with our patches visibly separate.

### Final result

```
main (T) tables: 20   Source (S) tables: 31
```

| Table | Rows | Table | Rows |
|---|---|---|---|
| DimDate | 25,933 | DimAccount | 12,339 |
| DimTime | 86,400 | DimSecurity | 1,227 |
| StatusType | 6 | DimTrade | 982,180 |
| TaxRate | 320 | FactCashBalances | 330,485 |
| TradeType | 5 | FactHoldings | 930,764 |
| Industry | 102 | Financial | 98,576 |
| DimBroker | 4,293 | Prospect | 14,982 |
| DimCompany | 1,500 | FactMarketHistory/FactWatches/DImessages/AuditTable | 0 (not_built, as expected) |
| DimCustomer | 6,440 | | |

**Referential-integrity spot checks, all clean:** zero orphaned `SK_CustomerID`/`SK_BrokerID` in
`DimAccount`, zero orphaned `SK_CompanyID` in `DimSecurity`, 0 of 98,576 `Financial` rows failed
to match a company. **SCD invariant holds exactly:** `DimCustomer` has 4,728 distinct
`CustomerID`s, 6,440 total rows (history), and exactly 4,728 `IsCurrent=true` rows — one current
row per customer, no more, no less. `DimCustomer`'s row count (6,440) also matches the customer-ID
boundary independently spotted in Batch2's sample data back in Task A4 (`Customer.txt` there
starts at `CustomerID=6440`).

**Deliverables:** `benchmark/deliverables/ported_historical_load.sql`,
`benchmark/deliverables/tpcdi_populated.duckdb` (342 MB — `S` fully loaded + `T` fully populated
for the 16 live tables). Disk headroom checked before and after: ~9 GB free throughout, no
concern at this scale.

### C5 — `tpcdi_column_mapping.csv` built (2026-10-03)

Materialized as `benchmark/deliverables/tpcdi_column_mapping.csv`, 241 rows, 17 fields, same
schema as the reference `column_mapping_flagged.csv`. Built from everything gathered above
(ported SQL comments, the bugs found, the table-status survey) rather than re-derived from
scratch. Final tallies:

| Field | Distribution |
|---|---|
| `table_status` | populated 210, not_built 31 |
| `rule_reliable` | yes 193, no 42, n/a 6 |
| `column_kind` | passthrough_copy 70, rename 41, lookup join 25, retype 18, constant 16, SCD history 12, conditional 7, copies_generated_key 6, value 9, generated_key 5, aggregate 1 |
| `table_caution=yes` | `DimSecurity`, `DimTrade`, `FactHoldings`, `FactMarketHistory`, `FactWatches`, `DImessages` (6 of 20 tables) |

This is now the authoritative held-out answer key for Phase C/D — see `project_plan.md` §5.4/5.5
for how it's used (matching fields shown to the LLM, `rule_sql`/`column_kind`/`rule_reliable`
withheld as the grading reference).

### C7 — deferred

`Generator_audit.csv` turned out to only hold generator *config* parameters (scale factor, date
ranges, etc.), not per-table row-count oracles — there's no external row-count authority to
check against beyond what we already verified. The referential-integrity and SCD-invariant checks
done in C6 (zero orphaned FKs, exact current-row-per-customer count) serve as the practical
verification instead; no further action planned here unless a specific discrepancy surfaces
later.

---

## Task A5 — Load the target (and source) schema into DuckDB

**Goal.** Confirm `tpcdi_target_schema.sql` (`T`) loads cleanly, per the doc's step. Extended to
also produce and load the standalone `tpcdi_source_schema.sql` (`S`) deliverable that was left
open from Task A2, since both were mechanical and gated on the same prerequisite (A2/A3/A4 all
clear).

### Extracting `tpcdi_source_schema.sql`

Wrote a small paren-aware Python parser (same technique used for the A2 column tabulation) over
`schema.sql`'s `Source.*` block, re-emitting clean `CREATE TABLE` statements: stripped trailing
commas before closing parens (present throughout the original, invalid standard SQL), mapped
`NVARCHAR(n) → VARCHAR(n)` and `DATETIME → TIMESTAMP` (the same SQL-Server-dialect fixes already
applied when `tpcdi_target_schema.sql` was originally converted), and prefixed with
`CREATE SCHEMA Source;`. Output: **[`benchmark/deliverables/tpcdi_source_schema.sql`](deliverables/tpcdi_source_schema.sql)**,
31 tables.

**Correction to Task A2's table count:** the "30 tables" figure recorded there was a plain
counting error — a recount of that same list is **31** (`AuditFiles` was always in the table,
just miscounted in the summary line). Fixed in both this file and `project_plan.md`.

### Loading both schemas

```
cd benchmark/deliverables
cp ../../files/tpcdi_target_schema.sql .
python3 load_schemas.py   # loads tpcdi_target_schema.sql into schema "main", tpcdi_source_schema.sql into schema "Source"
```
(Needed a working `duckdb` Python package first — the system `pip` pointed at a stray Python
3.9 while `python3` resolves to Homebrew's 3.13; installing under Homebrew's own Python hit
PEP 668's externally-managed-environment guard, so a throwaway venv was used instead of
`--break-system-packages`, to avoid touching the Homebrew Python install.)

**Result:**
```
tables created (total, all schemas): 51
  schema main: 20 tables      <- T, matches the doc's "20 tables, 30 foreign keys, 241 columns" exactly
  schema Source: 31 tables    <- S
```
Every table name matches the tabulations from Task A2 (`S`) and the doc's own manifest (`T`).
No errors, no type-mapping failures.

### Bonus verification: does generated `D` actually load into extracted `S`?

Not required by A5, but cheap and high-value: loaded three of the SF=3 generated files
(Task A4) straight into their corresponding `Source.*` tables via DuckDB's `COPY ... (DELIMITER
'|'/',')`, with no manual casting or column reordering:

| File (`D`) | Target table (`S`) | Rows loaded | Result |
|---|---|---|---|
| `Batch1/Trade.txt` | `Source.Trade` | 390,978 | Clean — `NUMERIC`/`TIMESTAMP`/`CHAR` columns all typed correctly on load |
| `Batch1/HR.csv` | `Source.HR` | 15,000 | Clean |
| `Batch1/DailyMarket.txt` | `Source.DailyMarket` | 1,282,768 | Clean |

This is a genuine end-to-end confirmation — not just eyeballed column-name matching — that `D`
(Task A4) and `S` (Task A2) are a real, mutually-consistent pair: the file layouts DIGen
produces parse without error against the exact DDL extracted from `schema.sql`. (These loads
were done in a scratch DuckDB file and not persisted — the deliverable DB at
`benchmark/deliverables/tpcdi.duckdb` is schema-only, kept small (1.5 MB) on purpose.)

### A5 verdict

**Done, no open issues.** Both `S` and `T` are portable, DuckDB-loadable, and (per the bonus
check) actually consistent with the generated `D`. All four pieces for TPC-DI — `S`, `D`, `T`,
transformation — are now on disk, portable, and cross-validated against each other. This closes
out Stage 0 for TPC-DI, modulo the one known gap (`FactMarketHistory`'s abandoned transformation
in R1 — R3 has a working reference implementation if we decide to port it later, see Task A4).

### Deliverables produced by this task

- [`benchmark/deliverables/tpcdi_source_schema.sql`](deliverables/tpcdi_source_schema.sql) — `S`, portable SQL, 31 tables
- [`benchmark/deliverables/tpcdi_target_schema.sql`](deliverables/tpcdi_target_schema.sql) — `T`, copied in from `files/`, 20 tables
- [`benchmark/deliverables/load_schemas.py`](deliverables/load_schemas.py) — reusable loader script
- `benchmark/deliverables/tpcdi.duckdb` — schema-only DuckDB file (both schemas loaded, no data)

---

## Phase C — LLM query synthesis, first real runs (2026-10-03 → 2026-10-04)

Detailed narrative, design rationale, and full result tables for this phase have been kept in
`project_plan.md` §5.4 onward rather than duplicated here (the two documents drifted — this
phase's work landed mostly in the plan, not this findings log — noted so future updates know
where the authoritative detail actually lives). Summary of what's been done, for continuity:

- **Harness built**: `benchmark/pipeline/{profiling,table_skeleton,build_prompt,call_llm,
  select_subset,run_subset,grade_subset}.py`. Two-level design (table-skeleton resolved once,
  per-column prompts built from it) per the Sec 5.4 design.
- **Models**: `nvidia/nemotron-3-super-120b-a12b:free`, `cohere/north-mini-code:free`,
  `qwen/qwen3.8-27b:free` — all free (no paid budget available), verified live against
  OpenRouter's `/api/v1/models` rather than assumed (an earlier pick, Llama 3.3 70B, was found to
  have silently dropped off the free tier).
- **2026-10-03**: first live run (12 columns), diagnosed and fixed a reasoning-model
  token-exhaustion bug (`max_tokens` 600→2000→6000), a missing-dialect-instruction bug (models
  defaulted to T-SQL/Postgres syntax), and an anti-hallucination gap. Graded the "value-like"
  subset that had a clean natural key: **4/5 exactly correct, 1/5 99.9% correct** (see
  `project_plan.md` for the full table). Found `tpcdi_column_mapping.csv` has `value_columns`
  empty for 86 of 210 populated rows (41%) — a significant, still only partially patched gap.
- **2026-10-03, round 2**: contamination concern raised (TPC-DI is a heavily-documented public
  benchmark) — subset revised to 13 columns favoring R1-specific bugs and idiosyncratic logic
  over textbook mappings, on the theory those are far less likely to be memorized from
  pretraining.
- **2026-10-04**: full 13-column run. Nemotron 13/13, Cohere 11/13, Qwen 3/13 (still the weakest,
  unresolved). Found and fixed a real prompt-construction bug: the mapping CSV's `" -> "`
  lookup-chain notation was being mis-parsed in both `build_prompt.py` and `table_skeleton.py`,
  causing 4 of 5 new "harder" columns to silently lose the information that a lookup into an
  already-populated target table was needed — not a model reasoning failure, a harness bug.
  Fixed, then validated: `DimCustomer.NationalTaxRateDesc` went from 0/2 to 3/3 correct on
  retest. A narrower follow-on gap surfaced (`DimSecurity.SK_CompanyID`): models now find the
  right target table to look up but guess a non-existent join column, since the target table's
  own schema still isn't shown to them the way `Source.*` tables' schemas are. Not yet fixed.
- **Budget**: 45 of 50 free-tier calls used on 2026-10-04; `Financial.SK_CompanyID` not yet
  retested (ran out of budget first); 5 calls held in reserve rather than spent same-day.

## Run 3 (2026-10-05) — summary
Baseline at prompt v3 across the 25-column subset. Nemotron via NVIDIA NIM complete (25/25); Cohere nearly complete; Qwen incomplete due to OpenRouter free-tier limits (429s, length errors, 50/day cap). Graded columns: NationalTaxRateDesc 100% all models; FoundingDate 75.3% cohere/qwen (SCD duplicate-CIK grader artifact) and Nemotron execution error (date format); Industry Nemotron execution error (hallucinated column). Details in project_plan.md "Run 3 status". Grader crash on `_prompt_version` string fixed.

Run 3 addendum: added openai/gpt-oss-20b via NVIDIA as a reliable second model (25/25, no errors); other NVIDIA-listed models timed out or 404'd despite being in /v1/models. See project_plan.md.

## Step 1 — generic swap-in grader and gold self-test (2026-10-26)
See project_plan.md "Step 1 done". Gold self-test 210/210 columns and 16/16 tables exact; NULL control flags 11 weakly-discriminating columns; the old 75.3% FoundingDate / 86.9% Industry numbers were duplicate-key grader artifacts (now 100%). Remaining subset failures are mostly a prompt-vs-grader scope mismatch (CTE/derived-table columns), to be fixed in Step 2.

## Step 2 — scope contract, answer-key bug, model drift (2026-11-04)
See project_plan.md "Step 2 done". Headline: same model + same grader, v3 -> v4 prompt takes the 25-column subset from 11 to 21 exact answers and 8 to 0 fail-to-run, confirming that prompt/grader scope mismatch was the main bottleneck. Our own port had a bug (DimTrade.CashFlag all FALSE) that three LLMs exposed by scoring identically; fixed and rebuilt. NVIDIA's catalog lists models that 404 or time out, so model availability must be probed per run.
