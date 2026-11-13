"""`fieldgen test` (reference side): compares a generated run with the reference next to the package (`reference/`).
reference/ holds tables  -> compare.   It holds recipes (the reference conversion as SQL) -> run them to build the reference tables, then compare.   Neither -> "no reference, nothing to test"."""
from pathlib import Path

def reference_kind(ref):
    """'tables', 'recipes' or None."""
    ref = Path(ref) if ref else None
    if ref is None or not ref.is_dir(): return None
    if any((ref / "reference_data").glob("*.csv")): return "tables"
    if any((ref / "recipes").glob("*.json")) and any((ref / "fields").glob("*.json")): return "recipes"
    return None

def run_test(package_dir, reference_dir, settings, run_dir, log=print):
    """{"status": "tested" | "nothing to test" | "error", "message": ..., "score": ...}"""
    from fieldgen.score_run import score_run
    run_dir = Path(run_dir)
    if settings.reference == "off": return {"status": "nothing to test", "message": "reference: off in config.yaml, nothing to test"}
    kind = reference_kind(reference_dir)
    if kind is None: return {"status": "nothing to test", "message": "no reference, nothing to test"}
    if not (run_dir / "recipes.jsonl").exists(): return {"status": "error", "message": f"no generated run in {run_dir}: run `fieldgen generate` first"}
    ref = Path(reference_dir)
    from fieldgen.check_reference import leak_check
    hits = leak_check(package_dir, ref)
    if hits: return {"status": "error", "message": "LEAK: reference text was found in the package files, so the test would not be fair:\n  " + "\n  ".join(hits[:5])}
    if kind == "tables" and not (ref / "alignment.json").exists() and not any((ref / "fields").glob("*.json")):
        return {"status": "error", "message": "the reference has tables but no alignment.json (which source columns identify each row): see docs/reference_format.md"}
    if kind == "recipes":
        from fieldgen.reference_build import build_reference_tables
        built_dir = run_dir / "reference_built"; built, errs = build_reference_tables(package_dir, ref, built_dir, log)
        log(f"reference tables built from the reference recipes: {len(built)} built, {len(errs)} failed" + ("" if not errs else f" ({', '.join(sorted(errs))})"))
        log("  note: numbered ids and keys taken from other tables may differ from the original program; they are not scored")
        ref = built_dir
    levels = "L2_and_L4" if settings.robustness_check else "L2"
    score = score_run(package_dir, ref, run_dir, settings, levels=levels)
    return {"status": "tested", "message": score["headline"], "kind": kind, "score": score}
