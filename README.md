# agent-memory-hub

**One trusted memory for every AI agent.**

`agent-memory-hub` is a local-first L2 memory layer for coding agents and LLM CLIs. It imports accessible L1 memory from each agent, keeps provenance and review status, detects duplicate/conflicting memories, and returns only a small relevant context pack when an agent needs past context.

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

## Design status

### v0.1 — working prototype

The current implementation is intentionally small and dependency-free (Python standard library):

- SQLite database with FTS5 when available
- append-only event log
- memory types/status/confidence/context quality
- provenance/source pointers
- duplicate detection by normalized statement hash
- conflict candidates without destructive overwrite
- recall producing compact context packs
- import adapters for common text-based L1 files
- doctor/status commands

### v0.2 — specification frozen before implementation

The next architecture is documented before code changes:

- [Architecture v0.2](docs/ARCHITECTURE-v0.2.md)
- [Schema v2](docs/schema-v2.md)
- [L1 migration & bootstrap workflow](docs/migration-workflow.md)
- [Benchmark plan](docs/benchmark-plan.md)

Key v0.2 changes:

- separate **Memory** from **Evidence**
- split governance into lifecycle / review state / confidence
- add explicit scope and typed memory
- reversible quarantine instead of destructive cleaning
- lazy extraction of large historical L1/session archives
- thin L2 → L1 projection and optional hot cache
- adapter/MCP/hook architecture
- benchmark conflict, temporal updates, contamination, provenance and latency

## Install as an Agent Skill

The repository contains a root `SKILL.md`, so it can be installed with the open Agent Skills CLI:

```bash
npx skills@latest add al-hub/agent-memory-hub -g
```

## Local CLI — v0.1

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

## Bootstrap existing L1 — v0.1

Preview discovered sources:

```bash
python3 scripts/memory_hub.py import-l1 --dry-run
```

Import them:

```bash
python3 scripts/memory_hub.py import-l1
```

The v0.1 adapter intentionally imports only accessible text files and never claims access to private product memory that is not present on disk. Add or override files explicitly with `--source PATH`.

v0.2 will replace eager structured import with a faster bootstrap model:

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

Memory is also typed and scoped so unrelated contexts do not create false conflicts.

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

## v0.1 commands

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
User: What did we decide about the Rust repository layout?

Agent → shared L2 recall

Context pack:
- active / verified / decision
  Rust implementation uses a separate repository.
  evidence: user decision + prior session

- superseded
  Earlier discussion considered a single repository.
```

If two memories disagree, the hub surfaces the conflict rather than inventing a winner.

## Roadmap

Implementation order for v0.2:

1. schema-v2 migration with lossless v0.1 compatibility
2. evidence/raw-source model
3. typed/scope-aware retrieval
4. cold-source index + lazy extraction interfaces
5. conflict/update/different-context classifier
6. quarantine + secret/contamination guards
7. per-agent adapters and thin projections
8. MCP gateway
9. benchmark harness and regression gates
10. optional semantic fallback after the fast path is measured

## Safety / privacy

Memory is local by default. The hub should never upload raw conversations implicitly. Import only sources the user can access and explicitly configured paths. External LLM extraction must be opt-in/configured. Suspicious or noisy content should be quarantined rather than silently promoted or destructively deleted.

## License

MIT
