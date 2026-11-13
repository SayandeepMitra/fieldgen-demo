"""Recipe step (generic; generator side): one model answer per target table with the output ladder (an answer cut at the output limit is asked again with the next limit),
and the retry on errors: `errors` retries a recipe that does not run; `errors_and_invalid` also retries an answer that is not JSON, fails the recipe schema or the checks. At most max_retries retries."""
from fieldgen.recipe_prompts import recipe_messages
from fieldgen.recipe_check import check, TIMEOUT_S

FOLLOW_UP = "Your recipe could not be used. The check reported: {err}. Return the corrected JSON object with the same keys."
LADDER = [16384, 32768, 65536, 131072]

def error_text(c): return c["db_error"] or "; ".join(c["errors"])[:600]

def generate_recipe(task, client, s, con, ladder=LADDER, max_attempts=8, timeout_s=TIMEOUT_S, **ov):
    msgs = recipe_messages(task, s); tag = "step1:" + task["task_id"]; mode, max_retries = s.retry_on_error, s.max_retries if s.retry_on_error != "off" else 0
    i = 0; cur = msgs; attempts = []; noresp = False; suffix = ""; retries = 0; errors = []
    while len(attempts) < max_attempts:
        L = ladder[i]
        try: r = client.chat(cur, tag=tag + suffix, **{**ov, "max_tokens": L})
        except Exception as e:
            attempts.append({"class": "no response", "limit": L, "errors": [str(e)[:120]], "recipe": None, "text": "", "tokens": {"in": 0, "out": 0}, "latency_s": 0, "runs": None, "db_error": None})
            if not noresp: noresp = True; suffix = ":again"; continue
            break
        c = check(r.text, task, con, timeout_s, allow_history=getattr(s, "history_auto", False)); tok = {"in": r.usage.get("prompt_tokens", 0), "out": r.usage.get("completion_tokens", 0)}
        a = {**c, "text": r.text, "tokens": tok, "latency_s": r.latency_s, "limit": L}; attempts.append(a)
        if not c["errors"]: a["class"] = "valid"; break
        truncated = tok["out"] >= L
        if truncated and i + 1 < len(ladder): a["class"] = "truncated"; i += 1; cur = msgs; suffix = f":limit{ladder[i]}"; continue
        a["class"] = "truncated" if truncated else "invalid below the limit"
        retry_ok = (mode == "errors_and_invalid") or (mode == "errors" and c["db_error"])
        if retry_ok and not truncated and retries < max_retries:
            err = error_text(c); retries += 1; errors.append(err); suffix = ":retry"
            cur = cur + [{"role": "assistant", "content": r.text}, {"role": "user", "content": FOLLOW_UP.format(err=err)}]; continue
        break
    last = attempts[-1]
    if last.get("errors") and error_text(last) not in errors and last.get("class") != "no response": errors.append(error_text(last))
    status = "ok" if last.get("class") == "valid" else ("run_error" if last.get("db_error") else "invalid")
    tok = {k: sum(x["tokens"][k] for x in attempts) for k in ("in", "out")}
    return {"messages": msgs, "attempts": attempts, "text": last.get("text", ""), "recipe": last.get("recipe"), "errors": last.get("errors", []), "runs": last.get("runs"),
            "tokens": tok, "latency_s": sum(x.get("latency_s") or 0 for x in attempts), "n_calls": len(attempts), "retry_log": {"retries": retries, "errors": errors, "status": status}}
