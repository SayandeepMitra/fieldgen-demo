"""Step 2 with the field-knowledge card in the prompt and a guardrail loop (generator side).
first = answer of the usual step 2 (including its one parse/run retry); then at most `max_guard_retries` retries driven by guardrail
violations. final = the last answer that parses and runs. Every answer is stored with its tokens; every call is in calls.jsonl."""
from fieldgen.formula_prompts import field_task, step2_messages
from fieldgen.parse import parse_field
from fieldgen.assemble import assemble_expr
from fieldgen.formula_run import _attempt, _with_retry, run_sql_ok, task_con, _usage
from fieldgen import guardrail as G

GUARD_RETRY = ("Your previous answer ran, but it violates checks on the target field. Each line names the check, the data or probe value the "
               "check ran on, the rule and the offending results:\n{viol}\n\nThe previous answer was:\n{text}\n\n"
               "Return a corrected JSON object only, in the same format. Keep what was correct; make the expression satisfy the rules, "
               "including on unusual input values (NULL, unseen values, different case, very short or very long values).")

GUARD_RETRY_V2 = ("Your previous answer ran, but it violates a check on the target field. Each line names the check, the rule and the offending results:\n{viol}\n\n"
                  "The previous answer was:\n{text}\n\n"
                  "Return a corrected JSON object only, in the same format. Keep what was correct and change only what the checks above require. "
                  "Do not add default values or invented constants: a NULL source value may give a NULL result.")

def _expressions(final):
    if not final: return None
    if final.get("status") == "answer": return final.get("expressions")
    c = final.get("candidates") or []; d = final.get("default", 0)
    return c[d]["expressions"] if final.get("status") == "ambiguous" and c and 0 <= d < len(c) else None

def step2_guarded(task, recipe, column, client, dump, pool, tables, max_guard_retries=2, conventions=False, guard_version=1, **ov):
    ft = field_task(task, recipe, column, dump=dump, conventions=conventions); msgs = step2_messages(ft); tag = "step2:" + ft["task_id"]
    def check(text):
        obj, errs = parse_field(text, ft); runs = None; asm = {}
        ex = _expressions(obj)
        if ex:
            asm = {e["branch"]: assemble_expr(recipe, e["branch"], [], e["sql"]) for e in ex}
            runs, err = run_sql_ok(task_con(task), list(asm.values()))
            if not runs: errs = errs + [f"does not run: {err}"]
        return {"final": obj, "errors": errs, "runs": runs, "assembled_sql": asm}
    first, parse_retry, cur = _with_retry(client, msgs, tag, check, ov)
    card = dump.tf[(ft["target"]["table"], column)]
    matched = [{"relation": m["relation"], "column": m["column"]} for m in ft["matched"]]
    probes = G.probe_list(dump, matched, tables, card["rules"]["max_length"])
    def guard(answer):
        ex = _expressions(answer["final"])
        if not ex or answer["errors"]: return None
        exs = [{"branch": e["branch"], "sql": e["sql"]} for e in ex]
        cps = G.case_probe_list(ft, exs, dump, tables) if guard_version == 2 else []
        spec = G.make_spec(recipe, exs, card, probes, case_probes=cps, version=guard_version)
        return pool.submit(G.check_in_worker, spec).result() if pool else None
    g = guard(cur); rounds = []; tokens = [first["tokens"]] + ([parse_retry["tokens"]] if parse_retry else [])
    first_answer = cur; first_guard = g; final = cur
    for k in range(1, max_guard_retries + 1):
        if not g or g["ok"]: break
        m2 = msgs + [{"role": "assistant", "content": cur["text"][:6000]},
                     {"role": "user", "content": (GUARD_RETRY_V2 if guard_version == 2 else GUARD_RETRY).format(viol=G.format_violations(g["violations"]), text=cur["text"][:3000])}]
        a = _attempt(client, m2, f"{tag}:guard{k}", check, ov); tokens.append(a["tokens"])
        rec = {"round": k, "violations_before": g["violations"], "answer": {x: a[x] for x in ("text", "final", "errors", "runs", "assembled_sql", "tokens", "latency_s")}}
        valid = a["final"] is not None and not a["errors"]
        if valid: cur = a; g = guard(a); final = a
        rec["violations_after"] = g["violations"] if valid and g else None; rec["valid"] = valid; rounds.append(rec)
    tok = {k: sum(t[k] for t in tokens) for k in ("in", "out")}
    pick = lambda a: {x: a[x] for x in ("text", "final", "errors", "runs", "assembled_sql", "tokens", "latency_s")}
    return {"task_id": ft["task_id"], "messages": msgs, "first": {**pick(first_answer), "guardrail": first_guard}, "parse_retry": pick(parse_retry) if parse_retry else None,
            "guard_rounds": rounds, "final_guardrail": g, **{k: final[k] for k in ("text", "final", "errors", "runs", "assembled_sql")},
            "tokens": tok, "n_calls": 1 + (1 if parse_retry else 0) + len(rounds),
            "latency_s": first["latency_s"] + sum(r["answer"]["latency_s"] for r in rounds)}
