"""Run the fieldgen CLI unchanged, except two mechanical overrides (no prompt / recipe / formula code is touched):
 1. cards.CAPS['max_file_mb'] 20 -> 2000: the shipped cap rejects any source CSV over 20 MB; our SF3 Source tables go up to 74 MB.
 2. guardrail.make_pool reads /proc/meminfo (Linux only); on macOS we serve the same text from sysctl hw.memsize.
"""
import builtins, io, subprocess, sys
from fieldgen import cards
cards.CAPS["max_file_mb"] = 2000
_open = builtins.open
def _patched(f, *a, **k):
    if f == "/proc/meminfo":
        kb = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip()) // 1024
        return io.StringIO(f"MemTotal:       {kb} kB\n")
    return _open(f, *a, **k)
builtins.open = _patched
from fieldgen.cli import main
if __name__ == "__main__":      # spawn workers re-import this file: do not re-run the CLI there
    sys.exit(main())
