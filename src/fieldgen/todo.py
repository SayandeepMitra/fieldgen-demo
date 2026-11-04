"""TODOs of a package (generator side): what `fieldgen init` leaves for you to fill, and which of it blocks `fieldgen generate`.
blocking: nothing can be generated without it (matched columns), or the config asks for it (domain knowledge `required`).
notes: quality hints (descriptions, target documentation, proposed keys and links, lookup-table list)."""
import json
from pathlib import Path

def _j(p):
    with open(p, encoding="utf-8") as f: return json.load(f)

def domain_ready(package):
    """True when domain/ holds at least one text file that has no TODO line left, or a non-empty expert JSON file."""
    d = Path(package) / "domain"
    if not d.is_dir(): return False
    for f in d.glob("*.md"):
        txt = f.read_text(encoding="utf-8")
        if txt.strip() and not any(l.lstrip().startswith("TODO") for l in txt.split("\n")): return True
    for n in ("descriptions_supplement.json", "value_meanings.json"):
        p = d / n
        if p.exists() and _j(p): return True
    return False

def package_todos(package, settings):
    """(blocking, notes): two lists of sentences."""
    root = Path(package); blocking, notes = [], []
    try: m = _j(root / "matches" / "matches.json"); st = _j(root / "source" / "tables.json"); fd = _j(root / "target" / "field_docs.json"); rt = _j(root / "target" / "reference_tables.json"); ln = _j(root / "source" / "links.json")
    except Exception: return blocking, notes          # `check` reports unreadable files
    if not any(m.values()): blocking.append("matches/matches.json: no target column has a matched source column yet. Fill in the matches (docs/input_package.md).")
    if settings.domain_knowledge == "required" and not domain_ready(root): blocking.append("domain/: no domain knowledge yet. Write domain/domain_knowledge.md or domain/flow_text.md (remove the TODO lines), or set domain_knowledge: optional or off in config.yaml.")
    ncols = sum(len(t["columns"]) for t in st); nd = sum(1 for t in st for c in t["columns"] if c.get("description")) + sum(1 for t in st if t.get("description"))
    if nd == 0: notes.append(f"source/tables.json: no descriptions yet for the {ncols} source columns (descriptions help the model).")
    if not any(v.get("guidance") or v.get("conventions") for v in fd.get("fields", {}).values()): notes.append("target/field_docs.json: no target documentation yet (guidance and conventions are empty).")
    if not rt.get("reference_tables"): notes.append("target/reference_tables.json: no lookup tables listed. That is fine if the source has no code lists or vocabularies.")
    pk = [t["name"] for t in st if (t.get("pk_provenance") or {}).get("source") == "proposed"]
    if pk: notes.append(f"source/tables.json: primary keys of {len(pk)} table(s) were proposed by `fieldgen init`; confirm them ({', '.join(pk[:4])}{', ...' if len(pk) > 4 else ''}).")
    pl = [l for l in ln if "proposed" in (l.get("note") or "")]
    if pl: notes.append(f"source/links.json: {len(pl)} link(s) were proposed by `fieldgen init` (marked proposed in the note); confirm or delete them.")
    return blocking, notes
