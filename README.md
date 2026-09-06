# agent-memory-hub

**One trusted memory for every AI agent.**

Current development baseline: **v0.2.0-alpha.15**

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

The installer installs the Agent Skill, copies a stable runtime to `~/.agent-memory-hub/runtime`, initializes the local store, and merges SessionStart hooks into Codex / Claude / Gemini configuration. Existing unrelated settings/hooks are preserved. Uninstall removes managed hooks/runtime/skill while preserving memory data.

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
scope-first SQLite FTS / bounded SessionStart scope browse
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

At SessionStart there may be no user prompt, so the system uses bounded visible-scope browse instead of lexical search:

```text
worktree → branch → repository → global
```

## Scope model

Visibility precedence:

```text
task > worktree > branch > repository > global
```

Branch/worktree/task refs are repository-qualified. If repository HEAD changes, volatile `project_state` is demoted and marked `STALE_HEAD`; stable verified decisions and constraints remain available unless independently invalidated.

## Scope-first FTS is now the production recall path

The pre-alpha.15 lexical path matched statement text broadly and applied repository/worktree scope after FTS matching. Synthetic 100k-memory tests showed that foreign repositories sharing the same lexical terms caused recall to grow toward ~100 ms and beyond.

The production layout is now one FTS index:

```text
memory_fts(id, statement, scope_key)
```

`scope_key` is a tokenizer-safe deterministic token derived from `(scope, scope_ref)`. Prompt recall intersects visible scope postings and statement postings inside FTS5 before joining governed memories.

### Three-way validation

Broad FTS, the earlier two-index experiment, and the new single-index layout were measured on identical corpora and queries. Ordered top-8 result IDs were identical at every tier.

| Memories | Broad p50 | Two-index p50 | Single-index p50 | Single speedup | Two-index extra | Single-index extra |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1k | 1.032 ms | 0.344 ms | 0.324 ms | 3.19x | 0.23 MiB | 0.03 MiB |
| 10k | 9.142 ms | 0.877 ms | 0.811 ms | 11.27x | 2.11 MiB | 0.33 MiB |
| 50k | 42.121 ms | 2.502 ms | 2.449 ms | 17.20x | 9.86 MiB | 0.46 MiB |
| 100k | 85.547 ms | 4.494 ms | 4.450 ms | **19.22x** | 21.10 MiB | **3.02 MiB** |

The single-index layout keeps the scope-first speedup while removing most duplicate-index storage.

### Production continuity baseline after adoption

After switching the real continuity composition to the single-index reader:

| Memories | NO_RECALL p50 | Resume p50 | Handoff p50 | SessionStart resume p50 | Codex hook p50 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1k | 9.087 ms | 10.361 ms | 10.228 ms | 9.722 ms | 89.184 ms |
| 10k | 8.651 ms | 10.345 ms | 10.264 ms | 11.989 ms | 93.028 ms |
| 50k | 8.723 ms | 13.256 ms | 12.996 ms | 22.136 ms | 103.489 ms |
| 100k | 8.723 ms | **16.547 ms** | **16.538 ms** | 34.983 ms | 116.151 ms |

The pre-adoption 100k resume/handoff baseline was roughly **146 ms p50**. The production prompt-facing path is now about **16.5 ms p50** while NO_RECALL remains flat.

SessionStart is intentionally different: with no prompt it uses bounded scope browse, so lexical scope-first FTS does not change that path in the same way.

These measurements are reference baselines, not latency guarantees or CI performance gates.

## Non-destructive FTS migration and legacy synchronization

Continuity now calls `ensure_single_index_scope_fts()` before composing the reader.

The governed `memories` table is never rewritten by this migration. A legacy two-column `memory_fts(id, statement)` is rebuildable cache, so it is safely reconstructed as the single scope-aware index.

```text
legacy two-column FTS
  ↓
rebuild FTS only
  ↓
memory_fts(id, statement, scope_key)
```

Compatibility writers can still write the legacy `(id, statement)` shape. Small triggers record changed `memories.rowid` values in `scope_fts_dirty`; the next continuity entry repairs only those dirty FTS rows and handles insert/update/delete. Clean read paths do not rebuild the archive.

If migration cannot run because the store is missing/incompatible/locked, continuity fails safe and the existing broad/LIKE fallback remains available.

## Performance records

Detailed records:

- [First 1k/10k baseline](docs/baseline-alpha11.md)
- [1k–100k scale + phase breakdown](docs/baseline-alpha12-scale.md)
- [Two-index scope-first A/B](docs/scope-first-fts-ab-alpha13.md)
- [Single-index three-way + production adoption](docs/scope-first-single-index-alpha15.md)
- [Benchmark plan](docs/benchmark-plan.md)

Reproduce the production continuity baseline:

```bash
python3 benchmarks/continuity_baseline.py \
  --sizes 1000,10000,50000,100000 \
  --warmup 5 \
  --iterations 30 \
  --subprocess-iterations 10 \
  --output benchmark-results.json
```

Reproduce the three-way comparison:

```bash
python3 benchmarks/scope_first_three_way.py \
  --sizes 1000,10000,50000,100000 \
  --warmup 5 \
  --iterations 30 \
  --output scope-first-three-way-results.json
```

CI uploads both benchmark artifacts. The three-way job fails if ordered result IDs diverge.

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

## v0.2.0-alpha.15 status

Implemented and tested:

- governed Memory/Evidence/raw-source groundwork
- canonical repository/worktree/branch/HEAD identity
- repository-qualified scope isolation
- deterministic Continuity Gate and bounded projector
- conflict/review/stale-HEAD warnings
- Codex / Claude / Gemini SessionStart adapters
- npx install/status/uninstall with persistent runtime
- fail-open hooks
- 1k / 10k / 50k / 100k p50/p95 benchmark harnesses
- scope-first FTS ordered-result parity at every measured tier
- production single-index `memory_fts(id, statement, scope_key)` reader
- non-destructive legacy FTS migration
- dirty-row insert/update/delete synchronization for compatibility writers
- broad/LIKE fallback when scoped FTS is unavailable
- Python 3.10/3.12/3.13 and Node installer CI

## Next work

Development remains driven by practical usage rather than feature parity:

1. reproduce alpha.15 on the normal WSL development machine, including cold/warm runs;
2. add persisted Agent A → Agent B handoff and multi-worktree end-to-end fixtures;
3. migrate/unify the useful `worktree-context` checkpoint semantics into governed `project_state` capture before archiving that separate implementation;
4. add meaningful-event capture only after continuity read behavior remains stable in real use;
5. optimize SessionStart scope browse only if real WSL measurements justify it;
6. add semantic fallback/MCP only where measured workflows justify them.

## Safety / privacy

Memory is local by default. Raw conversations are never uploaded implicitly. External extraction, if added later, must be opt-in/configured.

## License

MIT
