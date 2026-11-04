"""Recipe step input (generic; generator side): the view of the package for one target table, the task, and the two messages."""
import jinja2
from fieldgen.paths import PROMPTS_DIR
from fieldgen.view_cards import build_step1_task_v3
from fieldgen.view_nulls import Step1ViewV5
from fieldgen.view_conventions import Step1ViewV8
from fieldgen.domain_text import DomainTextV2
from fieldgen.link_facts_nulls import LinkProfilesV5

_env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(PROMPTS_DIR)), keep_trailing_newline=True, undefined=jinja2.Undefined)

def make_view(pkg, pkg_root, s, domain_on, con=None, profile_cache=None):
    """s: Settings. domain_on: the domain files are used (domain_knowledge required or optional-and-present)."""
    prof = LinkProfilesV5(con, profile_cache, null_label=True) if s.computed_facts and profile_cache else None
    if domain_on:
        dt = DomainTextV2(pkg, pkg_root, con, "", doc_first=s.documentation_first, measured=s.measured_links, min_coverage=s.min_coverage)
        v = Step1ViewV8(pkg, pkg_root, con=con, use_domain=True, link_profile=prof is not None, flow_text=True, profiles=prof, null_label=True, suffix="", dt=dt, conventions_shown=s.documentation_conventions)
    else:
        v = Step1ViewV5(pkg, pkg_root, con=con, use_domain=False, link_profile=prof is not None, flow_text=False, profiles=prof, null_label=True, suffix="")
    v.profiling = s.data_profiling
    return v

def build_task(pkg, view, table): return build_step1_task_v3(pkg, view, table, 1)

def recipe_messages(task, s):
    system = (PROMPTS_DIR / ("v3_step1_system.md" if s.join_rules_in_prompt else "v2_step1_system.md")).read_text().strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": _env.get_template("v3_step1_user.md").render(task=task)}]
