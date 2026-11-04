"""Template D view with the Experiment 2 switches (generic; generator side). Calls the V3 view; adds
- link_profile: after the link / overlap lines of a source column whose parent is a lookup relation (target/reference_tables.json), one fact line from src/link_profile_v4.py per linked lookup column;
- flow_text: <package>/domain/flow_text.md (if present) in the Domain knowledge section, after the project sentences and before the constraints block.
With both switches off the output equals the V3 view."""
import re
from pathlib import Path
from fieldgen.view_cards import Step1ViewV3, build_step1_task_v3
from fieldgen.link_facts import LinkProfiles, fact_line

_LINK = re.compile(r"^  link: -> (\S+?)\.(\S+) \(")
_OVER = re.compile(r"^  overlaps (\S+?)\.(\S+): ")
_CARD = re.compile(r"^- (\S+) \(")

class Step1ViewV4(Step1ViewV3):
    def __init__(self, pkg, pkg_root, con=None, use_domain=False, link_profile=False, flow_text=False, profiles=None):
        super().__init__(pkg, pkg_root, con=con, use_domain=use_domain)
        self.link_profile, self.profiles = link_profile, profiles
        p = Path(pkg_root) / "domain" / "flow_text.md"
        self.flow = p.read_text(encoding="utf-8").strip() if flow_text and p.exists() else ""

    def relation_text(self, name):
        text = super().relation_text(name)
        if not text or not self.link_profile or self.profiles is None: return text
        out, col, buf = [], None, []
        def flush():
            for lr, lc in buf:
                if lr not in self.lookups: continue
                p = self.profiles.get(name, col, lr, lc)
                if p is not None and p["distinct"]: out.append("  " + fact_line(lr, lc, p))
            buf.clear()
        for line in text.split("\n"):
            m = _CARD.match(line)
            if m: flush(); col = m.group(1)
            elif line.startswith("#### "): flush(); col = None
            else:
                m = _LINK.match(line) or _OVER.match(line)
                if m and col: buf.append((m.group(1), m.group(2)))
            if not line and col: flush()
            out.append(line)
        flush(); return "\n".join(out)

    def domain_section(self, table, fields):
        if not self.flow: return super().domain_section(table, fields)
        cs = self.constraint_sentences(table, fields) if self.use_domain else []
        parts = [self.domain.text] if self.use_domain and self.domain.text else []
        parts.append(self.flow)
        if cs: parts.append("Target column constraints:\n" + "\n".join(f"- {c}: {s}" for c, s in cs))
        return "\n\n".join(parts), sorted({c for c, _ in cs})

build_step1_task_v4 = build_step1_task_v3
