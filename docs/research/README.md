# Research Notes for agent-memory-hub

This directory records research that directly informs the design of `agent-memory-hub`. It is intentionally implementation-oriented: each paper is mapped to a design decision, a risk, or a benchmark requirement.

Last reviewed: 2026-09-06

## Selected papers

| Work | Why it matters to this project | Design takeaway |
|---|---|---|
| LongMemEval (Wu et al., 2024) | Defines concrete long-term-memory abilities and evaluates indexing/retrieval/reading choices | Benchmark extraction, multi-session reasoning, temporal reasoning, knowledge updates, and abstention; use session/time-aware retrieval |
| Mem0 (Chhikara et al., 2025) | Production-oriented extract/consolidate/retrieve architecture with latency/token measurements | Do not replay full history; compact memory and retrieval should be the normal path |
| A-MEM (Xu et al., 2025) | Dynamically links and evolves memories rather than treating them as isolated chunks | Add typed relations and controlled memory evolution, while preserving evidence/history |
| MemGPT (Packer et al., 2023) | Frames context management as hierarchical/virtual memory | Treat agent-native context as L1 and shared persistent storage as L2; move only useful context into L1 |
| MemGuard (Ha et al., 2026) | Identifies heterogeneous memory contamination | Keep memory types explicit and type-aware at retrieval; quarantine incompatible/noisy material |
| Agentic Memory / AgeMem (Yu et al., 2026) | Models store/retrieve/update/summarize/discard as explicit memory operations | Expose a small memory-operation vocabulary through CLI/MCP/skills; keep governance around autonomous writes |

## Primary references

- LongMemEval: https://arxiv.org/abs/2410.10813
- Mem0: https://arxiv.org/abs/2504.19413
- A-MEM: https://arxiv.org/abs/2502.12110
- MemGPT: https://arxiv.org/abs/2310.08560
- MemGuard: https://arxiv.org/abs/2605.28009
- Agentic Memory (AgeMem): https://arxiv.org/abs/2601.01885

## 1. LongMemEval

**Problem:** Long-running assistants must retrieve the right information across many sessions, reason over time, handle updated facts, and avoid answering when evidence is absent.

The benchmark separates long-term memory into five abilities: information extraction, multi-session reasoning, temporal reasoning, knowledge updates, and abstention. The authors also report useful design techniques such as session decomposition, fact-augmented indexing, and time-aware query expansion.

**For agent-memory-hub:**

- Make these five abilities first-class benchmark categories.
- Preserve session identity and timestamps during L1 bootstrap.
- Distinguish a newer update from a genuine contradiction.
- Include an explicit `no reliable memory found` path instead of forcing recall.
- Add time/scope constraints before expensive semantic retrieval.

## 2. Mem0

**Problem:** Full-history prompting is expensive and slow. Mem0 instead extracts, consolidates, and retrieves salient memories; its evaluation also studies graph memory and practical latency/token costs.

**For agent-memory-hub:**

- Keep compact context packs as the normal output.
- Avoid loading the complete RAW archive into an agent context.
- Measure p50/p95 recall latency and context-token size, not only answer accuracy.
- Consolidation is useful, but the hub must retain provenance so consolidation never becomes an irreversible source of truth.
- Graph/relations are useful after a simple retrieval baseline works; do not make a graph database a prerequisite.

## 3. A-MEM

**Problem:** Flat stores do not capture how memories become related or how their contextual interpretation changes. A-MEM uses a Zettelkasten-inspired organization with structured attributes, links, and evolving representations.

**For agent-memory-hub:**

- Keep `relations` as a first-class structure (`supports`, `conflicts_with`, `supersedes`, `related_to`, etc.).
- Allow derived memory representations to evolve while keeping RAW evidence immutable.
- Avoid uncontrolled cascading rewrites: changes to an interpretation should produce events/versions rather than silently altering evidence.
- Introduce graph-like retrieval only when it demonstrates measurable benefit over scope/type + FTS5.

## 4. MemGPT

**Problem:** The model context window is a scarce fast-memory tier. MemGPT introduces virtual context management inspired by operating-system memory hierarchies.

**For agent-memory-hub:**

- Formalize agent-native context/memory as **L1** and the shared durable hub as **L2**.
- Initial setup should bootstrap accessible L1 into L2 rather than start empty.
- L2 -> L1 sync should be a thin projection/hot cache, not a full copy.
- Skills should teach the agent how to access L2; they should not contain the full memory corpus.
- Lazy extraction of cold RAW sessions is analogous to paging: pay the expensive interpretation cost only when needed.

## 5. MemGuard

**Problem:** Semantically similar memories can have different functional roles. Mixing stable facts, episodic events, and behavioral rules in one undifferentiated retrieval pool can contaminate reasoning. MemGuard addresses this with type-aware memory construction and retrieval.

**For agent-memory-hub:**

- Keep explicit memory types such as `identity`, `preference`, `decision`, `constraint`, `project_state`, `episode`, `lesson`, `fact`, and `procedure`.
- Type/scope filtering belongs before broad retrieval.
- Cleaning should usually quarantine rather than destroy evidence.
- Benchmark contamination: inject semantically similar but functionally incompatible memories and verify they are not treated as interchangeable evidence.
- Treat type classification uncertainty as reviewable metadata rather than silently forcing a category.

## 6. Agentic Memory / AgeMem

**Problem:** Long-term and short-term memory management can be represented as actions the agent learns or chooses: storing, retrieving, updating, summarizing, and discarding.

**For agent-memory-hub:**

Use a small stable operation vocabulary:

```text
recall
propose/store
update/supersede
summarize/consolidate
archive/quarantine
inspect-evidence
```

However, autonomous memory operations must not bypass governance. Durable writes should carry provenance, review state, confidence, and an event-log entry. `discard` should normally mean archive/quarantine, not irreversible RAW deletion.

## Cross-paper synthesis

The papers converge on a practical architecture:

```text
Agent L1
   |
   | thin skill / MCP / hook
   v
Memory Gateway
   |
   +--> type + scope + temporal filtering
   |        |
   |        +--> FTS5/BM25 fast path
   |        +--> semantic/rerank fallback only when needed
   |
   +--> governed write pipeline
            |
            +--> dedupe
            +--> contamination check
            +--> update-vs-conflict classification
            +--> provenance/evidence
            +--> lifecycle + review state + confidence
            v
          L2 store
          /      \
     Memory      Evidence/RAW
          \      /
          Event ledger
```

## Decisions for v0.2

1. **Evidence is canonical; memory is an interpretation/index.** RAW sources and evidence must survive memory consolidation or supersession.
2. **Bootstrap first, understand lazily.** Initial L1 migration should hash/index RAW data quickly; extraction is performed on-demand for relevant cold sessions.
3. **Typed retrieval before semantic retrieval.** Scope/type/time filters + FTS5/BM25 are the default fast path.
4. **Govern memory writes.** Separate lifecycle (`candidate/active/superseded/archived/quarantined`) from review state (`verified/unverified/needs_review/conflict`) and confidence.
5. **Conflict is not overwrite.** Preserve competing evidence and distinguish true conflict from temporal update or different context/scope.
6. **L1 remains thin.** Agent instruction files contain access protocol and optionally a tiny hot cache, never the whole L2 corpus.
7. **Semantic/vector retrieval is optional.** Add it only after benchmarks show a meaningful recall gap that the fast path cannot solve.
8. **Abstention is success when evidence is insufficient.** A memory system must know when not to claim a remembered fact.

## Benchmark implications

The implementation benchmark should include:

- exact/single-session recall
- multi-session synthesis
- temporal ordering and historical-state questions
- knowledge updates and supersession
- true conflict vs different-scope discrimination
- heterogeneous-memory contamination
- duplicate evidence from multiple agents
- missing-evidence abstention
- provenance correctness
- cold-source lazy extraction
- cross-agent handoff
- context-pack token budget
- p50/p95 retrieval latency

See `../benchmark-plan.md` for the project-specific benchmark plan.

## Research guardrails

These papers are design evidence, not specifications. Reported benchmark gains are specific to their experimental setups and should not be copied as expected project performance. `agent-memory-hub` should validate each added mechanism against its own benchmark before accepting the added complexity.
