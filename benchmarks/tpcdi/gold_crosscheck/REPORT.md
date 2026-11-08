# Cross-check: repaired gold (v2) vs the independent `dbtpcdi` implementation (Batch 1)

Produced by a delegated agent; the scripts and evidence are in this folder (`run_crosscheck.py`, ~7 s; `dbt_port.sql`, `normalize.sql`,
`rootcause.py` -> `rootcause_output.txt`, `cmp_columns.csv`, `cmp_summary.csv`, `crosscheck_results.duckdb`). The port starts from the
parsed `Source.*` tables, so dbt's own raw fixed-width/XML parsing is not tested. Incremental models and Batch-2/3 halves are not ported
(irrelevant to a historical load). Surrogate keys are compared as (natural key, EffectiveDate) of the version they point at.
Findings reviewed by the benchmark author; R6 was verified directly and fixed (see GOLD_V2_CHANGES.md, G09).

## Result

The two implementations produce **identical key sets on all 9 compared tables** (DimCompany, DimCustomer, DimAccount, DimSecurity, DimTrade,
FactHoldings, FactCashBalances, Financial, Prospect: 0 only-in-v2, 0 only-in-dbt). **131 of 148 compared columns agree 100%.** Fully
identical, including running Cash, all version-pointing foreign keys of DimTrade/FactHoldings/DimSecurity/Financial/FactCashBalances, Gender,
Status, tax rates, SPrating handling and versioning of DimCompany/DimSecurity.

The 17 columns below 100% trace to **one defect in v2 (R6, fixed)** and to deviations of the dbt implementation from the specification:

| id | what differs | rows | cause | class |
|---|---|---|---|---|
| R1 | DimAccount.Status of accounts of an inactivated customer | 899 | dbt filters out INACT/UPDCUST so the accounts stay Active, and a later UPDACCT re-activates | dbt deviates (4.5.1.3) |
| R2 | DimCompany AddressLine2 / Country blank text | 1,352 / 73 | dbt only NULLs FoundingDate and invalid SPrating | dbt deviates (4.5.3.2) |
| R3 | DimCustomer Phone1/2/3 | 1,550 / 1,265 / 499 | dbt reads XML element `CTRY_CODE`, the real name is `C_CTRY_CODE`: every phone with a country code becomes NULL or stale | dbt typo; with it corrected: 0 differences |
| R4 | DimCustomer AgencyID/CreditRating/NetWorth/MarketingNameplate on historical versions | 1,354 | dbt joins Prospect to every version whose own name/address matches | dbt deviates (4.5.4.3: latest version only) |
| R5 | MarketingNameplate `''` instead of NULL | 80 Prospect, 22 DimCustomer | dbt's concat is never NULL | dbt deviates (4.5.15) |
| **R6** | **DimSecurity.Dividend** | **3,112 of 3,147** | **v2's own DDL declared `Dividend INTEGER`; spec type is SNUM(10,2)** (all differences = `round(dbt)`) | **v2 bug, fixed: `NUMERIC(10,2)`** |
| R7 | DimTrade / FactHoldings close date+time keys | 234,378 / 205,866 | dbt builds the close keys with the create-branch expression, so close = create and never NULL | dbt deviates (4.5.8.2, 4.5.10.2); with close events: 100% agreement |
| R8 | Prospect.IsCustomer | 335 | dbt does not require the matched customer to be Active | dbt deviates (4.5.15.1) |
| R9 | same-day consolidation | 0 here | dbt has none (4.4.1.5); the data barely exercises it (1 account-day) | latent; v2's consolidation is **not tested** by this cross-check |
| R10, R11 | dbt DimSecurity SK not unique (1,911 of 3,147 rows collide); dbt DimAccount has no IsCurrent | – | dbt | no effect on the comparison |

## Where the specification leaves room (v2 picks one reading; dbt cannot arbitrate)

* **A-1 demographics for customers that changed after the Prospect snapshot.** 976 customers match a Prospect record only on an older
  version; v2 gives them no demographics (literal "latest version" wording), dbt puts them on the older version.
* **A-2 which dimension version a trade points at.** Both implementations use the version valid on the earliest history event. A
  "version at close" reading would change 2,575 account keys and 357 security keys.
* **A-3 inclusive `<= EndDate`** in 4.5.1.3 would match two versions on a boundary day; both use half-open intervals (affects 2 account versions).
* 'ACTIVE' (spec text) vs 'Active' (Clause 3.2, audit, StatusType.txt): both use 'Active'.

## Limits

SF3 and Batch 1 only; raw parsing untested; same-day consolidation and zero-length versions barely exercised (so those v2 repairs rest on the
official audit, not on this comparison); if Snowflake read `HH` as 12-hour dbt's time-key join would drop afternoon events (unverified).
