# agent-memory-hub

**One trusted memory for every AI agent.**

Current development baseline: **v0.2.0-alpha.14**

`agent-memory-hub` is a local-first shared L2 memory and continuity layer for AI coding agents. It is specialized for practical coding workflows: fast startup/resume, repository/worktree/HEAD correctness, bounded context, cross-agent handoff, and minimal manual memory commands.

Raw evidence is canonical. Governed memories and summaries are rebuildable indexes/projections over that evidence.

## One-command install

Until the scoped npm package is published:

```bash
npx -y github:al-hub/agent-memory-hub install
```

After npm publication the same CLI contract will be:

```bash
npx -y @al-hub/agent-memory-hub@latest install
```

Install selected agents only:

```bash
npx -y github:al-hub/agent-memory-hub install --agents codex,claude
```

Status / uninstall:

```bash
npx -y github:al-hub/agent-memory-hub status
npx -y github:al-hub/agent-memory-hub uninstall
```

The installer:

```text
installs the Agent Skill
+ copies a stable runtime to ~/.agent-memory-hub/runtime
+ initializes the local store
+ merges SessionStart hooks into Codex / Claude / Gemini config
```

Existing unrelated settings/hooks are preserved. Install is idempotent and config files receive one-time `.agent-memory-hub.bak` backups. Uninstall removes managed hooks/runtime/skill while preserving memory data.

## Target experience

Users should normally work as usual:

```text
"이어서 구현해줘."
"아까 하던 성능 분석 계속해."
"Claude가 하던 작업을 Codex에서 이어서 해."
```

Continuity flow:

```text
SessionStart hook or user request
  ↓
Git repository / worktree / branch / HEAD inspection
  ↓
repository / session / checkpoint state
  ↓
Continuity Gate
  ├─ NO_RECALL
  ├─ RECALL
  ├─ ONBOARDING
  ├─ RESUME
  └─ HANDOFF
  ↓ only when needed
scope-aware SQLite recall / bounded scope browse
  ↓
governance + stale-HEAD handling
  ↓
bounded Context Projector
  ↓
small additionalContext / context pack
```

`NO_RECALL` deliberately skips archive retrieval and projection.

## Hook-native continuity

Installed hooks point to the persistent runtime:

```text
python3 ~/.agent-memory-hub/runtime/scripts/session_start_hook.py --agent <agent>
```

Current SessionStart behavior:

```text
startup  → ONBOARDING when prior repository memory exists
resume   → RESUME
clear    → RESUME even when session id is unchanged
compact  → RESUME where supported
fork     → RESUME where supported
```

Hook failures are fail-open: memory problems must never prevent the coding agent itself from starting.

At SessionStart there may be no user prompt yet, so the system uses bounded visible-scope browse instead of lexical search:

```text
worktree → branch → repository → global
```

## Scope and stale state

Visibility precedence:

```text
task > worktree > branch > repository > global
```

Branch/worktree/task refs are repository-qualified. If repository HEAD changes, volatile `project_state` is demoted and marked `STALE_HEAD`; stable verified decisions and constraints remain available unless independently invalidated.

## Practical performance baseline

The benchmark is a **reference baseline, not a competitive score, latency promise, or CI threshold**. It exists so practical specialization can be judged against measured behavior.

Recorded on a GitHub Actions Ubuntu 24.04 runner with Python 3.12.14, 5 warmups, 30 in-process iterations, and 10 hook subprocess iterations.

### End-to-end p50 / p95

| Memories | NO_RECALL | Resume prompt | SessionStart resume | Codex hook |
| ---: | ---: | ---: | ---: | ---: |
| 1k | 8.63 / 9.67 ms | 11.41 / 13.68 ms | 9.51 / 9.81 ms | 90.92 / 93.07 ms |
| 10k | 8.54 / 8.78 ms | 21.89 / 22.47 ms | 11.85 / 12.39 ms | 92.57 / 95.78 ms |
| 50k | 8.58 / 8.92 ms | 78.00 / 78.81 ms | 21.81 / 22.72 ms | 103.14 / 104.78 ms |
| 100k | 8.49 / 8.66 ms | 146.37 / 149.18 ms | 35.22 / 36.39 ms | 117.76 / 120.25 ms |

`p50` is the median: 50% of runs complete at or below it. `p95` is a tail-latency indicator: 95% of runs complete at or below it.

### Isolated phase p50

These phase timings are diagnostic and **not additive**.

| Phase | 1k | 10k | 50k | 100k |
| --- | ---: | ---: | ---: | ---: |
| Python startup | 10.79 ms | 10.83 ms | 11.07 ms | 10.90 ms |
| Git inspect | 7.96 ms | 8.04 ms | 8.08 ms | 8.01 ms |
| Repository-known | 0.214 ms | 0.164 ms | 0.171 ms | 0.169 ms |
| Checkpoint load | 0.024 ms | 0.024 ms | 0.024 ms | 0.024 ms |
| Checkpoint save | 0.188 ms | 0.204 ms | 0.215 ms | 0.207 ms |
| SQLite scope browse | 0.637 ms | 2.851 ms | 12.668 ms | 25.279 ms |
| SQLite FTS recall | 1.873 ms | 12.919 ms | 67.874 ms | 135.944 ms |
| Projection | 0.086 ms | 0.086 ms | 0.086 ms | 0.086 ms |

The first strong scale signal is clear:

```text
NO_RECALL              stays essentially flat
Git/Python              are fixed costs
state/governance        are negligible
scope browse            grows with archive size
prompt FTS recall       is the primary scale-sensitive path
```

### Scope-first FTS A/B experiment

The first scope-first experiment keeps the existing broad FTS reader as the control and adds a separate experimental FTS index containing a deterministic `(scope, scope_ref)` token. FTS5 can therefore intersect visible scope postings with lexical postings before joining governed memories.

Ordered top-8 result IDs were identical at every measured tier.

| Memories | Broad FTS p50 | Scope-first p50 | p50 speedup | Scope-first extra storage |
| ---: | ---: | ---: | ---: | ---: |
| 1k | 1.781 ms | 0.637 ms | 2.80x | 0.23 MiB |
| 10k | 13.247 ms | 1.382 ms | 9.59x | 2.11 MiB |
| 50k | 68.842 ms | 4.044 ms | 17.02x | 9.86 MiB |
| 100k | 138.777 ms | 7.362 ms | 18.85x | 21.10 MiB |

At 100k memories the experiment reduces lexical retrieval from roughly 139 ms to roughly 7 ms p50 while preserving ordered top-k parity. This validates scope-first retrieval as a strong optimization candidate.

It is **not the production default yet**. The first A/B implementation deliberately maintains a second full FTS index so control and experiment can coexist cleanly. Before adoption, the same scope-token idea should be integrated into a storage-efficient single-index layout with safe migration/backfill.

Detailed records:

- [First 1k/10k baseline](docs/baseline-alpha11.md)
- [1k–100k scale + phase breakdown](docs/baseline-alpha12-scale.md)
- [Scope-first FTS A/B](docs/scope-first-fts-ab-alpha13.md)
- [Benchmark plan](docs/benchmark-plan.md)

Reproduce the control baseline:

```bash
python3 benchmarks/continuity_baseline.py \
  --sizes 1000,10000,50000,100000 \
  --warmup 5 \
  --iterations 30 \
  --subprocess-iterations 10 \
  --output benchmark-results.json
```

Reproduce the A/B experiment:

```bash
python3 benchmarks/scope_first_ab.py \
  --sizes 1000,10000,50000,100000 \
  --warmup 5 \
  --iterations 30 \
  --output scope-first-ab-results.json
```

CI uploads `continuity-benchmark-baseline` and `scope-first-fts-ab`. The A/B job fails if ordered result IDs diverge.

## Memory governance

A memory claim and evidence are separate concepts:

```text
Memory
  ├─ Evidence A → raw transcript/session
  ├─ Evidence B → project file
  └─ Evidence C → explicit user decision
```

Governance axes:

```text
lifecycle:
  candidate | active | superseded | archived | quarantined

review_state:
  verified | unverified | needs_review | conflict

confidence:
  0.0 .. 1.0
```

Conflicts are surfaced rather than silently overwritten. Suspicious/noisy content is quarantined rather than destructively merged.

## Storage

Default local data directory:

```text
~/.agent-memory-hub/
  memory.db
  events.jsonl
  continuity-state.json
  raw/
  runtime/
```

Compatibility storage/governance commands remain available in `scripts/memory_hub.py`.

## v0.2.0-alpha.14 status

Implemented and tested:

- governed Memory/Evidence/raw-source groundwork
- canonical repository/worktree/branch/HEAD identity
- repository-qualified scope isolation
- SQLite FTS5 fast path + bounded SessionStart scope browse
- deterministic Continuity Gate and bounded projector
- conflict/review/stale-HEAD warnings
- Codex / Claude / Gemini SessionStart adapters
- npx install/status/uninstall with persistent runtime
- fail-open hooks
- reproducible p50/p95 practical benchmark harness
- isolated phase timing breakdown
- 1k / 10k / 50k / 100k archive tiers
- experimental `ScopeFirstSQLiteMemoryReader` with safe broad-reader fallback
- scope-token FTS A/B harness with ordered-result parity gate
- measured 2.80x → 18.85x p50 scope-first speedup from 1k → 100k
- machine-readable baseline and A/B benchmark artifacts
- Python 3.10/3.12/3.13 and Node installer CI

## Next work

Development is driven by practical usage rather than feature parity:

1. test a storage-efficient **single-index scope-token FTS layout** against both broad FTS and the validated two-index experiment;
2. require ordered-result parity, worktree/repository isolation, and governance-filter parity before default adoption;
3. add non-destructive scoped-index migration/backfill and write/update synchronization;
4. reproduce 1k–100k results on the normal WSL development machine;
5. add persisted Agent A → Agent B handoff and multi-worktree end-to-end fixtures;
6. add meaningful-event capture only after continuity read-path behavior is stable;
7. add semantic fallback/MCP only where measured workflows justify them.

## Safety / privacy

Memory is local by default. Raw conversations are never uploaded implicitly. External extraction, if added later, must be opt-in/configured.

## License

MIT
