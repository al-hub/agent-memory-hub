# Benchmark Plan

## Purpose

The benchmark suite should test whether `agent-memory-hub` is not only persistent, but useful, fast, and trustworthy across agents and long-running sessions.

The plan borrows practical evaluation dimensions from long-term memory research while adding governance-specific tests that matter for this project.

## Primary evaluation dimensions

### 1. Information extraction

Can the system recover a durable fact/decision from one relevant historical source?

Example:

```text
Session 12: "Use a separate Rust repository for the optimized version."
Query later: "How did we decide to structure the Rust version?"
```

Measure:
- recall@k
- exact source/evidence recovery
- answer support rate

### 2. Multi-session reasoning

Can the system combine facts across different sessions without loading the whole history?

Measure:
- retrieval coverage across evidence groups
- context-pack size
- end-task correctness

### 3. Temporal reasoning

Can it distinguish old truth from current truth?

Example:

```text
March: prefer Python
September: prefer Rust for systems tooling
```

Measure:
- current-state accuracy
- historical-state accuracy
- supersession accuracy

### 4. Knowledge updates

Can new evidence update or supersede prior memory without destroying history?

Measure:
- update classification accuracy
- preservation of old evidence
- false-conflict rate

### 5. Abstention / uncertainty

Does the system avoid confidently returning unsupported or ambiguous memories?

Measure:
- unsupported-answer rate
- needs-review surfacing rate
- abstention precision/recall

### 6. Contamination resistance

Can irrelevant, malicious, ambiguous, or wrong memories be prevented from dominating retrieval?

Test categories:
- wrong memory type
- unrelated project
- stale decision
- prompt-injection-like content in imported text
- duplicated observations of one source
- secret-like content

Measure:
- contamination hit rate
- quarantine precision/recall
- wrong-scope retrieval rate

### 7. Conflict handling

Can the system distinguish:
- duplicate
- temporal update
- true conflict
- different context

Measure confusion matrix across those four classes.

### 8. Provenance integrity

For every returned memory, can the system point to evidence that actually supports the claim?

Measure:
- provenance coverage
- evidence correctness
- broken pointer/hash rate

### 9. Cross-agent consistency

Run equivalent tasks from multiple supported agents using the same L2.

Measure:
- whether relevant memory is consistently available
- whether agent-specific L1 projection changes the underlying answer materially
- whether one agent can consume memories created/imported from another

### 10. Performance

Record at least:
- bootstrap wall-clock time
- recall p50/p95 latency
- SQLite query time
- context-pack token/byte size
- semantic fallback rate
- optional LLM call rate
- memory DB size

## Fast-path target

For local corpora of ordinary personal/project scale, target:

```text
scope/type filtering + FTS5/BM25 → dominant path
semantic fallback               → minority path
LLM rerank                      → rare path
```

No hard latency promise should be published before reproducible measurements exist.

## Test corpus tiers

### Tier A — deterministic synthetic

Small curated corpus with known answers and conflicts.

Used in CI.

### Tier B — generated long-history corpus

Hundreds/thousands of sessions containing:
- repeated facts
- evolving preferences
- decisions
- conflicting claims
- noise
- ambiguous references
- project switching

Used for scale/regression tests.

### Tier C — anonymized real workflow replay

Opt-in local evaluation from real agent histories, with no upload required.

Used to assess realistic retrieval patterns.

## Core benchmark scenarios

1. **Simple recall** — one exact prior decision
2. **Paraphrased recall** — semantic wording differs
3. **Cross-session merge** — answer requires two sessions
4. **Temporal update** — latest value supersedes prior value
5. **Historical query** — asks what was true at an earlier date
6. **False conflict** — same term but different project/scope
7. **True conflict** — incompatible claims in same scope
8. **Repeated-source inflation** — three agents imported same source
9. **Noise contamination** — transient chatter should not outrank durable memory
10. **Ambiguous context** — memory should remain needs-review
11. **Cold-source lazy extraction** — relevant raw source not yet structured
12. **Cross-agent handoff** — Codex writes/imports, Claude recalls
13. **Quarantine** — suspicious memory excluded by default
14. **Evidence inspection** — returned claim traces to exact source
15. **Context budget** — relevant pack remains bounded despite large archive

## Retrieval metrics

At minimum:
- Recall@1, @3, @5
- MRR
- nDCG@5
- wrong-scope rate
- stale-memory rate
- conflict-miss rate

## Governance metrics

At minimum:
- conflict classification accuracy
- update-vs-conflict accuracy
- quarantine precision/recall
- verified-memory precision
- unsupported promotion rate
- evidence coverage

## Efficiency metrics

At minimum:
- bootstrap seconds per 1k sources
- recall p50/p95
- bytes/tokens loaded per recall
- percentage of recalls requiring semantic fallback
- percentage requiring LLM rerank/extraction

## Regression gates

CI should eventually fail on material regressions such as:
- deterministic Recall@5 drop
- broken migration compatibility
- increase in wrong-scope retrieval beyond threshold
- provenance missing from active/verified memories
- quarantine bypass for known unsafe fixtures
- context-pack size exceeding configured budget

## Baselines

Compare against:

1. full raw-context grep/FTS only
2. v0.1 flat memory schema
3. v0.2 typed/scoped BM25
4. v0.2 + optional semantic fallback
5. selected external memory tools where reproducible locally

The goal is not to win every benchmark. The goal is to identify the simplest architecture that improves correctness/trust without harming interactive latency.

## Research mapping

Use external research mainly as evaluation inspiration rather than blindly copying implementations:

- LongMemEval-style: extraction, multi-session, temporal, updates, abstention
- contamination-focused memory research: typed retrieval and filtering
- Mem0-style: extraction/consolidation/retrieval efficiency
- hierarchical memory work: bounded active context + external memory
- graph/evolving-memory work: relations only where they improve retrieval

## Release criteria for v0.2 implementation

Before calling the architecture successful:

- schema migration is lossless on v0.1 fixtures
- bootstrap is resumable
- cold raw sources are searchable before full extraction
- conflicts never silently overwrite evidence
- active/verified memory always has provenance
- contaminated/quarantined memory is excluded from default recall
- cross-agent context packs are deterministic for the same query/config
- benchmark script produces machine-readable results
