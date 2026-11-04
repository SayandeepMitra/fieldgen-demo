"""Domain files with a name suffix (generic): descriptions_supplement<suffix>.json, value_meanings<suffix>.json, flow_text<suffix>.md; domain_knowledge.md has no suffix.
suffix "" reads the same files as src/domain_v3.py."""
import json
from pathlib import Path
from fieldgen.domain_base import Domain

class DomainV5(Domain):
    def __init__(self, root=None, suffix=""):
        d = Path(root) / "domain" if root else None
        def rd(name):
            p = d / name if d else None
            return json.load(open(p, encoding="utf-8")) if p and p.exists() else []
        self.columns, self.tables, self.provenance, self.meanings = {}, {}, {}, {}
        for e in rd(f"descriptions_supplement{suffix}.json"):
            if e.get("column"): self.columns[(e["table"], e["column"])] = e["text"]
            else: self.tables[e["table"]] = e["text"]
            self.provenance[(e["table"], e.get("column"))] = e.get("provenance")
        for e in rd(f"value_meanings{suffix}.json"): self.meanings.setdefault((e["table"], e["column"]), {})[str(e["value"])] = e["meaning"]
        p = d / "domain_knowledge.md" if d else None
        self.text = p.read_text(encoding="utf-8").strip() if p and p.exists() else ""
        f = d / f"flow_text{suffix}.md" if d else None
        self.flow_text = f.read_text(encoding="utf-8").strip() if f and f.exists() else ""
