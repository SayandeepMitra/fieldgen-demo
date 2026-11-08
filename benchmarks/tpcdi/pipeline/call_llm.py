"""
Unified access to all 3 comparison models through OpenRouter's single OpenAI-compatible
endpoint -- one API key, one HTTP call shape, just a different "model" string per call. Avoids
juggling 3 separate vendor SDKs/auth schemes, and avoids local hosting entirely (consistent with
our hardware read: 16GB unified memory / no dedicated GPU, API access is the practical route for
models at this scale).

Model picks (verified live against OpenRouter's current catalog on 2026-10-02/03, since "the
usual" Nemotron names from pretraining knowledge -- Llama-3.1/3.3-Nemotron -- turned out to be
superseded by a newer "Nemotron 3" family by now):
  - NVIDIA Nemotron:  nvidia/nemotron-3-super-120b-a12b:free   (reasoning-oriented MoE, free tier)
  - Meta Llama:       meta-llama/llama-3.3-70b-instruct:free   (strong general-purpose baseline)
  - Qwen (code-spec.): qwen/qwen-2.5-coder-32b-instruct        (code/SQL-specialized, no confirmed
                                                                 free tier but a small/cheap model)
Deliberately one reasoning-tuned MoE model, one strong generalist, one code-specialist -- a
spread across specializations rather than three similar general chat models.

Needs OPENROUTER_API_KEY in the environment. Not set in this session -- see __main__ for a
dry run that builds the request without sending it.
"""
import json
import os
import re
import time
import urllib.request

def _load_dotenv():
    """Minimal .env loader (no new dependency) -- looks for benchmark/pipeline/.env, only sets
    a variable if it isn't already set in the real environment (so an explicit `export` always
    wins over the file)."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = {
    "nemotron": "nvidia/nemotron-3-super-120b-a12b:free",
    "cohere_code": "cohere/north-mini-code:free",
    "qwen": "qwen/qwen3.8-27b:free",
    # NVIDIA-hosted (added 2026-10-05 after OpenRouter's free tier proved unreliable/capped)
    # Probed 2026-10-05: of NVIDIA's listed models only gpt-oss-20b answers promptly (~4s). deepseek-v4.1-flash
    # timed out >280s, glm-5.3-flash took ~260s, kimi-k3 timed out, and codestral/mistral-large/kimi-k2.6/
    # nemotron-70b/ultra/codellama/granite/mixtral are listed but return 404.
    "gpt_oss": "openai/gpt-oss-20b",   # intermittently times out (150s+) as of 2026-11-04; the runner retries
    "mistral_large": "mistralai/mistral-large-4-1t-a52b",   # probed 2026-11-04: ~10s
    "laguna": "poolside/laguna-xs-2.1",                      # probed 2026-11-04: ~2s
    "nemotron_ultra": "nvidia/nemotron-3-ultra-550b-a55b",   # probed 2026-11-04: ~3s
}
NVIDIA_HOSTED = {"gpt_oss", "mistral_large", "laguna", "nemotron_ultra"}
# Revised 2026-10-03: no paid budget available. Llama 3.3 70B (used before) has dropped off the
# free tier entirely (confirmed via OpenRouter's live /api/v1/models, not just scraped pages --
# some of those 404'd inconsistently and turned out stale). Qwen-Coder (paid) replaced with
# cohere/north-mini-code:free, a genuinely free code-specialist, confirmed $0/$0 pricing live.
# IMPORTANT: all 3 models are now ':free' -- the 50/day, 20/min cap is SHARED ACROSS ALL THREE
# combined, not just 2 of them as in the original (paid-Qwen) design. See select_subset.py for
# how the test subset size was adjusted (12 columns, 36 calls) to keep safe margin under 50/day.
FREE_TIER_MODELS = {"nemotron", "cohere_code", "qwen"}

# Revised 2026-10-05: Nemotron is served directly from NVIDIA's hosted NIM API
# (integrate.api.nvidia.com, OpenAI-compatible) using the developer-account key (NVIDIA_API_KEY,
# "nvapi-..."), NOT through OpenRouter -- so its calls draw on NVIDIA's own quota (third-party
# sources say ~40 requests/min and a finite credit pool; NVIDIA itself doesn't publish exact
# numbers, so check the account dashboard), not OpenRouter's shared 50/day. Cohere and Qwen stay
# on OpenRouter. If NVIDIA_API_KEY is absent, Nemotron falls back to OpenRouter's :free slug.
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
# 2026-11-04: nemotron-3-super-120b-a12b is still LISTED by NVIDIA but now returns 404 ("function not found")
# on invocation; the 3.5 Super (also 120B / 12B active) is the nearest working successor.
NVIDIA_NEMOTRON_ID = "nvidia/nemotron-3.5-super-vl-120b-a12b"
OPENROUTER_FREE_MODELS = {"cohere_code", "qwen"}  # calls that count against the OpenRouter 50/day cap


def _provider_for(model_key):
    """Return (provider_name, url, api_key_env, model_slug) for a model key."""
    if model_key == "nemotron" and os.environ.get("NVIDIA_API_KEY"):
        return "nvidia", NVIDIA_URL, "NVIDIA_API_KEY", NVIDIA_NEMOTRON_ID
    if model_key in NVIDIA_HOSTED:
        return "nvidia", NVIDIA_URL, "NVIDIA_API_KEY", MODELS[model_key]
    return "openrouter", OPENROUTER_URL, "OPENROUTER_API_KEY", MODELS[model_key]

# Throttle: raised from 4s to 8s after a live run showed Qwen hitting 429s repeatedly even at 4s
# -- the free-tier backends appear to have their own capacity-based throttling independent of
# the documented account-level 20/min figure. 8s is more conservative, trading runtime for
# reliability, which matters more than speed given a scarce daily call budget.
MIN_SECONDS_BETWEEN_CALLS = 8.0
_last_call_time = [0.0]


def _throttle():
    elapsed = time.monotonic() - _last_call_time[0]
    if elapsed < MIN_SECONDS_BETWEEN_CALLS:
        time.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)
    _last_call_time[0] = time.monotonic()


def extract_sql(response_text):
    """
    Pull just the SQL expression out of a model's free-text response (it was asked for one
    sentence of reasoning + the expression, not asked to format it, so be lenient): prefer a
    ```sql fenced block, else the last non-empty line, since models commonly put the final
    answer last after explaining.
    """
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", response_text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    lines = [l.strip() for l in response_text.strip().splitlines() if l.strip()]
    return lines[-1] if lines else ""


def call_model(model_key, prompt, temperature=0.0, max_tokens=6000):
    """Call one model via OpenRouter. Returns the raw text response. Throttled to stay under
    the shared 20/min cap regardless of which model is being called.

    max_tokens history: 600 -> 2000 -> 6000. Both cohere/north-mini-code:free and qwen/
    qwen3.8-27b:free are reasoning models (separate internal "reasoning" field before the final
    "content") that were exhausting their token budget mid-reasoning on our real multi-section
    column prompts, returning "content": null with finish_reason="max_tokens"/"length" --
    confirmed via the raw API response, not guessed. 2000 wasn't enough either (same failure mode,
    same finish_reason). Raising further costs nothing extra against the request-count-based
    50/day cap (that's PER CALL, not per token) -- the only real cost of a higher ceiling is
    latency on calls that do reason for a while, which is an acceptable tradeoff against wasting
    an irreplaceable daily call on a truncated non-answer."""
    provider, url, key_env, model_slug = _provider_for(model_key)
    api_key = os.environ.get(key_env)
    if not api_key:
        raise RuntimeError(
            f"{key_env} not set (needed for model '{model_key}' via {provider}). "
            f"Add it to benchmark/pipeline/.env or export it."
        )

    _throttle()
    body = json.dumps({
        "model": model_slug,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode()

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())
    content = result["choices"][0]["message"]["content"]
    if content is None:
        # surfaces clearly now instead of crashing inside extract_sql with a confusing TypeError
        finish_reason = result["choices"][0].get("native_finish_reason") or result["choices"][0].get("finish_reason")
        raise RuntimeError(f"model returned null content (finish_reason={finish_reason}) -- likely ran out of "
                            f"max_tokens during internal reasoning before producing a final answer")
    return content


def run_all_models(prompt, **kwargs):
    """Run the same prompt against all 3 comparison models, return {model_key: response_text}."""
    out = {}
    for key in MODELS:
        try:
            out[key] = call_model(key, prompt, **kwargs)
        except Exception as e:
            out[key] = f"ERROR: {e}"
    return out


if __name__ == "__main__":
    demo_prompt = "Say 'ok' and nothing else."
    if os.environ.get("OPENROUTER_API_KEY"):
        for key, response in run_all_models(demo_prompt).items():
            print(f"--- {key} ({MODELS[key]}) ---")
            print(response)
            print()
    else:
        print("OPENROUTER_API_KEY not set -- dry run only. Request that WOULD be sent per model:")
        for key, slug in MODELS.items():
            print(f"  {key:12s} -> model={slug!r}, endpoint={OPENROUTER_URL}")
        print("\nSet OPENROUTER_API_KEY and re-run to actually call the models.")
