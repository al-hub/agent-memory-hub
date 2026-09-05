---
name: agent-memory-hub
description: Shared L2 memory for AI coding agents. Use when a task depends on past decisions, preferences, project state, lessons, earlier sessions, or when importing/synchronizing agent memory. Prefer fast local recall, preserve provenance, and surface conflicts or uncertain context instead of guessing.
---

# Agent Memory Hub

Use `agent-memory-hub` as a shared, agent-independent L2 memory layer.

## Core model

- L1: the current agent's session context, local memory files, rules, and accessible history.
- L2: `agent-memory-hub`, a persistent local store shared across agents.
- Raw evidence is canonical. Summaries/memories are indexes and interpretations, not unquestionable truth.

## When to recall

Recall from L2 before answering when the user refers to:

- a previous decision or discussion;
- an earlier project state or architecture choice;
- established preferences or constraints;
- a lesson, failed attempt, workaround, or reason for a prior choice;
- context that is missing after session reset/clear;
- information another agent may have learned earlier.

Do not recall for ordinary questions that do not depend on prior user/project context.

## Fast path

Run the local CLI from this skill directory when available:

```bash
python3 scripts/memory_hub.py recall "<concise query>" --limit 8
```

Use returned memories as evidence. Prefer `confirmed` memories. Treat `candidate`, `needs_review`, `conflict`, and `stale` as warnings, not facts. Ignore `rejected` by default. A `superseded` memory is historical context unless the user asks about the past.

If a source pointer is important to the answer, inspect the memory:

```bash
python3 scripts/memory_hub.py inspect <memory-id>
```

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

Add durable information when it will plausibly matter in future sessions. Avoid transient chatter.

Good memory types:

- `fact`
- `preference`
- `decision`
- `constraint`
- `lesson`
- `mistake`
- `project_state`
- `hypothesis`
- `temporary`

Example:

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

Use `candidate` or `needs_review` when the user's intent was not explicit. Do not convert brainstorming language such as "A could work" into a confirmed decision.

## Conflict handling

Never silently overwrite contradictory memories.

When a known memory conflicts with another one, link them and mark the unresolved state:

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

Temporal change is not automatically a contradiction. Prefer supersession when a newer preference/decision clearly replaces an older one.

## Cleaning rules

Before promoting L1 observations into durable L2 memory:

1. Deduplicate semantically equivalent statements when possible.
2. Reject trivial short-lived chatter.
3. Preserve provenance and source pointers.
4. Mark ambiguous context `needs_review`.
5. Keep conflicting candidates instead of choosing one without evidence.
6. Prefer a small number of durable memories over storing every sentence as a fact.
7. Keep source raw material available when importing files.

## Context pack discipline

Return only the smallest relevant memory set. Do not dump the entire store into the model context. Prefer metadata/FTS retrieval first; use semantic retrieval only if a future implementation provides it and lexical recall is insufficient.

## Health checks

For setup or suspected corruption:

```bash
python3 scripts/memory_hub.py doctor
python3 scripts/memory_hub.py status
```

If the store reports conflicts or review-needed items relevant to the current task, surface that uncertainty to the user rather than guessing.
