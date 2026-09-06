# Continuity E2E + startup diagnosis — alpha.17

This record closes three practical continuity gaps after the alpha.16 WSL measurements:

1. persisted cross-agent handoff;
2. real Git multi-worktree continuity;
3. fresh-process / SessionStart startup diagnosis and bounded optimization experiments.

## Persisted cross-agent handoff

The continuity checkpoint now stores an optional last-agent identity alongside session and HEAD state.

```text
Codex SessionStart
  ↓
continuity-state.json: agent=codex
  ↓
Claude SessionStart in the same repository/worktree
  ↓
agent_changed = true
  ↓
HANDOFF projection
  ↓
continuity-state.json: agent=claude
  ↓
Gemini SessionStart
  ↓
HANDOFF projection
```

This does not create a second handoff database. Governed L2 memories remain the durable source; the checkpoint stores only the last observed agent identity needed to select the continuity mode.

The previous JSON format remains valid because `agent` is optional.

E2E coverage uses the real SessionStart script and a persistent SQLite store. Codex → Claude → Gemini is verified without requiring the user to type another agent's name.

## Real Git multi-worktree E2E

The integration fixture creates an actual repository and two real worktrees with `git worktree add`.

Verified behavior:

- both worktrees resolve to the same canonical repository;
- worktree IDs differ;
- repository-scoped decisions are visible in both worktrees;
- alpha worktree state never leaks into beta;
- beta worktree state never leaks into alpha;
- continuity checkpoints remain separate per worktree;
- advancing only alpha HEAD marks only alpha as stale;
- stale alpha `project_state` receives a `STALE_HEAD` revalidation warning;
- beta remains non-stale.

## Startup breakdown

The WSL measurements showed that fresh-process and hook latency were much larger than warm recall latency, especially on the low-memory PC-02. A new startup breakdown benchmark separates process/import costs from internal operations.

Initial GitHub Actions reference run: `34031138065` (Python 3.12.14).

| Phase | p50 | p95 |
| --- | ---: | ---: |
| empty Python process | 11.08 ms | 11.51 ms |
| import `sqlite3` | 16.52 ms | 17.15 ms |
| import compatibility session adapter | 34.70 ms | 35.59 ms |
| import hook command | 70.99 ms | 72.84 ms |
| import prompt continuity | 71.15 ms | 73.02 ms |
| build continuity after import | 0.67 ms | 0.69 ms |
| Git inspect after import | 8.93 ms | 9.32 ms |
| scope-index check after import | 0.60 ms | 0.66 ms |

The important result is that composition and scope-index maintenance are not the startup bottleneck. Most fresh-process cost is the Python/import graph.

## Optimization experiments

Two bounded changes were tested:

1. split SessionStart composition from prompt-only scope-first FTS migration;
2. split lightweight SessionStart protocol parsing from the dataclass/Enum compatibility adapter.

The SessionStart path now correctly avoids mutating or migrating prompt-only FTS during an empty-query hook. Existing compatibility APIs remain available.

However, hosted-runner fresh import wall time did not improve materially. A later reference run (`34031414351`) measured `import_hook_command` at 77.88 ms p50 while the runner's empty-Python baseline was also somewhat slower at 12.87 ms. The result is within cross-run runner variation and does not justify a more duplicated or specialized runtime path.

Therefore alpha.17 deliberately stops here:

```text
measured bottleneck = Python/import startup
successful correctness isolation = keep
unproven extra fast-path duplication = do not add
```

Further startup optimization should require a repeatable improvement on both CI diagnostics and real WSL measurements. Long-lived daemon/server architecture is not introduced merely to save tens of milliseconds at SessionStart.

## Benchmark command

The practical machine benchmark now includes the startup breakdown in the same JSON report:

```bash
npx --allow-git=all -y github:al-hub/agent-memory-hub benchmark --quick
```

or the full 1k / 10k / 50k / 100k run:

```bash
npx --allow-git=all -y github:al-hub/agent-memory-hub benchmark
```

The breakdown is diagnostic and phases are not additive.

## Validation policy

The new handoff and multi-worktree behavior is correctness-gated in Python 3.10 / 3.12 / 3.13 CI. Startup measurements remain reference distributions, not hard latency promises or CI gates.
