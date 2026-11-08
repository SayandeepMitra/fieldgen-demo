# L2 report

| table | ref rows | cand rows | recall % | precision % | dup | rows correct | cols exact / scored |
|---|---:|---:|---:|---:|---:|---|---|
| DimDate | 25933 | 25933 | 100.0 | 100.0 | 0 | True | 17/18 |
| DimTime | 86400 | 86400 | 100.0 | 100.0 | 0 | True | 10/10 |
| StatusType | 6 | 6 | 100.0 | 100.0 | 0 | True | 2/2 |
| TaxRate | 320 | 320 | 100.0 | 100.0 | 0 | True | 3/3 |
| TradeType | 5 | 5 | 100.0 | 100.0 | 0 | True | 4/4 |
| Industry | 102 | 102 | 100.0 | 100.0 | 0 | True | 3/3 |
| DimBroker | 4293 | 15000 | 100.0 | 28.62 | 0 | False | 11/13 |
| DimCompany | 1500 | 0 | 0.0 | None | 0 | False | 0/20 |
| DimCustomer | 6440 | 14572 | 100.0 | 44.194 | 8132 | False | 2/33 |
| DimAccount (defective ref. grain) | 12339 | 12860 | 100.0 | 95.949 | 521 | False | 2/11 |
| DimSecurity | 1227 | 2400 | 100.0 | 51.125 | 99 | False | 2/15 |
| DimTrade (defective ref. grain) | 982180 | 390978 | 39.807 | 100.0 | 0 | False | 0/21 |
| FactCashBalances | 330485 | 361856 | 9.8 | 8.95 | 18142 | False | 0/5 |
| FactHoldings (defective ref. grain) | 930764 | 362342 | 38.93 | 100.0 | 0 | False | 0/11 |
| Financial | 98576 | 98576 | 0.0 | 0.0 | 0 | False | 0/14 |
| Prospect | 14982 | 14982 | 100.0 | 100.0 | 0 | True | 22/27 |

## Headline

- tables_graded: 16
- tables_rows_correct: 7
- tables_rows_correct_sound_reference: 7/13
- columns_exact_all: 78/210
- columns_exact_core171: 75/171
- columns_exact_hard37: 7/37
- columns_exact_core: 75/171
- columns_exact_hard: 7/37
- constraint_violations: {'not_null_cells': 2752978, 'dangling_fk_cells': 856855}
- defective_reference_tables_flagged: ['DimAccount', 'DimTrade', 'FactHoldings']
- official audit (Batch-1 applicable): {'applicable': 78, 'ok': 34, 'not_ok': 44}