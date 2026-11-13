# Copies the model's answers (not the prompts) out of a finished run's calls.jsonl into replay/answers/<name>.json,
# and the run's scores.json into replay/recorded/<name>.json. Only needed to create the files in this folder.
# Usage: python replay/extract_answers.py NAME RUN_FOLDER
import json, sys, shutil
from pathlib import Path
name, run = sys.argv[1], Path(sys.argv[2])
answers = {}
for line in open(run / "calls.jsonl", encoding="utf-8"):
    c = json.loads(line)
    if "raw_response" not in c: continue                       # a failed HTTP call has no answer
    assert c["tag"] not in answers, c["tag"]
    answers[c["tag"]] = {"text": c["raw_response"], "finish_reason": c.get("finish_reason") or "stop"}
here = Path(__file__).parent
(here / "answers" / f"{name}.json").write_text(json.dumps({"model": json.loads(open(run / "calls.jsonl").readline())["model"], "answers": answers}, indent=1), encoding="utf-8")
shutil.copy(run / "scores.json", here / "recorded" / f"{name}.json")
print(name, len(answers), "answers")
