"""`fieldgen run` (generator side): check the package, build the field cards, recipe step per target table, formula step per matched column, table build, report.
The generator reads only the package (manifest, source, target, matches, domain). It never reads a reference folder; scoring is a separate step (fieldgen.score_run)."""
import concurrent.futures as cf, json, os, threading, time
from pathlib import Path
from fieldgen import cards, guardrail as G
from fieldgen.settings import untested, extra_body
from fieldgen.package import load_package
from fieldgen.db import package_connection
from fieldgen.check import check_package
from fieldgen.cards_view import DumpView
from fieldgen.rules_history import column_rules, history_text
from fieldgen.history import apply_history, formula_text, HistoryError
from fieldgen.domain_text import DomainTextV2, data_check, set_labels, description_part, split_label
from fieldgen.formula_run import set_connection
from fieldgen.models import ModelCfg
from fieldgen import recipe_prompts as rp
from fieldgen.recipe_stage import generate_recipe
from fieldgen.formulas import formula_columns, generate_formula, expressions
from fieldgen.build import build_tables, table_query
from fieldgen.todo import package_todos
from fieldgen.guard import Guard, Stop as GuardStop
from fieldgen.client import Stop as ClientStop
from fieldgen.report import write_report

LIMITS = {"max_input_tokens": 30000000, "window": 50, "max_fail_rate": 0.3}
OV = {"temperature": 0.0}

class PipelineError(Exception): pass

def model_cfg(s):
    return ModelCfg(name="main", provider="openai-compatible", base_url=s.base_url, api_key_env=s.api_key_env, model=s.model, temperature=0.0, top_p=1.0, max_tokens=4096, timeout_s=s.timeout_s,
                    requests_per_minute=s.requests_per_minute, max_concurrency=s.concurrency, retries=1, json_mode=True, strip_thinking=True, extra_body=extra_body(s))

def recipe_text(table, r):
    L = [f"Recipe for {table}", f"Grain: {r.get('grain')}", f"Combine: {r['combine']}" + (f"; group by {', '.join(r['group_by'])}" if r.get("group_by") else "")]
    for b in r["branches"]: L += [f"Branch {b['id']}:", "  " + " ".join(b["from"].split())]
    for k in r.get("keys") or []: L.append(f"Generated key {k['column']}, numbered in the order of: {', '.join(k['order_by'])}")
    d = r.get("decisions") or {}
    if d: L.append("Decisions: " + "; ".join(f"{k}: {v}" for k, v in d.items()))
    for a in r.get("assumptions") or []: L.append("Assumption: " + a)
    return "\n".join(L) + "\n"

def _read_jsonl(p): return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] if Path(p).exists() else []

def tables_to_build(pkg, copies):
    """Target tables with at least one matched source column that are not plain copies of a source table."""
    M = pkg.matches(); return [t["name"] for t in pkg.target.tables if any(M.get(f"{t['name']}.{c['name']}") for c in t["columns"]) and t["name"] not in copies]

def problems(package_dir, settings):
    """(errors, blocking TODOs, notes): what `fieldgen generate` checks before it starts."""
    chk = check_package(package_dir); blocking, notes = package_todos(package_dir, settings) if chk["ok"] else ([], [])
    return chk["errors"], blocking, notes

class Context:
    pass

def prepare(package_dir, settings, out, log=print, only=None):
    """Check the package, build the field cards, the view and the task of every target table. Nothing is sent to a model."""
    s = settings; package_dir = Path(package_dir).resolve(); out = Path(out); out.mkdir(parents=True, exist_ok=True); c = Context(); c.s, c.package_dir, c.out = s, package_dir, out
    errors, blocking, _ = problems(package_dir, s)
    if errors or blocking: raise PipelineError("the package is not ready:\n" + "\n".join([f"  problem: {e}" for e in errors[:10]] + [f"  TODO: {b}" for b in blocking]))
    domain_present = (package_dir / "domain").is_dir() and any((package_dir / "domain").iterdir())
    c.domain_on = s.domain_knowledge != "off" and domain_present
    c.warnings = [f"untested setting: {w}" for w in untested(s)]
    if s.domain_knowledge == "optional" and not domain_present: c.warnings.append("domain_knowledge is optional and the package has no domain/ folder: running without domain knowledge")
    for w in c.warnings: log("WARNING " + w)
    (out / "settings.json").write_text(json.dumps({**s.flat(), "domain_knowledge_used": c.domain_on}, indent=1), encoding="utf-8")
    work = out / "work"; work.mkdir(exist_ok=True)
    if not (work / "cards" / "manifest.json").exists(): log("building the field cards ..."); cards.build(package_dir, out_dir=work / "cards", progress_path=work / "cards_progress.json")
    cards.set_cards_dir(work / "cards"); set_labels(s.source_labels)
    c.pkg = load_package(package_dir); c.con = package_connection(c.pkg); set_connection(c.con)
    dt0 = DomainTextV2(c.pkg, package_dir, None); c.build = [t for t in tables_to_build(c.pkg, set(dt0.copies.values())) if not only or t in only]
    c.view = rp.make_view(c.pkg, package_dir, s, c.domain_on, c.con, str(work / "link_facts.json")); c.tasks = {t: rp.build_task(c.pkg, c.view, t) for t in c.build}
    c.check_lines = []
    if c.domain_on and s.text_data_check == "warn":
        for t in c.build:
            c.check_lines += [l for l in c.tasks[t]["e1"]["domain_knowledge"].split("\n") if l.strip()]
            for r in c.tasks[t]["e1"]["relation_text"].values(): c.check_lines += [d for d, l in ((description_part(l, c.view.dt.doc_label), l) for l in r.split("\n") if l.startswith("- ")) if d != l]
        bad = data_check(c.con, sorted(set(c.check_lines)))
        for line, lab_, kind, val in bad[:10]: c.warnings.append(f"text data check: {kind}: {val!r} (in: {split_label(line)[0][:90]})")
        if bad: log(f"WARNING text data check: {len(bad)} quoted value(s) in the domain text are not in the data (see report.md)")
    return c

def generate(package_dir, settings, out_dir, client_factory=None, log=print, only=None):
    """Recipes, formulas and the final SQL of every target table, written into the run folder. Does not run the SQL (that is `execute`)."""
    s = settings; t_start = time.time()
    errors, blocking, _ = problems(package_dir, s)
    if errors or blocking: raise PipelineError("the package is not ready:\n" + "\n".join([f"  problem: {e}" for e in errors[:10]] + [f"  TODO: {b}" for b in blocking]))
    if client_factory is None and not os.environ.get(s.api_key_env): raise PipelineError(f"environment variable {s.api_key_env} is not set (the key is only read from the environment)")
    c = prepare(package_dir, s, out_dir, log, only); out, pkg, con, tasks, build = c.out, c.pkg, c.con, c.tasks, c.build; package_dir = c.package_dir
    calls = out / "calls.jsonl"; cfg = model_cfg(s); sh = None
    if client_factory is None:
        from fieldgen.client import Client400, Shared
        sh = Shared(check_first=True, report=str(out / "stop_report.json")); Client400.report = str(out / "stop_400.json")
        client_factory = lambda p: Client400(cfg, s.flat(), sh, calls_path=p)
    client = client_factory(str(calls)); guard = Guard(LIMITS, 0); stats = {"recipe_runs": 0, "formula_runs": 0}; stopped = None; rec_path, form_path = out / "recipes.jsonl", out / "formulas.jsonl"
    try:
        done = {r["table"] for r in _read_jsonl(rec_path)}; todo = [t for t in build if t not in done]
        def work_recipe(t):
            try: r = generate_recipe(tasks[t], client, s, con, **OV)
            except Exception as e:
                guard.record(False, 0, str(e)); return {"table": t, "recipe": None, "errors": [str(e)[:200]], "tokens": {"in": 0, "out": 0}, "failed_call": True, "attempts": [], "n_calls": 0}
            hc = (s.history_tables or {}).get(t.lower())
            if not hc and s.history_auto and r.get("recipe"): hc = r["recipe"].get("history")      # the model's own decision (null = no history)
            if hc and r.get("recipe"):          # listed table: the tool sets the grouping (see history.py)
                try: r["recipe"] = apply_history(r["recipe"], hc, pkg, pkg.target.table(t)["pk"])
                except HistoryError as e: r["recipe"] = None; r["errors"] = list(r.get("errors") or []) + [str(e)]
            guard.record(True, r["tokens"]["in"]); return {"table": t, **r}
        log(f"recipe step: {len(todo)} of {len(build)} tables to do")
        with cf.ThreadPoolExecutor(max_workers=s.concurrency) as ex:
            for r in ex.map(work_recipe, todo):
                with open(rec_path, "a", encoding="utf-8") as f: f.write(json.dumps(r, default=str) + "\n")
                stats["recipe_runs"] += 1; log(f"  {r['table']}: {'recipe ok' if r.get('recipe') else 'NO VALID RECIPE'}")
        recipes = {r["table"]: r for r in _read_jsonl(rec_path)}
        for t, r in recipes.items():
            if r.get("recipe"): (out / "recipes").mkdir(exist_ok=True); (out / "recipes" / f"{t}.json").write_text(json.dumps(r["recipe"], indent=1), encoding="utf-8"); (out / "recipes" / f"{t}.txt").write_text(recipe_text(t, r["recipe"]), encoding="utf-8")
        if s.stages == "recipes_and_formulas":
            dump = DumpView(package_dir); src_tables = {r["relation"] for r in dump.sf.values()}; pool = G.make_pool(str(package_dir)); fdone = {r["task_id"] for r in _read_jsonl(form_path)}
            items = [(t, col) for t in build if recipes.get(t, {}).get("recipe") for col in formula_columns(tasks[t], recipes[t]["recipe"]) if f"{t}.{col}" not in fdone]
            log(f"formula step: {len(items)} columns to do")
            def work_formula(it):
                t, col = it
                try: res = generate_formula(tasks[t], recipes[t]["recipe"], col, client, dump, pool, src_tables, {**OV, "max_tokens": 8192}, max_guard_retries=s.max_retries if s.retry_on_error != "off" else 0,
                                           rules=column_rules(c.view, t, col) if s.formula_docs else None, history=(formula_text((s.history_tables or {})[t.lower()]) if t.lower() in (s.history_tables or {}) else history_text(s.history_pattern and bool(recipes[t]["recipe"].get("group_by")))), length_retry=s.formula_length_retry)
                except Exception as e:
                    guard.record(False, 0, str(e)); return {"task_id": f"{t}.{col}", "final": None, "errors": [str(e)[:200]], "runs": None, "tokens": {"in": 0, "out": 0}, "failed_call": True, "n_calls": 0}
                guard.record(True, res["tokens"]["in"]); return res
            try:
                with cf.ThreadPoolExecutor(max_workers=s.concurrency) as ex:
                    for res in ex.map(work_formula, items):
                        with open(form_path, "a", encoding="utf-8") as f: f.write(json.dumps(res, default=str) + "\n")
                        stats["formula_runs"] += 1
            finally: pool.shutdown(wait=True, cancel_futures=True)
            by_table = {}
            for r in _read_jsonl(form_path): by_table.setdefault(r["task_id"].split(".", 1)[0], {})[r["task_id"].split(".", 1)[1]] = expressions(r)
            (out / "sql").mkdir(exist_ok=True); (out / "formulas").mkdir(exist_ok=True)
            for t in build:
                if not recipes.get(t, {}).get("recipe"): continue
                spec = table_spec(pkg, t, recipes[t]["recipe"], by_table.get(t, {})); (out / "sql" / f"{t}.sql").write_text(table_query(spec["recipe"], spec["columns"], spec["exprs"], spec["types"]) + "\n", encoding="utf-8")
            for t, cols in by_table.items(): (out / "formulas" / f"{t}.json").write_text(json.dumps(cols, indent=1), encoding="utf-8")
    except (GuardStop, ClientStop) as e: stopped = str(e)
    if s.formula_length_retry:
        stats["formula_length_retries"] = sum(r.get("length_retries", 0) for r in _read_jsonl(form_path)); log(f"formula length retries (call ended length/empty, asked again with double max_tokens): {stats['formula_length_retries']}")
    summary = {"tables_to_build": build, "recipes_valid": sorted(t for t, r in (({r["table"]: r for r in _read_jsonl(rec_path)}).items()) if r.get("recipe")), "built": [],
               "served_models": (sh.served if sh else ["(test client)"]), "stopped": stopped, "warnings": c.warnings, "seconds": round(time.time() - t_start), "stats": stats,
               "text_data_check_lines": len(set(c.check_lines)), "stages": s.stages, "dropped_expert_lines": list(c.view.dt.dropped) if c.domain_on else []}
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8"); write_report(out, s, summary)
    return summary

def table_spec(pkg, t, recipe, exprs):
    tt = pkg.target.table(t)
    return {"table": t, "recipe": recipe, "columns": [col["name"] for col in tt["columns"]], "types": {col["name"]: col["type"] for col in tt["columns"]}, "exprs": {col: e for col, e in exprs.items() if e}}

def execute(package_dir, settings, out_dir, log=print):
    """Runs the final SQL of the run folder on the source data (all rows, or execute.sample_rows rows of each source table) and writes the target tables into tables.duckdb."""
    s = settings; out = Path(out_dir); package_dir = Path(package_dir).resolve()
    if not (out / "recipes.jsonl").exists(): raise PipelineError(f"nothing to execute: no recipes in {out} (run `fieldgen generate --package {package_dir}` first)")
    if s.stages == "recipes": raise PipelineError("stages is 'recipes' in config.yaml: there are no formulas, so there is nothing to execute. Set stages: recipes_and_formulas and run generate again.")
    if not (out / "formulas.jsonl").exists(): raise PipelineError(f"no formulas in {out}: run `fieldgen generate --package {package_dir}` first")
    pkg = load_package(package_dir); n = s.execute["sample_rows"]; con = package_connection(pkg, None if n == "all" else n)
    recipes = {r["table"]: r for r in _read_jsonl(out / "recipes.jsonl")}; by_table = {}
    for r in _read_jsonl(out / "formulas.jsonl"): by_table.setdefault(r["task_id"].split(".", 1)[0], {})[r["task_id"].split(".", 1)[1]] = expressions(r)
    specs = [table_spec(pkg, t, r["recipe"], by_table.get(t, {})) for t, r in recipes.items() if r.get("recipe")]
    db = out / "tables.duckdb"
    if db.exists(): db.unlink()
    built = build_tables(con, str(db), specs) if specs else []
    res = {"sample_rows": n, "tables": [{k: b[k] for k in ("table", "ok", "rows", "error", "dropped_window_formulas")} for b in built]}
    (out / "execute.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    summ = json.loads((out / "summary.json").read_text()) if (out / "summary.json").exists() else {"served_models": [], "seconds": 0, "tables_to_build": list(recipes), "warnings": [], "built": [], "stopped": None, "stages": s.stages}
    summ["built"] = res["tables"]; write_report(out, s, summ, execution=res)
    log(f"executed on {'all rows' if n == 'all' else f'the first {n} rows of each source table'}: {sum(b['ok'] for b in built)} of {len(built)} tables built into {db}")
    return res

def run(package_dir, settings, out_dir, client_factory=None, log=print, only=None):
    """generate + execute (used by the tests)."""
    summ = generate(package_dir, settings, out_dir, client_factory, log, only)
    if settings.stages == "recipes_and_formulas" and not summ["stopped"]: summ["built"] = execute(package_dir, settings, out_dir, log)["tables"]
    return summ
