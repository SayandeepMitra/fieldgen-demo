"""Per-table comparison of a fieldgen L2 run with the composed-L1 L2 runs (compose_v5a_*), plus a count of columns fieldgen left NULL.
usage: python compare_to_compose.py FIELDGEN_RUN_NAME [FIELDGEN_RUN_DIR]   (names under benchmark/pipeline/runs/l2/)"""
import csv, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); PIPE = os.path.join(os.path.dirname(HERE), "pipeline")
sys.path.insert(0, PIPE)
name = sys.argv[1]; rundir = sys.argv[2] if len(sys.argv) > 2 else None
EXACT = 99.995
runs = {"fieldgen": name, "mistral": "compose_v5a_mistral_large", "nemotron": "compose_v5a_nemotron"}
S = {k: json.load(open(f"{PIPE}/runs/l2/{v}/l2_scores.json")) for k, v in runs.items()}
sub = {f"{r['table']}.{r['column']}": r for r in csv.DictReader(open(f"{os.path.dirname(HERE)}/deliverables/tpcdi_clean_subset.csv"))}
core = {k for k, r in sub.items() if r["tier"] in ("clean", "clean_column", "fk_entity_only")}
nulls = {}
if rundir:
    for f in os.listdir(f"{rundir}/formulas"):
        d = json.load(open(f"{rundir}/formulas/{f}")); nulls[f[:-5]] = sum(1 for v in d.values() if not v)
print("| table | scored cols | fieldgen exact | compose-Mistral exact | compose-Nemotron exact | fieldgen rows correct | fieldgen recall / precision % |")
print("|---|---:|---:|---:|---:|---|---|")
tot = {k: 0 for k in runs}
for t, r in S["fieldgen"]["tables"].items():
    cols = list(r["columns"]); row = [t, str(len(cols))]
    for k in runs:
        n = sum(1 for c in cols if (S[k]["tables"][t]["columns"].get(c, {}).get("pct_ref") or 0) >= EXACT); tot[k] += n; row.append(str(n))
    row += [str(r["rows_correct"]), f"{r['recall']} / {r['precision']}"]
    print("| " + " | ".join(row) + " |")
print("| **total** | " + " | ".join([str(sum(len(r['columns']) for r in S['fieldgen']['tables'].values()))] + [str(tot[k]) for k in runs]) + " | | |")
