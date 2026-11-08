#!/bin/bash
# Sequential ablation driver: control (v4 rerun) then the three v5 additions one at a time.
# Generation is rate-limited (shared NVIDIA key, 40 RPM); each arm is graded in the background while the next one generates.
cd "$(dirname "$0")"
PY=python3
export LLM_MIN_SPACING=1.6
M=nemotron,mistral_large
for spec in "v4_rerun v4" "ab_v5b v5b" "ab_v5a v5a" "ab_v5c v5c"; do
  set -- $spec; run=$1; prompt=$2
  extra=""; [ "$prompt" = "v5c" ] && extra="--only-changed"
  $PY -u run_v4.py --run $run --prompt $prompt --models $M $extra > runs_$run.log 2>&1
  # retry pass for any timed-out cells (runner skips finished ones)
  $PY -u run_v4.py --run $run --prompt $prompt --models $M $extra >> runs_$run.log 2>&1
  nohup $PY -u grade_run.py --run $run > grade_$run.log 2>&1 &
done
wait
echo ALL_DONE > ablation_done.flag
