# Results

Source: the experiment log `FINDINGS.md` (not part of this folder). **Every result below is a single run** (one model, one call set); the tool was not rerun to pick a better result. One run varies by a few tables or columns, so differences of one or two columns are not evidence.
Model: nvidia/nemotron-3.5-super-vl-120b-a12b (reasoning low). Predictions were written before each run. The config of each run is in `configs/`.

## 1. Synthea to OMOP (18 scored tables, headline measure L2)

| | v1.2-demo (default) | column knowledge on (`formula_docs`) |
|---|---|---|
| change | none (formula prompts show no column rules) | formula prompts show each column's documented rules |
| prediction | | 11-13 tables, 53-57 columns |
| tables with correct rows | 11 of 18 | **13 of 18** |
| L2 columns correct (in tables with correct rows) | 54 (of 59) | **57** (of 65) |
| changed tables | | observation, cdm_source: rows wrong -> right; location, payer_plan_period: one column lost each |

The shipped v1.2-demo headline (12 of 18 tables, 54 of 60 columns) comes from separate experiments; the 11 / 54 above is one full default run of the same release, measured on the same package.

## 2. TPC-DI DimCustomer (28 columns), runs 1-10

Run 1 and 2 built 9 tables; the DimCustomer columns of those runs are shown. From run 3 only DimCustomer is built. Runs 7 and 9a stop after the recipe step. Run 5 has no entry in FINDINGS.md.

| run | what changed | prediction | result |
|---|---|---|---|
| 1 | v1.2-demo, documentation only, no expert text | 18-22 columns | 10 / 28 (9 tables: 67 / 91 columns, 6 tables PASS) |
| 2 | + 7 lines of expert text (history, lookups, valid values) | 15-24 | 0 / 28 (0 rows: self-join without ordering) |
| 3 | DimCustomer only; expert point 2 extended (join event fragments, empty = unchanged) | 12-22 | 10 / 28 |
| 4 | tool: `formula_docs` + `history_pattern` (generic history text) | 15-24 | 12 / 28 |
| 6 | tool: `history_tables` (package names key, order, tiebreak; tool groups and takes the latest non-empty value) + length retry | 16-24 | 22 / 28 |
| 7 | tool: `history_auto` (the model decides the wrapper), recipe only | on for DimCustomer, off for DimCompany | wrong: on in 1 of 3 DimCustomer calls |
| 8 | source filled by us: one `CustomerHistory` table, one row per action, empty fields carried forward | 15-22 | 10 / 28 |
| 9a | run 8 source, expert point 2 replaced (latest record by timestamp), recipe only | one latest row, no grouping, in 2 of 3 calls | holds: 2 of 3 use an anti-join (3 also groups) |
| 9b | run 9a, formulas too | 16-24 | 19 / 28 |
| 10 | run 9b + `formula_docs` (rules shown to the formula step) | 21-25 | **23 / 28** |

Still wrong in run 10: gender (NEW with no gender should give U), the three Prospect columns (the rule needs a match on current values; a plain `=` join was written), marketingnameplate (the tag list is not in the documentation given to the tool).

## Main findings

1. The model copies and looks up well (all copy tables, most DimCompany columns) but does not build "current state from events" by itself: runs 1-4 stayed at 0-12 of 28.
2. Giving the tool the history pattern as package input (run 6, key / order / tiebreak) or preparing the source (run 8) helps only when the recipe also keeps one latest row (run 9b: 19).
3. Showing each column's documented rules to the formula step is the one general change that helped on both datasets: TPC-DI 19 -> 23 of 28 (run 9b -> 10) and Synthea 11 -> 13 tables, 54 -> 57 columns. It is on by default.
4. Letting the model switch the history wrapper on by itself (run 7) was unreliable: 1 of 3 calls.
5. What remains is outside the tool's checkers or the documentation: matches on current values (subqueries are rejected in formulas) and rules that are not written in the documentation (nameplate tags).

Each number is one run of one model. Do not read a difference of one or two columns as an effect.

Note on the replay answers: in `replay/answers/tpcdi_run6.json` and `tpcdi_run10.json` the free-text `assumptions` lists of the model's answers were emptied, because they may quote the TPC-DI specification. Recipes, expressions and all other fields are unchanged; the replays reproduce the recorded scores (run 6: 22 of 28, run 10: 23 of 28).

## Known limits

- Each result is a single run of one model. A difference of one or two columns is within the variation between runs.
- The recipes and formulas fit the dataset they were made for. A new dataset needs a new run.
- `history_tables` (off by default) needs the package to name the key, the order and the tiebreak column of the event records. The tool does not find them.
- Three Prospect columns (agencyid, creditrating, networth) are wrong in both TPC-DI replays. In run 10 the generated join compares with plain `=`, so customers with an empty address line are not matched. In the run 6 setup (raw event records) the match needs a subquery, and the formula checker rejects subqueries.
- `history_auto` (off by default) expects `column` or `table.column` names. Alias forms such as `c.C_ID` are not resolved.
- MarketingNameplate is wrong in every TPC-DI run because we left its tag list out of the package by mistake.
- In the saved TPC-DI answers in `replay/answers/`, the free-text `assumptions` lists are emptied, because they may quote the TPC-DI specification. Recipes, expressions and all other fields are unchanged, and the replays still match the recorded scores.
- The default endpoint is free and records inputs and outputs.
