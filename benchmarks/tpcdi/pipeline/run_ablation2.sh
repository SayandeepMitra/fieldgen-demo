#!/bin/bash
# Gap-filling ablation driver (v2): the first pass lost many cells to HTTP 429; fill only the errored/missing cells,
# repeat until no errors remain (max 5 passes), then grade. Successful cells are never re-run.
cd "$(dirname "$0")"
PY=python3
export LLM_MIN_SPACING=2.0
M=nemotron,mistral_large
for spec in "v4_rerun v4" "ab_v5b v5b" "ab_v5a v5a" "ab_v5c v5c"; do
  set -- $spec; run=$1; prompt=$2
  extra=""; [ "$prompt" = "v5c" ] && extra="--only-changed"
  for pass in 1 2 3 4 5; do
    $PY -u run_v4.py --run $run --prompt $prompt --models $M $extra >> runs_$run.log 2>&1
    n=$($PY -I -c "
import json
d={};
for l in open('runs/$run/results.jsonl'):
    r=json.loads(l); k=(r['key'],r['model'],r['repeat'])
    if not r.get('error') or k not in d: d[k]=r
print(sum(1 for r in d.values() if r.get('error')))")
    echo "$run pass $pass remaining_errors=$n" >> run_ablation.log
    [ "$n" = "0" ] && break
    sleep 60
  done
  nohup $PY -u grade_run.py --run $run > grade_$run.log 2>&1 &
done
wait
echo ALL_DONE > ablation_done.flag
