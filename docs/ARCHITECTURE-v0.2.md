# Architecture v0.2

## Goal

`memcarry` is an agent-independent, evidence-backed, conflict-aware L2 memory layer shared by multiple LLM agents.

The system must be fast enough for normal interactive use, easy enough that users rarely think about memory management, and trustworthy enough that uncertain or conflicting memories are never silently promoted as truth.

## Core design rules

1. **Raw evidence is canonical.** Summaries and memories are indexes over evidence, not replacements for it.
2. **L1 is a cache, not the source of truth.** Claude/Codex/Gemini/Cursor-native memory remains useful, but durable cross-agent state belongs in L2.
3. **Bootstrap existing L1.** A new installation should ingest accessible existing memory/history instead of starting empty.
4. **Progressive disclosure.** Skill metadata is tiny; `SKILL.md` explains access protocol; only relevant context packs are loaded.
5. **Fast path first.** Scope/type filtering + SQLite FTS5/BM25 should answer most recalls without embeddings or LLM calls.
6. **Memory governance is first-class.** Every memory has lifecycle, review state, confidence, scope, type, provenance, and evidence links.
7. **Conflicts are surfaced, not overwritten.** Contradictions remain inspectable until resolved.
8. **Cleaning is reversible.** Suspicious or noisy data is quarantined rather than destroyed.
9. **Lazy extraction.** Import raw/index metadata first; extract structured memories on demand or during low-priority maintenance.
10. **Agent reads, deterministic layer writes.** Agents consume memory; adapters/hooks perform governed writes.

## High-level architecture

```text
                   LLM / Coding Agents
       Claude ─ Codex ─ Gemini ─ Cursor ─ OpenCode ...
                         │
                  Native skill / MCP
                         │
                         ▼
                  Memory Gateway
                  CLI / MCP / hooks
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
      READ              WRITE          BOOTSTRAP
       │                 │                 │
       ▼                 ▼                 ▼
 Retrieval         Ingestion        L1 adapters
       │                 │                 │
 scope/type         normalize          discovery
 FTS5/BM25          dedupe             raw import
 semantic?          contamination      metadata index
 rerank?            temporal check     lazy extract
       │            conflict detect
       └──────────────┬──────────────────┘
                      ▼
                    L2 CORE
              SQLite + filesystem
          ┌───────────┼───────────┐
          │           │           │
       Memory      Evidence    Relations
          │           │           │
          └───────┬───┴───────┬───┘
                  ▼           ▼
              Raw archive   Event ledger
```

## Layer model

### L1 — agent-local memory

Examples:
- current conversation context
- `CLAUDE.md`
- `AGENTS.md`
- `GEMINI.md`
- agent session histories
- native vendor memories available on disk/API

L1 is optimized for immediacy and agent-specific UX.

### L2 — shared trusted memory

L2 stores:
- structured memory records
- evidence records
- raw imported transcripts/files
- relations
- temporal validity
- review/conflict state
- append-only events

L2 is agent-neutral and local-first.

## Retrieval pipeline

```text
query
  ↓
query intent classification (cheap heuristic first)
  ↓
scope/type filter
  ↓
FTS5/BM25
  ↓
confidence/review/lifecycle filters
  ↓
optional semantic fallback
  ↓
optional LLM rerank only when needed
  ↓
compact context pack
```

Default recalls should not require an embedding model or external service.

## Write pipeline

```text
new observation / import
  ↓
raw capture + evidence record
  ↓
normalization
  ↓
exact/near duplicate check
  ↓
contamination/noise check
  ↓
scope/context check
  ↓
temporal update / supersession check
  ↓
conflict detection
  ↓
classification
  ↓
create candidate memory
  ↓
promotion / review policy
```

## Memory governance axes

Do not overload a single `status` field.

### Lifecycle
- `candidate`
- `active`
- `superseded`
- `archived`
- `quarantined`

### Review state
- `verified`
- `unverified`
- `needs_review`
- `conflict`

### Confidence
Floating score `0.0..1.0`, always paired with provenance.

## Memory types

Minimum v0.2 taxonomy:
- `identity`
- `preference`
- `decision`
- `constraint`
- `project_state`
- `episode`
- `lesson`
- `fact`
- `procedure`

Typed memory reduces contamination during retrieval.

## Scope model

A memory may be scoped to one or more dimensions:
- `user`
- `project`
- `repository`
- `task`
- `agent`
- `global`

This avoids false conflicts such as "Python preferred for data scripts" vs "Rust preferred for systems tooling".

## Evidence model

Memory and evidence are separate entities.

```text
Memory
  ├─ Evidence A → raw transcript pointer
  ├─ Evidence B → project file pointer
  └─ Evidence C → explicit user decision
```

Multiple agents repeating the same source must map to the same evidence group rather than artificially increasing confidence.

## Conflict model

When two candidate memories overlap in scope and type, classify the relationship as one of:
- duplicate
- update
- conflict
- different-context

Only true conflicts enter `review_state=conflict`.

## Temporal model

Memories support:
- `valid_from`
- `valid_until`
- `supersedes_memory_id`
- `superseded_by_memory_id`

Temporal updates should preserve historical truth rather than overwrite it.

## Cleaning / quarantine

Cleaning must be reversible.

Suspicious inputs move to `quarantined` with a reason such as:
- low-information observation
- ambiguous context
- possible prompt injection
- duplicated source
- secret/credential-like content
- unsupported inference
- malformed import

Raw evidence remains retained unless the user explicitly purges it.

## Lazy bootstrap

Initial install should be fast:

```text
Discover L1
  ↓
Copy/point raw sources
  ↓
Hash + metadata index
  ↓
Ready for recall
```

Structured extraction happens lazily:

```text
recall query
  ↓
relevant raw session found
  ↓
no structured extraction yet
  ↓
extract only that session/topic
  ↓
cache promoted memory
```

## L2 → L1 projection

Two outputs:

1. **Thin protocol projection**
   - how to call/consult L2
   - conflict warnings
   - review rules

2. **Optional hot cache**
   - small set of frequently used, verified memories
   - bounded size
   - disposable/rebuildable

Never dump the full L2 corpus into agent instruction files.

## Skill design

`SKILL.md` should remain small and describe behavior, not contain memory data.

Core agent behavior:
1. Recall when past context could materially affect the answer or action.
2. Prefer `active + verified` memories.
3. Surface `needs_review` and `conflict` states explicitly.
4. Inspect evidence before high-impact decisions.
5. Do not directly mutate memory storage outside the governed write API.

## Interfaces

### CLI
- `init`
- `bootstrap`
- `recall`
- `inspect`
- `status`
- `review`
- `resolve`
- `doctor`

### MCP
Minimal tool set:
- `memory.recall`
- `memory.inspect`
- `memory.propose`
- `memory.status`

### Hooks/adapters
Per-agent adapters should support only capabilities actually available on that platform.

## Non-goals for v0.2

- always-on cloud service
- mandatory vector database
- mandatory external LLM for every write
- silently rewriting all agent-native memories
- deleting ambiguous data automatically
- pretending inaccessible vendor memory is importable

## Main influences

The design intentionally combines:
- progressive-disclosure Agent Skills
- shared MCP/hook memory servers
- agent-reads/plugin-writes architecture
- staged/reviewable memory updates
- typed-memory contamination control
- long-session temporal/update benchmarks
- hierarchical L1/L2 memory

The differentiator remains: **trusted shared memory, not merely persistent memory.**
