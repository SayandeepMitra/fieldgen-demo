| table | v2 rows | dbt raw rows | v2 keys | dbt keys | matched | only-v2 | only-dbt |
|---|---|---|---|---|---|---|---|
| DimCompany | 1,500 | 1,500 | 1,500 | 1,500 | 1,500 | 0 | 0 |
| DimCustomer | 6,440 | 6,440 | 6,440 | 6,440 | 6,440 | 0 | 0 |
| DimAccount | 16,110 | 16,110 | 16,110 | 16,110 | 16,110 | 0 | 0 |
| DimSecurity | 3,147 | 3,147 | 3,147 | 3,147 | 3,147 | 0 | 0 |
| DimTrade | 390,978 | 390,978 | 390,978 | 390,978 | 390,978 | 0 | 0 |
| FactHoldings | 362,342 | 362,342 | 362,342 | 362,342 | 362,342 | 0 | 0 |
| FactCashBalances | 330,461 | 330,461 | 330,461 | 330,461 | 330,461 | 0 | 0 |
| Financial | 98,576 | 98,576 | 98,576 | 98,576 | 98,576 | 0 | 0 |
| Prospect | 14,982 | 14,982 | 14,982 | 14,982 | 14,982 | 0 | 0 |

Per-column agreement over matched keys (only columns < 100% listed; all others are 100.00%):

| table | column | matched | agree | % |
|---|---|---|---|---|
| DimAccount | status | 16,110 | 15,211 | 94.42 |
| DimCompany | addressline2 | 1,500 | 148 | 9.87 |
| DimCompany | country | 1,500 | 1,427 | 95.13 |
| DimCustomer | phone1 | 6,440 | 4,890 | 75.93 |
| DimCustomer | marketingnameplate | 6,440 | 5,064 | 78.63 |
| DimCustomer | agencyid | 6,440 | 5,086 | 78.98 |
| DimCustomer | creditrating | 6,440 | 5,152 | 80.00 |
| DimCustomer | networth | 6,440 | 5,158 | 80.09 |
| DimCustomer | phone2 | 6,440 | 5,175 | 80.36 |
| DimCustomer | phone3 | 6,440 | 5,941 | 92.25 |
| DimSecurity | dividend | 3,147 | 35 | 1.11 |
| DimTrade | closetime | 390,978 | 3 | 0.00 |
| DimTrade | closedate | 390,978 | 156,600 | 40.05 |
| FactHoldings | closetime | 362,342 | 3 | 0.00 |
| FactHoldings | closedate | 362,342 | 156,476 | 43.18 |
| Prospect | iscustomer | 14,982 | 14,647 | 97.76 |
| Prospect | marketingnameplate | 14,982 | 14,902 | 99.47 |
