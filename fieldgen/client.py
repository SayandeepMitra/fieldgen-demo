"""LLM client that writes the Experiment 1 flags into every calls.jsonl record (subclass; src/llm.py is unchanged)."""
from fieldgen.llm import Client

class FlaggedClient(Client):
    def __init__(self, cfg, flags, **kw):
        super().__init__(cfg, **kw); self.flags = dict(flags)
    def _log(self, rec): super()._log({**rec, "flags": self.flags})


"""Experiment 1 client (generator side): FlaggedClient that also logs finish_reason, the served model id and empty-content per call, and stops the chain on
(a) 5 failed calls in a row with the same HTTP status, (b) for run 0, >= 3 of the first 6 finished calls ending in finish_reason "length" or with empty content.
Raises Stop (BaseException, defined here). Never logs headers or the key."""
import json, re, threading

class Stop(BaseException):
    """Not an Exception subclass: the recipe runners catch Exception around the model call and must not swallow a chain stop."""

def mask(s): return re.sub(r"(account|Function) '[^']*'", r"\1 '***'", str(s))

class Shared:
    def __init__(self, first_n=6, bad_limit=3, fail_limit=5, report=None, check_first=False):
        self.lock = threading.Lock(); self.finished = []; self.consec = (None, 0); self.first_n, self.bad_limit, self.fail_limit = first_n, bad_limit, fail_limit
        self.report, self.check_first, self.abort, self.served = report, check_first, None, []

class MonitoredClient(FlaggedClient):
    def __init__(self, cfg, flags, shared, **kw):
        super().__init__(cfg, flags, **kw); self.sh = shared; self.tls = threading.local(); self._inner = self._transport; self._transport = self._capture

    def _capture(self, body):
        status, data, hdr = self._inner(body); last = {"status": status}
        if status == 200:
            ch = (data.get("choices") or [{}])[0]; msg = ch.get("message") or {}
            last.update({"served_model": data.get("model"), "finish_reason": ch.get("finish_reason"), "empty_content": not (msg.get("content") or "").strip(),
                         "completion_tokens": (data.get("usage") or {}).get("completion_tokens")})
        else: last["detail"] = mask(json.dumps(data)[:300])
        self.tls.last = last
        with self.sh.lock:
            st, n = self.sh.consec
            self.sh.consec = (status, n + 1) if (status != 200 and status == st) else ((status, 1) if status != 200 else (None, 0))
            if status != 200 and self.sh.consec[1] >= self.sh.fail_limit: self.sh.abort = f"{self.sh.fail_limit} calls in a row failed with HTTP {status}: {last['detail']}"
        return status, data, hdr

    def _log(self, rec):
        l = getattr(self.tls, "last", {}) or {}
        super()._log({**rec, **{k: l.get(k) for k in ("finish_reason", "served_model", "empty_content") if k in l}})

    def chat(self, messages, n=1, tag=None, **ov):
        if self.sh.abort: raise Stop(self.sh.abort)
        try: out = super().chat(messages, n=n, tag=tag, **ov)
        except RuntimeError:
            if self.sh.abort: raise Stop(self.sh.abort)
            raise
        l = self.tls.last
        with self.sh.lock:
            self.sh.finished.append({"tag": tag, **{k: l.get(k) for k in ("completion_tokens", "finish_reason", "empty_content", "served_model")}})
            if len(self.sh.finished) == 1: print("served model of first reply:", l.get("served_model"), flush=True)
            if l.get("served_model") not in self.sh.served: self.sh.served.append(l.get("served_model"))
            if self.sh.check_first and len(self.sh.finished) == self.sh.first_n:
                bad = [f for f in self.sh.finished if f["finish_reason"] == "length" or f["empty_content"]]
                if len(bad) >= self.sh.bad_limit:
                    if self.sh.report: json.dump({"first_calls": self.sh.finished, "bad": len(bad)}, open(self.sh.report, "w"), indent=1)
                    self.sh.abort = f"{len(bad)} of the first {self.sh.first_n} calls ended with finish_reason length or empty content"
                    raise Stop(self.sh.abort)
        return out


_REPORT_LOCK = threading.Lock()

class Client400(MonitoredClient):
    """MonitoredClient that also stops the run on any HTTP 400 and records the input size (the response body is not logged, so a context-length error cannot be told from another 400)."""
    report = None
    def chat(self, messages, n=1, tag=None, **ov):
        try: return super().chat(messages, n=n, tag=tag, **ov)
        except RuntimeError as e:
            if "http 400" in str(e):
                size = sum(len(m["content"]) for m in messages)
                if self.report:
                    with _REPORT_LOCK: json.dump({"tag": tag, "input_chars": size, "error": str(e)[:200]}, open(self.report, "w"), indent=1)      # two workers can fail together
                raise Stop(f"HTTP 400 on {tag} (input {size} chars; the response body is not logged)")
            raise
