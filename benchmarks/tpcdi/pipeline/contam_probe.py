"""Schema-only recall probe: how much of the MATCHING can a model produce with NO data, NO query scope and NO sample rows?
Prompt = target table/column/type + the bare Source schema (table.column names, no values). The model names the source
fields it believes populate the column. Scored against the gold's matched fields (base-table refs only).
Read against the trivial name-similarity matcher computed on the same candidate list: a model that beats the name matcher
by a wide margin on columns whose names give nothing away is recalling benchmark/spec knowledge (or inferring semantics);
one that does not is not showing contamination of the task. Also the matching-not-given variant's lower bound.

  python contam_probe.py --run contam_probe --models nemotron,mistral_large  (then --score)"""
import argparse, difflib, json, os, re, sys, threading
from concurrent.futures import ThreadPoolExecutor
import duckdb
import grade_swap as g, scope_prompt as sp, llm_parallel
HERE = os.path.dirname(os.path.abspath(__file__))
fold = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())


def source_columns(con):
    rows = con.execute("select table_name, column_name from information_schema.columns where table_schema='Source' order by table_name, ordinal_position").fetchall()
    out = {}
    for t, c in rows:
        out.setdefault(f"Source.{t}", []).append(c)
    return out


def gold_fields(gold, con, table, col):
    try:
        sc = sp.derive_scope(gold, con, table, col)
        mf = sp.matched_fields(sc) if sc else []
    except Exception:
        return None
    if not mf or any(not f.startswith("Source.") for f in mf):
        return None                                  # derived-relation refs: not comparable at schema level
    return sorted({f.lower() for f in mf})


def build_prompt(table, col, ctype, schema):
    lines = [f"  {t}: " + ", ".join(cs) for t, cs in schema.items()]
    return f"""You are doing schema matching for the TPC-DI data-integration benchmark (historical load).

TARGET column
  Table: {table}
  Column: {col}
  Declared type/constraints: {ctype}

SOURCE SCHEMA (table: columns; names only, no data)
""" + "\n".join(lines) + """

TASK
Which source column(s) feed the target column? Answer with ONLY a JSON list of "Source.Table.Column" strings
(use [] if it is derived purely from constants/generated values). Do not explain."""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="contam_probe"); ap.add_argument("--models", default="nemotron,mistral_large")
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    import gold_version as _gv
    rd = os.path.join(HERE, _gv.RUNS_SUBDIR, a.run); os.makedirs(rd, exist_ok=True)
    rpath = os.path.join(rd, "results.jsonl")
    gold = g.load_gold(); con = duckdb.connect(sp.DB_PATH, read_only=True); schema = source_columns(con)
    allf = [f"{t}.{c}" for t, cs in schema.items() for c in cs]
    items = []
    for table, s in gold.items():
        for col in s["cols"]:
            gf = gold_fields(gold, con, table, col)
            if gf is None: continue
            ct = con.execute(f"select data_type from information_schema.columns where table_name='{table}' and column_name='{col}'").fetchone()
            items.append((f"{table}.{col}", table, col, ct[0] if ct else "", gf))
    if not a.score:
        done = set()
        if os.path.exists(rpath):
            for l in open(rpath):
                r = json.loads(l)
                if not r.get("error"): done.add((r["key"], r["model"]))
        lock = threading.Lock()
        def work(it, model):
            key, table, col, ct, gf = it
            rec = {"key": key, "model": model}
            try:
                res = llm_parallel.call(model, build_prompt(table, col, ct, schema), temperature=0.0, timeout=180, tries=8)
                rec["raw"] = res["raw"]
            except Exception as e:
                rec.update(raw=None, error=str(e)[:200])
            with lock: open(rpath, "a").write(json.dumps(rec) + "\n")
        pools = {m: ThreadPoolExecutor(4) for m in a.models.split(",")}
        futs = [pools[m].submit(work, it, m) for it in items for m in pools if (it[0], m) not in done]
        print(len(futs), "calls"); [f.result() for f in futs]; return
    # scoring
    got = {}
    for l in open(rpath):
        r = json.loads(l)
        if r.get("raw"): got[(r["key"], r["model"])] = r["raw"]
    import csv
    B = os.path.dirname(HERE)
    sub = {f"{r['table']}.{r['column']}": r for r in csv.DictReader(open(_gv.CLEAN_SUBSET_CSV))}
    res = {}
    for key, table, col, ct, gf in items:
        k = len(gf)
        # trivial name matcher with oracle k
        sc = sorted(allf, key=lambda f: (-(fold(f.split(".")[-1]) == fold(col)), -difflib.SequenceMatcher(None, fold(col), fold(f.split(".")[-1])).ratio()))
        res.setdefault("trivial_name(oracle k)", {})[key] = {x.lower() for x in sc[:k]} == set(gf)
        for (kk, m), raw in got.items():
            if kk != key: continue
            try:
                lst = json.loads(re.search(r"\[.*\]", raw, re.S).group(0))
                pred = {str(x).lower() for x in lst}
            except Exception:
                pred = set()
            res.setdefault(m, {})[key] = pred == set(gf)
    print(f"columns scorable at schema level: {len(items)}  (single-field: {sum(len(i[4])==1 for i in items)})")
    for m, d in res.items():
        core = [k for k in d if sub.get(k, {}).get('tier') in ('clean', 'clean_column', 'fk_entity_only')]
        multi = [k for k in d if len(dict((i[0], i[4]) for i in items)[k]) > 1]
        print(f"{m:26s} exact field-set: all {sum(d.values())}/{len(d)}  core {sum(d[k] for k in core)}/{len(core)}  multi-field {sum(d[k] for k in multi)}/{len(multi)}")


if __name__ == "__main__":
    main()
