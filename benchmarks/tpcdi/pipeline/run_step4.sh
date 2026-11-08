#!/bin/bash
cd "$(dirname "$0")"
export LLM_MIN_SPACING=2.0
run=frozen_v5a_t07
for pass in 1 2 3 4 5; do
  python3 run_v4.py --run $run --prompt v5a --models nemotron,mistral_large --repeats 3 --temp 0.7 >> runs_$run.log 2>&1
  n=$(python3 - <<PY
import json
last={}
for l in open("runs/$run/results.jsonl"):
    r=json.loads(l); last[(r["key"],r["model"],r["repeat"])]=bool(r.get("error"))
print(sum(last.values()), len(last))
PY
)
  echo "RUN pass $pass errors/total=$n" >> run_step4.log
  set -- $n; [ "$1" = "0" ] && [ "$2" -ge 1260 ] && break
  sleep 60
done
nohup python3 grade_run.py --run $run > grade_$run.log 2>&1
touch step4_done.flag
