"""Parallel, resumable runner for prompt v4 (scope contract).

  python run_v4.py --run NAME [--subset] [--models nemotron,gpt_oss] [--repeats 1] [--temp 0.0] [--workers 6]

Results are APPENDED to runs/NAME/results.jsonl, one JSON object per (column, model, repeat);
a cell with a usable answer is never re-requested, so a killed run just resumes. Prompts are built
once from the gold-derived scope and cached in runs/NAME/prompts.json (the intermediate artifact).
"""
import argparse, json, os, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import duckdb
import grade_swap as g
from scope_prompt import build_prompt_v4, build_prompt_v5, PROMPT_VERSION as V4_VERSION, PROMPT_VERSION_V5, DB_PATH
# PROMPT_VERSION_OVERRIDE lets a control run replay another prompt set (prompts.json already in the run dir)
PROMPT_VERSION = os.environ.get('PROMPT_VERSION_OVERRIDE', V4_VERSION)
import llm_parallel
from call_llm import extract_sql

HERE = os.path.dirname(os.path.abspath(__file__))
import gold_version as _gv
# frozen v4 text that v5 extends: v1 gold -> runs/v4_full_t0 (the original run); v2 gold -> runs/v2/v4_full_t0 (rebuilt by `--prompt v4 --prompts-only`)
BASE_PROMPTS = os.path.join(HERE, 'runs', 'v4_full_t0' if _gv.VERSION == 'v1' else os.path.join('v2', 'v4_full_t0'), 'prompts.json')
# (request timeout s, attempts) and worker count per model: slow big models get their own pool so they
# cannot starve the fast ones (a shared queue stalled a first attempt for 10+ minutes)
MODEL_LIMITS = {"nemotron": (120, 8), "mistral_large": (180, 8), "gpt_oss": (150, 8), "laguna": (120, 8), "nemotron_ultra": (150, 8)}
MODEL_WORKERS = {"nemotron": 4, "mistral_large": 4, "gpt_oss": 4, "laguna": 4, "nemotron_ultra": 4}


def all_columns(subset):
    gold = g.load_gold()
    if subset:
        from select_subset import CURATED_SUBSET
        return gold, [(t, c) for t, c, _ in CURATED_SUBSET]
    return gold, [(t, c) for t, s in gold.items() for c in s["cols"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--subset", action="store_true")
    ap.add_argument("--models", default="nemotron,gpt_oss")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--temp", type=float, default=0.0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--prompt", choices=["v4", "v5", "v5a", "v5b", "v5c"], default="v4")
    ap.add_argument("--only-changed", action="store_true", help="skip columns whose prompt equals the frozen v4 text")
    ap.add_argument("--prompts-only", action="store_true", help="build prompts.json and stop (no model calls)")
    a = ap.parse_args()
    global PROMPT_VERSION
    FEATURES = {"v5": ("desc", "conv", "note"), "v5a": ("conv",), "v5b": ("desc",), "v5c": ("note",)}
    if a.prompt != "v4":
        PROMPT_VERSION = PROMPT_VERSION_V5 if a.prompt == "v5" else f"{PROMPT_VERSION_V5}-{a.prompt}"
        v4_frozen = json.load(open(BASE_PROMPTS))
    rd = os.path.join(HERE, _gv.RUNS_SUBDIR, a.run)
    os.makedirs(rd, exist_ok=True)
    rpath, ppath = os.path.join(rd, "results.jsonl"), os.path.join(rd, "prompts.json")

    gold, cols = all_columns(a.subset)
    prompts = json.load(open(ppath)) if os.path.exists(ppath) else {}
    if prompts.get("_version") != PROMPT_VERSION:
        prompts = {"_version": PROMPT_VERSION}
    con = duckdb.connect(DB_PATH, read_only=True)
    t0 = time.time()
    for t, c in cols:
        k = f"{t}.{c}"
        if k not in prompts:
            try:
                prompts[k] = (build_prompt_v5(gold, con, t, c, v4_frozen[k], FEATURES[a.prompt]) if a.prompt != 'v4'
                              else build_prompt_v4(gold, con, t, c))
            except Exception as e:
                prompts[k] = None
                print(f"PROMPT FAILED {k}: {str(e)[:100]}", flush=True)
            json.dump(prompts, open(ppath, "w"))
    con.close()
    print(f"prompts ready ({len(cols)} columns, {time.time()-t0:.0f}s)", flush=True)
    if a.prompts_only:
        return

    done = set()
    if os.path.exists(rpath):
        for line in open(rpath):
            r = json.loads(line)
            if not r.get("error") and r.get("prompt_version") == PROMPT_VERSION:
                done.add((r["key"], r["model"], r["repeat"]))
    models = [m for m in a.models.split(",") if m]
    tasks = [(f"{t}.{c}", m, rep) for t, c in cols for m in models for rep in range(a.repeats)
             if prompts.get(f"{t}.{c}") and (f"{t}.{c}", m, rep) not in done
             and not (a.only_changed and a.prompt != 'v4' and prompts[f"{t}.{c}"] == v4_frozen[f"{t}.{c}"])]
    print(f"{len(tasks)} calls to make ({len(done)} already done)", flush=True)
    wlock, counter = threading.Lock(), [0]

    def work(task):
        key, model, rep = task
        rec = {"key": key, "model": model, "repeat": rep, "temperature": a.temp, "prompt_version": PROMPT_VERSION}
        try:
            to, tr = MODEL_LIMITS.get(model, (240, 3))
            res = llm_parallel.call(model, prompts[key], temperature=a.temp, timeout=to, tries=tr)
            rec.update(raw=res["raw"], sql=extract_sql(res["raw"]), latency=res["latency"], usage=res["usage"], attempts=res["attempts"])
        except Exception as e:
            rec.update(raw=None, sql=None, error=str(e)[:200])
        with wlock:
            open(rpath, "a").write(json.dumps(rec) + "\n")
            counter[0] += 1
            if counter[0] % 10 == 0 or rec.get("error"):
                print(f"[{counter[0]}/{len(tasks)}] {key} {model} #{rep} {'ERROR ' + rec['error'] if rec.get('error') else 'ok'}", flush=True)
        return rec

    pools = {m: ThreadPoolExecutor(MODEL_WORKERS.get(m, a.workers)) for m in models}
    futs = [pools[t[1]].submit(work, t) for t in tasks]
    for f in futs:
        f.result()
    for p in pools.values():
        p.shutdown()
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
