"""Shared helper with no gold access: which expressions does a final output stand for."""
def final_expressions(final):
    if not final: return None
    if final.get("status") == "answer": return final.get("expressions")
    if final.get("status") == "ambiguous":
        c = final.get("candidates") or []; d = final.get("default", 0)
        return c[d]["expressions"] if c and 0 <= d < len(c) else None
    return None
