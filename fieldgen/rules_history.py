"""Two optional prompt additions (both off by default; with both off every prompt is byte-identical to v1.2-demo). Generic: no names of any dataset.
formula_docs: the documented rules (the conventions line the recipe prompt shows) of the target column, in the formula prompt.
history_pattern: tool instruction for sources that hold several records per target key (recipe prompt; formula prompt when the recipe is grouped)."""
from fieldgen.domain_text import lab

HISTORY_LABEL = "Tool instruction: history pattern"
HISTORY_TEXT = ("If a source holds several records per target key (versions or events with a timestamp), group by the target key. "
                "For each column, take the value from the latest record where that column is not empty, e.g. in DuckDB: "
                "arg_max(col, ts) FILTER (WHERE col IS NOT NULL). Do not use MIN, MAX or ANY_VALUE to choose a version. "
                "Join all tables that carry the event's fields to the event first, so each field has the event's timestamp.") + lab(HISTORY_LABEL)

def history_text(on): return HISTORY_TEXT if on else ""

def column_rules(view, table, col):
    """The labelled documentation line(s) the recipe prompt shows for the column (its conventions), or None."""
    dt = getattr(view, "dt", None); conv = getattr(view, "conventions", None)
    if dt is None or conv is None: return None
    c = conv(table, col)
    return f"conventions: {c}" + lab(f"{dt.doc_label}: {table}.{col}, conventions") if c else None
