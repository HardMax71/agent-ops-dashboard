---
id: PRD-009
title: PRD Authoring & Documentation Standards
status: DRAFT
domain: documentation
depends_on: []
key_decisions: [no-numeric-section-refs, anchor-link-convention, frontmatter-schema, cross-file-link-format]
---

# PRD-009 — PRD Authoring & Documentation Standards

| Field        | Value                                 |
|--------------|---------------------------------------|
| Document ID  | PRD-009                               |
| Version      | 1.0                                   |
| Status       | DRAFT                                 |
| Date         | March 2026                            |
| Author       | Engineering Team                      |
| Parent       | [PRD-001](PRD-001-master-overview.md) |
| Related Docs | —                                     |

---

## Purpose

This PRD defines the conventions for writing, structuring, and cross-referencing PRD documents in
this repository. All future PRDs and edits to existing PRDs must follow these rules. Consistent
conventions make documents navigable, keep cross-references valid through edits, and prevent the
class of broken `§N` reference bugs that arise when sections are renumbered or reordered.

---

## File Naming

```
PRD-NNN-slug.md
```

- `NNN` is a zero-padded three-digit integer, assigned sequentially: `001`, `002`, …
- `slug` is a short, lowercase, hyphen-separated description of the document's topic.
- Examples: `PRD-003-langgraph-orchestration.md`, `PRD-009-documentation-standards.md`
- Files live in `docs/prd/`.

---

## Frontmatter

Every PRD begins with a YAML frontmatter block:

```yaml
---
id: PRD-NNN
title: Human-Readable Title
status: DRAFT
domain: <area>          # e.g. backend/auth, frontend, tooling, documentation
depends_on: [PRD-001]   # IDs of PRDs this one directly extends or requires
key_decisions: [slug-1, slug-2]   # short identifiers for the key design choices made
---
```

**`status` values:**

| Value        | Meaning                                                    |
|--------------|------------------------------------------------------------|
| `DRAFT`      | Work in progress — content may change significantly        |
| `REVIEW`     | Complete enough for team review — structural changes unlikely |
| `APPROVED`   | Accepted by the team — changes require explicit discussion |
| `DEPRECATED` | Superseded or no longer applicable                         |

---

## Document Header

Immediately after the frontmatter, every PRD has:

1. An `h1` title: `# PRD-NNN — Full Document Title`
2. A metadata table:

```markdown
| Field        | Value                                 |
|--------------|---------------------------------------|
| Document ID  | PRD-NNN                               |
| Version      | 1.0                                   |
| Status       | DRAFT                                 |
| Date         | <Month Year>                          |
| Author       | Engineering Team                      |
| Parent       | [PRD-001](PRD-001-master-overview.md) |
| Related Docs | [PRD-XXX](PRD-XXX-slug.md) (reason)   |
```

`Parent` is the single PRD this document extends. `Related Docs` lists laterally related PRDs with
a parenthetical explaining the relationship. Use `—` for fields that are not applicable.

---

## Section Headings

- Use `##` for top-level sections and `###` for sub-sections. Avoid going deeper than `####`.
- **Do not prefix headings with numbers.** Write `## Session & JWT Model`, not `## 4. Session & JWT Model`.
- Numeric prefixes break cross-references whenever a section is inserted, removed, or reordered.
  Anchor links to section titles are stable; anchor links to `4-session-jwt-model` are not.

---

## Cross-References

### Within the Same File

Use a Markdown anchor link to the section title:

```markdown
see the [Interrupt Timeout Mechanism](#interrupt-timeout-mechanism) section
```

**Anchor derivation (CommonMark / GitHub Flavored Markdown):**

1. Take the full heading text, excluding any leading `#` characters.
2. Convert to lowercase.
3. Replace every space with `-`.
4. Remove every character that is not alphanumeric, a hyphen, or an underscore.

Examples:

| Heading                              | Anchor                                 |
|--------------------------------------|----------------------------------------|
| `## Session & JWT Model`             | `#session--jwt-model`                  |
| `### Token Expiry During an Active Stream` | `#token-expiry-during-an-active-stream` |
| `### Selected Approach: Fetch-Based EventSource` | `#selected-approach-fetch-based-eventsource` |
| `### BugTriageState Schema Change`   | `#bugtriagestate-schema-change`        |

> **Verify anchors** by opening the rendered file on GitHub or in a local Markdown preview.
> Anchors for headings containing special characters (`:`, `&`, `/`) can be surprising — always
> check rather than guess.

### Across Files

Combine a relative file path with an anchor. Always include a human-readable label that names the
destination section:

```markdown
[PRD-008 §REST API Authentication](PRD-008-authentication.md#rest-api-authentication)
[PRD-003 §Shared State Schema](PRD-003-langgraph-orchestration.md#shared-state-schema)
```

The label pattern is `PRD-NNN §Section Title` — the `§` symbol is used **only inside link labels**,
never as a standalone reference. A bare `§5` or `§8.3` in prose is forbidden (see below).

When an existing link already has a display name, append the anchor rather than restructuring the
link:

```markdown
# Before (file link with no anchor):
[PRD-004](PRD-004-agent-layer.md) §3.2

# After (anchor embedded in the link label):
[PRD-004 §Service Registry](PRD-004-agent-layer.md#service-registry)
```

### Forbidden: Bare Numeric Section References

Do **not** write bare numeric references such as `§5`, `§8.3`, or `see section 4.3`. These are
invisible to link validators, break silently when sections are reordered, and give the reader no
information about where they are going.

| Forbidden                                           | Correct                                                                                   |
|-----------------------------------------------------|-------------------------------------------------------------------------------------------|
| `see §6`                                            | `see [SSE Endpoint Authentication](#sse-endpoint-authentication)`                         |
| `(PRD-003 §5.2)`                                    | `([PRD-003 §Supervisor Output Schema](PRD-003-langgraph-orchestration.md#supervisor-output-schema))` |
| `[PRD-008](PRD-008-authentication.md) §6.4`         | `[PRD-008 §Token Expiry During an Active Stream](PRD-008-authentication.md#token-expiry-during-an-active-stream)` |
| `migration path documented in §8.4`                 | `migration path documented in [Token Expiry](#token-expiry)`                              |

### References Inside Code Blocks

Code block contents (including comments) cannot contain Markdown links. Use plain text that
describes the destination by name:

```toml
# see Inter-Service Authentication section
INTERNAL_SERVICE_SECRET=<64-byte random hex>
```

---

## Code Blocks

- Always use fenced code blocks (triple backtick).
- Always specify the language: ` ```python `, ` ```typescript `, ` ```toml `, ` ```mermaid `, etc.
- File paths or context comments go on the first line inside the block as a code comment:

```python
# src/auth/dependencies.py
async def get_current_user(...):
    ...
```

---

## Diagrams

Use [Mermaid](https://mermaid.js.org/) for all diagrams. Supported diagram types: `sequenceDiagram`,
`flowchart`, `erDiagram`, `classDiagram`. Embed inline:

````markdown
```mermaid
sequenceDiagram
    actor Browser
    participant Backend
    ...
```
````

Do not commit image files (`.png`, `.svg`) for diagrams that can be expressed in Mermaid.

---

## Tables

Use Markdown tables for structured comparisons, decision matrices, and field definitions. Every
table must have a header row and a separator row. Align columns for readability in source, but do
not use automated table formatters that collapse spacing — the diff noise outweighs the benefit.

---

## Updating Existing PRDs

When editing a PRD:

1. **Do not renumber sections.** Add new sections at a logical position; do not shift existing ones.
2. **Update all cross-references** that point to any heading you rename. Search all PRD files for
   the old anchor before renaming.
3. **Bump `Version`** in the metadata table for substantive changes (new sections, revised
   decisions). Typo fixes and link repairs do not require a version bump.
4. **Do not change `status` unilaterally** from `APPROVED` or higher — that requires team sign-off.
