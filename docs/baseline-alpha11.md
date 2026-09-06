# v0.2.0-alpha.11 Continuity Baseline

This document records the first reproducible performance baseline for the current `memcarry` architecture.

It is **not a competitive benchmark, performance promise, or release gate**. The purpose is to freeze the current level before optimizing for practical multi-agent coding workflows, so later changes can be judged against the same usage-shaped scenarios.

## Environment

First recorded run:

```text
GitHub Actions hosted runner
Ubuntu 24.04 / x86_64
Python 3.12.14
4 logical CPUs reported
warmup: 5
in-process iterations: 30
hook subprocess iterations: 10
context token budget: 1000
```

Run: `34027235196`
Commit containing the isolated benchmark fixture: `dcd0c424d89d69d4eec057d102256141e5f6a59f`

Because hosted runners are noisy, p50 is the main directional signal. p95 is recorded to expose tail behavior, not to make a latency guarantee.

## What is measured

Two layers are intentionally separated:

1. **In-process continuity path** — Git inspection + repository/session state + SQLite retrieval where required + governance/projection.
2. **SessionStart hook subprocess** — the full real hook command including Python process startup and the in-process path.

The corpus contains repository/worktree/branch/global memories plus unrelated foreign-repository noise. Superseded and quarantined records are present and excluded by normal retrieval rules.

## Baseline results

### 1,000 memories

Database size: about **428 KiB**.

| Scenario | p50 | p95 | Context |
| --- | ---: | ---: | ---: |
| NO_RECALL | 6.991 ms | 7.600 ms | 0 tokens |
| Resume prompt | 8.194 ms | 17.166 ms | 270 tokens / 8 items |
| Cross-agent handoff prompt | 7.789 ms | 38.995 ms | 270 tokens / 8 items |
| SessionStart onboarding | 6.886 ms | 7.505 ms | 410 tokens / 12 items |
| SessionStart resume | 6.806 ms | 7.222 ms | 270 tokens / 8 items |
| Stale-HEAD resume | 7.202 ms | 19.147 ms | 291 tokens / 8 items |
| Codex SessionStart hook | 72.266 ms | 76.086 ms | 1,222 context bytes |
| Claude clear hook | 71.294 ms | 75.671 ms | 1,222 context bytes |
| Gemini startup hook | 71.913 ms | 74.500 ms | 1,795 context bytes |

### 10,000 memories

Database size: about **3.90 MiB**.

| Scenario | p50 | p95 | Context |
| --- | ---: | ---: | ---: |
| NO_RECALL | 6.006 ms | 6.464 ms | 0 tokens |
| Resume prompt | 17.072 ms | 61.439 ms | 275 tokens / 8 items |
| Cross-agent handoff prompt | 16.875 ms | 21.252 ms | 275 tokens / 8 items |
| SessionStart onboarding | 8.776 ms | 20.010 ms | 422 tokens / 12 items |
| SessionStart resume | 8.669 ms | 20.769 ms | 283 tokens / 8 items |
| Stale-HEAD resume | 8.856 ms | 43.677 ms | 344 tokens / 8 items |
| Codex SessionStart hook | 72.696 ms | 75.684 ms | 1,263 context bytes |
| Claude clear hook | 74.415 ms | 76.296 ms | 1,263 context bytes |
| Gemini startup hook | 74.291 ms | 76.172 ms | 1,830 context bytes |

## Initial interpretation

The first baseline supports the current architecture direction:

- **NO_RECALL remains effectively independent of archive size** at this scale. It still performs cheap repository/state work, but skips memory retrieval and projection.
- **SessionStart scope-browse is inexpensive**: roughly 6.8 ms at 1k and 8.7 ms at 10k in-process.
- **Prompt lexical retrieval is the scale-sensitive path**: resume/handoff rises from roughly 8 ms to roughly 17 ms p50 when moving from 1k to 10k memories.
- **The real hook is dominated by process/startup overhead rather than retrieval**: approximately 71–72 ms at 1k and 73–74 ms at 10k.
- **Projected context remains bounded**: resume/handoff stays at 8 items and about 270–344 estimated tokens; onboarding stays at 12 items and about 410–422 tokens.
- p95 spikes on several in-process scenarios show shared-runner scheduling noise and/or occasional Git/SQLite tail latency. These should be studied with local repeated runs before adding hard thresholds.

## Practical specialization implications

The project is not trying to reproduce every capability of general memory platforms. This baseline highlights where practical coding-agent specialization can pay off:

```text
user-visible startup latency
  → reduce hook/Python/Git process overhead

large archive prompt recall
  → improve scope metadata indexing / FTS candidate narrowing

normal SessionStart continuity
  → preserve bounded scope browse + deterministic projector

irrelevant tasks
  → preserve NO_RECALL fast path
```

The highest-priority optimization should therefore be chosen from measured real workflow cost, not from feature parity with other memory systems.

## Reproduce locally

```bash
python3 benchmarks/continuity_baseline.py \
  --sizes 1000,10000 \
  --warmup 5 \
  --iterations 30 \
  --subprocess-iterations 10 \
  --output benchmark-results.json
```

CI uploads `benchmark-results.json` as the `continuity-benchmark-baseline` artifact. The benchmark job records results but does not currently fail CI based on latency thresholds.

## Next benchmark expansion

Before performance tuning is considered proven, add practical tiers and traces rather than synthetic complexity for its own sake:

- local WSL run on the user's normal development machine;
- 50k/100k archive tier;
- repository with multiple linked worktrees;
- repeated `/clear` / resume loop;
- Agent A → Agent B handoff with persisted memories;
- cold vs warm filesystem/cache runs;
- breakdown of Git inspection, repository-known lookup, FTS/scope browse, projection, JSON checkpoint I/O, and Python startup.
