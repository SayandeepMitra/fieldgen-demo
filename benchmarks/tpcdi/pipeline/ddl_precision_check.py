"""Does any target column's declared type change the value its gold expression computes? (TPCDI_GOLD picks the gold.)
For every table: run the gold SELECT WITHOUT the per-column type cast, and compare each column's multiset of values with what the
INSERT stored. A difference = the DDL type truncates/rounds/overflows (e.g. DimSecurity.Dividend INTEGER holding 1.85)."""
import collections, sys
import duckdb
import grade_swap as g
con = duckdb.connect(g.DB_PATH, read_only=True)
gold = g.load_gold()
bad = []
for t, spec in gold.items():
    cols = spec["cols"]
    rows = con.execute(g.probe_query(gold, t, cols[0], None, None)).fetchall()
    st = con.execute(f"select {', '.join(cols)} from {t}").fetchall()
    for i, c in enumerate(cols):
        a = collections.Counter(g._norm(r[i]) for r in rows); b = collections.Counter(g._norm(r[i]) for r in st)
        n = sum((a - b).values())
        if n:
            bad.append((t, c, n, len(st)))
            print(f"LOSS {t}.{c}: {n}/{len(st)} values change on insert", flush=True)
print("done;", len(bad), "columns with a type effect")
