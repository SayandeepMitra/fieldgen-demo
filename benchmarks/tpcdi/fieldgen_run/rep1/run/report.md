# fieldgen run report

Stages: **recipes_and_formulas**. Model asked for: `nvidia/nemotron-3.5-super-vl-120b-a12b`. Model id served: `private/nvidia/nemotron-3.5-super-120b-a12b`. Time: 198 s.

## Settings used

```json
{
 "model": "nvidia/nemotron-3.5-super-vl-120b-a12b",
 "reasoning_effort": "low",
 "stages": "recipes_and_formulas",
 "timeout_s": 900,
 "requests_per_minute": 4,
 "concurrency": 1,
 "domain_knowledge": "required",
 "reference": "auto",
 "data_profiling": true,
 "computed_facts": true,
 "measured_links": true,
 "min_coverage": 0.5,
 "documentation_conventions": true,
 "documentation_first": true,
 "source_labels": true,
 "join_rules_in_prompt": true,
 "retry_on_error": "errors_and_invalid",
 "max_retries": 2,
 "text_data_check": "warn",
 "score_levels": "L2",
 "robustness_check": false,
 "execute": {
  "sample_rows": "all"
 },
 "base_url": "https://integrate.api.nvidia.com/v1",
 "api_key_env": "NVIDIA_API_KEY"
}
```

## Warnings

- untested setting: requests_per_minute = 4
- untested setting: concurrency = 1
- text data check: quoted value not in data: 'type 2' (in: You are writing the Historical Load of the TPC-DI data warehouse: the first load of an emp)

## Recipes

| table | recipe | calls | retries | tokens in/out | errors |
|---|---|---|---|---|---|
| industry | ok | 1 | 0 | 1779/682 |  |
| statustype | ok | 1 | 0 | 1554/677 |  |
| taxrate | ok | 1 | 0 | 2244/1014 |  |
| tradetype | ok | 1 | 0 | 1888/1138 |  |
| dimdate | ok | 1 | 0 | 5910/1067 |  |
| dimtime | ok | 1 | 0 | 3729/1377 |  |
| dimbroker | ok | 1 | 0 | 11171/2439 |  |
| dimcustomer | ok | 1 | 0 | 22641/5517 |  |
| dimaccount | ok | 1 | 0 | 7377/10375 |  |
| dimcompany | ok | 1 | 0 | 11609/6704 |  |
| dimsecurity | ok | 1 | 0 | 7056/4627 |  |
| dimtrade | ok | 1 | 0 | 12256/2543 |  |
| factcashbalances | ok | 1 | 0 | 3174/10112 |  |
| factholdings | ok | 2 | 0 | 8018/20191 |  |
| financial | ok | 1 | 0 | 9222/4910 |  |
| prospect | ok | 1 | 0 | 12781/5151 |  |

## Formulas

205 columns answered, 1 with errors or no valid answer.

- dimsecurity.iscurrent: b1: SELECT/FROM not allowed

## Tables built (`tables.duckdb`; sample_rows: all)

| table | built | rows | error |
|---|---|---|---|
| industry | yes | 102 |  |
| statustype | yes | 6 |  |
| taxrate | yes | 320 |  |
| tradetype | yes | 5 |  |
| dimdate | yes | 25933 |  |
| dimtime | yes | 86400 |  |
| dimbroker | yes | 15000 |  |
| dimcustomer | yes | 14572 |  |
| dimaccount | yes | 12860 |  |
| dimcompany | yes | 1500 |  |
| dimsecurity | yes | 2400 |  |
| dimtrade | yes | 390978 |  |
| factcashbalances | yes | 361856 |  |
| factholdings | yes | 362342 |  |
| financial | yes | 98576 |  |
| prospect | yes | 14982 |  |

## Calls

383 calls, 33 failed, 10 cut at the output limit, 9 empty. Tokens in 1415564, out 762621.

## Scoring

Not tested yet (run `fieldgen test`; it needs a reference folder).
