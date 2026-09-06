# Memcarry

**AI가 바뀌어도, 작업은 이어진다.**

Current development baseline: **v0.2.0-alpha.18**

[실전 사용 시나리오](docs/USAGE-SCENARIOS.md) · [기존 설치 전환](docs/MIGRATION-MEMCARRY.md) · [검증 기록](docs/VALIDATION.md)

`memcarry` is a local-first shared L2 memory and continuity layer for AI coding agents. It is specialized for practical coding workflows: fast resume, repository/worktree/HEAD correctness, bounded context, persisted cross-agent handoff, and minimal manual memory commands.

Raw evidence is canonical. Governed memories and summaries are rebuildable indexes/projections over that evidence.

Memcarry means **Memory + Carry**: keep useful decisions, evidence, and progress, then carry relevant context into the next task. It is an independent local-first continuity layer with its own scoped package and CLI identity.

## One-command install

Until the scoped npm package is published, npm 12+ must explicitly opt in to Git-backed package fetching for that command:

```bash
npx --allow-git=all -y github:al-hub/memcarry install
```

Selected agents only:

```bash
npx --allow-git=all -y github:al-hub/memcarry install --agents codex,claude
```

Status / uninstall:

```bash
npx --allow-git=all -y github:al-hub/memcarry status
npx --allow-git=all -y github:al-hub/memcarry uninstall
```

After npm publication the intended form is:

```bash
npx -y @al-hub/memcarry@latest install
```

The installer copies a stable runtime to `~/.memcarry/runtime`, initializes the local store, and configures Codex / Claude / Gemini SessionStart hooks plus an Antigravity CLI (`agy`) plugin without replacing unrelated settings. Memory data survives runtime upgrades/uninstall.

Existing installations: see the migration guide before changing the storage path. No legacy data is silently moved, merged, or deleted.

## Target experience

Users should normally work as usual:

```text
"이어서 구현해줘."
"아까 하던 성능 분석 계속해."
```

Agent changes are also persisted automatically:

```text
Codex works in repo/worktree
  ↓
checkpoint records last agent = codex
  ↓
Claude starts in the same repo/worktree
  ↓
HANDOFF selected automatically
  ↓
Claude receives bounded governed L2 context
```

No separate handoff database is introduced; governed L2 memory remains the durable source.

Explicit requests such as “memcarry에 결정과 이유를 남겨줘” are supported through the skill's durable-write instructions.
They are not magic parser keywords: the agent must execute a write and confirm it. SessionStart saves continuity observations, not every conversation or task update.

Continuity modes:

```text
NO_RECALL | RECALL | ONBOARDING | RESUME | HANDOFF
```

Visibility precedence:

```text
task > worktree > branch > repository > global
```

Repository-local refs are repository-qualified. If HEAD changes, volatile `project_state` is marked `STALE_HEAD` and must be revalidated; stable decisions/constraints may remain useful.

## Hook-native continuity

Installed hooks run:

```text
python3 ~/.memcarry/runtime/scripts/session_start_hook.py --agent <agent>
```

AGY uses its native plugin hook format at `~/.gemini/antigravity-cli/plugins/memcarry/` and injects bounded context on the first `PreInvocation`.

Modes depend on repository knowledge, checkpoint compatibility, agent identity, and lifecycle payload.
Known-repository startup can onboard; reset/resume can resume; agent changes can hand off.
Client support determines which events actually invoke SessionStart. A configured hook is not proof that a client executed or consumed it.
Compatible fresh clones resume when repository ID and HEAD/branch match; linked worktrees do not use that fallback.

Hooks are fail-open: memory failure must never block the coding agent itself.

SessionStart normally has no user query, so it uses bounded visible-scope browse instead of lexical FTS. Prompt-facing continuity uses scope-first FTS.

## Scope-first FTS

Production prompt recall uses one FTS5 index:

```text
memory_fts(id, statement, scope_key)
```

`scope_key` is a deterministic token derived from `(scope, scope_ref)`. Visible scope postings and lexical postings are intersected inside FTS5 before governed-memory filtering.

Three-way validation preserved identical ordered top-8 results at every measured tier:

| Memories | Broad p50 | Two-index p50 | Single-index p50 | Single speedup | Single extra storage |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1k | 1.032 ms | 0.344 ms | 0.324 ms | 3.19x | 0.03 MiB |
| 10k | 9.142 ms | 0.877 ms | 0.811 ms | 11.27x | 0.33 MiB |
| 50k | 42.121 ms | 2.502 ms | 2.449 ms | 17.20x | 0.46 MiB |
| 100k | 85.547 ms | 4.494 ms | 4.450 ms | **19.22x** | **3.02 MiB** |

A legacy two-column FTS is non-destructively rebuilt from canonical `memories`. Compatibility writes are tracked through a small dirty-row table and repaired before prompt recall.

## Real-machine benchmark

Run the packaged benchmark without cloning:

```bash
npx --allow-git=all -y github:al-hub/memcarry benchmark --quick
```

Full 1k / 10k / 50k / 100k run:

```bash
npx --allow-git=all -y github:al-hub/memcarry benchmark
```

It records:

- WSL / kernel / CPU / RAM / filesystem metadata;
- Python / Node / Git / SQLite / FTS5 versions;
- warm in-process NO_RECALL / Resume / Handoff;
- fresh-process NO_RECALL / Resume / Handoff;
- real Codex / Claude / Gemini SessionStart and AGY PreInvocation hook latency;
- startup/import/composition phase breakdown;
- p50 / p95 and a JSON report.

Default report: `./memcarry-benchmark.json`.

Synthetic fixtures are temporary and do not populate the real memory DB. `fresh-process` means a new Python interpreter per request; it does not flush the OS page cache.

## Measured WSL reference

Two real WSL machines were measured at alpha.16 before the alpha.17 E2E/startup work:

| 100k memories | PC-01 | PC-02 |
| --- | ---: | ---: |
| Warm NO_RECALL p50 | 16.32 ms | 20.15 ms |
| Warm Resume p50 | 24.29 ms | 35.18 ms |
| Warm Handoff p50 | 22.30 ms | 34.56 ms |
| Fresh Resume p50 | 89.34 ms | 218.23 ms |
| Fresh Handoff p50 | 90.90 ms | 233.70 ms |
| Codex hook p50 | 118.03 ms | 248.51 ms |

The key scale result is that archive size increased 100x from 1k to 100k while warm resume/handoff rose only about 1.5x on both machines. Fresh-process differences were dominated by machine/process startup rather than FTS scaling.

## Startup diagnosis

A dedicated startup benchmark showed on GitHub Actions (Python 3.12.14):

| Phase | p50 |
| --- | ---: |
| empty Python process | 11.08 ms |
| import `sqlite3` | 16.52 ms |
| import compatibility session adapter | 34.70 ms |
| import hook command | 70.99 ms |
| build continuity after imports | 0.67 ms |
| Git inspect after imports | 8.93 ms |
| scope-index check after imports | 0.60 ms |

This isolates the main fresh-process cost to Python/import startup rather than continuity composition or FTS maintenance.

Two bounded optimizations were tested: separating SessionStart from prompt-only FTS migration, and separating a lightweight SessionStart protocol from the compatibility dataclass/Enum adapter. They improved structural isolation but did **not** produce a repeatable fresh-process wall-time win on hosted runners, so alpha.17 deliberately avoids adding a more duplicated daemon/fast-path architecture without stronger evidence.

Detailed record: [alpha.17 continuity E2E + startup diagnosis](docs/continuity-e2e-startup-alpha17.md).

## Real Git multi-worktree validation

CI now creates actual Git worktrees and verifies:

- shared repository memory is visible in each worktree;
- worktree-scoped state does not leak across worktrees;
- checkpoints are separate per worktree;
- a HEAD change in one worktree marks only that worktree stale;
- stale `project_state` receives a revalidation warning.

## Memory governance

Memory claims and evidence are separate:

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
~/.memcarry/
  memory.db
  events.jsonl
  continuity-state.json
  raw/
  runtime/
```

Compatibility storage/governance commands remain available in `scripts/memcarry_store.py`.

## v0.2.0-alpha.18 status

Implemented and tested:

- governed Memory/Evidence/raw-source groundwork;
- canonical repository/worktree/branch/HEAD identity;
- repository-qualified scope isolation;
- deterministic continuity gate and bounded projector;
- production single-index scope-first FTS with non-destructive migration;
- Codex / Claude / Gemini SessionStart adapters and fail-open hook behavior;
- persisted last-agent checkpoint and automatic Codex → Claude → Gemini HANDOFF selection;
- real Git multi-worktree isolation/resume/stale-HEAD E2E;
- WSL/toolchain/filesystem practical benchmark;
- fresh-process startup/import/composition breakdown;
- Python 3.10 / 3.12 / 3.13 and Node CI;
- ordered-result parity / scale benchmark artifacts.
- compatible fresh-clone Resume, distinct from linked worktrees;
- Memcarry product/skill/package/module naming and explicit legacy store compatibility;
- custom-home hook execution and mixed-group hook preservation regression tests.

## Performance records

- [First 1k/10k baseline](docs/baseline-alpha11.md)
- [1k–100k scale + phase breakdown](docs/baseline-alpha12-scale.md)
- [Two-index scope-first A/B](docs/scope-first-fts-ab-alpha13.md)
- [Single-index three-way + production adoption](docs/scope-first-single-index-alpha15.md)
- [Continuity E2E + startup diagnosis](docs/continuity-e2e-startup-alpha17.md)
- [Benchmark plan](docs/benchmark-plan.md)

## Next work

Development remains driven by practical usage:

1. use alpha.18 in normal Codex / Claude / Gemini workflows and collect real handoff failures rather than inventing more memory features;
2. add meaningful-event capture only after durable-write policy is proven against real usage;
3. optimize SessionStart further only if repeated WSL startup breakdowns show a stable, actionable target;
4. add semantic fallback/MCP only where measured workflows justify them.

`worktree-context` migration/archive work is intentionally outside the current `memcarry` plan.

## Safety / privacy

Memory is local by default. Raw conversations are never uploaded implicitly. External extraction, if added later, must be opt-in/configured.

## License

MIT
