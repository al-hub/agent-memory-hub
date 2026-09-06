# agent-memory-hub

**One trusted memory for every AI agent.**

Current development baseline: **v0.2.0-alpha.2**

`agent-memory-hub` is a local-first L2 memory and continuity layer for coding agents and LLM CLIs. It imports accessible L1 memory from each agent, keeps provenance and review status, detects duplicate/conflicting memories, and returns only a small relevant context pack when an agent needs past context.

The product goal is broader than storage: **an agent should be able to continue useful prior work across agent/session/repository/worktree boundaries without making the user restate context.**

## Why

LLMs already have L1 context/memory, but it is fragmented by product and constrained by each model's context window. This project adds a shared L2 layer:

```text
Claude L1 ─┐
Codex L1 ──┤
Gemini L1 ─┼──> agent-memory-hub (L2) ──> small context pack ──> any agent
Other L1 ──┘
```

The design rule is simple: **raw evidence is canonical; summaries are indexes, not truth.**

## Core principles

- Bootstrap from existing L1 instead of starting from zero.
- Keep source provenance for every memory.
- Never silently overwrite conflicts.
- Keep the fast path local: metadata + SQLite FTS5 first; semantic search is optional fallback.
- Project only thin instructions/pointers back into agent L1 files.
- Make normal use nearly invisible to the user.
- Recall proactively when continuity matters; do nothing when prior context cannot materially affect the task.
- Treat onboarding, resume, handoff, and worktree continuation as projections over the same governed L2 memory.

## Seamless continuity target

With the skill installed, users should normally be able to say things like:

```text
"이어서 구현해줘."
"아까 하던 성능 분석 계속해."
"Claude가 하던 작업을 Codex에서 이어서 해."
```

without manually asking for a memory lookup or maintaining a separate handoff file as the source of truth.

The target pipeline is:

```text
user request
  ↓
cheap Continuity Gate
  ↓ only when relevant
repository/worktree/task scope
  ↓
FTS5/BM25 fast recall
  ↓
governance filter
  ↓
token-budget context projection
  ↓
agent continues work
```

## Design status

### v0.1 — working prototype

The original implementation is intentionally small and dependency-free (Python standard library):

- SQLite database with FTS5 when available
- append-only event log
- memory types/status/confidence/context quality
- provenance/source pointers
- duplicate detection by normalized statement hash
- conflict candidates without destructive overwrite
- recall producing compact context packs
- import adapters for common text-based L1 files
- doctor/status commands

### v0.2.0-alpha.2 — repository/scope continuity baseline

The v0.2 architecture is documented before full implementation:

- [Architecture v0.2](docs/ARCHITECTURE-v0.2.md)
- [Schema v2](docs/schema-v2.md)
- [L1 migration & bootstrap workflow](docs/migration-workflow.md)
- [Benchmark plan](docs/benchmark-plan.md)
- [TDD/SOLID development guide](docs/DEVELOPMENT.md)

Implemented groundwork includes:

- non-destructive v1 → v2 schema migration path
- Memory/Evidence separation groundwork and raw-source registration
- package baseline under `src/agent_memory_hub`
- domain execution/repository identity models
- `RepositoryInspector` port
- tested Git remote normalization and canonical repository fingerprint primitive
- concrete local Git inspector for repository root, common-dir, worktree identity, branch, and HEAD
- explicit scope value object and precedence: task → worktree → branch → repository → global
- scope visibility rules that prevent worktree/branch context from leaking across unrelated repository contexts
- CI coverage for both legacy CLI syntax and the new `src/` package

Next continuity work proceeds test-first:

1. wire scope hierarchy into SQLite/FTS recall
2. add typed + scope-aware retrieval ranking
3. Continuity Gate
4. token-budget Context Projector
5. onboarding/resume/handoff projection presets
6. HEAD-aware stale checkpoint handling

## Install as an Agent Skill

The repository contains a root `SKILL.md`, so it can be installed with the open Agent Skills CLI:

```bash
npx skills@latest add al-hub/agent-memory-hub -g
```

The skill is designed to recall prior context proactively when continuity materially matters; the user should not need to explicitly say "use agent-memory-hub".

## Local CLI — compatibility path

Clone the repository and run:

```bash
python3 scripts/memory_hub.py init
python3 scripts/memory_hub.py status
python3 scripts/memory_hub.py add "Rust implementation uses a separate repository" \
  --type decision --status confirmed --source-agent codex
python3 scripts/memory_hub.py recall "repository decision"
```

By default data is stored under:

```text
~/.agent-memory-hub/
  memory.db
  events.jsonl
  raw/
```

Override with:

```bash
export AGENT_MEMORY_HUB_HOME=/path/to/memory
```

## Bootstrap existing L1

Preview discovered sources:

```bash
python3 scripts/memory_hub.py import-l1 --dry-run
```

Import them:

```bash
python3 scripts/memory_hub.py import-l1
```

The current adapter imports only accessible text files and never claims access to private product memory that is not present on disk. Add or override files explicitly with `--source PATH`.

The v0.2 bootstrap direction replaces eager full-corpus understanding with:

```text
Discover L1
  → preserve/register raw sources
  → hash + metadata/FTS index
  → ready immediately
  → lazily extract structured memories only when relevant
```

## Memory governance — v0.2 direction

A memory claim and its evidence become separate records:

```text
Memory
  ├─ Evidence A → raw transcript
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

Memory is typed and scoped so unrelated contexts do not create false conflicts.

## Fast retrieval path

```text
query
  → scope/type filter
  → SQLite FTS5/BM25
  → governance filter
  → optional semantic fallback
  → optional rerank only when necessary
  → compact context pack
```

The normal path deliberately avoids embeddings and external services.

## Development discipline

Long-term development follows:

```text
RED → GREEN → REFACTOR → PERF
```

Core logic follows SOLID boundaries so Git, SQLite, source adapters, retrieval strategies, and projection presets can evolve without turning the memory core into one large conditional script. See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

The main product regression metric is **Continuity Success Rate**:

> Can the agent continue the correct work without asking the user to restate previously available project context?

## Current compatibility commands

```text
init        initialize L2 storage
add         add one governed memory
recall      retrieve relevant memories
status      show store statistics
inspect     inspect one memory
resolve     change a memory status / supersession
import-l1   discover and import accessible L1 text files
doctor      validate DB, FTS, event log and source paths
```

## Example target experience

After weeks of work across agents:

```text
User: 이어서 구현해줘.

Codex
  → recognizes repository/worktree continuity
  → shared L2 recall

Context pack:
- schema v2 migration implemented
- Memory/Evidence separated
- raw_sources introduced
- FTS5 is the primary retrieval path
- semantic retrieval is fallback only
- next planned work: typed/scope-aware continuity retrieval
```

If two memories disagree, the hub surfaces the conflict rather than inventing a winner.

## Roadmap

Implementation order for v0.2:

1. schema-v2 migration with lossless v0.1 compatibility
2. evidence/raw-source model
3. repository/worktree/branch execution identity
4. typed/scope-aware retrieval
5. Continuity Gate + token-budget projection
6. onboarding/resume/handoff/worktree continuity presets
7. cold-source index + lazy extraction interfaces
8. conflict/update/different-context classifier
9. quarantine + secret/contamination guards
10. per-agent adapters and thin projections
11. MCP gateway
12. benchmark harness and regression gates
13. optional semantic fallback after the fast path is measured

`worktree-context` should remain a reference/compatibility benchmark until agent-memory-hub passes automatic repository onboarding, worktree resume, cross-agent handoff, session-reset continuity, and HEAD-aware stale detection.

## Safety / privacy

Memory is local by default. The hub should never upload raw conversations implicitly. Import only sources the user can access and explicitly configured paths. External LLM extraction must be opt-in/configured. Suspicious or noisy content should be quarantined rather than silently promoted or destructively deleted.

## License

MIT
