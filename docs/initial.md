# docs/

This folder contains the product requirements for **AgentOps Dashboard** — a Jira-inspired web app that lets developers
submit a GitHub issue and watch a coordinated team of AI agents (Investigator, Codebase Searcher, Web Searcher, Critic,
Writer) triage it in real time, with full human-in-the-loop control (pause, redirect, kill, and answer agent questions
mid-run), built on the full LangChain ecosystem: LCEL agent chains served via LangServe, orchestrated by a LangGraph
supervisor, prototyped in LangFlow, and instrumented end-to-end with LangSmith.

## PRD Index

| File                                                                         | Covers                                                                                                                             |
|------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------|
| [PRD-001-master-overview.md](prd/PRD-001-master-overview.md)                 | Product vision, architecture, personas, feature priority, roadmap, and risks                                                       |
| [PRD-002-frontend-ux.md](prd/PRD-002-frontend-ux.md)                         | Three-zone React UI (job queue, live workspace, output panel), SSE streaming, component tree, and GitHub write-back flow           |
| [PRD-003-langgraph-orchestration.md](prd/PRD-003-langgraph-orchestration.md) | LangGraph graph structure, shared state schema, supervisor routing, human-in-the-loop `interrupt()`, pause/kill, and checkpointing |
| [PRD-004-agent-layer.md](prd/PRD-004-agent-layer.md)                         | Per-agent LCEL chain specs, LangServe microservice setup, LangFlow prototyping workflow, and codebase vector index                 |
| [PRD-005-langsmith-observability.md](prd/PRD-005-langsmith-observability.md) | Trace hierarchy, eval framework, golden dataset, automated CI eval pipeline, cost/latency monitoring, and alerting                 |
