"""Run a pipeline SUBMISSION in the L2 sandbox, then grade it (l2_grade.py).

Submission = a directory with one file per target table, <Table>.sql, holding either
    * a single SELECT/WITH query whose output columns are the table's columns (loaded BY NAME), or
    * any SQL script (own INSERT INTO <Table> ..., helper TEMP tables, ...).
Optional order.txt lists tables in execution order; default = the gold's dependency order (dimensions before facts).
Later tables may read earlier TARGET tables (a fact joins the dimension it just built) and any Source.* table.

Sandbox: a copy of the benchmark database with Source.* only and EMPTY target tables created from the target DDL
(types kept; NOT NULL/PK/FK/CHECK stripped by default, --constraints strict keeps them; violations are counted by the grader either way).
The candidate runs on its own connection with external access disabled (no ATTACH of the reference, no file reads) and a
per-table timeout. The reference is only opened by the grader afterwards, in a separate connection.

usage: python l2_run.py SUBMISSION_DIR --name NAME [--timeout 900] [--audit] [--keep-gold-except T1,T2]   (last one is for controls only)
"""
import argparse, json, os, re, shutil, subprocess, sys, threading, time
import duckdb
import grade_swap as g
import l2_grade

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
import gold_version as _gv0
RUNS = os.path.join(HERE, _gv0.RUNS_SUBDIR, "l2")        # v2 sandboxes/runs live under runs/v2/l2, never mixed with v1
BASE = os.path.join(RUNS, "_base", "sandbox_base.duckdb")            # constraints as declared (NOT NULL / PK / FK / CHECK)
BASE_NC = os.path.join(RUNS, "_base", "sandbox_base_nc.duckdb")      # same types, constraints stripped (default, see below)
import gold_version as _gv
DDL = _gv.TARGET_DDL


def strip_constraints(ddl):
    ddl = re.sub(r"(?i)\s+CHECK\s*\((?:[^()]|\([^()]*\))*\)", "", ddl)
    ddl = re.sub(r"(?i)\s+REFERENCES\s+\w+\s*\(\w+\)", "", ddl)
    ddl = re.sub(r"(?i)\s+PRIMARY\s+KEY", "", ddl)
    return re.sub(r"(?i)\s+NOT\s+NULL", "", ddl)


def build_base(force=False, constraints="off"):
    path = BASE if constraints == "strict" else BASE_NC
    if os.path.exists(path) and not force:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    subprocess.run(["cp", "-c", l2_grade.GOLD_DB, path], check=True)      # APFS clone: instant, copy-on-write
    con = duckdb.connect(path)
    ddl = re.sub(r"--[^\n]*", "", open(DDL).read())
    if constraints != "strict":
        ddl = strip_constraints(ddl)
    created = re.findall(r"(?i)create\s+table\s+(\w+)", ddl)
    existing = [t for (t,) in con.execute("select table_name from information_schema.tables where table_schema='main' and table_type='BASE TABLE'").fetchall()]
    for t in [x for x in reversed(created) if x in existing] + [x for x in existing if x not in created]:   # children before parents (FKs)
        con.execute(f'drop table "{t}"')
    for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
        con.execute(stmt)
    n_src = con.execute("select count(*) from information_schema.tables where table_schema='Source'").fetchone()[0]
    con.close()
    print(f"sandbox base built ({constraints} constraints): {n_src} Source tables, empty targets")
    return path


def is_plain_query(sql):
    s = re.sub(r"--[^\n]*|/\*.*?\*/", "", sql, flags=re.S).strip().rstrip(";").strip()
    return bool(re.match(r"(?is)^(select|with|from|values)\b", s)) and ";" not in s


def run_table(con, table, cols, sql, timeout):
    sql = sql.strip().rstrip(";") if is_plain_query(sql) else sql
    if is_plain_query(sql):
        sql = f"INSERT INTO {table} BY NAME SELECT * FROM ({sql})"
    done = threading.Event()
    def killer():
        if not done.wait(timeout):
            con.interrupt()
    th = threading.Thread(target=killer, daemon=True); th.start()
    t0 = time.time()
    try:
        con.execute(sql)
        status, err = "OK", ""
    except Exception as e:
        status, err = "ERROR", str(e)[:300].replace("\n", " ")
    finally:
        done.set()
    n = con.execute(f"select count(*) from {table}").fetchone()[0]
    return {"status": status, "error": err, "rows": n, "seconds": round(time.time() - t0, 1)}


def run_submission(sub_dir, name, timeout=900, keep_gold_except=None, constraints="off"):
    base = build_base(constraints=constraints)
    rd = os.path.join(RUNS, name)
    os.makedirs(rd, exist_ok=True)
    db = os.path.join(rd, "sandbox.duckdb")
    if os.path.exists(db):
        os.remove(db)
    subprocess.run(["cp", "-c", base, db], check=True)
    gold = g.load_gold()
    order = [l.strip() for l in open(os.path.join(sub_dir, "order.txt")) if l.strip()] if os.path.exists(os.path.join(sub_dir, "order.txt")) else list(gold)
    if keep_gold_except is not None:                                   # CONTROLS ONLY: prerequisite tables are copied from the gold
        c0 = duckdb.connect(db)
        c0.execute(f"ATTACH '{l2_grade.GOLD_DB}' AS gold (READ_ONLY)")
        first = min(order.index(t) for t in keep_gold_except)
        for t in order[:first]:
            c0.execute(f"INSERT INTO {t} SELECT * FROM gold.main.{t}")
        c0.close()
    con = duckdb.connect(db, config={"enable_external_access": False})   # no ATTACH / file reads from candidate SQL
    ex = {}
    for t in order:
        f = os.path.join(sub_dir, f"{t}.sql")
        if not os.path.exists(f):
            ex[t] = {"status": "NO_FILE", "error": "", "rows": con.execute(f"select count(*) from {t}").fetchone()[0] if keep_gold_except is not None else 0, "seconds": 0}
            continue
        ex[t] = run_table(con, t, gold[t]["cols"], open(f).read(), timeout)
        print(f"  {t:18s} {ex[t]['status']:6s} rows={ex[t]['rows']:>8} {ex[t]['seconds']:>6}s {ex[t]['error'][:90]}", flush=True)
    con.close()
    json.dump(ex, open(os.path.join(rd, "l2_exec.json"), "w"), indent=1)
    return rd, db, ex


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("submission"); ap.add_argument("--name", required=True)
    ap.add_argument("--timeout", type=int, default=900); ap.add_argument("--audit", action="store_true")
    ap.add_argument("--keep-gold-except", default=None)
    ap.add_argument("--constraints", choices=["off", "strict"], default="off",
                    help="off (default): targets have the declared types but no NOT NULL/PK/FK/CHECK, so one bad column does not "
                         "discard the whole table; violations are counted and reported. strict: the declared constraints are enforced at load.")
    a = ap.parse_args()
    keep = a.keep_gold_except.split(",") if a.keep_gold_except else None
    rd, db, ex = run_submission(a.submission, a.name, a.timeout, keep, a.constraints)
    res = l2_grade.grade(db)
    for t, e in ex.items():                                            # carry the L0 execution result into the report
        if t in res["tables"]:
            res["tables"][t]["exec"] = e
            if e["status"] == "ERROR":
                res["tables"][t]["status"] = "ERROR"
    summ = l2_grade.summarise(res)
    res["summary"] = summ
    if a.audit:
        out = subprocess.run([sys.executable, os.path.join(HERE, "gold_audit.py"), "--db", db, "--out", os.path.join(rd, "audit.csv")], capture_output=True, text=True).stdout
        m = re.search(r"Applicable to a Batch-1-only load: (\d+)\s+OK (\d+)\s+NOT-OK (\d+)", out)
        res["audit"] = {"applicable": int(m.group(1)), "ok": int(m.group(2)), "not_ok": int(m.group(3))} if m else {"error": out[-300:]}
    json.dump(res, open(os.path.join(rd, "l2_scores.json"), "w"), indent=1)
    rep = l2_grade.render(res, summ) + (f"\n- official audit (Batch-1 applicable): {res['audit']}" if a.audit else "")
    open(os.path.join(rd, "l2_report.md"), "w").write(rep)
    print(rep)


if __name__ == "__main__":
    main()
