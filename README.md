# AgentOps Dashboard

Jira-like dashboard with multiple agents and whole LangX (LangChain, ..) stack. 

> [!NOTE]
> Precise description is to be written later. 
> Initial idea is to write PRDs with project description and explanations what-where-how,
> then let Claude implement it. 
> 
> Target: check what works and what doesn't. 
>
> Docs: https://hardmax71.github.io/agent-ops-dashboard/

What works:
1. Combination of LLM writing PRDs and another 2-3 reviews checking inconsistencies: >2/3 issues are valid.

What doesn't:
1. Models do not enforce any standard by default: globals, locals, DI and what not else can coexist simultenously. 