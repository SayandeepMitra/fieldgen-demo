"""
Data profiling for source columns, computed fresh from the loaded Source.* tables in
tpcdi_populated.duckdb. This is the "data profiling" input described in project_plan.md Sec 5.4
-- it gets handed to the LLM alongside sample rows, so it can infer format/type quirks (like the
literal 'true'/'false' text flags and YYYYMMDD dates we found the hard way) up front.
"""
import duckdb

DB_PATH = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))), "deliverables/tpcdi_populated.duckdb")


def profile_column(con, table, column, sample_k=5, topk=5):
    """Profile one column of one Source.* table. Returns a dict, no LLM calls."""
    total = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    nulls = con.execute(f"SELECT count(*) FROM {table} WHERE {column} IS NULL OR {column} = ''").fetchone()[0]
    distinct = con.execute(f"SELECT count(DISTINCT {column}) FROM {table}").fetchone()[0]

    profile = {
        "table": table,
        "column": column,
        "row_count": total,
        "null_or_empty_pct": round(100 * nulls / total, 2) if total else None,
        "distinct_count": distinct,
        "distinct_pct": round(100 * distinct / total, 2) if total else None,
    }

    # numeric / date range, if castable
    try:
        lo, hi = con.execute(
            f"SELECT min(TRY_CAST({column} AS DOUBLE)), max(TRY_CAST({column} AS DOUBLE)) FROM {table}"
        ).fetchone()
        if lo is not None:
            profile["min_numeric"] = lo
            profile["max_numeric"] = hi
    except Exception:
        pass

    # string length stats (useful for spotting fixed-width padding, e.g. 'YYYYMMDD' = always 8)
    lens = con.execute(
        f"SELECT min(length(CAST({column} AS VARCHAR))), max(length(CAST({column} AS VARCHAR))) FROM {table} WHERE {column} IS NOT NULL"
    ).fetchone()
    profile["min_length"] = lens[0]
    profile["max_length"] = lens[1]

    # top-k most frequent values (good for low-cardinality / categorical columns)
    top = con.execute(
        f"SELECT CAST({column} AS VARCHAR) AS v, count(*) AS n FROM {table} "
        f"WHERE {column} IS NOT NULL GROUP BY v ORDER BY n DESC, v ASC LIMIT {topk}"
    ).fetchall()
    profile["top_values"] = [{"value": v, "count": n} for v, n in top]

    # a few arbitrary sample distinct values (good for spotting format patterns on
    # high-cardinality columns where top-k would just be mostly-unique noise)
    samples = con.execute(
        f"SELECT DISTINCT CAST({column} AS VARCHAR) FROM {table} WHERE {column} IS NOT NULL ORDER BY 1 LIMIT {sample_k}"
    ).fetchall()
    profile["sample_distinct_values"] = [s[0] for s in samples]

    return profile


def format_profile_for_prompt(profile):
    """Render a profile dict as compact text for an LLM prompt."""
    lines = [f"Profile of {profile['table']}.{profile['column']} ({profile['row_count']:,} rows):"]
    lines.append(f"  - null/empty: {profile['null_or_empty_pct']}%")
    lines.append(f"  - distinct values: {profile['distinct_count']:,} ({profile['distinct_pct']}% of rows)")
    lines.append(f"  - string length: min={profile['min_length']}, max={profile['min_length']}" if profile['min_length'] == profile['max_length']
                 else f"  - string length: min={profile['min_length']}, max={profile['max_length']}")
    if "min_numeric" in profile:
        lines.append(f"  - numeric range: {profile['min_numeric']} to {profile['max_numeric']}")
    if profile["top_values"]:
        tv = ", ".join(f"{t['value']!r}×{t['count']}" for t in profile["top_values"])
        lines.append(f"  - top values: {tv}")
    if profile["sample_distinct_values"]:
        sv = ", ".join(repr(v) for v in profile["sample_distinct_values"])
        lines.append(f"  - sample distinct values: {sv}")
    return "\n".join(lines)


if __name__ == "__main__":
    con = duckdb.connect(DB_PATH, read_only=True)

    # Worked examples: the exact two columns whose real-world quirks we only discovered by
    # debugging failed CAST/NOT-NULL errors during Phase B. Profiling should surface both up front.
    examples = [
        ("Source.Date", "HolidayFlag"),
        ("Source.FinwireCMP", "FoundingDate"),
        ("Source.CustomerXML", "C_GNDR"),
    ]
    for table, col in examples:
        p = profile_column(con, table, col)
        print(format_profile_for_prompt(p))
        print()
