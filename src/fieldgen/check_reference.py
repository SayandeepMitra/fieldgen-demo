"""Reference side of `fieldgen check --reference`: checks that no reference expression leaked into the package files. Never imported by the generator."""
import glob, json, re
from pathlib import Path

def _j(p):
    with open(p, encoding="utf-8") as f: return json.load(f)

def _trivial(expr):
    e = expr.strip()
    return bool(re.fullmatch(r"[\w.]+", e)) or bool(re.fullmatch(r"CAST\(NULL AS \w+\)", e, re.I)) or len(e) < 8

def reference_strings(reference_dir):
    out = []; ref = Path(reference_dir)
    for f in glob.glob(str(ref / "recipes" / "*.json")):
        g = _j(f); out += [b["from"] for b in g["branches"]] + [g["grain"]] + [x for x in (g["group_by"] or []) if not _trivial(x)]
    for f in glob.glob(str(ref / "fields" / "*.json")):
        g = _j(f); out += [e["expr"] for e in g.get("expressions", []) if not _trivial(e["expr"])]
        if g.get("exclusion_reason"): out.append(g["exclusion_reason"])
    return sorted(set(s for s in out if s))

def _variants(s):
    n = " ".join(s.split()); return {s, n, json.dumps(s)[1:-1], json.dumps(n)[1:-1]}

def leak_check(root, reference_dir):
    """Reference strings found in the manifest, source files, target files, matches or domain files of the package."""
    root = Path(root); files = [root / "manifest.json", root / "source" / "tables.json", root / "source" / "links.json", root / "source" / "dependencies.json", root / "target" / "tables.json",
                                root / "target" / "reference_tables.json", root / "target" / "field_docs.json"] + sorted((root / "source" / "profiles").glob("*.json")) + sorted((root / "matches").glob("*.json")) + sorted((root / "domain").glob("*"))
    gs = reference_strings(reference_dir); hits = []
    for p in files:
        if not p.is_file(): continue
        txt = p.read_text(encoding="utf-8"); flat = " ".join(txt.split())
        for s in gs:
            if any(v in txt or v in flat for v in _variants(s)): hits.append(f"{p.relative_to(root)}: reference string {s[:60]!r}")
    return hits
