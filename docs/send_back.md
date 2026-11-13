# What to send back after a test

Send these files from your run folder (`run/`, next to your package folder). They contain no key and no source data.

1. `report.md`
2. `summary.json`
3. `settings.json`
4. `scores.json` and `execute.json` (only if you ran `test` and `execute`)
5. the folders `recipes/`, `formulas/` and `sql/`
6. the output of `fieldgen check --package <your package>` and of `fieldgen generate` (copy the text)
7. the `config.yaml` you used (if you changed it)
8. a few lines in plain words: what your dataset is, what the target model is, how many tables and columns, what went wrong or looked wrong

One command that collects 1 to 5 (run it inside the run folder):

```bash
zip -r send_back.zip report.md summary.json settings.json scores.json execute.json recipes formulas sql
```

(If `scores.json` or `execute.json` does not exist, zip complains about that name. Ignore it.)

**Do not send** these unless you are sure you may share your data: `calls.jsonl` (it holds the prompts, with samples of your values), `tables.duckdb` (your built tables), `recipes.jsonl` and `formulas.jsonl` (they hold the prompts too), `work/`, and anything from `source/data/` of your package.

If a run stopped early, also send `stop_report.json` or `stop_400.json` if they exist. They hold the reason and the size of the input, no data.
