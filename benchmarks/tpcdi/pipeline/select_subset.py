"""
Pick a small, diverse test subset instead of running all 210 populated columns -- driven by
OpenRouter's free-tier rate limit: 50 requests/day SHARED across all ':free' models combined (not
per-model), 20/min.

Revised 2026-10-03: no paid budget -- all 3 models are now ':free' (see call_llm.py), so N test
columns means 3*N calls all counting against the SAME shared 50/day cap (not 2*N as in the
original paid-Qwen design). Trimmed from 15 to 12 columns -> 36 calls, leaving 14 of margin for
retries/errors on this first live run, rather than running right up against the cap.

Revised again 2026-10-03 (round 2) -- contamination concern raised: TPC-DI is a decade-old,
heavily-documented public benchmark (spec PDF freely downloadable, 4+ full reference
implementations on public GitHub). The first 5 columns we graded (Industry.IN_NAME,
DimCompany.CEO/FoundingDate/Industry/isLowGrade) are all simple, "textbook" FinwireCMP->DimCompany
mappings -- exactly the kind of thing a model could plausibly know from pretraining rather than
from genuinely reasoning over the matching we handed it. Dropped the now-well-understood easy
ones (IN_NAME, CEO, isLowGrade, Phone1 -- already graded, no more signal to gain) and added 5
harder/more idiosyncratic targets, on the theory that these are much less likely to be memorized:
- Multi-hop lookups (NationalTaxRateDesc: TaxInfoXML -> TaxRate, two joins deep)
- Idiosyncratic business logic with no "textbook" answer (MarketingNameplate: a 6-branch CASE
  over 6 Prospect columns with arbitrary thresholds like NetWorth>1000000 -- this is R1's own
  invented marketing-segment logic, not part of the TPC-DI spec's required behavior)
- Temporal/SCD-gated surrogate key lookups (DimAccount.SK_CustomerID, Financial.SK_CompanyID's
  correlated subquery)
- A second "known fragile" column (DimSecurity.SK_CompanyID, flagged table_caution=yes) alongside
  the existing two "known buggy" ones (DimTrade.SK_BrokerID, Prospect.IsCustomer) -- R1's own
  mistakes/rough edges are a cleaner contamination test than its correct, spec-standard logic,
  since a memorized "I know TPC-DI" signal would reproduce the SPEC's intended behavior, not this
  one obscure student repo's specific bugs.
Kept DimCompany.FoundingDate/Industry (still need to confirm the dialect/anti-hallucination
prompt fix actually works) and the generated_key/copies_generated_key/aggregate columns (no
"easy win" signal yet on those categories either way).
"""
import csv

MAPPING_CSV = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))), "deliverables/tpcdi_column_mapping.csv")

# One hand-picked (table, column) per column_kind, chosen from reliable rows for a clean baseline,
# plus a couple of deliberately-flagged ones at the end for the "does the model reproduce the
# bug" question. Hand-picked rather than auto-sampled so the mix is interpretable column by column.
CURATED_SUBSET = [
    ("DimCompany", "FoundingDate", "retype (YYYYMMDD text -> DATE) -- RETEST: confirm dialect fix works"),
    ("DimCompany", "Industry", "lookup join -- RETEST: confirm anti-hallucination fix works"),
    ("DimCustomer", "IsCurrent", "SCD history"),
    ("DimCompany", "SK_CompanyID", "generated_key"),
    ("FactCashBalances", "SK_CustomerID", "copies_generated_key"),
    ("FactCashBalances", "Cash", "aggregate -- also flagged rule_reliable=no (not a running balance)"),
    ("DimTrade", "SK_BrokerID", "FLAGGED BUG: hardcoded-1 placeholder, author's own '-- FIX SK' comment"),
    ("Prospect", "IsCustomer", "FLAGGED BUG: COUNT(*) into a BOOLEAN column, type mismatch"),
    ("DimSecurity", "SK_CompanyID", "FLAGGED FRAGILE: varchar-based join, author's own TODO -- contamination-resistant"),
    ("DimCustomer", "NationalTaxRateDesc", "HARDER: 2-hop lookup join (TaxInfoXML -> TaxRate), less textbook"),
    ("DimCustomer", "MarketingNameplate", "HARDER: idiosyncratic 6-branch CASE, R1's own invented thresholds, not spec-mandated"),
    ("DimAccount", "SK_CustomerID", "HARDER: surrogate-key lookup gated by a temporal SCD window"),
    ("Financial", "SK_CompanyID", "HARDER: correlated subquery matching CIK OR Name, filtered WHERE IsCurrent"),

    # ======= Round 3 expansion, 2026-10-04: genuine column-count increase, not just a swap =======
    # Prioritizes TABLES never touched by rounds 1-2 (DimBroker, FactHoldings) and repeats of
    # categories already tested but in a different table (DimTrade's own lookup-join/boolean-text
    # columns, a second retype-YYYYMMDD test on DimSecurity, a second idiosyncratic-CASE test on
    # Prospect using the *same* logic as DimCustomer.MarketingNameplate to see if the model makes
    # the identical mistake twice independently). 9 of these 12 needed the same value_columns CSV
    # patch as the round-2 columns did -- confirms the 86-row gap is systemic, not isolated to a
    # few unlucky columns; fixed those 9 rows directly in tpcdi_column_mapping.csv while building
    # this list (plus fixed a related notation inconsistency: DimCustomer.MarketingNameplate's
    # value_columns used an unparsed "{A,B,C}" curly-brace list -- switched to clean ";"-separated
    # entries, which DimCustomer.MarketingNameplate now also uses).
    ("DimBroker", "FirstName", "untested table: rename"),
    ("DimBroker", "Branch", "untested table: rename"),
    ("DimTrade", "Status", "lookup join, same table as the SK_BrokerID bug test but a working column"),
    ("DimTrade", "CashFlag", "boolean-from-text pattern (source stores 'true'/'false' literally, like HolidayFlag)"),
    ("DimSecurity", "FirstTrade", "second retype-YYYYMMDD test (parallel to DimCompany.FoundingDate) in a different table"),
    ("FactHoldings", "CurrentPrice", "untested table; author's own comment flags uncertainty about this field choice"),
    ("FactHoldings", "TradeID", "untested table: rename baseline"),
    ("Prospect", "MarketingNameplate", "SAME idiosyncratic 6-branch CASE as DimCustomer.MarketingNameplate, different table -- does the model repeat the identical miss independently?"),
    ("DimAccount", "Status", "conditional, different column than the SK_CustomerID lookup already tested"),
    ("Financial", "FI_REVENUE", "retype numeric, different table than FoundingDate's YYYYMMDD retype"),
    ("DimCompany", "AddressLine1", "rename baseline, under-sampled table"),
    ("DimCustomer", "Email1", "rename baseline (TRIM-based)"),
]


def get_subset():
    with open(MAPPING_CSV, newline="") as f:
        rows = {(r["target_table"], r["target_column"]): r for r in csv.DictReader(f)}
    out = []
    for table, col, why in CURATED_SUBSET:
        r = rows.get((table, col))
        if r is None:
            raise KeyError(f"{table}.{col} not found in mapping CSV")
        out.append({"table": table, "column": col, "why_chosen": why, "ground_truth": r})
    return out


if __name__ == "__main__":
    subset = get_subset()
    print(f"{len(subset)} columns selected -> {3*len(subset)} total calls, "
          f"ALL counting against the shared 50/day free-tier cap (3 models, all :free)")
    print()
    for s in subset:
        gt = s["ground_truth"]
        print(f"  {s['table']}.{s['column']:20s} [{gt['column_kind']:20s} reliable={gt['rule_reliable']:3s}] -- {s['why_chosen']}")
