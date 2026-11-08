"""Thread-safe NVIDIA-hosted LLM calls for the parallel runner (call_llm.py's global 8s throttle and
shared state are for the OpenRouter free tier; NVIDIA has no daily cap, so we run workers in parallel
with a small per-provider minimum spacing and retry on 429/5xx)."""
import json, os, socket, threading, time, urllib.error, urllib.request
import call_llm

_lock = threading.Lock()
_last = {}
MIN_SPACING = float(os.environ.get("LLM_MIN_SPACING", "0.75"))  # seconds between request starts, per provider


_cool_until = {}   # provider -> monotonic time before which NO worker may send (set on 429)
_extra = {}        # provider -> adaptive extra spacing (grows on 429, decays on success)


def _space(provider):
    with _lock:
        now = time.monotonic()
        start = max(_last.get(provider, 0) + MIN_SPACING + _extra.get(provider, 0.0), _cool_until.get(provider, 0), now)
        _last[provider] = start
        wait = start - now
    if wait > 0:
        time.sleep(wait)


def _throttled(provider, retry_after=None):
    """A 429 on the shared key: pause every worker, and send slower from now on."""
    with _lock:
        now = time.monotonic()
        _cool_until[provider] = max(_cool_until.get(provider, 0), now + (retry_after or 20))
        _extra[provider] = min(4.0, _extra.get(provider, 0.0) + 0.5)


def _ok(provider):
    with _lock:
        _extra[provider] = max(0.0, _extra.get(provider, 0.0) - 0.02)


# Per-model request extras. mistral-large-4 is a reasoning model that spends ~5,700 tokens (~200s) thinking
# about a ~600-token prompt by default (timeouts / finish_reason=length); reasoning_effort=low gave a correct
# answer in 13s / 372 tokens (probed 2026-11-04). Applied to gpt-oss as well (same failure mode, supports it).
MODEL_EXTRA = {"mistral_large": {"reasoning_effort": "low"}, "gpt_oss": {"reasoning_effort": "low"}}


def call(model_key, prompt, temperature=0.0, max_tokens=6000, timeout=240, tries=5):
    """Returns {'raw','latency','usage','attempts'}; raises RuntimeError after the last failed attempt."""
    provider, url, key_env, slug = call_llm._provider_for(model_key)
    api_key = os.environ.get(key_env)
    if not api_key:
        raise RuntimeError(f"{key_env} not set")
    payload = {"model": slug, "messages": [{"role": "user", "content": prompt}],
               "temperature": temperature, "max_tokens": max_tokens}
    payload.update(MODEL_EXTRA.get(model_key, {}))
    body = json.dumps(payload).encode()
    last_err = None
    for attempt in range(1, tries + 1):
        _space(provider)
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                res = json.loads(resp.read())
            ch = res["choices"][0]
            content = ch["message"].get("content")
            if content is None:
                last_err = f"null content (finish_reason={ch.get('finish_reason')})"
                continue  # reasoning ate the budget; retry (same prompt) once or twice
            _ok(provider)
            return {"raw": content, "latency": round(time.monotonic() - t0, 1), "usage": res.get("usage"), "attempts": attempt}
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code == 429:
                ra = e.headers.get("Retry-After") if e.headers else None
                _throttled(provider, float(ra) if ra and ra.replace(".", "").isdigit() else min(60, 10 * attempt))
                continue
            if e.code in (500, 502, 503, 504):
                time.sleep(min(60, 3 * 2 ** attempt))
                continue
            raise RuntimeError(last_err)
        except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
            last_err = f"{type(e).__name__}: {str(e)[:80]}"
            time.sleep(min(30, 2 * attempt))
    raise RuntimeError(f"failed after {tries} attempts: {last_err}")
