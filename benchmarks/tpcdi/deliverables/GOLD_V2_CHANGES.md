# Gold v2: what was repaired, and how it was checked

`ported_historical_load.sql` (**v1**) is R1's `historical_load.sql` ported to DuckDB *with its defects preserved*. `ported_historical_load_v2.sql`
(**v2**) repairs them against the TPC-DI v1.1.0 specification (Clauses 3.2, 4.4, 4.5) and the official audit script.
Both stay in the repository; `TPCDI_GOLD=v1|v2` (see `pipeline/gold_version.py`) selects the gold for every grader, so any earlier
number can still be reproduced against v1. Rebuild v2 with `pipeline/build_gold_v2.py` (7 s; every NOT NULL / FK / CHECK enforced at load).

| | v1 | v2 |
|---|---|---|
| Official TPC-DI audit, checks applicable to a Batch-1 load | 72 / 89 | **89 / 89** |
| Independent invariants (`pipeline/gold_checks_v2.py`, 30 checks re-derived from `Source.*`/spec) | 12 / 30 | **30 / 30** |
| Tables with the spec's grain | 13 of 16 populated | **16 of 16** |

Row counts: DimAccount 12,339 → 16,110 · DimSecurity 1,227 → 3,147 · DimTrade 982,180 → 390,978 (= `Source.Trade`) ·
FactHoldings 930,764 → 362,342 (= `Source.HoldingHistory`) · FactCashBalances 330,485 → 330,461. Others unchanged.
Unchanged tables: DimDate, DimTime, StatusType, TaxRate, TradeType, Industry, DimBroker.

## Defects repaired

*Found by* = the official audit check that failed (A) or one of our own invariants / a spec read (I) — the audit does not test these.

| id | table.column(s) | v1 defect | spec | found by | v2 |
|---|---|---|---|---|---|
| F01/F02 | DimAccount.Status, DimCustomer.Status | `ACTIVE`/`INACTIVE` | 3.2 + audit: `Active`/`Inactive` | A | literals `Active`/`Inactive` |
| F03 | DimCompany.SPrating, isLowGrade | invalid S&P ratings (154 of 1,500 rows) passed through | 4.5.3.3: NULL both | A | NULL when not in the 22 valid ratings |
| F04 | DimSecurity.SK_CompanyID (+ versioning) | key pointed at a company version whose dates do not cover the security row (27%) | 4.4.1.6.1 | A | a new security version starts at every company-version start inside the symbol's company segment |
| F05, F09, F10 | DimAccount (rows, SK_CustomerID, EffectiveDate/EndDate/IsCurrent) | no version when the owning customer changes (UPDCUST/INACT); same-day versions not consolidated; CLOSEACCT row dated at the previous version's timestamp; accounts of inactive customers stayed Active | 4.5.1.3, 4.4.1.5, 4.4.1.6.1 | A | one version per account per day (latest wins); account versions split at every customer-version start; `Inactive` when closed or the customer is inactive |
| F06 | FactCashBalances.SK_CustomerID | followed from F05; `BETWEEN Eff AND End` matched two versions on a boundary day (22 duplicate keys) | 4.5.9.2 | A | half-open `[Eff, End)` |
| F07 | Prospect.MarketingNameplate | thresholds fine, tags not concatenated (single tag only) | 4.5.15 | A | `+`-joined tags in the spec's order, NULL if none |
| F08 | DimCustomer.AgencyID/CreditRating/NetWorth/MarketingNameplate | demographics copied onto 6,428 of 6,440 versions, carried across name/address changes | 4.5.4.3 | A | latest version only (3,745 rows), matched on that version's own name/address; NULL on earlier versions |
| F11 | DimTrade (grain) | one row per TradeHistory **event** (982,180) for 390,978 trades; canceled trades counted twice | 4.5.8.1 | A | one row per `T_ID`; create/close keys from the history events, Status from `Source.Trade` |
| F12 | FactHoldings (rows) | joined the duplicated DimTrade (930,764 rows) | 4.5.10 | A | one row per HoldingHistory record (362,342) |
| I01 | DimTrade.SK_BrokerID/SK_SecurityID/SK_CompanyID/SK_CustomerID/SK_AccountID, FactHoldings.SK_* | hardcoded `1` ("-- FIX SK" in the original) | 4.5.8.2: dimension version valid when the trade is first seen | A (partly), I | joined to DimAccount/DimSecurity on the first-seen day |
| G01 | DimCustomer.Gender | compared the **lower-case** literals `'m','f'` with the raw value: every upper-case M/F became `U` (M/F 1,186 of 6,440) | 4.5.4.3: upper-case first | I | M/F 2,991 of 6,440 |
| G02 | DimCustomer (all updatable fields) | an UPDCUST inherited only from the NEW record, so a second update dropped the first one's changes (220 customers have ≥2 updates) | 4.5.4.3: unchanged fields retain the current record | I | forward fill over the customer's whole action history |
| G03 | DimSecurity | `'0000000005'` vs `'5'` text comparison silently dropped every security whose `CoNameOrCIK` is numeric: 1,075 of 1,998 symbols kept | 4.5.6.2: match CIK or Name by content | I (row count vs `Source.FinwireSEC`) | numeric CIK matched as a number: all 1,998 symbols |
| G04 | Financial.SK_CompanyID | always the company's *current* version | 4.5.14.2: valid at PTS | I | `EffectiveDate <= PTS < EndDate` |
| G05 | FactCashBalances.Cash | the day's net amount, not a balance (author's own TODO) | 4.5.9.2 + 3.2: balance after this day | I | running sum per account |
| G06 | FactHoldings.CurrentPrice | `TRY_CAST(... AS INTEGER)` dropped the cents; DDL column was `INTEGER`; SK_DateID/TimeID fell back to the create keys | 4.5.10.2: close keys; price of the trade | I | `NUMERIC(8,2)` (target DDL v2); close keys |
| G07 | Prospect.IsCustomer | 480 `true` of 14,982: `=` on a NULL `AddressLine2` never matched, and any historical Active version counted | 4.5.15.1: current Active record | I | 3,410 `true`: NULL-safe AddressLine2 match against the current Active version |
| G09 | DimSecurity.Dividend | DDL declared `INTEGER`; the spec type is SNUM(10,2): 3,112 of 3,147 values were rounded (1.85 → 2) | 3.2 (VALUE_T) | found by the dbtpcdi cross-check | `NUMERIC(10,2)` (target DDL v2) |
| G08 | DimCompany text | 1,352 empty `AddressLine2` and 73 empty `Country` strings | 4.5.3.2: all-blank → NULL | I | NULL |

Target schema v2 (`tpcdi_target_schema_v2.sql`): two changes, both integer columns that rounded decimal values: `FactHoldings.CurrentPrice INTEGER` → `NUMERIC(8,2)` and `DimSecurity.Dividend INTEGER` → `NUMERIC(10,2)`. `pipeline/ddl_precision_check.py` runs every gold SELECT without the column casts and compares with what was stored: after the fix the only column whose stored value differs is DimCompany.CompanyID (a zero-padded string cast to integer, harmless).
`tpcdi_column_mapping_v2.csv`: `rule_sql` regenerated from the v2 expressions, all 17 populated `rule_reliable=no` rows cleared
(each named a defect repaired above), `v2_changed` marks the 74 populated columns whose defining expression text changed.

## Choices where the spec leaves room

1. **Demographics on the latest version only.** 4.5.4.3 says Prospect data is applied when "there are no newer UPDCUST or INACT records"
   and that it "will only be applied to the latest version of the customer record"; earlier versions keep NULL.
2. **Prospect match.** All five fields upper-cased; `AddressLine2` compared NULL-safely (empty = NULL), like the official audit script.
3. **Absent vs empty element in an update.** The parsed `Source.*` tables cannot tell them apart; absent (retain the current value) is used.
4. **INACT.** Sets the customer `Inactive` and, from that day, every account of the customer `Inactive`; CLOSEACCT is permanent.
5. **Time-of-day inside a day.** All history-tracking dimensions are daily (4.4.1.5); the latest action of a day wins.
6. **Spec text vs spec table.** 4.5.4.3/4.5.1.3 write `ACTIVE`; Clause 3.2 and the audit script require `Active`. v2 follows 3.2 + audit.

## Verification and its limits

* The audit passing is necessary, not sufficient: it does not test Gender, update accumulation, security coverage, running cash,
  price precision, IsCustomer or blank handling. Those are covered by the 30 invariants in `gold_checks_v2.py`, **which were written by
  the same person who wrote the repair, after seeing it** — they are guard rails, not an independent oracle.
* Independent oracle: `benchmark/gold_crosscheck/REPORT.md` compares v2 with a port of the separately written `dbtpcdi` models.
  Result: identical key sets on all 9 compared tables, 131 of 148 columns identical; the 17 others are one v2 defect (G09, found there and
  fixed) plus deviations of dbtpcdi from the spec (phone-element typo, close keys = create keys, accounts of inactive customers stay Active,
  demographics on historical versions, ...). Not exercised by that comparison: same-day consolidation (1 account-day in the data) and raw parsing.
* One reading is contestable: 976 customers match a Prospect record only on an older version; v2 gives them no demographics (A-1 in the report).
* Out of scope as before: batches 2/3, and the four tables R1 never built (FactMarketHistory, FactWatches, DImessages, Audit):
  20 target tables, 16 populated, 210 populated columns.
* The earlier benchmark numbers (README/`PROGRESS.md` "v1 gold") are *kept* and labelled; new numbers are produced against v2.
