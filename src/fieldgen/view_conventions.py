"""Step-1 view with the documentation conventions of the shown target columns (generic; generator side).
conventions_shown: every target column shown in a field card also gets its conventions text from the target documentation, verbatim (whitespace normalised), on a line
`  conventions: <text> [<doc label>: <table>.<column>, conventions]`. With the switch off the view is src view_domain.Step1ViewV6 unchanged."""
import re
from fieldgen.view_domain import Step1ViewV6
from fieldgen.domain_text import norm, lab

class Step1ViewV8(Step1ViewV6):
    def __init__(self, *a, conventions_shown=False, **kw):
        super().__init__(*a, **kw); self.conv_shown = conventions_shown

    def conventions(self, table, col):
        t = norm((self.dt.docs.get(f"{table}.{col}") or {}).get("conventions")); return "" if t in self.dt.empties else t

    def field_cards(self, table, fields):
        text = super().field_cards(table, fields)
        if not self.conv_shown or not text: return text
        groups = []
        for l in text.split("\n"):
            m = re.match(r"^- (\w+) \(", l)
            if m: groups.append([m.group(1), [l]])
            elif groups: groups[-1][1].append(l)
        out = []
        for col, lines in groups:
            c = self.conventions(table, col)
            if c: lines = lines + [f"  conventions: {c}" + lab(f"{self.dt.doc_label}: {table}.{col}, conventions")]
            out += lines
        return "\n".join(out)
