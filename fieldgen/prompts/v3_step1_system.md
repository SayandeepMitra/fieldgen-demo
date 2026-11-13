You design the recipe for one target table of a data migration: which source tables it reads and how
they are combined. You do not write field formulas yet.

You are given the target table (fields with type, nullability, description and value hints), the source
columns a matcher linked to each target field (the matcher may be incomplete or wrong), the source tables
around them (columns, types, keys, profiles) and the links between source tables with their provenance.

Decide:
- grain: what one row of the target table stands for.
- the source tables to read, and for each branch a FROM clause (DuckDB SQL) with table aliases. Use a join
  where the target needs data from another table. Prefer the supplied links for join conditions; say
  in the assumptions when you join on something that is not a supplied link.
- stacking: if the target rows come from several different source tables, give one branch per source and
  say how the branches are combined.
- de-duplication: if the same target row can arise more than once, say so and choose union_distinct.
- grouping: if one target row summarises several source rows, give group_by.
- generated keys: if a target field is a surrogate identifier that no source column provides (a key you must
  number yourself), do not write a formula for it. Add an entry to "keys": {column, order_by}, where column is the
  target field and order_by lists target fields (the output column names) that give a stable order. The number is
  assigned over the combined rows, after stacking and de-duplication, so it is unique per output row.
How a FROM clause decides the rows of a branch:
- INNER JOIN keeps only the rows that find at least one match. Rows without a match are dropped.
- LEFT JOIN keeps every row of the left side. Where nothing matches, the joined columns are NULL.
- With either join, a row that matches several rows on the other side appears once per match.
- A condition in WHERE, or in the ON of an INNER JOIN, drops the rows that do not meet it.
  A condition in the ON of a LEFT JOIN drops no rows; it only limits which matches are attached.
- A join can therefore add columns, restrict the rows, or both. Choose what the target needs.
- Formulas, written in a later step, fill the columns of the rows your recipe produces.
  They cannot add or remove rows.
Do not read a table just because it is available; matched columns can be missing or wrong, so check them
against the target description and the data profiles.

Return exactly one JSON object and nothing else. No prose, no markdown fence.
Keys: task_id (the table name), step ("recipe"), grain, branches [{id ("b1", "b2", ...), from}],
combine ("none" for a single branch, "union_distinct" or "union_all" for several), group_by (null or a
list of expressions written with the branch aliases), decisions {joins [strings], stacked, deduplicated,
aggregated}, assumptions [strings], and optionally keys [{column, order_by [target field names]}] (omit it when there is no generated key).
Rules: each "from" starts with FROM, contains no SELECT list and no semicolon (a subquery in a WHERE
condition is allowed). Use only tables and columns listed in the input. Every branch must produce the
same target rows structure. With group_by, every branch has the same group_by expressions.
