"""Experiment 2b view (generic; generator side): src/step1_view_v4.py with (a) null_label (src/link_profile_v5.py), (b) domain files with a name suffix (src/domain_v5.py).
With null_label false and suffix "" the output equals the V4 view."""
import re
from fieldgen.view_facts import Step1ViewV4, _LINK, _OVER, _CARD
from fieldgen.link_facts_nulls import LinkProfilesV5, fact_line
from fieldgen.domain_files import DomainV5

class Step1ViewV5(Step1ViewV4):
    def __init__(self, pkg, pkg_root, con=None, use_domain=False, link_profile=False, flow_text=False, profiles=None, null_label=False, suffix=""):
        super().__init__(pkg, pkg_root, con=con, use_domain=use_domain, link_profile=link_profile, flow_text=flow_text, profiles=profiles)
        self.null_label = null_label
        if use_domain: self.domain = DomainV5(pkg_root, suffix)
        if flow_text: self.flow = DomainV5(pkg_root, suffix).flow_text

    def relation_text(self, name):
        if not self.null_label: return super().relation_text(name)
        from fieldgen.view_cards import Step1ViewV3
        text = Step1ViewV3.relation_text(self, name)
        if not text or not self.link_profile or self.profiles is None: return text
        out, col, buf = [], None, []
        def flush():
            for lr, lc in buf:
                if lr not in self.lookups: continue
                p = self.profiles.get(name, col, lr, lc)
                if p is not None and p["distinct"]: out.append("  " + fact_line(lr, lc, p, True))
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
