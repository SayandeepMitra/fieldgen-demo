# config.yaml

One file with all options. Every option is optional; a missing option has the default shown here. The defaults are the path we tested as a whole.
The commands read `config.yaml` from the **package folder** first, then from the **current folder**; if neither exists the built-in defaults are used. Each command prints which file it used. The commands take no other options than `--package` (`init` also takes `--source` and `--target`).

**Status**
- *tested*: this value was run in our experiments (the numbers are below).
- *untested*: this value was never run. If you use it, `fieldgen generate` prints `WARNING untested setting: <option> = <value>` at the start.

Our experiments used one dataset (Synthea to OMOP), one model, temperature 0 and a fixed order of changes, so most options were not tested **one at a time**.
"Recipes passing" counts recipes whose rows match the reference (rescored with alias assignment), summed over repeats (18 tables per repeat).

| option | values | default | status | what we measured |
|---|---|---|---|---|
| `model` | any model id of the endpoint | `nvidia/nemotron-3.5-super-vl-120b-a12b` | default tested; others untested | Nemotron-3 Ultra 550B, recipe step: 35 of 54 recipes passing (the 120B model: 39 of 54); 12 tables correct with both; observation improved (1 to 2 of 3), observation_period dropped (3 to 1 of 3). Mistral Large 4 1T: not run (a long request ended with a dropped connection) |
| `reasoning_effort` | `low`, `high`, `off` | `low` | `low` tested; `high`, `off` untested | recipe step only, a rerun of the 25 table-runs without a valid answer: recipes passing per repeat (of 18) with low effort 9/8/9, with thinking off 8/7/7 |
| `stages` | `recipes`, `recipes_and_formulas` | `recipes_and_formulas` | both tested | recipes only: 39 of 54 recipes passing (3 repeats). With formulas, see `docs/results.md` |
| `timeout_s` | seconds per call | `900` | 900 and 1800 tested | median call 35 s, longest 313 s for recipes. With 1800 s, two stalls of 30 to 35 minutes happened (the process was frozen; not confirmed as a call timeout) |
| `requests_per_minute` | number | `20` | `20` tested | used in every run |
| `concurrency` | number of parallel calls | `2` | `2` tested | used in every run |
| `domain_knowledge` | `required`, `optional`, `off` | `required` | `required` tested; `optional` = same behaviour when the files exist; `off` untested | the domain text was added together with other changes: 30 of 54 recipes passing without it (first prompt), 34 with it plus a new system prompt and a retry |
| `reference` | `auto`, `off` | `auto` | tested | `auto` scores only if a reference folder exists |
| `data_profiling` | `true`, `false` | `true` | `true` tested; `false` untested | value lists, null rates and samples were in every prompt |
| `computed_facts` | `true`, `false` | `true` | both tested | facts on lookup links plus the flow text: 28 of 54 recipes passing (first version) against 34 without; after fixing the NULL wording 37 of 54. Not measured one at a time |
| `measured_links` | `true`, `false` | `true` | `true` tested; `false` untested | added with the second domain text: 57 of 90 recipes passing (together with key references that we later removed: 56 of 90 without them) |
| `min_coverage` | 0 to 1 | `0.5` | `0.5` tested | other values untested |
| `documentation_conventions` | `true`, `false` | `true` | both tested | with conventions (3 repeats): cdm_source correct 3 of 3 (0 of 5 without). drug_exposure 0 of 3 (4 of 5 without). Tables correct: 12 and 12. Single-table changes between runs are partly noise: a rerun with only a harmless extra line moved drug_exposure from 4 of 5 to 1 of 3 |
| `documentation_first` | `true`, `false` | `true` | `true` tested; `false` untested | added with the second domain text; not measured one at a time |
| `source_labels` | `true`, `false` | `true` | `true` tested; `false` untested | added with the second domain text; not measured one at a time |
| `join_rules_in_prompt` | `true`, `false` | `true` | both tested | the join explanation was part of the new system prompt (34 of 54 recipes passing with it plus other changes, 30 without) |
| `retry_on_error` | `off`, `errors`, `errors_and_invalid` | `errors_and_invalid` | all tested | in an early run one answer had the wrong format and was not retried, which cost a table (cdm_source). With `errors_and_invalid` the full runs made 4 to 6 retries per 54 to 90 table-runs |
| `max_retries` | 0, 1, 2 | `2` | `2` tested | |
| `text_data_check` | `warn`, `off` | `warn` | both tested | on the OMOP text it finds a few quoted examples that are not in the data (3 in our check) |
| `robustness_check` | `true`, `false` | `false` | both tested | `true` makes `fieldgen test` also run the L4 check on perturbed data (slower). 27 of 60 columns at L4 against 54 of 60 at L2 |
| `execute.sample_rows` | `all`, or a number | `all` | `all` tested | with a number, `fieldgen execute` uses only the first N rows of each source table. Joins on a sample can lose rows: use it to check that the SQL runs, not for real results. Write it as `execute:` with `sample_rows:` below, or as `execute.sample_rows: 100` |
| `score_levels` | `L2`, `L2_and_L4` | `L2` | both tested | L2 is the headline. L4 is slower and adds a second view: 27 of 60 columns at L4 against 54 of 60 at L2 |
| `base_url`, `api_key_env` | endpoint URL, name of the environment variable that holds the key | NVIDIA endpoint, `NVIDIA_API_KEY` | default tested | the key is only ever read from that variable |

## How the options act

- `join_rules_in_prompt`, `documentation_conventions`, `computed_facts`, `measured_links`, `documentation_first`, `source_labels`, `data_profiling` change what is in the recipe prompt (`docs/domain_knowledge.md` shows the labels).
- `retry_on_error`: `errors` asks again when the recipe does not run on your data; `errors_and_invalid` also asks again when the answer is not valid JSON, does not fit the format, or fails a check. The formula step uses the same budget for its guardrail checks (`max_retries`).
- `stages: recipes` stops after the recipes. No formulas, no built tables.
- `robustness_check: true` needs the full reference format (`docs/reference_format.md`). With the minimum format it says "L4 skipped". The older option `score_levels: L2_and_L4` does the same.
- `reference: off` makes `fieldgen test` say "nothing to test" even when a reference folder exists. Write `off` with or without quotes.

## What the numbers do not tell you

They come from one dataset and one model. A difference of one table or a few columns between two runs is inside the noise we saw.
