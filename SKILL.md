---
name: agent-memory-hub
description: Shared L2 memory and continuity layer for AI coding agents. Use proactively when a task may depend on prior decisions, project/repository/worktree state, lessons, earlier sessions, or another agent's work. Prefer fast local recall, preserve provenance, surface conflicts/stale context, and keep normal use nearly invisible.
---

# Agent Memory Hub

Use `agent-memory-hub` as a shared, agent-independent L2 memory and continuity layer.

## Installation

Preferred setup is the one-command npx installer:

```bash
npx -y github:al-hub/agent-memory-hub install
```

It installs this Agent Skill globally, copies a persistent runtime to `~/.agent-memory-hub/runtime`, initializes the local store, and non-destructively merges SessionStart hooks for Codex, Claude Code, and Gemini CLI.

After the scoped npm package is published, the same contract is:

```bash
npx -y @al-hub/agent-memory-hub@latest install
```

Remove managed hooks/runtime/skill while preserving memory data with:

```bash
npx -y github:al-hub/agent-memory-hub uninstall
```

## Core model

- L1: current agent session context, local rules, accessible history.
- L2: persistent `agent-memory-hub` memory shared across agents.
- Raw evidence is canonical. Memory claims and summaries are governed interpretations/indexes.
- Continuity should be automatic when relevant and effectively invisible when irrelevant.

## Hook-native continuity

When SessionStart hooks are available, prefer them over manual recall. The installed hook runs the persistent runtime, not the temporary npx cache:

```text
python3 ~/.agent-memory-hub/runtime/scripts/session_start_hook.py --agent <agent>
```

Typical mapping:

```text
startup → ONBOARDING when the repository already has L2 memory
resume  → RESUME
clear   → RESUME
compact → RESUME where supported
fork    → RESUME where supported
```

Hook errors are fail-open. Never prevent the coding agent from starting because memory lookup failed.

## Prompt-facing seamless path

When the hook did not already provide continuity context and the current user request plausibly depends on prior work, use:

```bash
python3 ~/.agent-memory-hub/runtime/scripts/continuity_context.py \
  "<current user/task message>" \
  --cwd "$PWD" \
  --json
```

Treat `mode: no_recall` as success. Do not fall back to broad history search simply because no memory was returned.

The production prompt-recall path is scope-first SQLite FTS. Repository/worktree/branch scope is intersected inside FTS before lexical candidates expand. The entry point also non-destructively upgrades legacy two-column FTS indexes and repairs dirty compatibility-writer rows before recall. If that scoped index is unavailable, broad/LIKE fallback remains valid.

Manual direct recall is for explicit historical lookup or deliberately narrow queries:

```bash
python3 ~/.agent-memory-hub/runtime/scripts/memory_hub.py recall "<query>" --limit 8
```

## Continuity gate

Recall when prior context can materially change the answer/action, especially:

- continue/resume/as-before wording;
- first entry or return to a repository/worktree with existing L2 memory;
- session clear/reset/compaction;
- cross-agent continuation;
- architecture, migration, implementation, performance, test, or tooling work that depends on prior decisions;
- repeated failures where a previous lesson/workaround may exist.

Do not recall for ordinary stateless questions or fully specified trivial edits.

## Scope discipline

Prefer the most specific visible scope:

```text
task > worktree > branch > repository > global
```

Never inject a branch/worktree/task memory from another repository merely because the local names match.

At SessionStart there may be no user prompt. In that case bounded visible-scope browse is valid; the projector should choose the smallest useful onboarding/resume pack.

## Projection discipline

Use the bounded projected context, not a raw memory dump.

Typical modes:

- **onboarding**: decisions, constraints, architecture/procedures, pitfalls, relevant project state;
- **resume**: current objective/state, decisions, lessons, next useful action;
- **handoff**: objective, changed/verified/failed, decisions, risks, next action;
- **recall**: memories directly relevant to the current question.

If `STALE_HEAD` is present, stable decisions/constraints may remain useful, but volatile `project_state` must be revalidated against current code before acting.

## Governance

Prefer active/verified evidence-backed memories. Preserve uncertainty explicitly:

```text
lifecycle:
  candidate | active | superseded | archived | quarantined

review_state:
  verified | unverified | needs_review | conflict
```

Never silently choose a winner between conflicting memories. A newer intentional decision can supersede an older one, but different scopes should not be turned into false conflicts.

## Writing durable memory

Capture only information likely to matter later:

- explicit decisions;
- verified tests/benchmarks;
- meaningful failures/lessons;
- discovered constraints;
- architecture changes;
- material task/project/worktree state;
- explicit user corrections.

Do not store transient chatter as durable fact. Use candidate/needs-review states when intent or context is ambiguous.

Compatibility write example:

```bash
python3 ~/.agent-memory-hub/runtime/scripts/memory_hub.py add \
  "Scope-first FTS is the production prompt-recall path." \
  --type decision \
  --status confirmed \
  --source-agent codex
```

Compatibility writes are synchronized into the scope-aware FTS at the next continuity entry; durable truth remains in `memories`/evidence, not the FTS cache.

## Evidence and conflicts

If a source pointer matters, inspect the memory/evidence instead of trusting a summary blindly. Preserve repeated claims from the same underlying source as one evidence group rather than treating agent repetition as independent confirmation.

When conflicts are unresolved, surface them to the user/agent rather than inventing a resolution.

## Health, benchmark, and bootstrap

The npx installer initializes the store. Existing accessible L1 sources can be bootstrapped explicitly:

```bash
python3 ~/.agent-memory-hub/runtime/scripts/memory_hub.py import-l1 --dry-run
python3 ~/.agent-memory-hub/runtime/scripts/memory_hub.py import-l1
```

For store diagnostics:

```bash
python3 ~/.agent-memory-hub/runtime/scripts/memory_hub.py doctor
python3 ~/.agent-memory-hub/runtime/scripts/memory_hub.py status
```

For practical local/WSL latency diagnostics use the packaged npx command rather than inventing a separate benchmark:

```bash
npx -y github:al-hub/agent-memory-hub benchmark
```

Use `--quick` for a smoke measurement. The full benchmark records WSL/toolchain/filesystem metadata, warm in-process continuity, fresh-process NO_RECALL/Resume/Handoff, real SessionStart hook p50/p95, and writes `agent-memory-hub-benchmark.json` by default. Fresh-process measurements do not claim to flush the OS page cache.

Only import sources actually accessible/configured on disk. Never claim access to private product memory that is not available.
