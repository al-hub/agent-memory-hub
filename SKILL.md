---
name: agent-memory-hub
description: Shared L2 memory and continuity layer for AI coding agents. Use proactively when a task may depend on prior decisions, project/repository/worktree state, lessons, earlier sessions, or another agent's work. The user should not need to ask for memory explicitly. Prefer fast local recall, preserve provenance, and surface conflicts or uncertain context instead of guessing.
---

# Agent Memory Hub

Use `agent-memory-hub` as a shared, agent-independent L2 memory and continuity layer.

## Core model

- L1: the current agent's session context, local memory files, rules, and accessible history.
- L2: `agent-memory-hub`, a persistent local store shared across agents.
- Raw evidence is canonical. Summaries/memories are indexes and interpretations, not unquestionable truth.
- Continuity should feel seamless: recall useful prior context when needed without requiring the user to say "use memory" or name this skill.

## Continuity gate

Before recalling, cheaply decide whether prior context can materially change the action or answer.

Recall proactively for continuity-sensitive situations such as:

- "continue", "resume", "as before", "the earlier approach", or equivalent wording;
- entering or returning to a repository/worktree where prior agent work may exist;
- switching from one AI agent to another on the same project;
- session reset/clear where the current task obviously continues earlier work;
- architecture, implementation, performance, test, migration, or tooling work that may depend on established project decisions;
- a repeated failure where an earlier lesson or workaround may exist.

Do **not** recall for ordinary stateless questions where past user/project context cannot materially affect the answer. The memory layer should be almost invisible when irrelevant.

## When to recall

Recall from L2 before answering or acting when the user refers to, or the current task plausibly depends on:

- a previous decision or discussion;
- an earlier project/repository/worktree state or architecture choice;
- established preferences or constraints;
- a lesson, failed attempt, workaround, benchmark, or reason for a prior choice;
- context missing after session reset/clear;
- information another agent may have learned earlier.

The user does not need to explicitly request a memory lookup.

## Fast path

Run the local CLI from this skill directory when available:

```bash
python3 scripts/memory_hub.py recall "<concise query>" --limit 8
```

When the relevant project/repository scope is known, prefer a scoped recall rather than broad global retrieval.

Use returned memories as evidence. Prefer active/verified (legacy `confirmed`) memories. Treat `candidate`, `needs_review`, `conflict`, and stale/archived states as warnings, not facts. Ignore quarantined/rejected records by default. A superseded memory is historical context unless the user asks about the past.

If a source pointer is important to the answer or action, inspect the memory:

```bash
python3 scripts/memory_hub.py inspect <memory-id>
```

## Continuity projection

Do not dump recall output verbatim into context. Build the smallest useful projection for the current need.

Typical projections:

- **onboarding**: repository purpose, architecture, important decisions, constraints, known pitfalls, build/test conventions;
- **resume**: current objective, completed work, verified current state, recent failures, next action;
- **handoff**: objective, what changed, what was verified, failures/risks, important decisions, next recommended action;
- **recall**: only memories directly relevant to the user's current question or action.

These are projections over L2, not independent sources of truth. Prefer evidence-backed current state over stale summaries.

## First use / bootstrap

Do not assume L2 starts empty. On a new machine or new agent environment:

```bash
python3 scripts/memory_hub.py init
python3 scripts/memory_hub.py import-l1 --dry-run
```

If the task explicitly authorizes setup/import, run the real import:

```bash
python3 scripts/memory_hub.py import-l1
```

The importer may only use L1 sources that are actually accessible on disk. Never claim access to a product's private/internal memory unless an accessible source exists.

## Writing memories

Add or propose durable information when it will plausibly matter in future sessions. Avoid transient chatter.

Strong capture candidates include:

- an explicit decision;
- a verified test or benchmark result;
- a failed approach worth avoiding;
- a discovered constraint;
- a meaningful architecture change;
- a material project/worktree/task state change;
- an explicit user correction that changes prior understanding.

Good memory types include:

- `identity`
- `preference`
- `decision`
- `constraint`
- `project_state`
- `episode`
- `lesson`
- `fact`
- `procedure`

Example using the compatibility CLI:

```bash
python3 scripts/memory_hub.py add \
  "Rust implementation uses a separate repository." \
  --type decision \
  --status confirmed \
  --confidence 0.96 \
  --context-quality clear \
  --source-agent codex \
  --source-pointer "conversation:2026-09-02"
```

Use candidate/unverified/needs-review states when the user's intent was not explicit. Do not convert brainstorming language such as "A could work" into a verified decision.

## Conflict handling

Never silently overwrite contradictory memories.

When a known memory conflicts with another one, preserve both and link the conflict. Temporal change is not automatically a contradiction: prefer supersession when a newer preference or decision clearly replaces an older one. Apparently incompatible claims in different repository/worktree/task scopes should be treated as different context rather than a false conflict.

Compatibility CLI example:

```bash
python3 scripts/memory_hub.py add "<new statement>" \
  --status conflict \
  --conflicts-with <existing-id>
```

When the user later resolves it:

```bash
python3 scripts/memory_hub.py resolve <memory-id> --status confirmed
python3 scripts/memory_hub.py resolve <old-id> --status superseded --superseded-by <memory-id>
```

## Cleaning rules

Before promoting L1 observations into durable L2 memory:

1. Deduplicate semantically equivalent statements when possible.
2. Reject or quarantine trivial short-lived chatter.
3. Preserve provenance and source pointers.
4. Mark ambiguous context `needs_review`.
5. Keep conflicting candidates instead of choosing one without evidence.
6. Prefer a small number of durable memories over storing every sentence as a fact.
7. Keep source raw material available when importing files.
8. Do not increase confidence merely because several agents repeat the same underlying evidence.

## Context pack discipline

Return only the smallest relevant memory set. Do not dump the entire store into the model context. Prefer scope/type filtering and metadata/FTS retrieval first; use semantic retrieval only if a future implementation provides it and lexical recall is insufficient.

Normal continuity should favor a few high-value memories over exhaustive history. Expand into evidence/raw history only when the task requires it.

## Health checks

For setup or suspected corruption:

```bash
python3 scripts/memory_hub.py doctor
python3 scripts/memory_hub.py status
```

If the store reports conflicts or review-needed items relevant to the current task, surface that uncertainty to the user rather than guessing.
