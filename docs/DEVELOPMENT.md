# Development Guide

## Development goal

`agent-memory-hub` is developed as an **Agent Continuity Layer**, not merely a memory database.

The product should be almost invisible when installed, but its absence should be obvious when a user changes agent, session, repository, branch, or worktree and must repeat prior context manually.

## TDD loop

Every behavior change follows:

```text
RED
  write a failing behavior test
  ↓
GREEN
  implement the smallest correct change
  ↓
REFACTOR
  improve structure without changing behavior
  ↓
PERF
  check latency/token/context regression where relevant
```

Do not start a feature by adding production branches first and tests later.

## SOLID boundaries

The long-term package direction is:

```text
src/agent_memory_hub/
├── domain/          pure value objects and policy concepts
├── ports/           small interfaces owned by the core
├── application/     use cases: recall, build context, propose, resolve
├── continuity/      gate, fingerprint, scope, projection policies
├── infrastructure/  SQLite, Git, filesystem, adapters
└── cli/             user-facing commands
```

Dependency rule:

```text
infrastructure → ports/application → domain
```

The domain must not import SQLite, Git subprocess code, Codex, Claude, Gemini, MCP, or filesystem adapters.

### Single Responsibility

Keep repository detection, scope resolution, retrieval, governance filtering, ranking, projection, and persistence separate.

### Open/Closed

Adding a new agent adapter, retrieval strategy, or projection preset should normally add an implementation behind a port rather than edit a central `if agent == ...` switch.

### Liskov Substitution

In-memory and SQLite repositories, or different source adapters, must satisfy the same contract tests.

### Interface Segregation

Prefer small ports such as `RepositoryInspector`, `MemoryReader`, `MemoryWriter`, `EvidenceReader`, and `RawSourceRegistry` instead of a single giant store interface.

### Dependency Inversion

Application/domain code depends on ports. Infrastructure implements those ports.

## Read/write asymmetry

Normal reads must stay deterministic and fast:

```text
continuity gate
→ scope/type filter
→ SQLite FTS5/BM25
→ governance filter
→ token-budget projection
```

The normal read path should not require embeddings, external services, or an LLM.

Writes may be more expensive because they must preserve trust:

```text
observation
→ memory.propose
→ normalize/dedupe
→ scope/context check
→ update/conflict/different-context check
→ candidate/review/quarantine
```

Agents propose durable memory; the governed layer owns durable state changes.

## Seamless continuity scenarios

These scenarios are release-level regression tests, not optional demos.

1. **Repository onboarding** — an agent with no local history enters a known repository and receives the minimum useful repository context without the user asking for memory.
2. **Worktree resume** — returning to a worktree restores its objective/current state/next action while repository-level knowledge remains shared.
3. **Cross-agent handoff** — Agent B continues Agent A's verified work without a hand-written `handoff.md` being the source of truth.
4. **Session reset** — after `/clear` or a new session, continuity is restored from L2 with a small context pack.
5. **HEAD-aware staleness** — checkpoint-derived state is downgraded when repository HEAD materially diverges.
6. **Scope isolation** — worktree/task-specific memories do not leak into unrelated worktrees/tasks.
7. **Conflict safety** — unresolved conflicts are never silently projected as verified truth.

The main product metric is **Continuity Success Rate**:

> Can the agent continue the correct work without asking the user to restate previously available project context?

## Context budget

Context projection must be bounded. Initial benchmark targets, not guarantees:

- normal projected L2 context: 500–1000 tokens
- hard ceiling for ordinary continuity packs: 1500–2000 tokens
- normal recall: FTS fast path, target <50 ms on a representative local WSL benchmark
- normal recall LLM calls: 0
- semantic fallback: exceptional, target <5–10% once implemented and measured

Prefer dedupe + scope + type + governance ranking before adding semantic retrieval.

## Test layout

```text
tests/
├── unit/          pure policies/value objects
├── integration/   SQLite/Git/filesystem boundaries
├── contract/      interchangeable port implementations/adapters
├── regression/    end-to-end continuity scenarios
└── performance/   reproducible latency/scale regressions
```

Performance CI should initially detect regressions relative to a baseline rather than use brittle absolute wall-clock gates on shared runners.

## Definition of Done

A feature is complete only when applicable items are satisfied:

- failing test existed first
- unit tests pass
- contract tests pass for affected ports
- a regression scenario is added or preserved
- dependency direction remains valid
- context/token budget is bounded
- no silent conflict overwrite is introduced
- performance regression is checked where relevant
- docs are updated

## Versioning

The first package-development baseline is `0.2.0-alpha.1`.

`0.2.0` should not be declared stable until at least the following are integrated and regression-tested:

- canonical repository fingerprint
- worktree/branch/HEAD execution context
- typed + scope-aware retrieval
- Continuity Gate
- token-budget Context Projector
- onboarding/resume/handoff projection presets
- governed capture/propose path
- lazy raw-source lookup/extraction interfaces

## Implementation sequence

### Phase A — Seamless Core

1. canonical repository identity
2. worktree/branch/HEAD detection
3. scope hierarchy
4. typed + scope-aware FTS retrieval
5. Continuity Gate
6. token-budget Context Projector

### Phase B — Continuity presets

1. onboarding
2. resume
3. handoff
4. worktree checkpoint/resume
5. HEAD-aware stale handling

### Phase C — Automatic learning

1. meaningful-event detection
2. `memory.propose`
3. deterministic dedupe
4. update vs conflict vs different-context
5. promotion/review/quarantine policy

### Phase D — Historical bootstrap

1. adapter discovery
2. raw-source registration
3. cold FTS indexing
4. lazy extraction
5. extracted-memory cache

### Phase E — Universal integration

1. Codex adapter
2. Claude adapter
3. Gemini/Antigravity adapter
4. MCP gateway
5. optional hot cache
6. benchmark/regression hardening

## Worktree-context retirement gate

Do not remove `worktree-context` merely because similar concepts exist here. Deprecate it only after `agent-memory-hub` passes all of:

- known-repository automatic onboarding
- worktree resume
- cross-agent handoff
- session-reset continuity
- HEAD-aware stale detection

Until then it remains a useful reference implementation and compatibility benchmark.
