"""The scorer behind `fieldgen test` (reference side): scores a finished run against a reference folder. Never imported by the generator.
Per target table: does the recipe build the rows of the reference (recipe layer; an alias assignment is tried when a table appears under several aliases)? Per scored column (reference kind 'value'
and a matched source column): L0-L3 and, with score_levels L2_and_L4 and a full reference (reference expressions given), L4 on perturbed data. L2 is the headline measure."""
import concurrent.futures as cf, itertools, json, multiprocessing as mp, os
from pathlib import Path

def _limit_duckdb():
    import duckdb
    nw = max(1, (os.cpu_count() or 2) // 2); ram = [int(l.split()[1]) for l in open("/proc/meminfo") if l.startswith("MemTotal")][0] * 1024 if os.path.exists("/proc/meminfo") else 8 * 2**30
    mem = int(0.7 * ram / nw); thr = max(1, (os.cpu_count() or 2) // nw); o = duckdb.connect
    def conn(*a, **k):
        cfg = dict(k.pop("config", {}) or {}); cfg.update({"memory_limit": f"{mem // 2**20}MB", "threads": thr})
        if a and a[0] != ":memory:" and "read_only" not in k: k["read_only"] = True
        return o(*a, config=cfg, **k)
    duckdb.connect = conn

def _unit(args):
    package_dir, reference_dir, table, recipe, finals, want_l4 = args
    _limit_duckdb()
    from fieldgen.scorer import Scorer
    from fieldgen.package import load_package
    H = Scorer(package_dir, reference_dir); M = load_package(package_dir).matches(); full = bool(H.recipes)
    out = {"table": table, "recipe_rows_correct": False, "assignment": None, "reason": None, "fields": {}, "full_reference": full}; choice = None
    if recipe is None: out["reason"] = "no valid recipe"
    else:
        H._set("strict"); old = H.recipe_layer(table, recipe); out["reason"] = old.get("reason")
        if not old["pass"]:
            H._set("record"); H.recipe_layer(table, recipe); pts = dict(H._points or {}); H._set("strict")
            for combo in itertools.product(*[pts[k] for k in pts]) if pts and len(pts) < 8 else []:
                ch = dict(zip(pts, combo)); H._set("apply", ch)
                try: r = H.recipe_layer(table, recipe)
                finally: H._set("strict")
                if r["pass"]: choice = ch; break
        out["recipe_rows_correct"] = bool(old["pass"] or choice); out["assignment"] = {f"{b}:{tb}.{c}": a for (b, tb, c), a in (choice or {}).items()} or None
    scored = sorted(tid for tid, g in H.fields.items() if g["table"] == table and g["kind"] == "value" and M.get(tid))
    for tid in scored:
        if recipe is None or tid not in finals: out["fields"][tid] = {"L0": False, "L1": False, "L2": False, "L3": False, "L4": None, "error": "no recipe" if recipe is None else "no formula"}; continue
        if choice: H._set("apply", choice)
        try: r = H.score_field(recipe, finals[tid], tid, robust=want_l4 and full)
        finally: H._set("strict")
        out["fields"][tid] = {k: r.get(k) for k in ("L0", "L1", "L2", "L3", "L4", "error")}
    return out

def score_run(package_dir, reference_dir, run_dir, s, levels=None):
    from fieldgen.report import write_report
    run_dir = Path(run_dir); levels = levels or s.score_levels; want_l4 = levels == "L2_and_L4"
    recs = {}
    for l in open(run_dir / "recipes.jsonl", encoding="utf-8"):
        if l.strip(): r = json.loads(l); recs[r["table"]] = r
    finals = {}
    if (run_dir / "formulas.jsonl").exists():
        for l in open(run_dir / "formulas.jsonl", encoding="utf-8"):
            if l.strip(): r = json.loads(l); finals[r["task_id"]] = r.get("final")
    ref_tables = {p.stem for p in (Path(reference_dir) / "reference_data").glob("*.csv")}
    tables = [t for t in recs if t in ref_tables]
    units = [(str(package_dir), str(reference_dir), t, recs[t].get("recipe"), {k: v for k, v in finals.items() if k.startswith(t + ".")}, want_l4) for t in tables]
    nw = max(1, min(len(units), (os.cpu_count() or 2) // 2)); res = []
    with cf.ProcessPoolExecutor(max_workers=nw, mp_context=mp.get_context("fork")) as ex: res = list(ex.map(_unit, units))
    res = {r["table"]: r for r in res}; fields = {tid: f for r in res.values() for tid, f in r["fields"].items()}
    good = [t for t, r in res.items() if r["recipe_rows_correct"]]; in_good = [tid for tid in fields if tid.split(".")[0] in good]
    l2 = sum(bool(f["L2"]) for f in fields.values()); l2g = sum(bool(fields[t]["L2"]) for t in in_good); l4 = sum(f["L4"] is True for f in fields.values()); full = any(r["full_reference"] for r in res.values())
    head = (f"tables with correct rows: {len(good)} of {len(res)} scored tables | L2 columns correct: {l2} of {len(fields)} scored columns ({l2g} of {len(in_good)} in tables with correct rows)"
            + (f" | additional, L4: {l4} of {len(fields)}" if want_l4 and full else (" | L4 skipped: the reference has no reference expressions (minimum format)" if want_l4 else "")))
    score = {"levels": levels, "headline": head, "tables": {t: {k: r[k] for k in ("recipe_rows_correct", "assignment", "reason")} for t, r in res.items()}, "fields": fields}
    (run_dir / "scores.json").write_text(json.dumps(score, indent=1, default=str), encoding="utf-8")
    L = [f"**{head}**", "", "L2 is the headline measure; L4 (perturbed data) is an additional result. The recipes and formulas fit the dataset they were generated from; regenerate for new data.", "",
         "| table | rows correct | columns scored | L2 correct | L4 correct |", "|---|---|---|---|---|"]
    for t, r in sorted(res.items()):
        f = r["fields"]; L.append(f"| {t} | {'yes' if r['recipe_rows_correct'] else '**no**'}{' (alias assignment)' if r['assignment'] else ''} | {len(f)} | {sum(bool(x['L2']) for x in f.values())} | {sum(x['L4'] is True for x in f.values()) if want_l4 else '-'} |")
    L += ["", "Wrong columns (L2):", ""] + [f"- {tid}: {f.get('error') or 'value differs from the reference'}" for tid, f in sorted(fields.items()) if not f["L2"]][:60]
    summary = json.loads((run_dir / "summary.json").read_text()) if (run_dir / "summary.json").exists() else {"served_models": [], "seconds": 0, "tables_to_build": [], "warnings": [], "built": [], "stopped": None}
    exe = json.loads((run_dir / "execute.json").read_text()) if (run_dir / "execute.json").exists() else None
    write_report(run_dir, s, summary, scores=L, execution=exe); score["headline_lines"] = L; return score
