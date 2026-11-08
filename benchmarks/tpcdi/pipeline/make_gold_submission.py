"""Write the gold's own per-table SQL as an L2 submission (control C1: gold-as-pipeline must score 210/210 + the same audit as the gold).
usage: TPCDI_GOLD=v2 python make_gold_submission.py   -> runs[/v2]/l2/_subs/gold_pipeline/<Table>.sql + order.txt
Each file is `INSERT INTO T (cols) <the gold SELECT, WITH clause first>` (DuckDB rejects `WITH ... INSERT`)."""
import os
import grade_swap as g
import l2_run

gold = g.load_gold()
d = os.path.join(l2_run.RUNS, "_subs", "gold_pipeline")
os.makedirs(d, exist_ok=True)
for t, spec in gold.items():
    cols = spec["cols"]
    open(os.path.join(d, f"{t}.sql"), "w").write(f"INSERT INTO {t} ({', '.join(cols)}) {g.probe_query(gold, t, cols[0], None, None)}")
open(os.path.join(d, "order.txt"), "w").write("\n".join(gold) + "\n")
print(f"{len(gold)} tables -> {d}")
