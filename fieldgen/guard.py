"""Run guard (generic): cumulative input tokens, failure rate, authentication."""
import collections, threading

class Stop(Exception): pass

class Guard:
    def __init__(self, lim, tokens_in):
        self.lim, self.tokens_in, self.win, self.lock = lim, tokens_in, collections.deque(maxlen=lim["window"]), threading.Lock()
    def record(self, ok, tin=0, err=""):
        with self.lock:
            self.tokens_in += tin; self.win.append(0 if ok else 1)
            if "http 401" in err or "http 403" in err: raise Stop("authentication failed")
            if self.tokens_in > self.lim["max_input_tokens"]: raise Stop(f"cumulative input tokens {self.tokens_in} exceed the limit")
            if len(self.win) == self.lim["window"] and sum(self.win) / len(self.win) > self.lim["max_fail_rate"]: raise Stop("more than 30% of the last 50 calls failed")

