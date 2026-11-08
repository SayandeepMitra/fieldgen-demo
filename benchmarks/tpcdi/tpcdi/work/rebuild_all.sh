#!/bin/bash
set -e
cd "$(dirname "$0")/../.."      # benchmarks/tpcdi
rm -f tpcdi/work/tpcdi.duckdb
echo "=== C2+schemas: simple tables ==="
python3 tpcdi/work/load_simple_tables.py
echo
echo "=== C3: FINWIRE ==="
python3 tpcdi/work/load_finwire.py
echo
echo "=== C4: CustomerMgmt.xml ==="
python3 tpcdi/work/load_customermgmt_xml.py
echo
echo "=== C6: ported historical_load.sql ==="
python3 tpcdi/work/run_ported.py
