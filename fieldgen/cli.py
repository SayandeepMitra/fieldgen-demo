"""Command line: fieldgen init | generate | execute | test (and check). Every command takes --package DIR; everything else comes from config.yaml in the current folder."""
import argparse, sys
from pathlib import Path

NEXT = {"init": "fieldgen generate --package {p}", "generate": "fieldgen execute --package {p}", "execute": "fieldgen test --package {p}"}

def run_dir(package): return Path(package).resolve().parent / "run"
def reference_dir(package): return Path(package).resolve().parent / "reference"

def _settings(package):
    from fieldgen.settings import load_settings, find_config
    cfg = find_config(package); s = load_settings(cfg); print(f"config: {Path(cfg).resolve() if cfg else 'no config.yaml in the package folder or the current folder: built-in defaults'}"); return s

def _next(cmd, package): print("next:", NEXT[cmd].format(p=package))

def cmd_init(a):
    from fieldgen.init_package import init_package, InitError
    try: init_package(a.package, a.source, a.target)
    except InitError as e: print("ERROR:", e); return 1
    _next("init", a.package); return 0

def cmd_check(a):
    from fieldgen.check import check_package
    r = check_package(a.package)
    for e in r["errors"]: print("ERROR  ", e)
    for w in r["warnings"]: print("warning", w)
    print("package OK" if r["ok"] else f"package NOT valid ({len(r['errors'])} error(s))", "|", __import__("json").dumps(r["checks"])); return 0 if r["ok"] else 1

def cmd_generate(a):
    from fieldgen.settings import ConfigError
    from fieldgen.pipeline import generate, problems, PipelineError
    try: s = _settings(a.package)
    except ConfigError as e: print("config error:", e); return 2
    errors, blocking, notes = problems(a.package, s)
    for e in errors: print("PROBLEM", e)
    for b in blocking: print("TODO   ", b)
    if errors or blocking: print(f"generate stops: fix the {len(errors)} problem(s) and {len(blocking)} TODO(s) above. `fieldgen check --package {a.package}` lists the details."); return 1
    for n in notes: print("hint   ", n)
    out = run_dir(a.package); print(f"run folder: {out} | model: {s.model} | stages: {s.stages} | domain_knowledge: {s.domain_knowledge}")
    try: summary = generate(a.package, s, out)
    except PipelineError as e: print("ERROR:", e); return 1
    print("served model id(s):", ", ".join(map(str, summary["served_models"])), "| seconds:", summary["seconds"])
    if summary["stopped"]: print("STOPPED:", summary["stopped"]); return 3
    print(f"recipes valid: {len(summary['recipes_valid'])} of {len(summary['tables_to_build'])} tables | report: {out / 'report.md'}"); _next("generate", a.package); return 0

def cmd_execute(a):
    from fieldgen.settings import ConfigError
    from fieldgen.pipeline import execute, PipelineError
    try: s = _settings(a.package)
    except ConfigError as e: print("config error:", e); return 2
    try: res = execute(a.package, s, run_dir(a.package))
    except PipelineError as e: print("ERROR:", e); return 1
    for t in res["tables"]:
        if not t["ok"]: print(f"FAILED  {t['table']}: {' '.join((t['error'] or '').split())[:200]}")
    if not all(t["ok"] for t in res["tables"]): print("a table that fails here has SQL that does not run on the whole table; its scores from `test` are still computed per column")
    _next("execute", a.package)
    failed = [x["table"] for x in res["tables"] if not x["ok"]]
    if failed: print(f"execute finished with {len(failed)} failed table(s): {', '.join(failed)} (exit code 1)"); return 1
    return 0

def cmd_test(a):
    from fieldgen.settings import ConfigError
    from fieldgen.testing import run_test
    try: s = _settings(a.package)
    except ConfigError as e: print("config error:", e); return 2
    r = run_test(a.package, reference_dir(a.package), s, run_dir(a.package))
    print(r["message"])
    if r["status"] == "tested": print("report:", run_dir(a.package) / "report.md")
    return 1 if r["status"] == "error" else 0

def main(argv=None):
    ap = argparse.ArgumentParser(prog="fieldgen", description="LLM-assisted generation of field-level SQL transformations")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", help="create a package from your source data and target schema"); i.add_argument("--package", required=True); i.add_argument("--source", required=True, help="a folder of CSV files, or a DuckDB file")
    i.add_argument("--target", required=True, help="a DDL file (.sql), a folder of .sql files, or a DuckDB file with the target tables"); i.set_defaults(f=cmd_init)
    for name, f, h in (("generate", cmd_generate, "check the package, then write recipes, formulas and the final SQL"), ("execute", cmd_execute, "run the SQL and write the target tables into a DuckDB file"),
                       ("test", cmd_test, "compare with the reference next to the package"), ("check", cmd_check, "validate the package only (no model calls)")):
        x = sub.add_parser(name, help=h); x.add_argument("--package", required=True); x.set_defaults(f=f)
    try: sys.stdout.reconfigure(line_buffering=True)          # lines appear at once, also when the output goes to a file or a pipe
    except Exception: pass
    a = ap.parse_args(argv); return a.f(a)

if __name__ == "__main__": sys.exit(main())
