# Build notes (demo release v1.1-demo)

How this repository was made from the experiment repository (`~/benchmark/fieldgen`, not modified), what was kept, what was left out, what was checked, and what is open.

## What the default path contains

| step | modules (`src/fieldgen/`) |
|---|---|
| package and data | `package`, `check` (format checks), `db`, `profiling` (profiles computed from CSV when missing) |
| field cards (what the model sees of each column) | `cards` (builder), `cards_view`, `neighbourhood`, `tasks` |
| recipe step | `recipe_prompts`, `view_base` > `view_cards` > `view_facts` > `view_nulls` > `view_domain` > `view_conventions` (a chain of views, one feature each), `domain_base`, `domain_files`, `domain_text`, `link_facts`, `link_facts_nulls`, `recipe_check`, `recipe_stage`, `parse`, `json_extract` |
| formula step | `formula_prompts`, `formula_run`, `formula_stage`, `formulas`, `guardrail`, `assemble`, `final_expr` |
| table build | `build`, `assemble` |
| model access | `llm`, `client` (flags logged, stop rules, HTTP 400 stop), `models`, `guard` |
| scoring (reference side only) | `score_run`, `scorer` (alias assignment), `harness_keys`, `harness_fix`, `harness`, `compare`, `l4` (with the UTC session time zone), `assemble_v1`, `check_reference` |
| command line | `cli` (init, generate, execute, test, check), `__main__`, `settings` (config.yaml), `pipeline` (prepare, generate, execute), `report` |
| package creation | `init_package` (source data and target schema to a package; proposed keys and links), `todo` (what is left, what blocks `generate`) |
| test (reference side only) | `testing`, `reference_build` (runs reference recipes to build reference tables), `score_run` and the scorer modules above |

Left out on purpose: all experiment launchers and old variants, option B (documentation on request), `target_key_refs`, the key-reference part of the scorer, the old V1 evaluator and the old robustness code.
The first copy was mechanical (renamed modules, rewritten imports). Old name in the experiment repository (`src/`) and new name here:

| old module | new module |
|---|---|
| `llm` | `llm` |
| `config` | `models` |
| `package` | `package` |
| `db_v2` | `db` |
| `dump` | `cards` |
| `dump_view` | `cards_view` |
| `taskgen` | `tasks` |
| `neighbourhood` | `neighbourhood` |
| `domain_v3` | `domain_base` |
| `domain_v5` | `domain_files` |
| `link_profile_v4` | `link_facts` |
| `link_profile_v5` | `link_facts_nulls` |
| `step1_view` | `view_base` |
| `step1_view_v3` | `view_cards` |
| `step1_view_v4` | `view_facts` |
| `step1_view_v5` | `view_nulls` |
| `step1_view_v6` | `view_domain` |
| `step1_view_v8` | `view_conventions` |
| `parse_v2` | `parse` |
| `parse` | `json_extract` |
| `recipe_retry_v3` | `recipe_check` |
| `context_v2` | `formula_prompts` |
| `guardrail` | `guardrail` |
| `assemble_v2` | `assemble` |
| `assemble` | `assemble_v1` |
| `evaluate_free` | `final_expr` |
| `evaluate_v2` | `harness` |
| `evaluate_fix_v2` | `harness_fix` |
| `evaluate_e1` | `harness_keys` |
| `scorer_v4` | `scorer` |
| `l4_v2` | `l4` |
| `generate_v2` | `formula_run` |
| `generate_d2` | `formula_stage` |
| `evaluate` | `compare` |
| `client_v3` | `client` |
| `client_exp1` | `client` |
| `run_c5` | `guard` |
| `domain_text_v2` | `domain_text` |

Modules written new for this release: `settings`, `check`, `check_reference`, `pipeline`, `report`, `cli`, `build`, `formulas`, `recipe_prompts`, `recipe_stage`, `profiling`, `score_run`, `paths`, and for v1.1 `init_package`, `todo`, `testing`, `reference_build`.
Class names inside the view chain (`Step1ViewV3`, ...) and some variable names in the scorer (`gold`) are unchanged.

## Changes made while copying (everything else is unchanged code)

- Paths: prompts and schemas are package resources; no absolute paths.
- The reference folder is `reference/` (was `gold/`); `check` rejects a package manifest with a `gold` section.
- Matches come from one file, `matches/matches.json` (was three settings).
- Domain files have plain names (`descriptions_supplement.json`, `value_meanings.json`, `flow_text.md`); the flow text is our Standard v3 text with the sentence about the domain of the standard concept.
- The field cards are built into the run folder (`work/cards`); the package is never written to.
- New: `data_profiling`, `documentation_first`, `source_labels`, `measured_links` and `min_coverage` as switches (these are the "untested" ones), the minimum reference format (`alignment.json`), profiles computed from the CSV files, the `fieldgen` command line, `check`, the report.
- `l4`: the perturbed-data connections run in UTC (the fix we found after the Mode B results). Earlier L4 numbers kept the local zone.

## v1.1: the restructure into init, generate, execute, test

- The commands of v1.0 (`check`, `run`, `score`) became `init`, `generate`, `execute`, `test` (and `check`). Each takes only `--package DIR`; all other settings come from `config.yaml` in the current folder. The run folder is `run/` and the reference is `reference/`, both next to the package folder.
- `generate` stops when the package has problems or blocking TODOs; it no longer builds tables (`execute` does). `execute.sample_rows` and `robustness_check` are new options (nothing removed from `config.yaml`; `score_levels` still works and `L2_and_L4` switches `robustness_check` on).
- `test` handles three cases: reference tables, reference recipes (it runs them to build the reference tables), neither ("no reference, nothing to test"). It also stops if reference text is found in the package.
- A bug found on the way: an unquoted `off` in YAML is read as false, so `domain_knowledge: off` and similar options were rejected. `off` is now accepted with or without quotes (test added).
- Issue 10 (the +05:30 text): it comes from the data files, not from the tool. The prompts are identical in other machine time zones (a test builds them under four zones in separate processes); `export_reference.py` now pins UTC. The data was not changed.
- **No prompt changed.** After the restructure the 18 recipe prompts equal the Standard v4 prompts (18 of 18) and the 60 formula prompts equal the stored prompts (60 of 60), built through `pipeline.prepare` (the code path `generate` uses).
- **Reference built from recipes** (corrected in v1.2): the 10-of-26 figure given in v1.1 came from comparing whole tables, including numbered ids and cross-table keys that are never scored. Measured the way the scorer measures, the rebuilt reference equals the original on 26 of 26 tables and 152 of 152 scored columns. The one exception was a key the reference program took from another table (`observation_period.person_id`); it is now filled from the referenced table. The reproduction run tested against the rebuilt reference gives the same result as against the original tables (11 of 18 tables, 54 of 95 columns).

## Checks done on the build

- **Recipe prompts:** built with the default settings from the full example package, they are identical to our Standard v4 prompts for all 18 tables (byte for byte). The same with no profile files and no dependencies file.
- **Formula prompts:** identical to the stored prompts of the Mode B run for all 60 columns.
- **Tests (v1.0):** `pytest` ran 65 offline tests (no network, no key): config parsing and the "untested setting" warnings, `check` on a good and several broken packages (and the reference leak check), a static and a run-time leak test (the tool opens nothing under the reference folder), a key scan of the repository and of run outputs, `reference` auto and off, both reference formats, L4 on a full reference and its skipping on a minimum one, resume, stop on HTTP 400, missing key, domain knowledge required, optional and off.
  The tests use a small synthetic package (a shop) with invented names, and a fake model endpoint.
- **Install:** `pip install .` puts the prompts and schemas in place and the `fieldgen` command works from the installed copy.
- **Helper scripts for the example** (`examples/synthea_omop/tools/`): the source data they write equals ours row for row; the reference tables they export equal ours for 24 of 26 tables (cost and measurement differ in trailing zeros of decimals).

## Reproduction run (one run, defaults, API calls)

The v1.0 command `fieldgen run --package <example package, completed>` (now `generate`, `execute`, `test`) with the default settings (model `nvidia/nemotron-3.5-super-vl-120b-a12b`, served as `private/nvidia/nemotron-3.5-super-120b-a12b`), one repeat, scored against the reference at the end.
The package used was our full local copy of the example (the same files that `examples/.../tools` rebuild, plus the data). The result files are not in this repository: the report quotes values from the source data (in the text data check warnings).

| measure | this run | headline |
|---|---|---|
| tables with correct rows, of the 18 scored tables | **11** | 12 |
| L2 columns correct on the 60 columns of the 12 headline tables | **54 of 60** | 54 of 60 |
| L2 columns correct on all 95 scored columns (this run also wrote formulas for tables with wrong rows) | 54 of 95 (54 of 59 in the tables with correct rows) | not measured the same way |

- The table that dropped out: **cdm_source** (it was correct in 3 of 3 repeats of the Standard v4 recipe experiment, in 0 of 5 before; one repeat varies).
- The wrong columns in tables with correct rows are the ones we knew: `visit_occurrence.visit_concept_id` and `visit_end_date`, `visit_detail.visit_detail_concept_id` and `visit_detail_end_date`, `provider.gender_source_concept_id`.
  `location.zip` was correct this time (it is wrong in some runs).
- 19 tables were built (the 18 scored tables and `drug_era`, which has no reference). 130 calls, none failed, 2 cut at the output limit, 2 empty, 1.24M tokens in and 0.30M out, 1374 s for the run plus scoring time.
- One run varies by a table or a few columns. The two headline numbers come from separate experiments (recipes: 12 of 18; formulas on the first passing recipes: 54 of 60).
- In this run the domain-text data check printed 60 warnings. That was a bug in the choice of lines to check (it included lines with clipped sample values). It was fixed after the run started and only changes the warning. On the correct lines the check finds 3 quoted examples of the OMOP documentation that are not in the data.

## v1.2 fixes

1. `reference_build`: cause and fix above. A test covers the foreign-key fill.
2. `init` on the real OMOP CDM v5.4 DuckDB DDL (OHDSI/CommonDataModel tag v5.5.0, the three files for tables, primary keys and foreign keys): 39 tables, 432 columns, 27 primary keys, 178 foreign keys, no errors; the same tables, columns, keys and foreign-key counts as the example's `target/tables.json`. Fixed on the way: `TIMESTAMP` was written as `timestampntz` (DuckDB rejects it), `varchar(50)` lost its length, and constraint files that sort before the table file lost their keys. `--target` now also takes a folder of `.sql` files. On the source side (our Synthea data): 25 of 29 tables got a proposed key (none for 4), 48 links proposed.
3. `config.yaml` is read from the package folder, then the current folder, then the defaults; the command prints the full path it used.
4. Tracked files: the v1.1 tree held `docs/reproduction/` (a run report that quotes values of the source data); it is no longer tracked. **The local commits v1.0-demo and v1.1-demo still contain those three files in their history: squash or rewrite before any publication.** No other tracked file holds run output or data.
5. Live check of the tester's path (example package from this repository, data added with the fill script, default config, one run): `generate` 1341 s, `execute` 4 s, `test` 78 s. 11 of 18 tables with correct rows; L2 columns 53 of 60 (the 12 headline tables) and 54 of 95. 122 calls, none failed, 0.86M tokens in and 0.28M out. Confusing points found and fixed: `execute` said "18 of 19 tables built" without naming the failing table (cdm_source: a generated formula that is not valid in a grouped query); output reached a file only at the end (now line-buffered); the config line showed a relative path.

## Open issues

1. **Licence of the tool.** Not chosen. `LICENSES.md` says all rights are reserved until the owner decides.
2. **The example is not self-contained.** Data, vocabulary seeds and reference tables are left out for licence reasons; two scripts rebuild them from your own dbt-synthea copy. The reproduction used our local complete copy.
3. **No package builder.** Packages are written by hand (`docs/input_package.md`). Profiles are computed; dependencies are not used.
4. **One model tested in full.** Ultra 550B was tested on the recipe step only. Mistral Large 4 1T was not run.
5. **The free endpoint records inputs and outputs.** See `docs/results.md`.
6. **Keys from other target tables are out of scope** (`target_key_refs` was removed).
7. **HTTP 400 stop.** The response body is not logged, so a context-length error cannot be told from another 400.
8. **Scoring time.** The scorer starts one process per table and needs a minute or more for each; L4 is slower. It uses the fork start method, so scoring is for Linux.
9. **The minimum reference format** (`alignment.json`) was tested on the synthetic package only, not on a real move.
10. **Time zone of the example data.** The example data is written with a +05:30 offset (the zone it was built in); the instants equal the original seeds.
11. **Run time.** The default run took about 25 minutes of calls on the free endpoint; the example completion steps and scoring take longer.
12. Cosmetic: internal names such as `gold` and `Step1ViewV6` remain in the code.
