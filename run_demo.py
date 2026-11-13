# Replays the saved model answers (replay/answers/) through the tool's own generate -> execute -> test, with no network and no key.
# A scripted stand-in replaces the HTTP call only: it hands back the answer the model gave for the same task (matched by the call's tag).
# Then it prints the score table and compares it with the scores recorded in the live run (replay/recorded/).
#   python run_demo.py --dataset synthea                       (needs the Synthea data, see datasets/synthea_omop/SETUP.md)
#   python run_demo.py --dataset tpcdi --run run10 --work DIR  (DIR = the --work folder of datasets/tpcdi/make_package.py)
import argparse, json, os, sys, threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ["NVIDIA_API_KEY"] = "dummy-not-a-key"        # never a real key: the stand-in makes no HTTP call
RUNS = {"synthea": ("formula_docs", "synthea_formula_docs"), "tpcdi": ("run10", "tpcdi_run10")}   # dataset -> (default run, answers file)


def install_stand_in(answers):
    """Replace Client._http: look up the saved answer by the tag of the call; skip the rate-limit sleeps."""
    import fieldgen.llm as llm
    local, lock, used = threading.local(), threading.Lock(), set()
    orig_chat, orig_init = llm.Client.chat, llm.Client.__init__

    def chat(self, messages, n=1, tag=None, **kw):
        local.tag = tag
        return orig_chat(self, messages, n=n, tag=tag, **kw)

    def http(self, body):
        tag = local.tag
        if tag not in answers: raise KeyError(f"no saved answer for call {tag!r}")
        with lock: used.add(tag)
        a = answers[tag]
        return 200, {"model": "replay", "choices": [{"message": {"content": a["text"]}, "finish_reason": a["finish_reason"]}],
                     "usage": {"prompt_tokens": 0, "completion_tokens": 0}}, {}

    llm.Client.chat, llm.Client._http = chat, http
    llm.Client.__init__ = lambda self, cfg, calls_path=None, transport=None, sleep=None: orig_init(self, cfg, calls_path=calls_path, transport=transport, sleep=lambda s: None)
    return used


def l2_table(scores):
    """Per table: rows correct, and L2 columns correct / scored."""
    rows = {}
    for t, v in scores["tables"].items(): rows[t] = [v["recipe_rows_correct"], 0, 0]
    for key, v in scores["fields"].items():
        t = key.split(".", 1)[0]
        if t in rows and v.get("L2") is not None:
            rows[t][2] += 1; rows[t][1] += bool(v["L2"])
    return rows


def main():
    ap = argparse.ArgumentParser(description="Replay saved model answers through fieldgen (no key, no network)")
    ap.add_argument("--dataset", choices=sorted(RUNS), default="synthea")
    ap.add_argument("--run", help="synthea: formula_docs; tpcdi: run10 or run6")
    ap.add_argument("--package", help="package folder (default: datasets/synthea_omop/package, or WORK/packages/RUN/package)")
    ap.add_argument("--work", help="tpcdi: the --work folder given to datasets/tpcdi/make_package.py")
    a = ap.parse_args()
    run = a.run or RUNS[a.dataset][0]
    name = f"{a.dataset}_{run}" if a.dataset == "tpcdi" else RUNS[a.dataset][1]
    f = ROOT / "replay" / "answers" / f"{name}.json"
    if not f.exists(): sys.exit(f"no saved answers for run {run!r}: {sorted(p.stem for p in f.parent.glob('*.json'))}")
    if a.package: pkg = Path(a.package).resolve()
    elif a.dataset == "synthea": pkg = ROOT / "datasets/synthea_omop/package"
    else:
        if not a.work: sys.exit("tpcdi needs --work DIR (the folder written by datasets/tpcdi/make_package.py)")
        pkg = Path(a.work).resolve() / "packages" / run / "package"
    if not (pkg / "manifest.json").exists(): sys.exit(f"no package at {pkg}")
    if not any((pkg / "source/data").glob("*.csv")): sys.exit(f"no source data in {pkg}/source/data (see the dataset's README / SETUP.md)")
    os.chdir(ROOT)                                       # the tool reads config.yaml from the package folder, else from the current folder
    answers = json.load(open(f, encoding="utf-8"))["answers"]
    used = install_stand_in(answers)
    from fieldgen import cli
    for cmd in ("generate", "execute", "test"):
        print(f"===== {cmd}", flush=True)
        rc = cli.main([cmd, "--package", str(pkg)])
        if rc: sys.exit(f"{cmd} ended with exit code {rc}")
    scores = json.load(open(pkg.parent / "run" / "scores.json", encoding="utf-8")); rec = json.load(open(ROOT / "replay/recorded" / f"{name}.json", encoding="utf-8"))
    now, was = l2_table(scores), l2_table(rec)
    print(f"\nscore table, run '{name}' (replay vs recorded live run)\n{'table':24s} rows  L2 columns   recorded")
    for t in now:
        w = was.get(t, [None, 0, 0])
        print(f"{t:24s} {'yes' if now[t][0] else 'no ':4s}  {now[t][1]:2d} / {now[t][2]:2d}      {'yes' if w[0] else 'no '} {w[1]:2d} / {w[2]:2d}")
    tabs = sum(v[0] for v in now.values()); cols = sum(v[1] for v in now.values())
    rtabs = sum(v[0] for v in was.values()); rcols = sum(v[1] for v in was.values())
    print(f"\nreplay  : {tabs} of {len(now)} tables with correct rows, {cols} L2 columns correct\nrecorded: {rtabs} of {len(was)} tables with correct rows, {rcols} L2 columns correct")
    same = now == was and {k: v.get("L2") for k, v in scores["fields"].items()} == {k: v.get("L2") for k, v in rec["fields"].items()}
    print(f"calls replayed: {len(used)} of {len(answers)} saved answers; per-table and per-column results identical to the recorded run: {'YES' if same else 'NO'}")
    sys.exit(0 if same else 1)


if __name__ == "__main__":                              # needed: the tool's guardrail uses a process pool that re-imports this file
    main()
