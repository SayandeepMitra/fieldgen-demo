1. Read each table's documented rules first. If the documentation says which source records belong to the table, apply it as a filter in the recipe.
2. History sources: some source tables hold several records per business key, each with a timestamp. The target keeps one row per business key: its current state, which is the latest record (ordered by timestamp). Choose the record by its order, not by the size of its values.
3. Event or action types are not target values. Use them only as the documentation says.
4. If the documentation says a target column holds a name or description, look it up through the linked lookup table; do not copy the code.
5. If the documentation gives a list of valid values, treat values outside the list as the documentation says.
6. If the documentation describes how to build a value, build it exactly as described.
7. In a grouped recipe, every column must come from an aggregate or from the selected latest record.
