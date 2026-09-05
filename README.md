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
- Distinguish confirmed, uncertain, needs-review, stale and superseded context.
- Keep the fast path local: metadata + SQLite FTS5 first; semantic search is optional fallback.
- Project only thin instructions/pointers back into agent L1 files.
- Make normal use nearly invisible to the user.

## v0.1 scope

The first implementation is intentionally small and dependency-free (Python standard library):

- SQLite database with FTS5 when available
- append-only event log
- memory types/status/confidence/context quality
- provenance/source pointers
- duplicate detection by normalized statement hash
- conflict candidates without destructive overwrite
- recall producing compact context packs
- import adapters for common text-based L1 files
- doctor/status commands

## Install as an Agent Skill

The repository contains a root `SKILL.md`, so it can be installed with the open Agent Skills CLI:

```bash
npx skills@latest add al-hub/agent-memory-hub -g
```

The skills CLI discovers a repository-root `SKILL.md` and can install skills to multiple supported agents. See the upstream skills CLI documentation for agent-specific destinations.

## Local CLI

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

The v0.1 adapter intentionally imports only accessible text files and never claims access to private product memory that is not present on disk. Add or override files explicitly with `--source PATH`.

## Memory governance

A memory has a type, status and evidence trail. Example:

```yaml
type: decision
status: confirmed
confidence: 0.96
context_quality: clear
statement: Rust implementation uses a separate repository.
sources:
  - agent: codex
    pointer: ~/.codex/...
```

Supported statuses:

```text
candidate | confirmed | needs_review | conflict | superseded | stale | rejected
```

The hub does not treat three agents repeating the same source as three independent facts. Provenance remains attached so later consolidation can reason about evidence groups.

## Fast retrieval path

```text
query
  -> metadata filters
  -> SQLite FTS5/BM25
  -> compact context pack
  -> optional semantic fallback (future)
```

The normal path deliberately avoids embeddings and external services.

## Commands

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

## Example

After weeks of work across agents:

```text
User: What did we decide about the Rust repository layout?

Agent -> memory-hub recall

Context pack:
- [confirmed, 0.96] Rust implementation uses a separate repository.
  reason/source pointer available
- [superseded] Earlier discussion considered a single repository.
```

If two memories disagree, the hub surfaces the conflict rather than inventing a winner.

## Roadmap

- richer Claude/Codex/Gemini session adapters
- automatic capture hooks where an agent supports them
- L1 -> L2 consolidation rules
- evidence-group aware confidence updates
- temporal validity (`valid_from`, `valid_until`)
- optional embeddings/reranking fallback
- thin L2 -> L1 projections (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`)
- background-safe dedupe/cleaning commands
- packaging as a single binary once the schema stabilizes

## Safety / privacy

Memory is local by default. The hub should never upload raw conversations implicitly. Import only sources the user can access and explicitly configured paths. Sensitive source files should remain protected by normal filesystem permissions.

## License

MIT
