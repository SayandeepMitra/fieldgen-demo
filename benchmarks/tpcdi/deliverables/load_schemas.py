import duckdb, re

con = duckdb.connect('tpcdi.duckdb')

for label, path in [('target (T)', 'tpcdi_target_schema.sql'), ('source (S)', 'tpcdi_source_schema.sql')]:
    sql = open(path).read()
    sql = re.sub(r'^\s*--.*', '', sql, flags=re.M)  # remove comment lines
    for statement in sql.split(';'):
        statement = statement.strip()
        if statement:
            con.execute(statement)
    print(f'loaded {label} from {path}')

count = con.execute("SELECT count(*) FROM information_schema.tables").fetchone()[0]
print('tables created (total, all schemas):', count)

for schema in ['main', 'Source']:
    n = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = ?", [schema]
    ).fetchone()[0]
    print(f'  schema {schema}: {n} tables')

print()
print('main (T) tables:')
for row in con.execute(
    "SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY table_name"
).fetchall():
    print(' -', row[0])

print()
print('Source (S) tables:')
for row in con.execute(
    "SELECT table_name FROM information_schema.tables WHERE table_schema='Source' ORDER BY table_name"
).fetchall():
    print(' -', row[0])
