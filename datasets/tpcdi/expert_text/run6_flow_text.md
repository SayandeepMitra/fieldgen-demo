1. Read each table's documented rules first. If the documentation says which source records belong to the table, apply it as a filter in the recipe.
2. History sources: some source tables hold several records per business key (versions or events with a timestamp). The target keeps one row per business key: its current state. Event data may be split across several tables linked to the event record; join them to the event first, so every field carries the event's timestamp. An empty field means "not changed in this event", not "cleared". Order the records by their timestamp; each field takes the latest non-empty value up to the last record (fields not supplied by a later record keep the earlier value). Choose each value by record order (timestamp), not by the value itself: MIN, MAX or ANY_VALUE of a field do not give its latest value.
3. Event or action types are not target values. Use them only as the documentation says.
4. If the documentation says a target column holds a name or description, look it up through the linked lookup table; do not copy the code.
5. If the documentation gives a list of valid values, treat values outside the list as the documentation says.
6. If the documentation describes how to build a value, build it exactly as described.
7. In a grouped recipe, every column must come from an aggregate or from the selected latest record.
