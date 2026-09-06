---
name: agent-memory-hub
description: Shared L2 memory and continuity layer for AI coding agents. Use proactively when a task may depend on prior decisions, project/repository/worktree state, lessons, earlier sessions, or another agent's work. Prefer fast local recall, preserve provenance, surface conflicts/stale context, and keep normal use nearly invisible.
---

# Agent Memory Hub

Use `agent-memory-hub` as a shared, agent-independent L2 memory and continuity layer.

## Installation

For the current GitHub-backed package, npm 12+ requires per-command Git opt-in:

```bash
npx --allow-git=all -y github:al-hub/agent-memory-hub install
```

The installer copies a persistent runtime to `~/.agent-memory-hub/runtime`, initializes the local store, and non-destructively merges SessionStart hooks for Codex, Claude Code, and Gemini CLI.

After the scoped npm package is published, the intended form is:

```bash
npx -y @al-hub/agent-memory-hub@latest install
```

## Core model

- L1: current agent session context, local rules, accessible history.
- L2: persistent governed memory shared across agents.
- Raw evidence is canonical; summaries/indexes are rebuildable projections.
- Continuity should be automatic when relevant and effectively invisible when irrelevant.

## Hook-native continuity

Prefer installed SessionStart hooks over manual recall when available:

```text
python3 ~/.agent-memory-hub/runtime/scripts/session_start_hook.py --agent <agent>
```

Typical mapping:

```text
startup → ONBOARDING when repository L2 exists
resume  → RESUME
clear   → RESUME
compact → RESUME where supported
fork    → RESUME where supported
persisted agent change in same repo/worktree → HANDOFF
```

The continuity checkpoint persists the last observed agent identity. Codex → Claude → Gemini can therefore select HANDOFF without requiring the user to name the previous agent. Governed L2 memory remains the durable truth; the checkpoint only selects continuity mode.

Hook errors are fail-open. Never prevent the coding agent from starting because memory lookup failed.

## Prompt-facing path

When the hook did not already provide continuity context and the request depends on prior work, use:

```bash
python3 ~/.agent-memory-hub/runtime/scripts/continuity_context.py \
  "<current user/task message>" \
  --cwd "$PWD" \
  --json
```

Treat `mode: no_recall` as success. Do not broaden into history search merely because no memory was returned.

Prompt recall uses scope-first SQLite FTS. Repository/worktree/branch scope is intersected inside FTS before lexical candidates expand. Legacy FTS caches are rebuilt non-destructively and dirty compatibility writes are repaired before prompt recall.

SessionStart has no lexical query by design and uses bounded visible-scope browse instead of prompt FTS.

## Scope discipline

Prefer the most specific visible scope:

```text
task > worktree > branch > repository > global
```

Never inject worktree/branch/task memory from another repository merely because local names match. Real Git multi-worktree E2E tests enforce worktree isolation while allowing repository-scoped decisions to remain shared.

If `STALE_HEAD` is present, stable decisions/constraints may remain useful, but volatile `project_state` must be revalidated against current code.

## Projection discipline

Use bounded projected context, not raw memory dumps.

- **onboarding**: decisions, constraints, procedures, lessons, relevant state.
- **resume**: current state, decisions, lessons, next useful action.
- **handoff**: objective/state, verified decisions, failures/risks, next action.
- **recall**: memories directly relevant to the question.

## Governance

Prefer active/verified evidence-backed memories and preserve uncertainty explicitly:

```text
lifecycle:
  candidate | active | superseded | archived | quarantined

review_state:
  verified | unverified | needs_review | conflict
```

Never silently choose a winner between unresolved conflicting memories.

## Durable writes

Capture only information likely to matter later: explicit decisions, verified benchmarks/tests, meaningful failures/lessons, constraints, architecture changes, material project/worktree state, and explicit user corrections. Do not persist transient chatter as durable fact.

Compatibility writer example:

```bash
python3 ~/.agent-memory-hub/runtime/scripts/memory_hub.py add \
  "Scope-first FTS is the production prompt-recall path." \
  --type decision \
  --status confirmed \
  --source-agent codex
```

## Diagnostics and benchmark

Store diagnostics:

```bash
python3 ~/.agent-memory-hub/runtime/scripts/memory_hub.py doctor
python3 ~/.agent-memory-hub/runtime/scripts/memory_hub.py status
```

Practical local/WSL benchmark:

```bash
npx --allow-git=all -y github:al-hub/agent-memory-hub benchmark --quick
npx --allow-git=all -y github:al-hub/agent-memory-hub benchmark
```

The benchmark records WSL/toolchain/filesystem metadata, warm continuity, fresh-process continuity, real SessionStart hook p50/p95, and startup/import/composition breakdown. Fresh-process measurements do not claim to flush the OS page cache; startup phases are diagnostic and not additive.

Only import sources actually accessible/configured on disk. Never claim access to private product memory that is unavailable.
