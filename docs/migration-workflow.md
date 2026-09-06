# Migration & Bootstrap Workflow

## Objective

A fresh installation must become useful immediately by discovering and indexing accessible existing L1 memory from supported agents. It must not attempt an expensive full-corpus LLM extraction during setup.

## User experience target

```bash
npx skills@latest add al-hub/memcarry -g
memcarry init
```

Expected flow:

```text
Scanning accessible L1 sources...

Claude    428 sessions   6 instruction/memory files
Codex     329 sessions  18 instruction/memory files
Gemini    121 sessions   4 instruction/memory files
Other       9 sources

Raw sources discovered: 906
Indexed: 906
Structured memories imported immediately: 28
Cold sources available for lazy extraction: 878

Ready.
```

The exact counts depend on what each local runtime exposes. The tool must never claim access to hidden vendor memory.

## Phase 0 — discovery

Each adapter implements:

```text
detect()
list_sources()
describe_capabilities()
```

Possible source classes:
- instruction files
- explicit agent memory files
- session transcript files
- project-local memory
- export files
- supported local databases, read-only

Discovery is read-only.

## Phase 1 — raw registration

For every source:

1. identify adapter and source type
2. compute source hash
3. collect cheap metadata
4. preserve original pointer
5. optionally archive a byte-preserving local copy according to policy
6. create `raw_sources` record
7. mark `extraction_state=indexed`

No LLM is required.

## Phase 2 — lightweight indexing

Index only metadata and searchable text needed for cold retrieval:
- title/session id
- timestamp
- project/repository/path
- agent
- cheap keyword text where safe
- source hash

Use SQLite FTS5 where possible.

The system should be usable after this phase.

## Phase 3 — deterministic immediate import

Structured files with explicit durable content may be converted immediately without an LLM, for example:
- clear Markdown decisions
- structured YAML/JSON memories
- existing project instruction files

Default review state should reflect certainty:
- explicit user-authored durable decision → `verified` if context is clear
- agent-authored inference → `unverified` or `needs_review`

## Phase 4 — lazy extraction

Cold transcript sources remain raw until needed.

Trigger conditions:
- a recall query hits a cold source strongly
- repeated queries target the same topic
- user requests consolidation
- maintenance command has an explicit budget

Workflow:

```text
query
 ↓
FTS finds cold transcript
 ↓
retrieve relevant window
 ↓
extract candidate memories
 ↓
attach evidence/provenance
 ↓
run conflict/context/temporal checks
 ↓
cache structured memories
 ↓
return context pack
```

## Phase 5 — promotion

A candidate can become active based on:
- explicit user confirmation
- direct unambiguous source evidence
- repeated independent evidence groups
- deterministic structured source

Promotion must not rely on raw repetition count when evidence groups are identical.

## Phase 6 — thin L1 projection

After bootstrap, each supported agent receives only:

1. instructions for when/how to consult L2
2. MCP/CLI connection metadata if supported
3. optional bounded hot cache

Example projection:

```md
## Shared Memory
Use memcarry when prior decisions, preferences, lessons, or project state may affect the current task.
Prefer active/verified memories. Surface conflicts and needs-review entries instead of assuming they are true.
Inspect evidence for important decisions.
```

## Adapter capability matrix

Each adapter declares capabilities rather than pretending all agents work the same way.

```text
capabilities:
  instruction_file_read
  instruction_file_write
  transcript_discovery
  session_hook
  mcp
  project_scope
  user_scope
```

Examples:
- an agent with native hooks can auto-capture session boundaries
- an agent with only Markdown skills gets read protocol + explicit/manual capture
- inaccessible cloud-only memory is documented as unavailable

## Conflict handling during migration

Imported memories are compared only within overlapping scope/type.

Decision tree:

```text
same normalized claim + same source group
  → duplicate source

same claim + independent evidence
  → merge evidence

same subject/scope, newer value with temporal evidence
  → update / supersession

same subject/scope, incompatible claims
  → conflict

apparently incompatible but scopes differ
  → different-context
```

No destructive overwrite.

## Cleaning during migration

Potentially unsafe/noisy items are quarantined with retained evidence.

Checks:
- exact duplicate
- near duplicate
- unsupported inference
- ambiguous pronouns/context
- transient chatter
- prompt-injection-like memory requests embedded in untrusted content
- secrets/tokens/credentials
- malformed source

Quarantine is reversible.

## Privacy rules

- local-first by default
- do not send raw transcripts to an external model unless the user configured such a provider
- local/heuristic extraction remains a supported path
- source file permissions should be preserved where practical
- archived raw data should default to user-only filesystem permissions

## Failure recovery

Bootstrap should be resumable.

Store:
- per-source hash
- adapter
- phase reached
- extraction state
- failure reason

Rerunning `bootstrap` skips unchanged completed sources.

## Commands proposed for v0.2

```text
memcarry init
memcarry bootstrap [--dry-run] [--agent ...]
memcarry bootstrap --resume
memcarry sources
memcarry recall "..."
memcarry consolidate [scope] [--budget ...]
memcarry project-l1 [agent]
memcarry doctor
```

## Performance principle

Setup time should scale primarily with local filesystem scan + hashing/indexing, not number of LLM calls.

The system should prefer:

```text
index now → understand later when needed
```

over:

```text
understand everything before first use
```
