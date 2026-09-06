# agent-memory-hub

**One trusted memory for every AI agent.**

Current development baseline: **v0.2.0-alpha.10**

`agent-memory-hub` is a local-first shared L2 memory and continuity layer for AI coding agents. Its goal is simple: an agent should be able to continue useful prior work across agent, session, repository, branch, and worktree boundaries without making the user restate context.

Raw evidence is canonical; memories and summaries are governed indexes over that evidence, not unquestionable truth.

## Target experience

With the skill installed, ordinary prompts should be enough:

```text
"이어서 구현해줘."
"아까 하던 성능 분석 계속해."
"Claude가 하던 작업을 Codex에서 이어서 해."
```

The current continuity pipeline is:

```text
SessionStart hook or user request
  ↓
Git repository/worktree/branch/HEAD inspection
  ↓
local repository/session/checkpoint state detection
  ↓
cheap deterministic Continuity Gate
  ↓ only when relevant
scope-aware SQLite FTS5/BM25 recall or bounded scope browse
  ↓
governance + conflict/review handling
  ↓
HEAD-aware bounded Context Projector
  ↓
small context pack
  ↓
agent continues work
```

When continuity is irrelevant, `NO_RECALL` takes a zero-read/zero-project fast path.

## Install as an Agent Skill

```bash
npx skills@latest add al-hub/agent-memory-hub -g
```

The root `SKILL.md` instructs compatible agents to use the seamless continuity path proactively; users should not normally need to say "use agent-memory-hub".

## Hook-native seamless continuity

Codex CLI, Claude Code, and Gemini CLI all expose a `SessionStart` hook payload containing a stable `session_id`, `cwd`, and `source`. `agent-memory-hub` normalizes those payloads through one shared adapter and returns hook-compatible `additionalContext` JSON.

Shared entry point:

```bash
python3 /path/to/agent-memory-hub/scripts/session_start_hook.py --agent codex
python3 /path/to/agent-memory-hub/scripts/session_start_hook.py --agent claude
python3 /path/to/agent-memory-hub/scripts/session_start_hook.py --agent gemini
```

Each command reads the agent's hook JSON from stdin and writes only valid hook JSON to stdout.

Supported SessionStart source behavior:

```text
startup              → empty L1; known repo becomes ONBOARDING
resume               → RESUME refresh
clear                → RESUME refresh even if session id is unchanged
compact              → RESUME refresh (Codex / Claude)
fork                 → RESUME refresh (Claude)
```

Hook failures are intentionally fail-open: an invalid payload or memory error never blocks the coding agent from starting. The hook emits an empty valid SessionStart response and writes the warning to stderr.

A typical Codex hook command in `~/.codex/hooks.json` points its `SessionStart` command to:

```text
python3 /path/to/agent-memory-hub/scripts/session_start_hook.py --agent codex
```

Claude Code uses the same command shape in its `SessionStart` hook settings with `--agent claude`; Gemini CLI uses `--agent gemini`.

The next install/UX slice will automate these per-agent config edits so users do not have to maintain the paths manually.

## Prompt-facing seamless continuity entry point

The skill-facing fallback/explicit command remains:

```bash
python3 scripts/continuity_context.py "<current user/task message>" --cwd "$PWD" --json
```

When an agent exposes a stable session id:

```bash
python3 scripts/continuity_context.py "<current user/task message>" \
  --cwd "$PWD" \
  --session-id "<session-id>" \
  --json
```

After a clear/reset or when entering an existing repository with little usable L1 context:

```bash
python3 scripts/continuity_context.py "<current user/task message>" \
  --cwd "$PWD" \
  --empty-session \
  --json
```

The command is intentionally safe before L2 initialization: a missing store is treated as no available memory rather than an error.

## Why SessionStart needs scope browse

A SessionStart hook fires before a new user prompt exists. A pure lexical query would therefore be empty and return no memories. The package now treats an empty internal recall query as a **bounded browse of currently visible scopes**:

```text
worktree → branch → repository → global
```

Foreign repository scopes and superseded/quarantined memories remain excluded. The Context Projector then applies onboarding/resume type priorities, governance state, dedupe, and token budget. Normal non-empty queries still use FTS5/BM25 first.

## Compatibility storage CLI

The original dependency-free CLI remains available for storage and governance operations:

```bash
python3 scripts/memory_hub.py init
python3 scripts/memory_hub.py status
python3 scripts/memory_hub.py add "FTS5 is the normal recall path" \
  --type decision --status confirmed --source-agent codex
python3 scripts/memory_hub.py recall "recall path"
python3 scripts/memory_hub.py doctor
```

Default data directory:

```text
~/.agent-memory-hub/
  memory.db
  events.jsonl
  continuity-state.json
  raw/
```

Override with:

```bash
export AGENT_MEMORY_HUB_HOME=/path/to/memory
```

## Bootstrap existing L1

Preview accessible text sources:

```bash
python3 scripts/memory_hub.py import-l1 --dry-run
```

Import them:

```bash
python3 scripts/memory_hub.py import-l1
```

The importer only uses sources actually accessible on disk. It never assumes access to private product memory.

The v0.2 direction is lazy rather than eager:

```text
Discover L1
  → preserve/register raw sources
  → hash + metadata/FTS index
  → become usable quickly
  → lazily extract structured memories only when relevant
```

## Memory governance

A memory claim and its evidence are separate concepts:

```text
Memory
  ├─ Evidence A → raw transcript/session
  ├─ Evidence B → project file
  └─ Evidence C → explicit user decision
```

Governance uses independent axes:

```text
lifecycle:
  candidate | active | superseded | archived | quarantined

review_state:
  verified | unverified | needs_review | conflict

confidence:
  0.0 .. 1.0
```

Conflicts are surfaced rather than silently overwritten. Suspicious/noisy content should be quarantined instead of destructively merged.

## Scope model

Current precedence is:

```text
task
> worktree
> branch
> repository
> global
```

Branch/worktree/task storage references are repository-qualified so `main` in one repository cannot leak into another repository.

## HEAD-aware continuity

The local continuity checkpoint stores repository/worktree session and HEAD information. If HEAD changed since the prior checkpoint:

- stable memories such as verified decisions and constraints remain usable;
- volatile `project_state` is demoted below stable context;
- the projected item receives an explicit `STALE_HEAD` warning and must be revalidated against current code.

This keeps old execution state from being treated as current truth while preserving useful durable knowledge.

## Fast retrieval path

Normal prompt recall:

```text
query
  → scope/type filter
  → SQLite FTS5/BM25
  → governance filter
  → mode-specific ranking
  → dedupe
  → hard token budget
  → context pack
```

SessionStart without a prompt:

```text
empty query
  → bounded visible-scope browse
  → governance filter
  → mode-specific ranking
  → dedupe
  → hard token budget
  → additionalContext
```

Embeddings, external services, and LLM reranking are deliberately excluded from the normal fast path. Semantic fallback remains a future optional fallback after lexical retrieval is measured.

## v0.2.0-alpha.10 status

Implemented and tested:

- non-destructive v1 → v2 migration groundwork
- Memory/Evidence + raw-source groundwork
- Git remote normalization and canonical repository identity
- repository/worktree/branch/HEAD inspection
- repository-qualified scope hierarchy and isolation
- typed + scope-aware SQLite/FTS5 retrieval
- bounded visible-scope browse when SessionStart has no prompt text
- deterministic `NO_RECALL / RECALL / ONBOARDING / RESUME / HANDOFF` Continuity Gate
- SessionStart source-aware onboarding/resume decisions
- zero-read fast path when continuity is irrelevant
- mode-specific bounded Context Projector
- conflict/review warnings and duplicate collapse
- repository/session/checkpoint state detection
- tiny JSON continuity state store
- stale-HEAD detection and projection rules
- composed seamless continuity application service
- prompt-facing `scripts/continuity_context.py` entry point
- shared `scripts/session_start_hook.py` for Codex / Claude / Gemini
- normalized hook profiles for agent-specific SessionStart source support
- hook-compatible `hookSpecificOutput.additionalContext` rendering
- fail-open hook behavior
- safe behavior when the store is not initialized
- end-to-end subprocess tests for Git/non-Git contexts and all three SessionStart agents
- CI across Python 3.10, 3.12, and 3.13

Architecture docs:

- [Architecture v0.2](docs/ARCHITECTURE-v0.2.md)
- [Schema v2](docs/schema-v2.md)
- [L1 migration & bootstrap](docs/migration-workflow.md)
- [Benchmark plan](docs/benchmark-plan.md)
- [TDD/SOLID development guide](docs/DEVELOPMENT.md)

## Development discipline

Core development follows:

```text
RED → GREEN → REFACTOR → PERF
```

The domain/application layer does not depend directly on Git subprocesses, SQLite, or agent-specific APIs. External systems are behind ports/adapters so Codex, Claude, Gemini, MCP, and future integrations can share the same continuity engine.

Primary quality metric:

> **Continuity Success Rate:** Can the agent continue the correct work without asking the user to restate previously available project context?

Secondary metrics include wrong-scope injection, stale-state usage, silent-conflict rate, context tokens, p50/p95 latency, and manual memory invocation count.

## Next work

The next implementation slices are:

1. one-command installation/removal of SessionStart hooks for Codex / Claude / Gemini;
2. end-to-end cross-agent handoff fixtures using persisted scoped memories;
3. measured latency/token regression tests;
4. automatic meaningful-event capture (`memory.propose`) with governance;
5. cold-source lazy extraction and cache;
6. MCP gateway and thin per-agent projections.

`worktree-context` remains a compatibility/reference benchmark until automatic onboarding, worktree resume, cross-agent handoff, session-reset continuity, and HEAD-aware stale handling are all proven in real agent workflows.

## Safety / privacy

Memory is local by default. Raw conversations are never uploaded implicitly. External LLM extraction, if added later, must be opt-in/configured. Only accessible/configured sources should be imported.

## License

MIT
