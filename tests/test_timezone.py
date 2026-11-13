"""The machine's time zone must not change what the tool sends to the model (the source data carries explicit offsets as plain text)."""
import hashlib, json, os, subprocess, sys
from pathlib import Path

SCRIPT = r"""
import sys, json, hashlib
from pathlib import Path
from fieldgen import cards, recipe_prompts as rp
from fieldgen.package import load_package
from fieldgen.db import package_connection
from fieldgen.settings import load_settings
package, work = Path(sys.argv[1]), Path(sys.argv[2]); work.mkdir(exist_ok=True)
cards.build(package, out_dir=work / "cards", progress_path=work / "p.json"); cards.set_cards_dir(work / "cards")
pkg = load_package(package); con = package_connection(pkg); s = load_settings(None); view = rp.make_view(pkg, package, s, True, con, str(work / "lf.json"))
text = ""
for t in ("client", "purchase"):
    text += json.dumps(rp.recipe_messages(rp.build_task(pkg, view, t), s))
print(hashlib.sha256(text.encode()).hexdigest(), "placed_at" in text, "+05:30" in text)
"""

def test_prompts_are_identical_in_other_machine_time_zones(tmp_path, package):
    from conftest import SRC
    assert any(c == "placed_at" for c, _ in SRC["orders"][0])
    out = {}
    for zone in ("UTC", "America/New_York", "Pacific/Auckland", "Asia/Kolkata"):
        env = {**os.environ, "TZ": zone, "PYTHONPATH": os.pathsep.join(sys.path)}
        r = subprocess.run([sys.executable, "-c", SCRIPT, str(package), str(tmp_path / f"w_{zone.replace('/', '_')}")], capture_output=True, text=True, encoding="utf-8", env=env, timeout=300)
        assert r.returncode == 0, r.stderr[-400:]; out[zone] = r.stdout.split()
    assert len({v[0] for v in out.values()}) == 1, out                      # the same prompt bytes in every zone
    assert all(v[1] == "True" and v[2] == "True" for v in out.values())      # the column and its +05:30 text are really in the prompt

def test_the_export_script_pins_utc():
    src = (Path(__file__).resolve().parent.parent / "datasets/synthea_omop/tools/export_reference.py").read_text(encoding="utf-8")
    assert "SET TimeZone='UTC'" in src
