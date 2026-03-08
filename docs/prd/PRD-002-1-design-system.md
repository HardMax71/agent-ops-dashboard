---
id: PRD-002-1
title: Design System & Shared Component Library
status: DRAFT
domain: frontend
depends_on: [ PRD-002 ]
---

# PRD-002-1 — Design System & Shared Component Library

| Field        | Value                                      |
|--------------|--------------------------------------------|
| Document ID  | PRD-002-1                                  |
| Version      | 1.0                                        |
| Status       | DRAFT                                      |
| Date         | March 2026                                 |
| Parent Doc   | [PRD-002](PRD-002-frontend-ux.md)          |

> **Part of:** [PRD-002-2 Pages & Wireframes](PRD-002-2-pages-and-wireframes.md) ·
> [PRD-002-3 Interactions & A11y](PRD-002-3-interactions-and-a11y.md)

---

## 1. Color Tokens

All colors are dark-mode only. The application ships dark-first with no light theme in v1.

### Background

| Token                     | Hex       | Usage                                              |
|---------------------------|-----------|----------------------------------------------------|
| `--color-bg-base`         | `#0d0f12` | Page / app root background                         |
| `--color-bg-surface`      | `#151820` | Cards, sidebars, panels                            |
| `--color-bg-elevated`     | `#1e2230` | Modal dialogs, dropdowns, tooltips                 |
| `--color-bg-hover`        | `#252a3a` | Interactive element hover state                    |

### Border

| Token                     | Hex       | Usage                                              |
|---------------------------|-----------|----------------------------------------------------|
| `--color-border-subtle`   | `#1f2435` | Dividers, card outlines (very low contrast)        |
| `--color-border-default`  | `#2d3348` | Standard component borders                         |
| `--color-border-focus`    | `#4f6ef7` | Keyboard focus ring                                |
| `--color-border-active`   | `#5b7cff` | Selected job card left accent border               |

### Status Colors

Each status has three variants: `dim` (background tint), `default` (badge/icon fill), `bright` (text/label).

| Status    | Variant   | Token                              | Hex       |
|-----------|-----------|------------------------------------|-----------|
| queued    | dim       | `--color-status-queued-dim`        | `#1a1d24` |
| queued    | default   | `--color-status-queued`            | `#6b7280` |
| queued    | bright    | `--color-status-queued-bright`     | `#9ca3af` |
| running   | dim       | `--color-status-running-dim`       | `#0e1a3a` |
| running   | default   | `--color-status-running`           | `#3b82f6` |
| running   | bright    | `--color-status-running-bright`    | `#60a5fa` |
| waiting   | dim       | `--color-status-waiting-dim`       | `#2a1a08` |
| waiting   | default   | `--color-status-waiting`           | `#f59e0b` |
| waiting   | bright    | `--color-status-waiting-bright`    | `#fbbf24` |
| done      | dim       | `--color-status-done-dim`          | `#0a2018` |
| done      | default   | `--color-status-done`              | `#22c55e` |
| done      | bright    | `--color-status-done-bright`       | `#4ade80` |
| failed    | dim       | `--color-status-failed-dim`        | `#2a0e0e` |
| failed    | default   | `--color-status-failed`            | `#ef4444` |
| failed    | bright    | `--color-status-failed-bright`     | `#f87171` |
| pausing   | dim       | `--color-status-pausing-dim`       | `#0e1a3a` |
| pausing   | default   | `--color-status-pausing`           | `#3b82f6` |
| pausing   | bright    | `--color-status-pausing-bright`    | `#60a5fa` |

### Text

| Token                     | Hex       | Usage                                              |
|---------------------------|-----------|----------------------------------------------------|
| `--color-text-primary`    | `#e8eaf0` | Headings, primary content                          |
| `--color-text-secondary`  | `#9aa0b8` | Subtitles, labels, field names                     |
| `--color-text-muted`      | `#5a6180` | Timestamps, captions, placeholders                 |
| `--color-text-inverse`    | `#0d0f12` | Text on bright/light backgrounds                   |

### Amber Accent Scale

Used for WAITING state, QuestionCard, and HITL highlights.

| Token                     | Hex       | Usage                                              |
|---------------------------|-----------|----------------------------------------------------|
| `--color-amber-50`        | `#fffbeb` | (reserved)                                         |
| `--color-amber-400`       | `#fbbf24` | QuestionCard border, WAITING badge text            |
| `--color-amber-500`       | `#f59e0b` | WAITING status dot, glow pulse base                |
| `--color-amber-900`       | `#2a1a08` | QuestionCard background tint                       |

---

## 2. Typography

### Font Stack

```css
--font-sans: 'Inter', ui-sans-serif, system-ui, sans-serif;
--font-mono: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
```

**Google Fonts imports:**

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

### Type Scale

| Element     | Font Family | Size px | Size rem | Weight | Line Height | Letter Spacing | Usage                          |
|-------------|-------------|---------|----------|--------|-------------|----------------|--------------------------------|
| H1          | Inter       | 24px    | 1.5rem   | 700    | 1.25        | -0.02em        | Page titles                    |
| H2          | Inter       | 18px    | 1.125rem | 600    | 1.35        | -0.01em        | Section headings               |
| H3          | Inter       | 14px    | 0.875rem | 600    | 1.4         | 0              | Card titles, subsections       |
| label       | Inter       | 11px    | 0.6875rem| 600    | 1.2         | +0.06em        | Status labels, form labels     |
| body        | Inter       | 14px    | 0.875rem | 400    | 1.6         | 0              | Default text, descriptions     |
| mono-data   | JetBrains   | 13px    | 0.8125rem| 400    | 1.5         | 0              | Agent output, code snippets    |
| caption     | Inter       | 12px    | 0.75rem  | 400    | 1.4         | 0              | Timestamps, metadata           |
| error       | Inter       | 12px    | 0.75rem  | 500    | 1.4         | 0              | Inline validation messages     |

---

## 3. Spacing & Layout

### Spacing Scale (4px base unit)

| Token       | px  | rem     | Common uses                                |
|-------------|-----|---------|--------------------------------------------|
| `space-1`   | 4px | 0.25rem | Icon gap, tight padding                    |
| `space-2`   | 8px | 0.5rem  | Input padding, badge padding               |
| `space-3`   | 12px| 0.75rem | Card inner padding (compact)               |
| `space-4`   | 16px| 1rem    | Card inner padding (standard)              |
| `space-6`   | 24px| 1.5rem  | Section gap, form field gap                |
| `space-8`   | 32px| 2rem    | Zone internal padding                      |
| `space-12`  | 48px| 3rem    | Large section separation                   |
| `space-16`  | 64px| 4rem    | Page-level padding                         |

### Zone Dimensions

| Zone                  | Width        | Notes                                    |
|-----------------------|--------------|------------------------------------------|
| Zone 1 — Job Sidebar  | 280px fixed  | Does not resize                          |
| Zone 3 — Output Panel | 320px fixed  | Does not resize                          |
| Zone 2 — Workspace    | flex (fills remaining) | Min ~640px at 1280px viewport   |
| Topbar                | 100% width   | Height: 48px fixed                       |

### Border Radius

| Use                      | Value  |
|--------------------------|--------|
| Card (JobCard, AgentCard)| 8px    |
| Button                   | 6px    |
| Badge / pill             | 9999px |
| Input / textarea         | 6px    |
| Modal                    | 12px   |
| Toast                    | 8px    |
| Skeleton block           | 4px    |

---

## 4. Animation Constants

| Name               | Duration  | Easing               | CSS / Tailwind class           | Usage                                          |
|--------------------|-----------|----------------------|--------------------------------|------------------------------------------------|
| skeleton-shimmer   | 1.5s      | linear               | `animate-shimmer`              | SkeletonBlock placeholder loading              |
| status-pulse       | 1.5s      | ease-in-out          | `animate-status-pulse`         | RUNNING and WAITING StatusBadge dot            |
| stream-cursor      | 0.7s      | step-start           | `animate-cursor-blink`         | AgentCard streaming text cursor                |
| card-fade-in       | 200ms     | ease-out             | `animate-card-in`              | Job card added to list                         |
| modal-backdrop     | 150ms     | ease-out             | `animate-backdrop-in`          | Modal background fade                          |
| agent-spawn        | 300ms     | ease-out             | `animate-agent-spawn`          | AgentCard appearing on agent.spawned SSE       |
| question-pulse     | 2s        | ease-in-out          | `animate-question-pulse`       | QuestionCard amber glow (infinite)             |
| modal-in           | 150ms     | ease-out             | `animate-modal-in`             | Modal card scale + opacity                     |
| toast-in           | 250ms     | spring               | `animate-toast-in`             | Toast notification entering                    |

---

## 5. Z-Index Stack

| Layer                | Z-Index | What lives there                               |
|----------------------|---------|------------------------------------------------|
| base                 | 0       | Page background                                |
| card                 | 1       | JobCard, AgentCard                             |
| sticky-header        | 10      | Topbar, zone headers                           |
| dropdown             | 100     | Filter dropdowns, avatar menu                  |
| modal-backdrop       | 200     | Modal overlay / blur backdrop                  |
| modal                | 210     | Modal card content                             |
| toast                | 300     | Toast notifications (above everything)         |
| tooltip              | 400     | Tooltips (top of stack)                        |

---

## 6. Component Specs

---

### StatusBadge

**Props:**

| Prop        | Type                                                                 | Required | Default |
|-------------|----------------------------------------------------------------------|----------|---------|
| `status`    | `'queued' \| 'running' \| 'pausing' \| 'waiting' \| 'done' \| 'failed'` | yes  | —       |
| `animated`  | `boolean`                                                            | no       | `false` |

**Rendering:** A colored dot (6px circle) followed by the status label in `label` typography (all caps).

| Status   | Dot color                    | Label text  | Animated pulse         |
|----------|------------------------------|-------------|------------------------|
| QUEUED   | `--color-status-queued`      | `QUEUED`    | No                     |
| RUNNING  | `--color-status-running`     | `RUNNING`   | Yes (when `animated`)  |
| PAUSING  | `--color-status-pausing`     | `PAUSING`   | No (static)            |
| WAITING  | `--color-status-waiting`     | `WAITING`   | Yes (when `animated`)  |
| DONE     | `--color-status-done`        | `DONE`      | No                     |
| FAILED   | `--color-status-failed`      | `FAILED`    | No                     |

Pulse animation applies to the dot only (`animate-status-pulse`), not the label text.

---

### JobCard

**Props:**

| Prop  | Type       | Required |
|-------|------------|----------|
| `job` | `JobState` | yes      |

**Wireframe — RUNNING state:**

```
┌─────────────────────────────────────────┐
│ ● RUNNING                    #1042      │
│ Auth token expiry causes 500 on /api/me │
│ github.com/org/repo                     │
│ Submitted 4 min ago    3 agents active  │
└─────────────────────────────────────────┘
```

**Wireframe — WAITING state:**

```
┌─────────────────────────────────────────┐
│ ● WAITING                    #1098      │
│ Null pointer in payment checkout flow   │
│ github.com/org/payments-svc             │
│ Submitted 9 min ago    Needs your input │
└─────────────────────────────────────────┘
```

**Wireframe — DONE state:**

```
┌─────────────────────────────────────────┐
│ ● DONE                       #1031      │
│ Login page flickers on Safari 16        │
│ github.com/org/frontend                 │
│ Completed 22 min ago                    │
└─────────────────────────────────────────┘
```

**Wireframe — QUEUED state:**

```
┌─────────────────────────────────────────┐
│ ● QUEUED                     #1103      │
│ Redis connection pool exhausted at peak │
│ github.com/org/infra                    │
│ Submitted just now                      │
└─────────────────────────────────────────┘
```

**States:**

| State    | Visual treatment                                                              |
|----------|-------------------------------------------------------------------------------|
| Default  | `--color-bg-surface` background, `--color-border-default` border              |
| Hover    | Background transitions to `--color-bg-hover`, border to `--color-border-default` |
| Active / selected | 3px left border in `--color-border-active`, background `--color-bg-hover` |

---

### AgentCard

**Props:**

| Prop    | Type             | Required |
|---------|------------------|----------|
| `agent` | `AgentCardState` | yes      |

**State: Spawning (skeleton)**

```
┌────────────────────────────────────────────────────────────────┐
│  ░░░░░░░░░░░░░░░░░░░░░░░  SPAWNING...                          │
├────────────────────────────────────────────────────────────────┤
│  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░                        │
│  ░░░░░░░░░░░░░░░░                                              │
└────────────────────────────────────────────────────────────────┘
```

Title and body are SkeletonBlock placeholders with shimmer animation.

**State: Running (streaming)**

```
┌────────────────────────────────────────────────────────────────┐
│  🔍  INVESTIGATOR AGENT                    ● RUNNING           │
├────────────────────────────────────────────────────────────────┤
│  Reading issue body...                                         │
│  Identified error: HTTP 500 on authenticated endpoint▌         │
└────────────────────────────────────────────────────────────────┘
```

`▌` is the blinking stream cursor (`animate-cursor-blink`).

**State: Tool Calling**

```
┌────────────────────────────────────────────────────────────────┐
│  🔍  INVESTIGATOR AGENT                    ● RUNNING           │
├────────────────────────────────────────────────────────────────┤
│  Reading issue body...                                         │
│  Identified error: HTTP 500 on authenticated endpoint          │
│                                                                │
│  🔧 search_codebase — "JWT middleware expiry"...               │
└────────────────────────────────────────────────────────────────┘
```

Tool indicator format while calling: `🔧 {tool_name} — {input_preview}...`

**State: Tool Done (result returned)**

```
┌────────────────────────────────────────────────────────────────┐
│  🔍  INVESTIGATOR AGENT                    ● RUNNING           │
├────────────────────────────────────────────────────────────────┤
│  Reading issue body...                                         │
│  Identified error: HTTP 500 on authenticated endpoint          │
│                                                                │
│  ✓ search_codebase                                             │
│  Hypothesis forming: likely JWT validation issue▌              │
└────────────────────────────────────────────────────────────────┘
```

Tool indicator format after result: `✓ {tool_name}`

**State: Done**

```
┌────────────────────────────────────────────────────────────────┐
│  🔍  INVESTIGATOR AGENT                    ● DONE  (12s)       │
├────────────────────────────────────────────────────────────────┤
│  Reading issue body...                                         │
│  Identified error: HTTP 500 on authenticated endpoint          │
│  Hypothesis: JWT validation or middleware issue                │
│                                                                │
│  → Passed to: Codebase Searcher, Web Search Agent              │
└────────────────────────────────────────────────────────────────┘
```

**State: Error**

```
┌────────────────────────────────────────────────────────────────┐  ← red border
│  🔍  INVESTIGATOR AGENT                    ● FAILED            │
├────────────────────────────────────────────────────────────────┤
│  Reading issue body...                                         │
│  Error: Tool call timed out after 30s                          │
│                                                                │
│  [View trace in LangSmith →]                                   │
└────────────────────────────────────────────────────────────────┘
```

---

### QuestionCard

**Props:**

| Prop       | Type                        | Required |
|------------|-----------------------------|----------|
| `question` | `string`                    | yes      |
| `onSubmit` | `(answer: string) => void`  | yes      |

Pinned above the AgentCardList. Amber border (`--color-status-waiting`) + amber background tint (`--color-amber-900`). Infinite amber glow pulse (`animate-question-pulse`).

**Wireframe:**

```
┌────────────────────────────────────────────────────────────────┐  ← amber border
│  ⚠  SUPERVISOR NEEDS YOUR INPUT               ● WAITING        │
├────────────────────────────────────────────────────────────────┤
│  The error appears in two separate code paths:                 │
│                                                                │
│  (A) auth/middleware.py — JWT token validation                 │
│  (B) db/session.py — Database connection pooling               │
│                                                                │
│  Which code path should agents prioritize for deep analysis?   │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Type your answer here...                                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                             [Continue →]        │
└────────────────────────────────────────────────────────────────┘
```

**Disabled state** (after user submits, awaiting `graph.resumed`):

- Textarea becomes `readonly`
- "Continue →" button shows spinner, text changes to "Sending…"
- Card opacity reduced to 0.7

---

### ExecutionTimeline

**Props:**

| Prop    | Type             | Required |
|---------|------------------|----------|
| `nodes` | `TimelineNode[]` | yes      |

Horizontal scrollable row. Each node is a circle + label + elapsed time, connected by a line.

**Node states:**

| State   | Circle appearance                  | Label style       |
|---------|------------------------------------|-------------------|
| pending | Empty circle, dashed border        | Muted text        |
| running | Spinner animation                  | Secondary text    |
| done    | Filled circle (green)              | Primary text      |
| error   | Red fill + white X icon            | Error text (red)  |
| waiting | Amber fill + spinning (HITL node)  | Amber text        |

**Wireframe:**

```
  ●────────●────────◌────────◌────────◌
START    inv✓   cs_search  human   writer
          12s    (18s...)
```

Connector lines are `--color-border-subtle` for pending segments, `--color-status-done` for completed.

---

### Button

**Variants:** `primary`, `secondary`, `destructive`, `ghost`
**Sizes:** `sm` (height 28px), `md` (height 36px)

| Variant      | Idle                                        | Hover                                   | Loading                     | Disabled                  |
|--------------|---------------------------------------------|-----------------------------------------|-----------------------------|---------------------------|
| primary      | Blue bg `#3b82f6`, white text               | Bg `#2563eb`                            | Spinner replaces label      | Opacity 0.4, no cursor    |
| secondary    | `--color-bg-elevated` bg, border, secondary text | Border brightens                  | Spinner replaces label      | Opacity 0.4, no cursor    |
| destructive  | Red bg `#ef4444`, white text                | Bg `#dc2626`                            | Spinner replaces label      | Opacity 0.4, no cursor    |
| ghost        | Transparent bg, secondary text              | Bg `--color-bg-hover`                   | Spinner replaces label      | Opacity 0.4, no cursor    |

Loading state: 14px spinner (white for primary/destructive, secondary color for others) centered in button. Original label hidden.

---

### Modal

Shared wrapper used by NewJobModal, RedirectModal, and KillModal.

**Props:**

| Prop      | Type            | Required |
|-----------|-----------------|----------|
| `title`   | `string`        | yes      |
| `children`| `ReactNode`     | yes      |
| `onClose` | `() => void`    | yes      |

**Behavior:** backdrop blur (`backdrop-filter: blur(4px)`) + `--color-bg-base` at 80% opacity. Card centered vertically and horizontally. Escape key calls `onClose`. Focus trapped inside modal while open (first focusable element receives focus on open; trigger element receives focus on close).

**Wireframe:**

```
╔════════════════════════════════════════════╗  ← blur backdrop
║                                            ║
║   ┌────────────────────────────────────┐   ║
║   │  Modal Title                   [✕] │   ║
║   ├────────────────────────────────────┤   ║
║   │                                    │   ║
║   │  {children}                        │   ║
║   │                                    │   ║
║   │          [Cancel]  [Primary Action] │   ║
║   └────────────────────────────────────┘   ║
║                                            ║
╚════════════════════════════════════════════╝
```

Entry animation: `animate-modal-in` (opacity + scale 0.96 → 1, 150ms ease-out).

---

### SkeletonBlock

**Props:**

| Prop      | Type               | Required | Default |
|-----------|--------------------|----------|---------|
| `width`   | `string \| number` | yes      | —       |
| `height`  | `string \| number` | yes      | —       |
| `rounded` | `boolean`          | no       | `false` |

Renders a `div` with `--color-bg-elevated` base and animated shimmer gradient (`animate-shimmer`). `rounded` applies `border-radius: 9999px` instead of the default 4px.

Used in: AgentCard spawning state (title + body placeholders), OutputPanel sections before first `output.token` arrives.

---

### Toast / Notification

**Props:**

| Prop      | Type                                    | Required | Default |
|-----------|-----------------------------------------|----------|---------|
| `message` | `string`                                | yes      | —       |
| `variant` | `'success' \| 'error' \| 'info'`        | yes      | —       |
| `action`  | `{ label: string; onClick: () => void }` | no      | —       |

Appears bottom-right of viewport. Stacks if multiple toasts are active (newest on top). Auto-dismisses after 4 seconds. Manual dismiss via `✕` button.

| Variant | Border-left color            | Icon  |
|---------|------------------------------|-------|
| success | `--color-status-done`        | ✓     |
| error   | `--color-status-failed`      | ✕     |
| info    | `--color-border-focus`       | i     |

Entry animation: `animate-toast-in` (translateY + opacity, 250ms spring).
