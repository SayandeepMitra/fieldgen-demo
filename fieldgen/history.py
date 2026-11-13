"""History wrapper for tables listed in the package config (history_tables). Generic: the key / order / tiebreak columns come from the config.
For a listed table the recipe is one row per event (no grouping, written by the model); the tool resolves the columns to aliases, sets GROUP BY <key> and wraps every
formula (written for a single event row) as arg_max(f, (order, tiebreak)) FILTER (WHERE NULLIF(CAST(f AS VARCHAR), '') IS NOT NULL). The key column is not wrapped."""
from fieldgen.domain_text import lab
from fieldgen.parse import recipe_info

LABEL = "Tool instruction: history table"

def recipe_text(c):
    return (f"This table is built from events. For each target key the tool keeps the latest value of every column over all events (ordered by {c['order']}, ties by {c['tiebreak']}; the key is {c['key']}). "
            "Write the recipe with one row per event: join every table that carries the event's fields to the event with LEFT JOIN, and do not group (group_by must be null). "
            "The tool adds the grouping itself and picks the latest value per column.") + lab(LABEL)

def formula_text(c):
    return ("This table keeps the latest value per key over all events; the tool wraps every formula and picks the latest non-empty value. "
            "Write the formula for a single event row: do not use aggregates or window functions; return NULL (not an empty string) when the event does not supply the value.") + lab(LABEL)

AUTO_LABEL = "Tool instruction: history decision"
AUTO_TEXT = ("If the source has several records per target key, and each record only fills in the fields that changed, set history to the key, the column that orders the records, "
             "and a tiebreak column. The tool will then keep the latest filled-in value of each column. If each record is a full copy, or there is one record per key, set history to null. "
             'Write it as the field "history" of the recipe JSON: {"key": <column>, "order": <column>, "tiebreak": <column>} or null.') + lab(AUTO_LABEL)

class HistoryError(Exception): pass

def _resolve(name, aliases, cols):
    tab, col = name.split(".", 1) if "." in name else (None, name)
    for a, t in aliases.items():
        if (tab is None or t.lower() == tab.lower()) and col.lower() in cols.get(t, set()): return f"{a}.{col}"
    raise HistoryError(f"history_tables: column {name} not found in the tables of the recipe")

def apply_history(recipe, cfg, pkg, pk_columns):
    """Returns the recipe with group_by = [key] and a `history` entry (resolved expressions). The model's own group_by is replaced."""
    if len(recipe["branches"]) != 1: raise HistoryError("history_tables: the recipe must have exactly one branch")
    al = recipe_info(recipe)[recipe["branches"][0]["id"]]["aliases"]
    cols = {t["name"]: {c["name"].lower() for c in t["columns"]} for t in pkg.source.tables}
    key, order, tie = (_resolve(cfg[k], al, cols) for k in ("key", "order", "tiebreak"))
    out = dict(recipe); out["group_by"] = [key]; out["history"] = {"key": key, "order": order, "tiebreak": tie, "unwrapped": list(pk_columns)}
    return out
