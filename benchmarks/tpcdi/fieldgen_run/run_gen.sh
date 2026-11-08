#!/bin/bash
# usage: run_gen.sh REPDIR   (REPDIR contains pkg/; run/ is created next to it). Key is read from pipeline/.env into the environment only.
cd "$(dirname "$0")"; rep=$1
set -a; . ../pipeline/.env; set +a; export OPENROUTER_API_KEY=
( time ./venv/bin/python run_fieldgen.py generate --package $rep/pkg ) 2>&1 | sed -u 's/nvapi-[A-Za-z0-9_-]*/[redacted]/g' >> $rep/generate.log
touch $rep/generate_done.flag
