{# jinja2. Variables: task (field task). #}
## Target field
Table: {{ task.target.table }}   Column: {{ task.target.column }}   Type: {{ task.target.type }}   Nullable: {{ "yes" if task.target.nullable else "no" }}
{% if task.target.description %}Description: {{ task.target.description }}
{% endif %}{% if task.target.constraints %}Constraints: {{ task.target.constraints | join("; ") }}
{% endif %}{% if task.target.value_hints %}Value hints: {{ task.target.value_hints | tojson }}
{% endif %}Table keys: PK {{ task.target.table_keys.pk | join(", ") }}; business ids {{ task.target.table_keys.business_ids | join(", ") or "none" }}
{% if task.dump %}{{ task.dump.target }}{% endif %}
## Recipe (fixed)
Grain: {{ task.recipe.grain }}
Rows are combined by: {{ task.recipe.combine }}{% if task.recipe.group_by %}; grouped by: {{ task.recipe.group_by | join(", ") }}{% endif %}

{% set gk = task.recipe.get('keys') %}{% if gk %}Generated keys (assigned by the recipe over the combined rows): {% for k in gk %}{{ k.column }} ordered by {{ k.order_by | join(", ") }}; {% endfor %}
{% endif %}{% for b in task.recipe.branches %}Branch {{ b.id }}: {{ b.from }}
  aliases: {{ task.aliases[b.id] | tojson }}
{% endfor %}
## Matched source columns for this field
{% for m in task.matched %}- {{ m.relation }}.{{ m.column }}{% if m.aliases %} (as {{ m.aliases | tojson }}){% endif %}
{% if task.dump %}{{ task.dump.sources.get(m.relation ~ "." ~ m.column, "") }}{% endif %}
{% else %}none found by the matcher
{% endfor %}{% if task.dump and task.dump.links %}
Links between the matched relations:
{{ task.dump.links }}{% endif %}
## Source tables used by the recipe
{% for name, r in task.relations.items() %}### {{ name }}
PK: {{ r.pk | join(", ") or "none" }}
{% for cname, c in r.columns.items() %}- {{ cname }} ({{ c.type }}){% if c.description %}: {{ c.description | truncate(160) }}{% endif %}{% if c.origin %} [derives from: {{ c.origin | join(", ") }}]{% endif %}{% if c.profile %} [distinct {{ c.profile.distinct }}, null rate {{ c.profile.null_rate }}, e.g. {{ c.profile.top | tojson }}{% if c.profile.min is defined %}, range {{ c.profile.min }}..{{ c.profile.max }}{% endif %}]{% endif %}

{% endfor %}
{% endfor %}Return the JSON object for task_id "{{ task.task_id }}".
