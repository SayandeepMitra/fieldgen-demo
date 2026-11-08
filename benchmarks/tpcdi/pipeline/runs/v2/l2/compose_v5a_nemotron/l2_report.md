# L2 report

| table | ref rows | cand rows | recall % | precision % | dup | rows correct | cols exact / scored |
|---|---:|---:|---:|---:|---:|---|---|
| DimDate | 25933 | 25933 | 100.0 | 100.0 | 0 | True | 18/18 |
| DimTime | 86400 | 86400 | 100.0 | 100.0 | 0 | True | 10/10 |
| StatusType | 6 | 6 | 100.0 | 100.0 | 0 | True | 2/2 |
| TaxRate | 320 | 320 | 100.0 | 100.0 | 0 | True | 3/3 |
| TradeType | 5 | 5 | 100.0 | 100.0 | 0 | True | 4/4 |
| Industry | 102 | 102 | 100.0 | 100.0 | 0 | True | 3/3 |
| DimBroker | 4293 | 4293 | 100.0 | 100.0 | 0 | True | 12/13 |
| DimCompany | 1500 | 1500 | 100.0 | 100.0 | 0 | True | 10/20 |
| DimCustomer | 6440 | 6440 | 100.0 | 100.0 | 0 | True | 7/33 |
| DimAccount | 16110 | 16110 | 100.0 | 100.0 | 0 | True | 8/11 |
| DimSecurity | 3147 | 0 | 0.0 | None | 0 | False | 0/15 |
| DimTrade | 390978 | 390978 | 100.0 | 100.0 | 0 | True | 18/21 |
| FactCashBalances | 330461 | 330461 | 100.0 | 100.0 | 0 | True | 4/5 |
| FactHoldings | 362342 | 362342 | 100.0 | 100.0 | 0 | True | 9/11 |
| Financial | 98576 | 98576 | 0.0 | 0.0 | 0 | False | 0/14 |
| Prospect | 14982 | 14982 | 100.0 | 100.0 | 0 | True | 24/27 |

## Headline

- tables_graded: 16
- tables_rows_correct: 14
- tables_rows_correct_sound_reference: 14/16
- columns_exact_all: 132/210
- columns_exact_core171: 129/196
- columns_exact_hard37: 25/70
- columns_exact_core: 129/196
- columns_exact_hard: 25/70
- constraint_violations: {'not_null_cells': 1621698, 'dangling_fk_cells': 0}
- defective_reference_tables_flagged: []
- official audit (Batch-1 applicable): {'applicable': 78, 'ok': 65, 'not_ok': 13}