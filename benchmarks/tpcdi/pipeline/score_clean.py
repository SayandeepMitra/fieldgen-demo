"""Score graded runs on the audited clean subset, by tier and dev/test split, with repeat statistics.

usage: score_clean.py RUN [RUN ...] [--base BASE_RUN]
  RUN       a directory name under runs/ (needs graded.json). Several RUNs are pooled as repeats of one condition
            only if you pass them as ONE comma-separated argument (e.g. rep0,rep1,rep2); otherwise each is its own row.
  --base    for partial runs (e.g. --only-changed arms): cells absent from RUN fall back to BASE_RUN's result.
Reports, per model: exact counts on core (clean+clean_column+fk_entity_only; 171), clean (147), and dev/test halves of core,
plus the weak (11) and flagged (28) groups separately. With several repeats: mean, min-max, and the number of
columns whose exactness is unstable (exact in some repeats, not in others).
"""
import csv, json, os, sys, collections, statistics
B = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gold_version as _gv                                   # TPCDI_GOLD=v1|v2: subset, run folder and trivial baseline follow the gold
sub = {f"{r['table']}.{r['column']}": r for r in csv.DictReader(open(_gv.CLEAN_SUBSET_CSV))}
split = {f"{r['table']}.{r['column']}": r["split"] for r in csv.DictReader(open(f"{B}/deliverables/tpcdi_split.csv"))}
CORE = {"clean", "clean_column", "fk_entity_only"}
args = [a for a in sys.argv[1:]]
base = None
if "--base" in args:
    i = args.index("--base"); base = args[i + 1]; del args[i:i + 2]
load = lambda n: [r for r in json.load(open(f"{B}/pipeline/{_gv.RUNS_SUBDIR}/{n}/graded.json"))]
_bp = f"{B}/pipeline/{_gv.RUNS_SUBDIR}/baseline_trivial/graded.json"
HARD = None
if os.path.exists(_bp):    # hard = core columns the name-matcher baseline gets wrong
    _ok = {r["key"]: (r["status"] == "EXECUTED" and (r["match_pct"] or 0) >= 99.995) for r in json.load(open(_bp)) if r["model"] == "trivial_name"}
    HARD = {k for k, r in sub.items() if r["tier"] in ("clean", "clean_column", "fk_entity_only") and not _ok.get(k)}
exact = lambda r: r is not None and r["status"] == "EXECUTED" and r["match_pct"] is not None and r["match_pct"] >= 99.995


def table(run_names):
    cells = collections.defaultdict(dict)       # (model, repeat) -> key -> exact?
    for n in run_names:
        off = 0
        for r in load(n):
            cells[(r["model"], r["repeat"])][r["key"]] = exact(r)
    if base:
        for r in load(base):
            if r["repeat"] == 0:
                for (m, rep), d in list(cells.items()):
                    if m == r["model"] and r["key"] not in d:
                        d[r["key"]] = exact(r)
    return cells


for spec in args:
    names = spec.split(",")
    cells = table(names)
    models = sorted({m for m, _ in cells})
    print(f"\n=== {spec}" + (f"  (missing cells filled from {base})" if base else ""))
    print(f"{'model':14s} {'reps':>4s} | {'core':>13s} {'clean':>13s} {'hard':>11s} {'core-dev':>11s} {'core-test':>11s} | {'weak':>7s} {'flagged':>9s} | unstable")
    for m in models:
        reps = sorted(r for mm, r in cells if mm == m)
        def cnt(pred):
            v = [sum(1 for k, e in cells[(m, r)].items() if pred(k) and e) for r in reps]
            return v
        groups = dict(core=lambda k: sub[k]["tier"] in CORE, clean=lambda k: sub[k]["tier"] == "clean",
                      dev=lambda k: sub[k]["tier"] in CORE and split[k] == "dev", test=lambda k: sub[k]["tier"] in CORE and split[k] == "test",
                      hard=lambda k: HARD is not None and k in HARD, weak=lambda k: sub[k]["tier"] == "weak", flagged=lambda k: sub[k]["tier"] in ("known_defect", "audit_flagged"))
        def fmt(v):
            return f"{statistics.mean(v):5.1f}({min(v)}-{max(v)})" if len(v) > 1 else f"{v[0]:d}"
        keys = set().union(*[cells[(m, r)].keys() for r in reps])
        unstable = sum(1 for k in keys if len({cells[(m, r)].get(k) for r in reps}) > 1) if len(reps) > 1 else "-"
        o = {g: cnt(p) for g, p in groups.items()}
        print(f"{m:14s} {len(reps):>4d} | {fmt(o['core']):>13s} {fmt(o['clean']):>13s} {fmt(o['hard']):>11s} {fmt(o['dev']):>11s} {fmt(o['test']):>11s} | {fmt(o['weak']):>7s} {fmt(o['flagged']):>9s} | {unstable}")
