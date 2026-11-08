"""Frozen dev/test column split (deterministic; re-running reproduces it exactly).

Rule: within each column_kind, order columns by sha256(SEED + 'table.column'), alternate dev/test starting with dev.
Stratifies kinds (SCD history, constants, lookups, ...) across both halves; the hash makes the assignment independent of
anything about the columns' results. Prompt changes after the freeze may only be developed on `dev`; `test` is for final
reporting. Run: python3 -I make_split.py
"""
import csv, hashlib, os
SEED = "tpcdi-split-v1-2026-11-05"
D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deliverables")
rows = list(csv.DictReader(open(os.path.join(D, "tpcdi_clean_subset.csv"))))
bykind = {}
for r in rows:
    bykind.setdefault(r["kind"], []).append(r)
for kind, rs in bykind.items():
    rs.sort(key=lambda r: hashlib.sha256((SEED + f"{r['table']}.{r['column']}").encode()).hexdigest())
    for i, r in enumerate(rs):
        r["split"] = "dev" if i % 2 == 0 else "test"
out = [dict(table=r["table"], column=r["column"], kind=r["kind"], tier=r["tier"], split=r["split"]) for r in rows]
with open(os.path.join(D, "tpcdi_split.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
import collections
c = collections.Counter((r["split"], r["tier"]) for r in out)
print("split x tier:"); [print(f"  {k}: {v}") for k, v in sorted(c.items())]
core = [r for r in out if r["tier"] in ("clean", "clean_column", "fk_entity_only")]
print("core columns:", len(core), "dev", sum(r["split"] == "dev" for r in core), "test", sum(r["split"] == "test" for r in core))
