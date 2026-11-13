"""OpenAI-compatible chat client. Logs every call (no headers, no key) to calls.jsonl."""
import json, re, threading, time, datetime
from dataclasses import dataclass, field
import httpx

@dataclass
class Response:
    text: str; usage: dict; latency_s: float; raw: str = ""; headers: dict = field(default_factory=dict)

def strip_think(text):
    if "</think>" in text: text = text.split("</think>")[-1]
    return re.sub(r"<think>.*?(</think>|$)", "", text, flags=re.S).strip()

class Client:
    def __init__(self, cfg, calls_path=None, transport=None, sleep=time.sleep):
        self.cfg, self.calls_path, self.sleep = cfg, calls_path, sleep
        self._transport = transport or self._http
        self._lock = threading.Lock(); self._next = 0.0
        self._sem = threading.Semaphore(cfg.max_concurrency)

    def _http(self, body):
        r = httpx.post(self.cfg.base_url.rstrip("/") + "/chat/completions", json=body, timeout=self.cfg.timeout_s,
                       headers={"Authorization": "Bearer " + self.cfg.api_key(), "Content-Type": "application/json"})
        return r.status_code, r.json() if r.content else {}, dict(r.headers)

    def _wait_slot(self):
        with self._lock:
            gap = 60.0 / max(self.cfg.requests_per_minute, 1e-6)
            now = time.monotonic(); at = max(now, self._next); self._next = at + gap
        if at > now: self.sleep(at - now)

    def _log(self, rec):
        if not self.calls_path: return
        with self._lock, open(self.calls_path, "a", encoding="utf-8") as f: f.write(json.dumps(rec, default=str) + "\n")

    def _one(self, messages, params, tag):
        body = {"model": self.cfg.model, "messages": messages, **params}
        if self.cfg.json_mode is True: body["response_format"] = {"type": "json_object"}
        body.update(self.cfg.extra_body or {})
        t_wall = datetime.datetime.now(datetime.timezone.utc).isoformat()
        err = None
        with self._sem:
            for attempt in range(self.cfg.retries + 1):
                self._wait_slot(); t0 = time.monotonic()
                try:
                    status, data, hdr = self._transport(body)
                except Exception as e:
                    status, data, hdr = 599, {}, {}; err = type(e).__name__
                if status == 200: break
                err = f"http {status}"
                if status in (429, 500, 502, 503, 504, 599) and attempt < self.cfg.retries:
                    self.sleep(min(2 ** attempt * 2, 60)); continue
                break
            lat = time.monotonic() - t0
        if status != 200:
            self._log({"time": t_wall, "model": self.cfg.model, "params": params, "messages": messages, "error": err, "latency_s": lat, "tag": tag})
            raise RuntimeError(f"LLM call failed: {err}")
        msg = data["choices"][0]["message"]; raw = msg.get("content") or ""
        usage = data.get("usage", {})
        keep = {k: v for k, v in hdr.items() if k.lower().startswith(("x-ratelimit", "retry-after"))}
        self._log({"time": t_wall, "model": self.cfg.model, "params": {**params, "json_mode": self.cfg.json_mode, "extra_body": self.cfg.extra_body},
                   "messages": messages, "raw_response": raw, "reasoning_content": msg.get("reasoning_content") or msg.get("reasoning"),
                   "usage": usage, "latency_s": lat, "ratelimit_headers": keep, "tag": tag})
        text = strip_think(raw) if self.cfg.strip_thinking else raw
        return Response(text, usage, lat, raw, keep)

    def chat(self, messages, n=1, tag=None, **overrides):
        params = {"temperature": self.cfg.temperature, "top_p": self.cfg.top_p, "max_tokens": self.cfg.max_tokens}
        params.update(overrides)
        out = [self._one(messages, params, tag) for _ in range(n)]
        return out[0] if n == 1 else out
