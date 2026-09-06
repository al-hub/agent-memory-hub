# v0.2.0-alpha.12 Practical Scale Baseline

This document extends the first continuity baseline to practical scale tiers and decomposes the read path into isolated diagnostic phases.

It is **not a competitive benchmark, performance promise, or CI latency gate**. Its purpose is to freeze the current implementation before optimization for real coding-agent usage.

## Environment

Recorded run:

```text
GitHub Actions hosted runner
Ubuntu 24.04 / x86_64
Python 3.12.14
warmup: 5
in-process iterations: 30
hook subprocess iterations: 10
context token budget: 1000
```

Run: `34027605543`
Commit: `c18706b6fdd173fb96f9e1de06a7d8b16092e3ee`

`p50` is the median latency: 50% of runs complete at or below that value.
`p95` is the tail indicator: 95% of runs complete at or below that value.

Because hosted runners are noisy, these values should be compared directionally and reproduced on the normal WSL development machine before hard thresholds are introduced.

## End-to-end scenario baseline

| Memories | NO_RECALL p50/p95 | Resume p50/p95 | Handoff p50/p95 | SessionStart resume p50/p95 | Codex hook p50/p95 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1k | 8.63 / 9.67 ms | 11.41 / 13.68 ms | 10.94 / 11.30 ms | 9.51 / 9.81 ms | 90.92 / 93.07 ms |
| 10k | 8.54 / 8.78 ms | 21.89 / 22.47 ms | 21.98 / 22.49 ms | 11.85 / 12.39 ms | 92.57 / 95.78 ms |
| 50k | 8.58 / 8.92 ms | 78.00 / 78.81 ms | 77.71 / 82.51 ms | 21.81 / 22.72 ms | 103.14 / 104.78 ms |
| 100k | 8.49 / 8.66 ms | 146.37 / 149.18 ms | 146.16 / 146.92 ms | 35.22 / 36.39 ms | 117.76 / 120.25 ms |

The Claude clear and Gemini startup hook paths track the Codex hook closely across all tiers.

## Isolated phase baseline

These timings are **diagnostic and not additive**. Each phase is measured independently with normal local I/O behavior.

| Phase | 1k p50 | 10k p50 | 50k p50 | 100k p50 |
| --- | ---: | ---: | ---: | ---: |
| Python startup | 10.79 ms | 10.83 ms | 11.07 ms | 10.90 ms |
| Git inspect | 7.96 ms | 8.04 ms | 8.08 ms | 8.01 ms |
| Repository-known lookup | 0.214 ms | 0.164 ms | 0.171 ms | 0.169 ms |
| Checkpoint load | 0.024 ms | 0.024 ms | 0.024 ms | 0.024 ms |
| Checkpoint save | 0.188 ms | 0.204 ms | 0.215 ms | 0.207 ms |
| SQLite scope browse | 0.637 ms | 2.851 ms | 12.668 ms | 25.279 ms |
| SQLite FTS recall | 1.873 ms | 12.919 ms | 67.874 ms | 135.944 ms |
| Context projection | 0.086 ms | 0.086 ms | 0.086 ms | 0.086 ms |

## Interpretation

### 1. NO_RECALL is scale-stable

The no-recall path stays near 8.5 ms from 1k through 100k memories. That validates the design choice to gate retrieval before touching the archive.

### 2. Governance/projection is not the bottleneck

Repository-known lookup, checkpoint I/O, and context projection remain sub-millisecond. There is currently no reason to complicate those components for performance.

### 3. Git inspection is a meaningful fixed cost

Git inspection is about 8 ms and does not grow with memory count. It matters for the real hook path, but it is not the scale problem.

### 4. Python startup is another fixed cost

A minimal Python process costs about 11 ms on this runner. The full hook is therefore expected to have a substantial fixed floor even before application work.

### 5. FTS recall is the primary scale-sensitive path

Prompt-based FTS recall grows almost linearly in this synthetic corpus:

```text
1k      ~1.9 ms
10k    ~12.9 ms
50k    ~67.9 ms
100k  ~135.9 ms
```

This explains the resume/handoff growth at large tiers. The benchmark deliberately contains many foreign-repository rows that share query terms, exposing the cost of applying scope constraints after broad FTS candidate matching.

The next optimization should therefore investigate **scope-first candidate narrowing / indexing**, not semantic retrieval, LLM reranking, or a larger runtime.

### 6. SessionStart browse scales better than prompt FTS

SessionStart uses bounded visible-scope browse instead of lexical matching. It rises from about 9.5 ms at 1k to about 35 ms at 100k end-to-end in-process, substantially better than prompt FTS recall but still showing that visible-scope selection should be indexed for large archives.

### 7. Real hook latency remains acceptable but no longer flat at 100k

The Codex hook rises from about 91 ms at 1k to about 118 ms at 100k. Most fixed overhead still comes from Python/Git/process composition, while the archive-dependent portion increasingly comes from SQLite scope browsing.

## Practical specialization direction

The measured priority order is now:

```text
1. preserve NO_RECALL gate
2. make scope narrowing cheap before FTS ranking
3. preserve bounded SessionStart browse
4. avoid optimizing projector/governance prematurely
5. only then consider reducing Python/Git fixed startup overhead
```

This matches the project goal: optimize the workflows real coding agents hit repeatedly rather than maximizing general memory-platform feature count.

## Reproduce locally

```bash
python3 benchmarks/continuity_baseline.py \
  --sizes 1000,10000,50000,100000 \
  --warmup 5 \
  --iterations 30 \
  --subprocess-iterations 10 \
  --output benchmark-results.json
```

CI stores the JSON as the `continuity-benchmark-baseline` artifact and does not fail builds based on latency values.

## Next measurement

Before implementing the first performance optimization, reproduce this benchmark on the normal WSL machine and then add a focused experiment comparing:

1. current FTS-first query;
2. scope-qualified candidate table/index then FTS;
3. repository-partitioned or scope-indexed alternatives.

The optimization should be accepted only if it improves 50k/100k latency without materially harming 1k/10k latency, correctness, worktree isolation, or token budget.
