# Architecture

## Goal

`agent-memory-hub` is an agent-independent L2 memory layer. It does not replace each model/agent's L1 context. It bootstraps from accessible L1 sources, governs the resulting memories, and returns small context packs on demand.

## Layers

```text
L0  raw evidence / imported source copies
L1  observations extracted from sessions/files
L2  governed memories (facts, decisions, preferences, lessons, project state)
L3  topic/project summaries (planned)
L4  global memory map (planned)
```

The authoritative evidence is L0 plus the append-only event history. Higher layers are derived interpretations and indexes.

## L1 -> L2 ingestion

```text
accessible L1 source
  -> normalize
  -> raw snapshot
  -> chunk / observation
  -> exact dedupe
  -> governance status
  -> L2
```

v0.1 deliberately imports text chunks as `needs_review`. Automatic LLM-based promotion is not trusted yet.

Future consolidation should perform:

1. semantic duplicate grouping;
2. noise filtering;
3. ambiguity detection;
4. temporal replacement detection;
5. conflict candidate detection;
6. evidence-group aware confidence updates;
7. promotion/rejection.

## Memory governance

Every durable memory includes:

- type;
- status;
- confidence;
- context quality;
- source agent/type/pointer/hash;
- optional evidence group;
- optional temporal validity;
- relations to other memories.

Statuses:

```text
candidate -> confirmed -> superseded
    |            |
    +-> needs_review
    +-> conflict <-+
    +-> rejected
confirmed -> stale
```

`conflict` means the hub cannot safely choose a winner. `superseded` means a newer value intentionally replaced the older value and is not necessarily a contradiction.

## Provenance and evidence groups

Multiple agents can repeat the same underlying source. Those repetitions are not independent evidence. `evidence_group` identifies a common source so future confidence aggregation does not triple-count it.

## Retrieval

The latency-oriented path is:

```text
metadata filters -> SQLite FTS5/BM25 -> small context pack
```

A semantic vector/reranker path is intentionally deferred and should remain a fallback for fuzzy queries rather than the default for every recall.

## L2 -> L1 projection

Do not copy the entire L2 store into `AGENTS.md`, `CLAUDE.md`, or `GEMINI.md`. Future projection adapters should write only thin instructions such as:

```text
When a task depends on prior decisions or project history, query agent-memory-hub.
Treat conflict/needs_review/stale memories as warnings and inspect provenance when needed.
```

This keeps agent startup context small and prevents L2 growth from consuming model context windows.

## Sync model

L2 is the integration point, not a last-writer-wins synchronization file.

```text
Agent A L1 --\
Agent B L1 ----> L2 ingest/governance ----> thin agent-specific projection
Agent C L1 --/
```

The desired long-term loop is:

```text
bootstrap -> capture -> consolidate -> recall -> resolve -> project
```

## Data layout

```text
~/.agent-memory-hub/
  memory.db       # materialized fast index/state
  events.jsonl    # append-only governance history
  raw/            # snapshots of imported evidence
```

The SQLite database is optimized state. Raw evidence and event history allow later verification/reconstruction.
