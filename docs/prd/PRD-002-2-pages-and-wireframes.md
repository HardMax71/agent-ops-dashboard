---
id: PRD-002-2
title: Pages, Routes & View States — Full Wireframes
status: DRAFT
domain: frontend
depends_on: [ PRD-002, PRD-002-1 ]
---

# PRD-002-2 — Pages, Routes & View States

| Field        | Value                                      |
|--------------|--------------------------------------------|
| Document ID  | PRD-002-2                                  |
| Version      | 1.0                                        |
| Status       | DRAFT                                      |
| Date         | March 2026                                 |
| Parent Doc   | [PRD-002](PRD-002-frontend-ux.md)          |

> **Part of:** [PRD-002-1 Design System](PRD-002-1-design-system.md) ·
> [PRD-002-3 Interactions & A11y](PRD-002-3-interactions-and-a11y.md)

---

## 1. Route Table

| Path          | Component           | Auth Required | Redirect Behavior                                  |
|---------------|---------------------|---------------|----------------------------------------------------|
| `/login`      | `LoginPage`         | No            | If authenticated → redirect to `/dashboard`        |
| `/`           | —                   | —             | Always redirect to `/dashboard`                    |
| `/dashboard`  | `DashboardPage`     | Yes           | If not authenticated → redirect to `/login`        |
| `/settings`   | `SettingsPage`      | Yes           | If not authenticated → redirect to `/login`        |
| `*`           | `NotFoundPage`      | No            | —                                                  |

---

## 2. Page: Login (`/login`)

### Wireframe

```
╔══════════════════════════════════════════════════════════════════════╗
║                                                                      ║
║                                                                      ║
║                                                                      ║
║                    ┌──────────────────────────────┐                 ║
║                    │                              │                 ║
║                    │        [AgentOps Logo]        │                 ║
║                    │          AgentOps            │                 ║
║                    │                              │                 ║
║                    │  Jira for AI agents.         │                 ║
║                    │  Supervise, steer, and trust │                 ║
║                    │  your multi-agent workflows. │                 ║
║                    │                              │                 ║
║                    │  ┌────────────────────────┐  │                 ║
║                    │  │  🐙  Continue with     │  │                 ║
║                    │  │       GitHub           │  │                 ║
║                    │  └────────────────────────┘  │                 ║
║                    │                              │                 ║
║                    └──────────────────────────────┘                 ║
║                                                                      ║
║              AgentOps Dashboard · v1.0 · Open Source                ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
```

**Exact copy:**

- Tagline: `"Jira for AI agents. Supervise, steer, and trust your multi-agent workflows."`
- Button label: `"Continue with GitHub"`

### States

**Idle (default):** As shown above.

**Loading:**

```
║  ┌────────────────────────┐  ║
║  │  ⟳  Connecting to      │  ║
║  │      GitHub...         │  ║
║  └────────────────────────┘  ║
```

Button disabled, spinner replaces GitHub icon, text changes to `"Connecting to GitHub..."`.

**Error — OAuth denied:**

```
║  ┌──────────────────────────────┐  ║
║  │  ⚠  Access denied by GitHub  │  ║  ← red inline message
║  └──────────────────────────────┘  ║
║  ┌────────────────────────┐        ║
║  │  🐙  Continue with     │        ║
║  │       GitHub           │        ║
║  └────────────────────────┘        ║
```

Error message: `"Access denied. Please authorise the AgentOps app on GitHub to continue."`

**Error — server error:**

Error message: `"Something went wrong. Please try again."` + retry button below the message.

### Auth Flow

```
[Click button] → GET /auth/login → GitHub OAuth consent → GET /auth/callback
→ Backend sets httpOnly cookie → redirect to /dashboard
```

---

## 3. Page: Dashboard (`/dashboard`)

### 3a. Full Layout Skeleton

```
┌─────────────────────────────────────────────────────────────────────────────┐  ← 48px topbar
│  AgentOps          ● Connected                    [⧉]  [@user ▾]           │
├─────────────────┬───────────────────────────────────────┬───────────────────┤
│  Zone 1         │  Zone 2                               │  Zone 3           │
│  280px fixed    │  flex (fills remaining ≈ 640px+)      │  320px fixed      │
│                 │                                       │                   │
│  Job Queue      │  Live Workspace                       │  Output Panel     │
│  Sidebar        │                                       │                   │
│                 │                                       │                   │
│                 │                                       │                   │
│                 │                                       │                   │
│                 │                                       │                   │
│                 │                                       │                   │
│                 │                                       │                   │
│                 │                                       │                   │
└─────────────────┴───────────────────────────────────────┴───────────────────┘
  ↑ 280px            ↑ flex                                  ↑ 320px
```

Full app height = `100vh - 48px` (topbar). All three zones scroll independently.

---

### 3b. Topbar (always rendered)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  [◈] AgentOps        ● Connected              [⧉ LangFlow]  [@user ▾]      │
└─────────────────────────────────────────────────────────────────────────────┘
```

| Section | Contents                                                               |
|---------|------------------------------------------------------------------------|
| Left    | App logo icon + `"AgentOps"` wordmark                                  |
| Center  | Connection status pill: `"● Connected"` (green) or `"○ Disconnected"` (gray) |
| Right   | LangFlow icon link (external) + user avatar + `"@login ▾"` dropdown chevron |

**Avatar dropdown:**

```
┌─────────────────┐
│  Settings       │
├─────────────────┤
│  Log out        │
└─────────────────┘
```

Separator between "Settings" and "Log out". Clicking outside or pressing Escape closes it.

---

### 3c. Zone 1 — Job Queue Sidebar

```
┌─────────────────────────────────┐
│  [Status ▾] [Repo ▾]  [↕]  [+ New Job] │
├─────────────────────────────────┤
│ ┌─────────────────────────────┐ │
│ │ ● RUNNING          #1042   │ │  ← selected (left accent border)
│ │ Auth token expiry causes    │ │
│ │ 500 on /api/me              │ │
│ │ github.com/org/repo         │ │
│ │ 4 min ago  3 agents active  │ │
│ └─────────────────────────────┘ │
│ ┌─────────────────────────────┐ │
│ │ ● WAITING          #1098   │ │
│ │ Null pointer in payment     │ │
│ │ checkout flow               │ │
│ │ github.com/org/payments-svc │ │
│ │ 9 min ago  Needs your input │ │
│ └─────────────────────────────┘ │
│ ┌─────────────────────────────┐ │
│ │ ● QUEUED           #1103   │ │
│ │ Redis connection pool       │ │
│ │ exhausted at peak load      │ │
│ │ github.com/org/infra        │ │
│ │ just now                    │ │
│ └─────────────────────────────┘ │
│ ┌─────────────────────────────┐ │
│ │ ● DONE             #1031   │ │
│ │ Login page flickers on      │ │
│ │ Safari 16                   │ │
│ │ github.com/org/frontend     │ │
│ │ Completed 22 min ago        │ │
│ └─────────────────────────────┘ │
└─────────────────────────────────┘
```

**Filter row:** Status dropdown, Repo dropdown, sort toggle (newest/oldest). All three are compact controls in a single row above the list.

**Empty state** (no jobs):

```
┌─────────────────────────────────┐
│  [Status ▾] [Repo ▾]  [↕]  [+ New Job] │
├─────────────────────────────────┤
│                                 │
│                                 │
│      No jobs yet.               │
│      Submit your first issue →  │
│                                 │
│                                 │
└─────────────────────────────────┘
```

Faint muted text, centered vertically in the available list area.

---

### 3d. Zone 2 — Live Workspace

#### State 1 — Empty (no job selected)

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│                                                     │
│                                                     │
│                   [◈ icon, faint]                   │
│                                                     │
│       Select a job from the queue,                  │
│       or submit a new one.                          │
│                                                     │
│              [+ New Job]                            │
│                                                     │
│                                                     │
└─────────────────────────────────────────────────────┘
```

Icon and text in `--color-text-muted`. "+ New Job" is a ghost button, centered.

---

#### State 2 — Running

```
┌─────────────────────────────────────────────────────┐
│  #1042  Auth token expiry causes 500 on /api/me     │  ← workspace header
│  github.com/org/repo · @user · 2 hours ago          │
│  ● RUNNING        [↪ Redirect]  [⏸ Pause]  [✕ Kill] │
├─────────────────────────────────────────────────────┤
│  ●────────●────────◌────────◌────────◌              │  ← execution timeline
│ START   inv✓   cs_search  human   writer             │
│          12s    (18s...)                             │
├─────────────────────────────────────────────────────┤
│ ┌───────────────────────────────────────────────┐   │
│ │ 🔍 INVESTIGATOR AGENT            ● DONE (12s) │   │
│ ├───────────────────────────────────────────────┤   │
│ │ Reading issue body...                         │   │
│ │ Identified error: HTTP 500 on auth endpoint   │   │
│ │ Hypothesis: JWT validation or middleware      │   │
│ │                                               │   │
│ │ → Passed to: Codebase Searcher                │   │
│ └───────────────────────────────────────────────┘   │
│                                                     │
│ ┌───────────────────────────────────────────────┐   │
│ │ 🔎 CODEBASE SEARCH AGENT         ● RUNNING    │   │
│ ├───────────────────────────────────────────────┤   │
│ │ Searching for JWT middleware...               │   │
│ │ 🔧 search_codebase — "JWT expiry check"...    │   │
│ │ Found: auth/middleware.py:142▌                │   │
│ └───────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

Control bar shows: `[↪ Redirect]` (ghost), `[⏸ Pause]` (secondary), `[✕ Kill]` (destructive).

---

#### State 3 — HITL / Waiting

```text
┌─────────────────────────────────────────────────────┐
│  #1042  Auth token expiry causes 500 on /api/me     │  ← workspace header
│  github.com/org/repo · @user · 2 hours ago          │
│  ● WAITING                    Awaiting your response… │
├─────────────────────────────────────────────────────┤
│  ●────────●────────◌────────◌────────◌              │  ← timeline: human_input = amber spinner
│ START   inv✓   cs_search⚠ human   writer             │
│                   amber↑                             │
├─────────────────────────────────────────────────────┤
│ ┌───────────────────────────────────────────────┐   │  ← amber border + glow
│ │ ⚠  SUPERVISOR NEEDS YOUR INPUT  ● WAITING     │   │
│ ├───────────────────────────────────────────────┤   │
│ │ The error appears in two code paths:          │   │
│ │                                               │   │
│ │ (A) auth/middleware.py — JWT validation       │   │
│ │ (B) db/session.py — DB connection pooling     │   │
│ │                                               │   │
│ │ Which should agents prioritize?               │   │
│ │                                               │   │
│ │ ┌───────────────────────────────────────────┐ │   │
│ │ │ Type your answer here...                  │ │   │
│ │ └───────────────────────────────────────────┘ │   │
│ │                              [Continue →]      │   │
│ └───────────────────────────────────────────────┘   │
│                                                     │
│ ┌───────────────────────────────────────────────┐   │  ← frozen, no cursor
│ │ 🔎 CODEBASE SEARCH AGENT         ● DONE (18s) │   │
│ ├───────────────────────────────────────────────┤   │
│ │ Found relevant files in auth/middleware.py    │   │
│ └───────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

- Control bar replaced by `"Awaiting your response…"` label (amber text).
- QuestionCard pinned above AgentCards.
- AgentCards below are frozen (no streaming cursor, no new tokens).
- Timeline `human_input` node shown as amber spinner.

---

#### State 4 — Pausing

```
┌─────────────────────────────────────────────────────┐
│  #1042  Auth token expiry causes 500 on /api/me     │
│  github.com/org/repo · @user · 2 hours ago          │
│  ● PAUSING    [↪ Redirect]  [⟳ Pausing…]  [✕ Kill] │  ← Pause replaced by spinner
├─────────────────────────────────────────────────────┤
│  ●────────●────────◌────────◌────────◌              │
├─────────────────────────────────────────────────────┤
│ ┌───────────────────────────────────────────────┐   │
│ │ 🔎 CODEBASE SEARCH AGENT         ● RUNNING    │   │  ← still streaming
│ ├───────────────────────────────────────────────┤   │
│ │ Searching for JWT middleware...               │   │
│ │ Found: auth/middleware.py▌                    │   │
│ └───────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

- Pause button replaced with `"⟳ Pausing…"` (disabled, spinner).
- Kill button remains active.
- Status badge shows `PAUSING` in static blue (no pulse).
- Agents continue streaming (pause has not taken effect yet).

---

#### State 5 — Done

```
┌─────────────────────────────────────────────────────┐
│  #1042  Auth token expiry causes 500 on /api/me     │
│  github.com/org/repo · @user · 2 hours ago          │
│  ● DONE                    Job complete · 4m 32s    │  ← control bar replaced
├─────────────────────────────────────────────────────┤
│  ●────────●────────●────────●────────●              │  ← fully green timeline
│ START   inv✓   cs_search✓  human✓  writer✓           │
├─────────────────────────────────────────────────────┤
│ ┌───────────────────────────────────────────────┐   │
│ │ 🔍 INVESTIGATOR AGENT            ● DONE (12s) │   │
│ └───────────────────────────────────────────────┘   │
│ ┌───────────────────────────────────────────────┐   │
│ │ 🔎 CODEBASE SEARCH AGENT         ● DONE (18s) │   │
│ └───────────────────────────────────────────────┘   │
│ ┌───────────────────────────────────────────────┐   │
│ │ ✍  WRITER AGENT                  ● DONE (31s) │   │
│ └───────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

- Control bar hidden; replaced by `"Job complete · {elapsed time}"` label.
- All AgentCards show ✓ DONE with elapsed time.
- Timeline fully green.
- Zone 3 fully populated.

---

### 3e. Zone 3 — Output Panel

#### State 1 — Accumulating (streaming)

```
┌───────────────────────────────────┐
│  OUTPUT PANEL                     │
├───────────────────────────────────┤
│  TRIAGE REPORT                    │
│  ░░░░░░░░░░░░░░░░░░░░░            │  ← SkeletonBlock
│  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░     │
│  ░░░░░░░░░░░░░░░░                 │
├───────────────────────────────────┤
│  GITHUB COMMENT                   │
│  ░░░░░░░░░░░░░░░░░░░░░            │  ← SkeletonBlock
│  ░░░░░░░░░                        │
├───────────────────────────────────┤
│  TICKET DRAFT                     │
│  ░░░░░░░░░░░░░░░░░░░░░            │  ← SkeletonBlock
├───────────────────────────────────┤
│  [Post Comment] [Create Issue]    │  ← all disabled
│  [Copy Report]  [View LangSmith]  │
└───────────────────────────────────┘
```

SkeletonBlock placeholders until first `output.token` arrives per section. Each section activates independently as its tokens stream in. Action buttons disabled until `job.done` SSE received.

---

#### State 2 — Done

```
┌───────────────────────────────────┐
│  TRIAGE REPORT                    │
│  ┌────────────────────────────┐   │
│  │ Severity:   🔴 HIGH        │   │
│  │ Category:   Auth / Tokens  │   │
│  │ Confidence: 87%            │   │
│  │                            │   │
│  │ Root Cause:                │   │
│  │   JWT expiry check in      │   │
│  │   auth/middleware.py:L142  │   │
│  │   does not account for     │   │
│  │   timezone offset.         │   │
│  │                            │   │
│  │ Relevant Files:            │   │
│  │   · auth/middleware.py     │   │
│  │   · tests/test_auth.py     │   │
│  │   · config/jwt_settings.py │   │
│  │                            │   │
│  │ Similar Past Issues:       │   │
│  │   · #891 — Fixed 2024-11   │   │
│  └────────────────────────────┘   │
├───────────────────────────────────┤
│  GITHUB COMMENT                   │
│  ┌────────────────────────────┐   │
│  │ ## AgentOps Triage #1042   │   │
│  │ **Severity:** High         │   │
│  │ **Root Cause:** JWT bug... │   │  ← editable textarea
│  │                            │   │
│  └────────────────────────────┘   │
│  [Preview]  1,247 chars           │
├───────────────────────────────────┤
│  TICKET DRAFT                     │
│  Title: [Bug] JWT expiry fails... │
│  Labels: [bug] [auth] [high-pri]  │
│  Assignee: @backend-team          │
│  Effort: M (2-4 hours)            │
├───────────────────────────────────┤
│  [Post Comment ↗]  [Create Issue] │
│  [Copy Report]  [View LangSmith↗] │
└───────────────────────────────────┘
```

**Action buttons:**

| Button              | Variant     |
|---------------------|-------------|
| Post Comment        | primary     |
| Create Issue        | secondary   |
| Copy Report         | ghost       |
| View in LangSmith   | ghost + external link icon |

---

#### State 3 — Write-back pending

```
├───────────────────────────────────┤
│  [⟳ Posting…]  [Create Issue]    │  ← all buttons disabled
│  [Copy Report]  [View LangSmith]  │
└───────────────────────────────────┘
```

"Post Comment" button shows spinner + `"Posting…"`. All other buttons disabled.

**After success:**

```
├───────────────────────────────────┤
│  [✓ Posted · View on GitHub →]    │  ← link replaces button
│  [Create Issue]                   │
│  [Copy Report]  [View LangSmith]  │
└───────────────────────────────────┘
```

---

## 4. Page: Settings (`/settings`)

Single-column centered layout, `max-width: 600px`.

```
┌─────────────────────────────────────────────────────────────────────┐
│  [topbar — same as dashboard]                                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│       Settings                                                      │
│                                                                     │
│  ┌──────────────────────────────────────────────┐                  │
│  │  GitHub Account                              │                  │
│  │                                              │                  │
│  │  [avatar]  @octocat                          │                  │
│  │            Connected since Jan 12 2026       │                  │
│  │                                              │                  │
│  │                   [Disconnect GitHub]        │                  │
│  └──────────────────────────────────────────────┘                  │
│                                                                     │
│  ┌──────────────────────────────────────────────┐                  │
│  │  Session                                     │                  │
│  │                                              │                  │
│  │  @octocat                                    │                  │
│  │                                              │                  │
│  │                             [Log out]        │                  │
│  └──────────────────────────────────────────────┘                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**After GitHub disconnect:**

```
│  ┌──────────────────────────────────────────────┐  │
│  │  GitHub Account                              │  │
│  │                                              │  │
│  │  [○ gray circle]  Not connected              │  │
│  │                                              │  │
│  │  ⚠ Write-back disabled until reconnected.   │  │
│  │                                              │  │
│  │                   [Connect GitHub]           │  │
│  └──────────────────────────────────────────────┘  │
```

- Avatar replaced with gray empty circle.
- "Disconnect GitHub" button replaced with "Connect GitHub" link (triggers OAuth flow).
- Inline warning shown in amber text.

---

## 5. Page: 404

```
╔══════════════════════════════════════════════════════════════════════╗
║                                                                      ║
║                                                                      ║
║                            404                                       ║  ← H1, mono, muted
║                                                                      ║
║                   This page doesn't exist.                          ║
║                                                                      ║
║                   ← Back to dashboard                               ║  ← link
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
```

`"404"` rendered in H1 mono-data style at `--color-text-muted`. "This page doesn't exist." in body style. Link navigates to `/dashboard`.
