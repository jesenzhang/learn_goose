# Current Task
{{ task_objective }}

{% if context_files %}
# Relevant Files
The following files are relevant to the task:
{% for file in context_files %}
- `{{ file }}`
{% endfor %}
{% endif %}

# Requirement
Please analyze the above information and provide a solution.