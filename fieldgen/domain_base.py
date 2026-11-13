"""Optional project-supplied knowledge next to a package (<package>/domain/). Every file is optional.
descriptions_supplement.json: [{table, column|null, text, provenance}]; value_meanings.json: [{table, column, value, meaning}];
domain_knowledge.md: free text for the prompt. Generator side; reads only that directory."""
import json
from pathlib import Path

class Domain:
    def __init__(self, root=None):
        d = Path(root) / "domain" if root else None
        def rd(name):
            p = d / name if d else None
            return json.load(open(p, encoding="utf-8")) if p and p.exists() else []
        self.columns, self.tables, self.provenance = {}, {}, {}
        for e in rd("descriptions_supplement.json"):
            if e.get("column"): self.columns[(e["table"], e["column"])] = e["text"]
            else: self.tables[e["table"]] = e["text"]
            self.provenance[(e["table"], e.get("column"))] = e.get("provenance")
        self.meanings = {}
        for e in rd("value_meanings.json"): self.meanings.setdefault((e["table"], e["column"]), {})[str(e["value"])] = e["meaning"]
        p = d / "domain_knowledge.md" if d else None
        self.text = p.read_text(encoding="utf-8").strip() if p and p.exists() else ""

    def column_text(self, table, column, stored):
        """Stored description wins; the supplement only fills an empty one."""
        return stored if (stored or "").strip() else self.columns.get((table, column), "")

    def table_text(self, table, stored):
        return stored if (stored or "").strip() else self.tables.get(table, "")

    def meaning(self, table, column, value):
        return self.meanings.get((table, column), {}).get(str(value))
