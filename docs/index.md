# AgentOps Dashboard — Docs

This folder contains the product requirements for **AgentOps Dashboard** — a Jira-inspired web app that lets developers
submit a GitHub issue and watch a coordinated team of AI agents (Investigator, Codebase Searcher, Web Searcher, Critic,
Writer) triage it in real time, with full human-in-the-loop control (pause, redirect, kill, and answer agent questions
mid-run), built on the full LangChain ecosystem: LCEL agent chains served via LangServe, orchestrated by a LangGraph
supervisor, prototyped in LangFlow, and instrumented end-to-end with LangSmith.

<!-- Auto-generated from mkdocs.yml nav — edit that file, not this section. -->

{% for entry in config.nav %}
{% for section, value in entry.items() %}
{% if value is not string %}
## {{ section }}

{% for item in value %}{% for label, path in item.items() %}- [{{ label }}]({{ path }})
{% endfor %}{% endfor %}
{% endif %}
{% endfor %}
{% endfor %}
