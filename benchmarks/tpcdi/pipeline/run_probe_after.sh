#!/bin/bash
cd "$(dirname "$0")"
while [ ! -f step4_done.flag ]; do sleep 30; done
export LLM_MIN_SPACING=2.0
for pass in 1 2 3; do
  python3 contam_probe.py --run contam_probe --models nemotron,mistral_large >> contam_probe.log 2>&1
  sleep 30
done
python3 contam_probe.py --run contam_probe --score > contam_probe_score.txt 2>&1
touch probe_done.flag
