"""Step 1 (recipe) with an error retry (generic; generator side). Reuses parse_recipe, task_con and the SQL shape of src/generate_e1.py.
After each answer every branch is run on the package data (read-only, 120 s timeout). A DuckDB error gets one follow-up that quotes the
error and nothing else; at most `max_retries` follow-ups. Without the retry flag the recipe call is made once."""
import jsonschema, threading
from fieldgen.formula_run import task_con
from fieldgen.json_extract import extract_json
from fieldgen.parse import parse_recipe, RECIPE_SCHEMA

FOLLOW_UP = "Your recipe could not be run on the data. DuckDB reported: {err}. Return the corrected JSON object with the same keys."
TIMEOUT_S = 120

def branch_sql(recipe, b):
    return f"SELECT 1 {b['from']}" + (f" GROUP BY {', '.join(recipe['group_by'])}" if recipe.get("group_by") else "")

def run_branches(con, recipe, timeout_s=TIMEOUT_S):
    """(True, None) or (False, error text). Each branch runs in a cursor that is interrupted after `timeout_s`."""
    for b in recipe["branches"]:
        cur = con.cursor(); timer = threading.Timer(timeout_s, cur.interrupt); timer.start()
        try: cur.execute(f"select count(*) from ({branch_sql(recipe, b)})").fetchall()
        except Exception as e: return False, f"{b['id']}: {str(e).strip()[:600]}"
        finally: timer.cancel()
    return True, None

def check(text, task, con, timeout_s):
    """Parse, then run. An answer that fits the schema is run even when parse_recipe rejects it (unknown alias, unknown table),
    so the database error text is what the model sees."""
    recipe, errs = parse_recipe(text, task)
    obj = recipe
    if obj is None:
        o = extract_json(text)
        if o is not None and not list(jsonschema.Draft7Validator(RECIPE_SCHEMA).iter_errors(o)) and o.get("branches"): obj = o
    if obj is None: return {"recipe": None, "errors": errs, "runs": None, "db_error": None}
    ok, err = run_branches(con, obj, timeout_s)
    return {"recipe": recipe, "errors": errs + ([] if ok else [f"recipe does not run: {err}"]), "runs": ok, "db_error": err}
