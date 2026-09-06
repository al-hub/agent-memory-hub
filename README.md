# agent-memory-hub

**One trusted memory for every AI agent.**

Current development baseline: **v0.2.0-alpha.12**

`agent-memory-hub` is a local-first shared L2 memory and continuity layer for AI coding agents. It is designed so Codex, Claude Code, Gemini CLI, and future agents can continue useful prior work across sessions, repositories, branches, worktrees, and agent switches without making the user restate context.

Raw evidence is canonical; memories and summaries are governed indexes over that evidence, not unquestionable truth.

## One-command install

The preferred installation path is now `npx`.

Until the scoped npm package is published, use the GitHub-backed package directly:

```bash
npx -y github:al-hub/agent-memory-hub install
```

The installer performs four operations:

```text
install Agent Skill globally
  +
copy stable runtime → ~/.agent-memory-hub/runtime
  +
initialize local memory store
  +
merge SessionStart hooks into Codex / Claude / Gemini user config
```

It never points hooks at the temporary npx cache. Hooks reference the persistent runtime under `~/.agent-memory-hub/runtime`, so clearing the npm cache does not break continuity.

After the npm package is published, the same CLI contract becomes:

```bash
npx -y @al-hub/agent-memory-hub@latest install
```

### Install selected agents only

```bash
npx -y github:al-hub/agent-memory-hub install --agents codex,claude
```

Supported agent ids:

```text
codex
claude
gemini
```

### Status

```bash
npx -y github:al-hub/agent-memory-hub status
```

### Uninstall

```bash
npx -y github:al-hub/agent-memory-hub uninstall
```

Uninstall removes only the `agent-memory-hub` SessionStart hook entries, removes the installed Agent Skill, and removes the copied runtime. Existing unrelated hooks/settings are preserved. Memory data such as `memory.db`, raw evidence, and checkpoints is deliberately preserved so reinstalling does not destroy memory.

The installer creates one-time backups before modifying existing config files:

```text
~/.codex/hooks.json.agent-memory-hub.bak
~/.claude/settings.json.agent-memory-hub.bak
~/.gemini/settings.json.agent-memory-hub.bak
```

Repeated install is idempotent: the managed hook is replaced rather than duplicated.

## Target experience

After installation, users should normally be able to use their coding agents as usual:

```text
"이어서 구현해줘."
"아까 하던 성능 분석 계속해."
"Claude가 하던 작업을 Codex에서 이어서 해."
```

The continuity pipeline is:

```text
SessionStart hook or user request
  ↓
Git repository/worktree/branch/HEAD inspection
  ↓
repository/session/checkpoint state detection
  ↓
cheap deterministic Continuity Gate
  ↓ only when relevant
scope-aware SQLite FTS5/BM25 recall
or bounded visible-scope browse at SessionStart
  ↓
governance + conflict/review handling
  ↓
HEAD-aware bounded Context Projector
  ↓
hook additionalContext / small context pack
  ↓
agent continues work
```

When continuity is irrelevant, `NO_RECALL` skips memory retrieval and projection.

## Hook-native continuity

Codex CLI, Claude Code, and Gemini CLI expose SessionStart-style hook inputs containing session/workspace context. `agent-memory-hub` normalizes those inputs through one shared adapter and emits hook-compatible `additionalContext`.

The installed hook points to the persistent command:

```text
python3 ~/.agent-memory-hub/runtime/scripts/session_start_hook.py --agent <agent>
```

Current source behavior:

```text
startup  → ONBOARDING when prior repository memory exists
resume   → RESUME
clear    → RESUME even if the session id did not change
compact  → RESUME where supported
fork     → RESUME where supported
```

Hook failures are fail-open: memory problems must not prevent the coding agent from starting.

## Why SessionStart needs scope browse

A SessionStart hook can run before there is a new user prompt. In that case a lexical query would be empty, so `agent-memory-hub` performs a bounded browse of currently visible scopes instead:

```text
worktree → branch → repository → global
```

Foreign repository memories and superseded/quarantined memories stay excluded. The Context Projector then applies onboarding/resume type priorities, governance state, dedupe, stale-HEAD handling, and the hard token budget.

Normal prompt-facing queries still use SQLite FTS5/BM25 first.

## Scope model

Current visibility precedence is:

```text
task
> worktree
> branch
> repository
> global
```

Branch/worktree/task references are repository-qualified, preventing `main` or similarly named tasks in unrelated repositories from leaking into each other.

## HEAD-aware continuity

The local continuity checkpoint stores repository/worktree session and HEAD information. If HEAD changed since the previous checkpoint:

- stable memories such as verified decisions and constraints remain usable;
- volatile `project_state` is demoted below stable context;
- projected volatile state receives an explicit `STALE_HEAD` warning and must be revalidated against current code.

## Practical baseline before specialization

The project keeps its current name and direction. External memory systems are useful as reference baselines, but the goal is not feature-by-feature competition. `agent-memory-hub` will specialize around real coding-agent conditions: startup/resume latency, worktree/HEAD correctness, bounded context, low manual invocation, and safe cross-agent continuity.

The first reproducible baseline measures both the in-process continuity path and the real SessionStart subprocess path. On a GitHub Actions Ubuntu runner with Python 3.12.14:

```text
1,000 memories
  NO_RECALL core         p50  6.99 ms
  resume core            p50  8.19 ms
  SessionStart resume    p50  6.81 ms
  Codex hook end-to-end  p50 72.27 ms

10,000 memories
  NO_RECALL core         p50  6.01 ms
  resume core            p50 17.07 ms
  SessionStart resume    p50  8.67 ms
  Codex hook end-to-end  p50 72.70 ms
```

The first useful signal is that SessionStart hook latency is currently dominated by process/Git startup rather than archive size, while prompt-based lexical recall is more sensitive to archive growth. Context remained bounded at 8 items for resume/handoff and 12 items for onboarding.

These numbers are a **reference baseline, not a latency promise or CI threshold**. See [docs/baseline-alpha11.md](docs/baseline-alpha11.md) and [docs/benchmark-plan.md](docs/benchmark-plan.md).

Reproduce locally:

```bash
python3 benchmarks/continuity_baseline.py \
  --sizes 1000,10000 \
  --warmup 5 \
  --iterations 30 \
  --subprocess-iterations 10 \
  --output benchmark-results.json
```

CI records the JSON result as the `continuity-benchmark-baseline` artifact without failing builds on latency values.

## Memory governance

A memory claim and its evidence are separate concepts:

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

Conflicts are surfaced rather than silently overwritten. Suspicious/noisy content should be quarantined instead of destructively merged.

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

Override the memory/runtime location during npx install:

```bash
npx -y github:al-hub/agent-memory-hub install --home /path/to/memory
```

The compatibility Python CLI remains available inside the runtime/repository for explicit storage and governance operations:

```bash
python3 scripts/memory_hub.py init
python3 scripts/memory_hub.py status
python3 scripts/memory_hub.py add "FTS5 is the normal recall path" \
  --type decision --status confirmed --source-agent codex
python3 scripts/memory_hub.py recall "recall path"
python3 scripts/memory_hub.py doctor
```

## Bootstrap existing L1

Preview accessible text sources:

```bash
python3 scripts/memory_hub.py import-l1 --dry-run
```

Then import when explicitly desired:

```bash
python3 scripts/memory_hub.py import-l1
```

The importer only uses sources actually accessible on disk. It never assumes access to private product memory.

## v0.2.0-alpha.12 status

Implemented and tested:

- non-destructive v1 → v2 migration groundwork
- Memory/Evidence + raw-source groundwork
- canonical repository/worktree/branch/HEAD identity
- repository-qualified scope isolation
- typed + scope-aware SQLite/FTS5 retrieval
- bounded visible-scope browse for SessionStart without prompt text
- deterministic `NO_RECALL / RECALL / ONBOARDING / RESUME / HANDOFF` Continuity Gate
- mode-specific bounded Context Projector
- conflict/review warnings and duplicate collapse
- session/checkpoint and stale-HEAD continuity
- shared SessionStart adapter for Codex / Claude / Gemini
- hook-compatible `additionalContext` rendering
- fail-open hook behavior
- dependency-free Node npx installer
- persistent runtime copy outside the npx cache
- non-destructive/idempotent hook merge and one-time config backup
- npx install/status/uninstall integration tests
- reproducible practical continuity benchmark harness
- 1k/10k memory latency, context-size, stale-HEAD, onboarding/resume/handoff and real hook baselines
- machine-readable benchmark artifact in CI without hard latency gates
- Python CI across 3.10, 3.12, 3.13 plus Node installer CI

## Development discipline

Core development follows:

```text
RED → GREEN → REFACTOR → PERF
```

The domain/application layer does not depend directly on Git subprocesses, SQLite, or agent-specific APIs. External systems are behind ports/adapters so agent integrations share the same continuity engine.

Primary quality metric:

> **Continuity Success Rate:** Can the agent continue the correct work without asking the user to restate previously available project context?

## Next work

The highest-value next slices are now driven by practical usage rather than feature parity:

1. run the same benchmark on the normal WSL development environment and add cold/warm breakdowns;
2. break the ~72 ms hook path into Python startup, Git inspection, state lookup, retrieval, and projection costs;
3. add 50k/100k archive and multi-worktree tiers before changing indexes;
4. add end-to-end Agent A → Agent B handoff fixtures using persisted scoped memories;
5. automatic meaningful-event capture (`memory.propose`) with governance;
6. cold-source lazy extraction/cache and MCP only where real workflows justify them.

`worktree-context` remains a compatibility/reference benchmark until automatic onboarding, worktree resume, cross-agent handoff, session reset, and HEAD-aware stale handling are all proven in real workflows.

## Safety / privacy

Memory is local by default. Raw conversations are never uploaded implicitly. External LLM extraction, if added later, must be opt-in/configured. Only accessible/configured sources should be imported.

## License

MIT
