# Scope-first FTS A/B — alpha.13 experiment

This document records the first controlled A/B experiment between the existing broad FTS path and an experimental scope-first FTS path.

The goal is practical specialization, not a competitive benchmark. The experiment asks one narrow question:

> When coding-agent context already gives us repository/worktree/branch scope, can we intersect that scope inside FTS before lexical ranking and preserve the same results while reducing latency?

## Experiment design

Control:

```text
statement MATCH query
  ↓
join memories
  ↓
scope/lifecycle filtering
  ↓
top-k
```

Experimental path:

```text
(scope token AND statement terms) MATCH
  ↓
join memories
  ↓
defensive scope/lifecycle filtering
  ↓
top-k
```

Each memory receives a tokenizer-safe deterministic token derived from `(scope, scope_ref)`. The experimental FTS table indexes both the statement and that scope token, so SQLite FTS5 can intersect postings before the governed-memory join.

Important safeguards:

- existing `SQLiteMemoryReader` remains the production control;
- experimental reader falls back to the control if scoped FTS is unavailable;
- empty-query SessionStart browse keeps the existing path;
- foreign, superseded, and quarantined memories remain excluded;
- memory-type filtering and scope-rank ordering remain unchanged;
- A/B benchmark exits non-zero if ordered top-k result IDs differ.

## Environment

GitHub Actions hosted runner:

```text
Ubuntu 24.04 / x86_64
Python 3.12
warmup: 5
iterations: 30
query: "architecture implementation"
limit: 8
```

Workflow run: `34028097527`
A/B job: `benchmark-scope-first-ab`
Artifact: `scope-first-fts-ab`

The synthetic corpus intentionally gives many foreign repositories the same lexical terms. This models the scale problem we want to solve: lexical similarity is broad, but repository/worktree scope is already known.

## Results

Ordered top-8 result IDs were identical between broad and scope-first retrieval at every tier.

| Memories | Broad p50 | Scope-first p50 | p50 speedup | Broad p95 | Scope-first p95 | p95 speedup |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1k | 1.781 ms | 0.637 ms | 2.80x | 1.822 ms | 0.661 ms | 2.76x |
| 10k | 13.247 ms | 1.382 ms | 9.59x | 13.859 ms | 1.418 ms | 9.77x |
| 50k | 68.842 ms | 4.044 ms | 17.02x | 76.659 ms | 4.105 ms | 18.68x |
| 100k | 138.777 ms | 7.362 ms | 18.85x | 141.636 ms | 7.504 ms | 18.88x |

The practical scale signal is strong:

```text
100k broad FTS       ≈ 139 ms p50
100k scope-first FTS ≈   7 ms p50
```

At 100k, the experimental retrieval time returns to roughly the same order of magnitude as the small-archive fast path.

## Cost of the first experiment

The first implementation uses a second FTS table so the control and experiment can coexist in the same database. That makes A/B clean, but it is not the desired production storage layout.

| Memories | Scoped FTS build | Extra storage |
| ---: | ---: | ---: |
| 1k | 9.1 ms | 0.23 MiB |
| 10k | 56.3 ms | 2.11 MiB |
| 50k | 316.3 ms | 9.86 MiB |
| 100k | 603.7 ms | 21.10 MiB |

The extra ~21 MiB at 100k is acceptable for an experiment but too expensive to adopt blindly when the same scope-token idea may be integrated into one FTS index.

## Interpretation

The experiment supports the architectural hypothesis:

```text
coding context already knows scope
        ↓
use scope as an indexed retrieval signal
        ↓
intersect before broad lexical candidate expansion
```

This is preferable to adding embeddings or an LLM reranker to solve a problem that deterministic repository/worktree metadata already solves.

The result also strengthens the practical specialization direction of `memcarry`:

- repository/worktree/branch identity is not only correctness metadata;
- it can be a primary performance primitive;
- `NO_RECALL` stays important for irrelevant tasks;
- SessionStart bounded browse remains a separate cheap path;
- semantic fallback can remain exceptional rather than becoming the normal path.

## Adoption decision

**Do not switch the production reader yet.**

Scope-first is promoted from "idea" to "validated optimization candidate", with the following adoption gates:

1. preserve ordered retrieval parity across deterministic fixtures;
2. preserve worktree/repository isolation and governance filters;
3. integrate scope tokens without maintaining a full duplicate statement FTS index if possible;
4. provide non-destructive migration/backfill for existing databases;
5. keep legacy broad/LIKE fallback for compatibility;
6. re-run 1k/10k/50k/100k and real WSL benchmarks after integration;
7. verify write/update/delete synchronization of the chosen FTS layout.

## Reproduce

```bash
python3 benchmarks/scope_first_ab.py \
  --sizes 1000,10000,50000,100000 \
  --warmup 5 \
  --iterations 30 \
  --output scope-first-ab-results.json
```

The CI job uploads the result as `scope-first-fts-ab` and fails if the ordered result IDs diverge.

## Next experiment

Test a storage-efficient **single-index scope-token layout** against both current broad FTS and this two-table scope-first control.

Target:

```text
100k lexical recall: single-digit to low-teens ms p50
ordered top-k parity: 100%
no second full statement index
safe migration/fallback
```
