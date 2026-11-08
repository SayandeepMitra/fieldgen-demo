"""
Batch-run the curated 15-column subset (select_subset.py) through all 3 models and save results
for later Phase D grading. Resumable: re-running skips (table, column) pairs already present in
the results file, so a run interrupted by the daily rate cap can continue tomorrow without
re-spending today's budget. Tracks and prints the free-tier call count (Nemotron+Llama) as it
goes, since that's the binding constraint (50/day, shared, not per-model).
"""
import json
import os
import duckdb

from select_subset import get_subset
from build_prompt import build_column_prompt, DB_PATH, PROMPT_VERSION
from call_llm import call_model, extract_sql, MODELS, FREE_TIER_MODELS, OPENROUTER_FREE_MODELS, _provider_for

RESULTS_PATH = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))), "pipeline/subset_results.json")


def load_results():
    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH) as f:
            return json.load(f)
    return {}


def save_results(results):
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)


def main(max_calls=None):
    """max_calls: stop cleanly after this many calls this run, to respect a scarce remaining
    daily budget instead of blindly attempting every outstanding (column, model) pair."""
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY not set -- nothing to run. See the README/instructions for how to set it.")
        return

    con = duckdb.connect(DB_PATH, read_only=True)
    subset = get_subset()
    results = load_results()
    free_tier_calls_this_run = 0

    for item in subset:
        if max_calls is not None and free_tier_calls_this_run >= max_calls:
            print(f"Reached max_calls={max_calls} for this run -- stopping cleanly, re-run later to continue.")
            break
        key = f"{item['table']}.{item['column']}"
        results.setdefault(key, {})

        # Always (re)store the rendered prompt, even on a skip -- it's deterministic given the
        # same CSV/DB state, cheap to regenerate, and this is the intermediate artifact that was
        # missing before: only "raw"/"sql" were ever saved, not what was actually sent.
        prompt = build_column_prompt(item["table"], item["column"], con)
        results[key]["_prompt"] = prompt
        results[key]["_prompt_version"] = PROMPT_VERSION

        # retry anything missing OR previously failed (has an 'error' key) -- a prior failed
        # attempt is not "done", it's a call we spent budget on without getting a usable answer
        # optional RUN_MODELS=nemotron,cohere_code limits which models this invocation calls (used to
        # prioritize the reliable models and keep scarce OpenRouter quota off a flaky one)
        only = [x for x in os.environ.get("RUN_MODELS", "").split(",") if x]
        missing = [m for m in MODELS if (not only or m in only) and (m not in results[key] or results[key][m].get("error"))]
        if not missing:
            print(f"SKIP {key} -- already have all 3 model results")
            save_results(results)  # still persist the (re)stored prompt on a skip
            continue
        for model_key in missing:
            if max_calls is not None and free_tier_calls_this_run >= max_calls:
                print(f"Reached max_calls={max_calls} for this run -- stopping cleanly, re-run later to continue.")
                save_results(results)
                print(f"\nPartial results saved to {RESULTS_PATH}")
                return
            print(f"CALL {key} -> {model_key} ({MODELS[model_key]})")
            try:
                raw = call_model(model_key, prompt)
                prov = _provider_for(model_key)
                results[key][model_key] = {"raw": raw, "sql": extract_sql(raw), "provider": prov[0], "model_slug": prov[3], "prompt_version": PROMPT_VERSION}
            except Exception as e:
                results[key][model_key] = {"raw": None, "sql": None, "error": str(e)}
                print(f"  ERROR: {e}")
            if _provider_for(model_key)[0] == 'openrouter':
                free_tier_calls_this_run += 1  # only OpenRouter calls draw on its 50/day cap
            save_results(results)  # persist after every call, not just every column

        print(f"  (OpenRouter calls used this run: {free_tier_calls_this_run} -- cap is 50/day, shared; NVIDIA-routed calls not counted)")

    print(f"\nDone. Results saved to {RESULTS_PATH}")


if __name__ == "__main__":
    import sys
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(max_calls=cap)
