{# jinja2. Variables: task (Mode B task with task.e1 from src/step1_view_v3.py). Same section order as e1_step1_user.md plus Domain knowledge. #}
## Target table: {{ task.target_table.name }}
{{ task.e1.table_card }}
Fields to fill (those with a matched source column are described below):
{% for f in task.target_table.fields %}{% if f.column in task.fields %}- {{ f.column }} ({{ f.type }}, {{ "nullable" if f.nullable else "not null" }})
{% endif %}{% endfor %}
## Field cards (fields that have a matched source column)
{{ task.e1.field_cards }}
{% if task.e1.domain_knowledge %}
## Domain knowledge
{{ task.e1.domain_knowledge }}
{% endif %}
{% if history %}## Tool instructions
{{ history }}
{% endif %}## Matched source columns (from a matcher; may be incomplete or noisy)
{% for m in task.matched_sources %}- {{ m.field }} <- {{ m.relation }}.{{ m.column }}
{% else %}none
{% endfor %}
## Cards of the matched source columns
{{ task.e1.matched_cards }}
## Source tables
### matched tables
{% for r in task.e1.matched_relations %}{{ task.e1.relation_text[r] }}
{% endfor %}{% if task.e1.connected_relations %}### connected tables (not matched)
{% for r in task.e1.connected_relations %}{{ task.e1.relation_text[r] }}
{% endfor %}{% endif %}{% if task.e1.bridges %}### bridge tables (they point into two or more of the tables above)
{% for r in task.e1.bridges %}{{ task.e1.relation_text[r] }}
{% endfor %}{% endif %}
## Links between source tables
{{ task.e1.links or "none" }}
{% if task.source_graph.children %}
## Tables that point to the tables above (not shown in detail)
{% for c in task.source_graph.children %}- {{ c.table }} -> {{ c.points_to }} via {{ c.via }} ({{ c.cardinality }})
{% endfor %}{% endif %}
Return the recipe JSON for task_id "{{ task.task_id }}".
