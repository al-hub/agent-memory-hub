# L1 Bootstrap and Reconciliation Development Plan

Last reviewed: 2026-09-08

## Purpose

This document defines the next priority development plan for `memcarry`: a bounded, evidence-aware L1 ingestion pipeline that works not only for an empty store, but also for first-seen repositories and already-known repositories.

The goal is not to copy agent histories into L2. The goal is to convert heterogeneous agent-native L1 histories into governed evidence and candidate claims that can safely participate in `RECALL`, `RESUME`, and `HANDOFF`.

The core rule is:

```text
L1 history != durable truth
L1 history = evidence source
```

Therefore the target pipeline is:

```text
Codex / Claude / Gemini / AGY L1
               |
               v
          source adapter
               |
               v
        normalized L1 record
               |
               v
        ingestion state detector
               |
      +--------+---------+
      |        |         |
      v        v         v
  BOOTSTRAP  ONBOARD  RECONCILE
   EMPTY      FIRST     EXISTING
      \        |        /
       \       |       /
        v      v      v
          candidate claims
               |
               v
            governance
   dedupe / provenance / time
   conflict / stale / confidence
               |
               v
          governed shared L2
```

`EMPTY`, `FIRST`, and `EXISTING` are different entry policies over one ingestion core. They must not become three separate memory systems.

## Why this work moves earlier

The previous development sequence placed meaningful-event capture before historical bootstrap. The revised priority moves the ingestion/governance core earlier for four reasons:

1. **First-run value**: a new installation should not necessarily start from zero when useful local agent history already exists.
2. **Governance validation**: historical L1 data is a strong test bed for dedupe, conflict, temporal validity, provenance, abstention, and contamination handling.
3. **Reuse**: future meaningful-event capture should feed the same governed ingestion path instead of creating a second write architecture.
4. **Reproducibility**: memory behavior is difficult to validate only through dogfooding because time, repository state, agent versions, and user behavior vary. Deterministic replay fixtures can make these cases testable in CI.

Dogfooding remains important, but primarily as a source of new failure cases. A real failure should be converted into a deterministic fixture and permanent regression test.

## Research-derived design constraints

The implementation is informed by external research and existing agent-memory systems, but those references are evidence rather than specifications. Every mechanism must earn its complexity through `memcarry`-specific tests and benchmarks.

### 1. Separate memory roles and provenance

CoALA models language-agent memory with distinct semantic, episodic, and procedural roles. `memcarry` does not need to copy that taxonomy literally, but bootstrap must not flatten decisions, events, failures, rules, and inferred summaries into one undifferentiated record.

Implications:

- preserve source type and source agent;
- keep episodic evidence separate from durable claims;
- allow stable decisions/constraints to outlive volatile project state;
- avoid treating procedural instructions as ordinary facts.

Reference:
- CoALA — Cognitive Architectures for Language Agents: https://arxiv.org/abs/2309.02427

### 2. Preserve raw episodes; derive memories

Generative Agents stores experience and derives higher-level reflections instead of equating every observation with memory. This supports the existing `memcarry` rule that raw evidence is canonical and governed memory is a derived interpretation/index.

Implications:

```text
raw L1 episode
  -> evidence
  -> candidate claim
  -> governed memory
```

Reference:
- Generative Agents: Interactive Simulacra of Human Behavior: https://arxiv.org/abs/2304.03442

### 3. Treat time and invalidation as first-class

Zep/Graphiti demonstrates the value of temporal knowledge representation where facts can become invalid without erasing history. `memcarry` should borrow temporal semantics without adopting a graph database by default.

Initial metadata candidates:

```text
observed_at
valid_from      optional
valid_until     optional
ingested_at
source_agent
source_session
source_head
```

A newer statement may be an update rather than a contradiction. A historical statement can remain useful while no longer describing current HEAD state.

References:
- Graphiti: https://github.com/getzep/graphiti
- Zep Graph Overview: https://help.getzep.com/graph-overview
- Zep Key Concepts / fact invalidation: https://help.getzep.com/v2/concepts

### 4. Make abstention a correct outcome

LongMemEval identifies five important long-term-memory abilities: information extraction, multi-session reasoning, temporal reasoning, knowledge updates, and abstention.

`memcarry` should map these directly into regression categories. In particular, insufficient or conflicting evidence must be allowed to result in `needs_review`, `conflict`, or `no reliable memory found` rather than a forced claim.

References:
- LongMemEval paper: https://arxiv.org/abs/2410.10813
- LongMemEval benchmark/code: https://github.com/xiaowu0162/LongMemEval

### 5. Consolidate repeated evidence instead of multiplying memories

Mem0 motivates extract/consolidate/retrieve architectures for scalable long-term memory. For `memcarry`, repeated agent statements should normally strengthen one canonical claim through multiple evidence records rather than create N nearly identical memories.

Reference:
- Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory: https://arxiv.org/abs/2504.19413

### 6. Preserve failed attempts and lessons

Reflexion shows the value of episodic feedback and reflection for improving later decisions. For coding continuity, a failed attempt plus reason and evidence can be more valuable than a bare final decision because it prevents another agent from repeating the same experiment.

High-value candidate type:

```text
failed_attempt
  tried
  result
  evidence
  reason
  environment/conditions
```

Reference:
- Reflexion: Language Agents with Verbal Reinforcement Learning: https://arxiv.org/abs/2303.11366

### 7. Keep L1 small and L2 durable

MemGPT frames limited model context as a fast memory tier backed by slower external memory. This supports the `memcarry` L1/L2 model: agent-native context is a thin working set, while L2 is durable and shared.

Bootstrap must not turn L1 into a full mirror of L2 or L2 into a full prompt dump.

Reference:
- MemGPT: Towards LLMs as Operating Systems: https://arxiv.org/abs/2310.08560

### 8. Keep simple local-first UX and bounded injection

Existing coding-agent memory tools provide useful product lessons even where their trust model is simpler than `memcarry`.

`agentmemory` demonstrates one-shot local setup, shared memory across coding agents, bounded context injection, and simple inspectable storage. `claude-memory-skill` demonstrates a small summary/pointer hierarchy and low-friction deterministic retrieval.

Useful lessons:

- installation and first-run behavior must be simple;
- only bounded context should be injected;
- summaries should point to deeper evidence rather than contain everything;
- local inspection should remain easy.

References:
- AgentMemory: https://github.com/jayzeng/agentmemory
- claude-memory-skill: https://github.com/hanfang/claude-memory-skill

### 9. Preserve current memcarry research decisions

Existing project research already selected several complementary ideas:

- A-MEM: relations/evolving memories while preserving evidence;
- MemGuard: type-aware contamination handling and quarantine;
- Agentic Memory/AgeMem: explicit memory operations with governance;
- scope/type/time filtering before expensive semantic retrieval.

References:
- A-MEM: https://arxiv.org/abs/2502.12110
- MemGuard: https://arxiv.org/abs/2605.28009
- Agentic Memory / AgeMem: https://arxiv.org/abs/2601.01885
- Project synthesis: `docs/research/README.md`

## Ingestion states

### EMPTY

Definition:

- L2 contains no useful governed memory for continuity, typically immediately after installation or explicit clean initialization.

Policy:

- discover available supported L1 sources;
- perform cheap metadata scanning first;
- rank candidate sessions by repository relevance;
- inspect only a bounded subset;
- register raw evidence/provenance;
- import extracted claims as `candidate` by default;
- do not silently promote agent summaries to verified truth.

EMPTY may use broader discovery than FIRST, but it must still be bounded.

### FIRST

Definition:

- L2 already exists, but the current canonical repository identity has not previously been observed.

Policy:

- restrict discovery to records plausibly related to the current repository;
- prefer canonical repository identity and remote identity over path-only similarity;
- do not reprocess unrelated histories already known to L2;
- use the same candidate/governance pipeline as EMPTY.

FIRST is repository-targeted onboarding, not a global re-bootstrap.

### EXISTING

Definition:

- current repository is already known to L2.

Policy:

- never run a full historical bootstrap by default;
- inspect only unseen or changed L1 sources;
- reconcile new evidence against existing governed memory;
- unchanged sources should result in near-zero work.

Expected reconciliation outcomes:

| L1 vs L2 | Expected action |
|---|---|
| exact duplicate + same evidence | no-op |
| same claim + new source/evidence | attach evidence |
| semantically equivalent claim | deterministic/controlled dedupe candidate |
| genuinely new claim | add candidate |
| contradictory evidence | conflict/needs-review path |
| old claim against newer HEAD | stale or temporally historical |
| weak L1 inference vs verified L2 | preserve verified L2; record weak contradiction if useful |
| stronger direct evidence for an unverified L2 claim | attach evidence and re-evaluate through policy |

### PARTIAL / INTERRUPTED

Definition:

- a previous ingestion run ended before completion.

Policy:

- resume safely from persisted source/cursor state;
- already committed evidence must not duplicate;
- replay of the same input must be idempotent;
- partial failure must not corrupt existing L2 state.

## Normalized L1 boundary

Do not begin by writing Codex/Claude/Gemini-specific policy into the core.

Define a small normalized input contract first, conceptually:

```text
L1Record
  agent
  source_kind
  session_id
  timestamp
  repo_hint
  branch_hint
  head_hint
  record_kind
  content
  provenance
```

Agent adapters own parsing. The ingestion core owns state, comparison, governance, and persistence policy.

Dependency direction:

```text
Codex adapter -----+
Claude adapter ----+--> Normalized L1 port --> ingestion core --> governed L2
Gemini adapter ----+
AGY adapter -------+
```

This keeps future agent support open/closed and allows fake adapters to drive TDD before real history formats are integrated.

## Source fingerprint and incremental reconciliation

Normal startup must not repeatedly scan old histories.

Persist enough source state to cheaply identify unchanged input. Candidate fields:

```text
agent
source_path_or_source_id
session_id
mtime
size
content_hash      optional / only when justified
last_processed_offset_or_cursor
```

Desired cost curve:

```text
first import          -> bounded bootstrap work
known source changed  -> incremental reconciliation
known source unchanged-> fingerprint/no-op only
```

The most important performance case is not the first bootstrap. It is `EXISTING + unchanged L1`, because that cost is paid repeatedly in ordinary use.

## TDD strategy

Development must follow the existing `RED -> GREEN -> REFACTOR -> PERF` loop. Do not implement real agent parsers first.

### Golden scenarios

The first version should freeze at least these deterministic scenarios before production implementation expands:

| # | Scenario | Required result |
|---|---|---|
| 1 | EMPTY + no usable L1 | clean no-op / onboarding continues |
| 2 | EMPTY + one agent + one valid claim | candidate + provenance |
| 3 | EMPTY + multiple agents + same claim | one canonical candidate + multiple evidence records |
| 4 | EMPTY + conflicting agents | conflict/needs-review; no silent winner |
| 5 | FIRST + matching repository history | import only matching repository evidence |
| 6 | FIRST + unrelated repository history | unrelated input ignored |
| 7 | EXISTING + exact duplicate | idempotent no-op |
| 8 | EXISTING + new supporting evidence | attach evidence without duplicate memory |
| 9 | EXISTING + genuine conflict | preserve both evidence paths and mark review state |
| 10 | historical L1 + changed current HEAD | stale/historical classification |
| 11 | interrupted ingestion | restart safely without duplicate durable writes |
| 12 | EXISTING + unchanged L1 | near-zero work beyond fingerprint/state checks |

### LongMemEval-derived dimensions

Every applicable scenario should identify which correctness dimensions it covers:

```text
information extraction
a multi-session/multi-agent synthesis
temporal reasoning
knowledge update
abstention
```

Add project-specific dimensions:

```text
repository isolation
worktree isolation
provenance correctness
conflict safety
idempotency
latency/context budget
```

### Required edge fixtures after the golden set

Add these only after the first 12 scenarios are green:

- corrupt/truncated L1 source;
- very large session;
- missing repository metadata;
- path changed but canonical remote identity matches;
- duplicate clones of one repository;
- detached HEAD;
- changed/deleted branch;
- multiple worktrees;
- old agent inference conflicting with current direct Git/test evidence;
- repeated import after schema/runtime upgrade.

## Test pyramid

### Unit

Pure policy/value-object tests:

- ingestion state detector;
- source fingerprint comparison;
- evidence strength classification;
- update-vs-conflict decision;
- temporal/stale classification;
- deterministic dedupe keys;
- abstention/review policy.

### Contract

All source adapters must satisfy one normalized L1 contract test suite. Storage implementations must satisfy idempotent evidence/memory write contracts.

### Integration

Use fake L1 + real SQLite + disposable Git repositories to test:

- scope/repository identity;
- persistence;
- crash/restart behavior;
- stale HEAD behavior;
- dedupe and conflict transaction boundaries.

### Regression / E2E

Only after the core is stable, add real source adapters and fixtures for Codex, Claude, Gemini, and AGY. Cross-agent flows must prove that source-specific differences do not leak into governance semantics.

### Performance

Benchmark at least:

```text
10 / 100 / 1,000 source sessions
EMPTY bounded bootstrap
FIRST repo-targeted discovery
EXISTING unchanged
EXISTING + 1 new session
EXISTING + 100 new sessions
interrupted-resume path
```

Track p50/p95 and breakdowns. Do not set brittle shared-CI wall-clock gates before a stable baseline exists.

## Performance and safety guardrails

1. Bootstrap must remain bounded by source count/bytes/records or an equivalent deterministic budget.
2. Ordinary `SessionStart` must remain fail-open.
3. Full historical interpretation must not become a mandatory startup-path LLM call.
4. `EXISTING + unchanged` must avoid rescanning/parsing full histories.
5. A raw L1 statement must never overwrite a verified L2 memory directly.
6. Conflict is preserved, not resolved by source-agent preference.
7. Current repository/Git/test evidence outranks stale agent inference when policy can establish that relation.
8. Source corruption must not block normal agent startup.
9. Evidence and raw source provenance must remain inspectable after consolidation/supersession.
10. Semantic/vector/graph retrieval remains optional until measured failures justify it.

## Implementation order

### Phase 0 — Specification and fixture freeze

1. finalize `EMPTY`, `FIRST`, `EXISTING`, `PARTIAL` definitions;
2. define normalized L1 record contract;
3. define evidence provenance/strength metadata required by v1;
4. encode the 12 golden scenarios as fixtures/expected outcomes;
5. document explicit non-goals.

No production adapter implementation should precede this phase.

### Phase 1 — Pure ingestion policy core

TDD implementation of:

1. ingestion state detection;
2. candidate/evidence normalization;
3. deterministic exact dedupe;
4. update vs conflict vs different-context policy;
5. temporal/stale policy;
6. abstention/review outcomes.

Keep this layer independent of SQLite, Git subprocesses, and agent-specific formats.

### Phase 2 — Idempotent persistence and replay

1. raw/evidence source registration;
2. source fingerprint state;
3. idempotent evidence writes;
4. transaction boundaries;
5. interruption/restart replay;
6. real SQLite integration tests.

### Phase 3 — EMPTY and FIRST execution paths

1. cheap source discovery metadata path;
2. bounded source/session ranking;
3. EMPTY broader-but-bounded bootstrap;
4. FIRST repository-targeted onboarding import;
5. fail-open behavior;
6. performance breakdown instrumentation.

### Phase 4 — EXISTING incremental reconciliation

1. unchanged fast no-op;
2. new-session/new-record cursor processing;
3. supporting-evidence attachment;
4. conflict and update handling;
5. stale/current-state reconciliation;
6. regression tests for repeated runs.

### Phase 5 — Real agent adapters

Add adapters one at a time behind the same contract:

1. Codex;
2. Claude;
3. Gemini;
4. AGY/Antigravity.

For each adapter:

```text
adapter fixture RED
-> minimal parser GREEN
-> contract suite
-> integration fixture
-> performance check
```

Do not copy source-specific semantics into the domain core.

### Phase 6 — Meaningful-event capture over the same pipeline

Only after bootstrap/reconciliation governance is stable, route new-session meaningful events through the same evidence/candidate/governance path.

Initial event classes should stay narrow:

```text
decision
constraint
verified_result
failed_attempt
current_goal
next_action
unresolved_issue
```

This closes the architecture:

```text
historical L1 bootstrap ----+
                            +--> one governed ingestion pipeline --> L2
ongoing meaningful capture -+
```

### Phase 7 — Dogfood, replay, and expand

Use normal development workflows to discover missing scenarios. Each important failure should become:

```text
real failure
 -> minimized replay fixture
 -> RED regression
 -> fix
 -> permanent CI protection
```

Dogfooding is discovery. Deterministic replay is validation.

## Explicit non-goals for this priority cycle

Do not add these merely because related systems use them:

- graph database as a required dependency;
- embedding/vector retrieval on the normal startup path;
- LLM interpretation of every historical session during first start;
- autonomous deletion of raw evidence;
- agent-preference-based conflict resolution;
- full L2 mirroring into agent-native L1;
- background consolidation architecture without a measured need;
- broad MCP expansion before the ingestion core is stable.

## Definition of Done for Bootstrap/Reconciliation v1

The priority cycle is complete when all applicable conditions are met:

- the 12 golden scenarios pass deterministically;
- EMPTY bootstrap is bounded;
- FIRST imports only repository-relevant evidence;
- EXISTING unchanged input is an inexpensive no-op;
- repeated/import-resume execution is idempotent;
- duplicate L1 claims consolidate rather than multiply memories;
- conflict never silently overwrites verified state;
- stale/historical evidence is distinguishable from current state;
- provenance can identify agent/source/session and relevant repository/HEAD hints;
- insufficient evidence can abstain or produce `needs_review`;
- real adapters satisfy the same contract tests;
- p50/p95 benchmark results and startup breakdowns are recorded;
- ordinary SessionStart remains bounded and fail-open;
- meaningful-event capture can reuse the same governed ingestion interface without redesigning the core.

## Reference index

### Academic / benchmark

1. Sumers, Yao, Narasimhan, Griffiths. **Cognitive Architectures for Language Agents (CoALA)**. https://arxiv.org/abs/2309.02427
2. Park et al. **Generative Agents: Interactive Simulacra of Human Behavior**. https://arxiv.org/abs/2304.03442
3. Wu et al. **LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory**. https://arxiv.org/abs/2410.10813
4. LongMemEval reference implementation/data. https://github.com/xiaowu0162/LongMemEval
5. Chhikara et al. **Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory**. https://arxiv.org/abs/2504.19413
6. Packer et al. **MemGPT: Towards LLMs as Operating Systems**. https://arxiv.org/abs/2310.08560
7. Shinn et al. **Reflexion: Language Agents with Verbal Reinforcement Learning**. https://arxiv.org/abs/2303.11366
8. **A-MEM**. https://arxiv.org/abs/2502.12110
9. **MemGuard**. https://arxiv.org/abs/2605.28009
10. **Agentic Memory / AgeMem**. https://arxiv.org/abs/2601.01885

### Systems / implementation references

11. Graphiti — open-source temporal context graph engine. https://github.com/getzep/graphiti
12. Zep Graph Overview. https://help.getzep.com/graph-overview
13. Zep Key Concepts / fact invalidation. https://help.getzep.com/v2/concepts
14. AgentMemory — local persistent memory for coding agents. https://github.com/jayzeng/agentmemory
15. claude-memory-skill — minimal hierarchical coding-agent memory. https://github.com/hanfang/claude-memory-skill

### Internal project references

16. `docs/research/README.md`
17. `docs/DEVELOPMENT.md`
18. `docs/ARCHITECTURE-v0.2.md`
19. `docs/schema-v2.md`
20. `docs/benchmark-plan.md`
21. `docs/USAGE-SCENARIOS.md`

## Decision summary

The next major development target should be described as:

> **L1 -> Governed L2 Ingestion Pipeline v1**

not merely "L1 bootstrap".

The same core must support:

```text
EMPTY      -> bounded BOOTSTRAP
FIRST      -> repository-targeted ONBOARD
EXISTING   -> incremental RECONCILE
PARTIAL    -> idempotent RESUME_INGEST
```

Once this core is proven through deterministic TDD and performance regression tests, ongoing meaningful-event capture should be added as another input source to the same governance pipeline rather than as a separate memory subsystem.
