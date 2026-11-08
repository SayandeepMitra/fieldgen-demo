#!/bin/bash
cd "$(dirname "$0")/../.."
export TPCDI_GOLD=v2
PY=python3
$PY run_v4.py --run ab_v5a --prompt v5a --models nemotron,mistral_large > runs/v2/regen_ab_v5a.log 2>&1
$PY run_v4.py --run frozen_v5a_t07 --prompt v5a --models nemotron,mistral_large --repeats 3 --temp 0.7 > runs/v2/regen_t07.log 2>&1
$PY run_v4.py --run v4_full_t0 --prompt v4 --models nemotron,mistral_large > runs/v2/regen_v4.log 2>&1
touch runs/v2/regen_done.flag
