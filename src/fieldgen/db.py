"""Generator-side connection over a package's source tables (in memory, TimeZone UTC). Reads only the package source part."""
import duckdb
from fieldgen.package import load_package

def package_connection(pkg_or_path, limit=None):
    """limit: keep only the first `limit` rows of every source table (execute.sample_rows)."""
    pkg = load_package(pkg_or_path) if isinstance(pkg_or_path, (str, bytes)) or hasattr(pkg_or_path, "__fspath__") else pkg_or_path
    con = duckdb.connect(":memory:"); con.execute("SET TimeZone='UTC'")
    for t in pkg.source.tables:
        cols = ", ".join(f'"{c["name"]}" {c["type"]}' for c in t["columns"])
        con.execute(f'CREATE TABLE "{t["name"]}" ({cols})')
        con.execute(f'COPY "{t["name"]}" FROM \'{pkg.source.data_path(t["name"])}\' (HEADER true)')
        if limit: con.execute(f'CREATE TABLE "__s" AS SELECT * FROM "{t["name"]}" LIMIT {int(limit)}'); con.execute(f'DROP TABLE "{t["name"]}"'); con.execute(f'ALTER TABLE "__s" RENAME TO "{t["name"]}"')
    return con
