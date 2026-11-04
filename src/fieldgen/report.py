"""report.md of a run (settings used, tables built, errors, model served, scoring when done). No key, no headers."""
import json
from pathlib import Path

def _jl(p): return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] if Path(p).exists() else []

def write_report(out, s, summary, scores=None, execution=None):
    out = Path(out); recs = {r["table"]: r for r in _jl(out / "recipes.jsonl")}; forms = _jl(out / "formulas.jsonl"); calls = _jl(out / "calls.jsonl"); ok = [c for c in calls if "finish_reason" in c]
    L = ["# fieldgen run report", "", f"Stages: **{s.stages}**. Model asked for: `{s.model}`. Model id served: `{', '.join(map(str, summary['served_models'])) or 'none'}`. Time: {summary['seconds']} s.", ""]
    if summary.get("stopped"): L += [f"**The run stopped early:** {summary['stopped']}", ""]
    L += ["## Settings used", "", "```json", json.dumps({**s.as_dict()}, indent=1), "```", ""]
    if summary["warnings"]: L += ["## Warnings", ""] + [f"- {w}" for w in summary["warnings"]] + [""]
    L += ["## Recipes", "", "| table | recipe | calls | retries | tokens in/out | errors |", "|---|---|---|---|---|---|"]
    for t in summary["tables_to_build"]:
        r = recs.get(t)
        if not r: L.append(f"| {t} | not run | | | | |"); continue
        L.append(f"| {t} | {'ok' if r.get('recipe') else '**no valid recipe**'} | {r.get('n_calls')} | {(r.get('retry_log') or {}).get('retries', 0)} | {r['tokens']['in']}/{r['tokens']['out']} | {'; '.join(r.get('errors') or [])[:100]} |")
    if s.stages == "recipes_and_formulas":
        bad = [f for f in forms if not f.get("final") or f.get("errors")]
        L += ["", f"## Formulas", "", f"{len(forms)} columns answered, {len(bad)} with errors or no valid answer.", ""]
        for f in bad[:20]: L.append(f"- {f['task_id']}: {'; '.join(f.get('errors') or ['no valid answer'])[:120]}")
        if execution:
            L += ["", f"## Tables built (`tables.duckdb`; sample_rows: {execution['sample_rows']})", "", "| table | built | rows | error |", "|---|---|---|---|"]
            for b in execution["tables"]: L.append(f"| {b['table']} | {'yes' if b['ok'] else '**no**'} | {b['rows']} | {(b['error'] or '')[:100]} |")
        else: L += ["", "## Tables built", "", "Not executed yet: run `fieldgen execute`."]
    if summary.get("dropped_expert_lines"): L += ["", "## Expert text dropped because the documentation covers the same column", ""] + [f"- {x[:200]}" for x in summary["dropped_expert_lines"][:60]]
    L += ["", "## Calls", "", f"{len(calls)} calls, {len(calls) - len(ok)} failed, {sum(c.get('finish_reason') == 'length' for c in ok)} cut at the output limit, {sum(bool(c.get('empty_content')) for c in ok)} empty. "
          f"Tokens in {sum((c.get('usage') or {}).get('prompt_tokens', 0) for c in ok)}, out {sum((c.get('usage') or {}).get('completion_tokens', 0) for c in ok)}."]
    L += ["", "## Scoring", ""]
    if scores is None: L.append("Not tested yet (run `fieldgen test`; it needs a reference folder).")
    else: L += scores
    (out / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
