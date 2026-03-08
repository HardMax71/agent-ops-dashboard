---
id: roadmap-v2
title: Roadmap v2 (General)
status: PLANNED
domain: planning
depends_on: [PRD-001, roadmap-v1]
---

# Roadmap v2 — High-Level Backlog

| Field   | Value                                                        |
|---------|--------------------------------------------------------------|
| Version | v2.0                                                         |
| Status  | PLANNED (not week-scheduled)                                 |
| Date    | March 2026                                                   |
| Parent  | [PRD-001 Master Overview](../prd/PRD-001-master-overview.md) |

This document captures the themes and features explicitly deferred from v1.0 plus natural extension areas
identified during v1 design. v2 items are not week-scheduled; they will be prioritized after v1.0 ships
and user feedback is collected.

---

## Theme 1 — Multi-Tracker Support

**v1 scope:** GitHub issues only.

**v2 extension:** Support additional issue trackers as first-class input sources.

- Jira Cloud: OAuth 2.0 integration, issue fetch via Jira REST API v3, write-back via `POST /issue/{key}/comment`
- Linear: GraphQL API integration, status sync, team/project scoping
- GitLab: Issues API, MR linking, self-hosted GitLab instance support
- Generic webhook ingest: any tracker that can POST a structured payload gets routed through the agent graph

**Key design decisions needed:**

- Abstraction layer (`IssueSource` interface) so agents receive a normalized `IssueContext` regardless of origin
- Auth credential management per workspace (each user may have Jira + GitHub credentials simultaneously)
- Write-back adapter per tracker (comment format differs)

---

## Theme 2 — Non-Software Domains

**v1 scope:** Software bug triage only.

**v2 extension:** Generalize the agent graph to support other structured investigation workflows.

- **Legal document review:** Investigator reads contract clause, Critic identifies risk, Writer drafts summary
- **Security incident triage:** Alert ingested from SIEM, agents research CVEs, recommend remediation
- **Customer support escalation:** Ticket from Zendesk/Intercom, agents search knowledge base, draft reply
- **Data quality investigation:** Anomaly detected in pipeline, agents trace data lineage, identify root cause

**Key design decisions needed:**

- Domain-specific agent prompts and output schemas per domain (plugin system — see Theme 7)
- Domain-specific tool sets (legal DB search, CVE DB, knowledge base RAG)
- UI output panel templates per domain

---

## Theme 3 — Self-Hosted LLM Support

**v1 scope:** OpenAI and Anthropic cloud APIs only.

**v2 extension:** Allow users to run agents against locally-hosted or self-hosted models.

- **Ollama:** Local model runner; expose as OpenAI-compatible endpoint for drop-in use
- **vLLM:** High-throughput inference server for enterprise self-hosted deployments
- **LM Studio:** Desktop app for Mac/Windows; compatible via local OpenAI API
- **Custom fine-tuned models:** Support `base_url` override per agent in config

**Key design decisions needed:**

- Per-agent model config (each agent may use a different model or backend)
- Latency and context-window constraints for smaller local models (adjust prompts accordingly)
- Fallback chain: if local model times out, optionally fall back to cloud API

---

## Theme 4 — Real-Time Multi-User Sessions

**v1 scope:** Single-user session; one job owner.

**v2 extension:** Multiple users can observe and interact with the same job simultaneously.

- Shared job view: multiple users see the same live workspace in real time
- Collaborative question answering: any permitted user can answer an agent's question
- Role-based permissions: `owner` (full control), `reviewer` (can answer questions, cannot kill), `observer` (read-only)
- Presence indicators: show which users are currently viewing a job (WebSocket-based)
- Conflict resolution: if two users submit an answer simultaneously, use first-write-wins with notification to the other

**Key design decisions needed:**

- WebSocket upgrade for presence and collaborative state (vs. SSE which is unidirectional)
- Session isolation: each job has an ACL; sharing requires explicit invite
- Audit log: every user action on a shared job is recorded

---

## Theme 5 — Mobile Interface

**v1 scope:** Desktop web app only (1280px+ viewport).

**v2 extension:** Native-quality mobile experience for monitoring and responding to agent questions on the go.

- Responsive layout: job queue as bottom sheet, workspace as full-screen view
- Push notifications: notify job owner when an agent asks a question or a job completes
- Answer-on-mobile: question card is thumb-friendly with large input area and confirmation step
- Mobile-first output panel: collapsible sections for each output field
- PWA packaging: installable from browser on iOS and Android

**Key design decisions needed:**

- Native app vs. PWA (PWA preferred for v2 to avoid App Store release process)
- Push notification delivery: Firebase Cloud Messaging or Apple Push Notifications
- Reduced streaming fidelity on mobile (batch chunks to reduce re-renders on slower connections)

---

## Theme 6 — Expanded Evaluation & A/B Prompt Framework

**v1 scope:** Single LangSmith eval dataset, manual evaluator script.

**v2 extension:** First-class evaluation and experimentation infrastructure for continuous agent improvement.

- **A/B prompt testing:** Define prompt variants per agent; route a % of jobs to each variant; compare LangSmith eval scores
- **Automated regression suite:** CI runs evals on every PR against the `bug_triage_v1` dataset; blocks merge if score drops > 5%
- **Human feedback loop:** Thumbs up/down on final output in UI; feedback stored as LangSmith annotation; auto-added to eval dataset
- **Cost/quality Pareto dashboard:** Plot each agent configuration on a cost vs. quality 2D chart; surface Pareto-optimal configs
- **Shadow mode:** Run new agent versions on live traffic without affecting the user-facing response; compare outputs asynchronously

**Key design decisions needed:**

- Prompt version registry (link prompt hash to eval result in LangSmith)
- Sampling strategy for A/B (per-user consistent assignment vs. per-job random)
- Feedback data governance (PII scrubbing before adding to eval dataset)

---

## Theme 7 — Plugin / Extension System for Custom Agents

**v1 scope:** 5 fixed agents (Investigator, Codebase Searcher, Web Searcher, Critic, Writer).

**v2 extension:** Allow teams to add custom agents and tools without modifying core code.

- **Agent plugin interface:** Define an `AgentPlugin` protocol (Python); any class implementing it registers as a new agent node
- **Tool plugin interface:** Define a `ToolPlugin` protocol; custom tools are injected into existing agents via config
- **Plugin registry:** UI panel to browse, enable/disable, and configure installed plugins
- **LangFlow import:** A LangFlow flow file can be registered as a plugin agent; no Python code required
- **Plugin marketplace (future):** Public registry of community agent plugins (similar to VS Code extensions)
- **Sandbox execution:** Plugins run in isolated subprocess or container to prevent host compromise

**Key design decisions needed:**

- Plugin discovery mechanism (file system scan vs. entry points vs. explicit config)
- Versioning and compatibility: plugin declares compatible core version range
- Security model for sandboxed plugins (what resources can a plugin access?)
- Plugin state access: read-only vs. read-write `AgentState`

---

## Deferred Non-Goals from v1 — Resolution in v2

The following items from the [v1 Non-Goals](../prd/PRD-001-1-goals-and-dod.md#non-goals-v10) are formally tracked here:

| v1 Non-Goal                                    | v2 Theme              |
|------------------------------------------------|-----------------------|
| Non-GitHub tracker support                     | Theme 1               |
| Non-software domains                           | Theme 2               |
| Self-hosted LLM support (Ollama etc.)          | Theme 3               |
| Real-time multi-user collaborative sessions    | Theme 4               |
| Mobile interface                               | Theme 5               |
| Fully autonomous operation (zero oversight)    | Theme 6 (eval-gated)  |
