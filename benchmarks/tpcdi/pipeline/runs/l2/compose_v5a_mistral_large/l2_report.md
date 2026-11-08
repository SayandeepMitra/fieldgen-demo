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
| DimCompany | 1500 | 1500 | 100.0 | 100.0 | 0 | True | 12/20 |
| DimCustomer | 6440 | 6440 | 100.0 | 100.0 | 0 | True | 22/33 |
| DimAccount (defective ref. grain) | 12339 | 12339 | 100.0 | 100.0 | 0 | True | 8/11 |
| DimSecurity | 1227 | 0 | 0.0 | None | 0 | False | 0/15 |
| DimTrade (defective ref. grain) | 982180 | 982180 | 100.0 | 100.0 | 0 | True | 16/21 |
| FactCashBalances | 330485 | 330485 | 100.0 | 100.0 | 0 | True | 5/5 |
| FactHoldings (defective ref. grain) | 930764 | 930764 | 100.0 | 100.0 | 0 | True | 7/11 |
| Financial | 98576 | 98576 | 0.0 | 0.0 | 0 | False | 0/14 |
| Prospect | 14982 | 14982 | 100.0 | 100.0 | 0 | True | 25/27 |

## Headline

- tables_graded: 16
- tables_rows_correct: 14
- tables_rows_correct_sound_reference: 11/13
- columns_exact_all: 147/210
- columns_exact_core171: 125/171
- columns_exact_hard37: 20/37
- constraint_violations: {'not_null_cells': 2029502, 'dangling_fk_cells': 6709103}
- defective_reference_tables_flagged: ['DimAccount', 'DimTrade', 'FactHoldings']