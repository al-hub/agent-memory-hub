# Schema v2

## Purpose

Schema v2 separates durable memory claims from the evidence that supports them. It also separates lifecycle, review state, and confidence instead of overloading a single status field.

## Entities

### memories

```sql
CREATE TABLE memories (
  id TEXT PRIMARY KEY,
  statement TEXT NOT NULL,
  normalized_hash TEXT NOT NULL,
  memory_type TEXT NOT NULL,
  lifecycle TEXT NOT NULL,
  review_state TEXT NOT NULL,
  confidence REAL NOT NULL,
  context_quality TEXT NOT NULL,
  scope_json TEXT NOT NULL,
  valid_from TEXT,
  valid_until TEXT,
  supersedes_memory_id TEXT,
  superseded_by_memory_id TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
```

Recommended enums:

```text
memory_type:
  identity | preference | decision | constraint | project_state |
  episode | lesson | fact | procedure

lifecycle:
  candidate | active | superseded | archived | quarantined

review_state:
  verified | unverified | needs_review | conflict

context_quality:
  clear | partial | ambiguous
```

### evidence

```sql
CREATE TABLE evidence (
  id TEXT PRIMARY KEY,
  source_agent TEXT,
  source_type TEXT NOT NULL,
  source_pointer TEXT,
  source_hash TEXT,
  evidence_group TEXT NOT NULL,
  raw_pointer TEXT,
  observed_at TEXT,
  imported_at INTEGER NOT NULL,
  metadata_json TEXT NOT NULL
);
```

`evidence_group` prevents duplicated observations of the same original source from being counted as independent confirmation.

### memory_evidence

```sql
CREATE TABLE memory_evidence (
  memory_id TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  support_kind TEXT NOT NULL,
  weight REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY(memory_id, evidence_id)
);
```

`support_kind`:

```text
supports | contradicts | contextualizes
```

### relations

```sql
CREATE TABLE relations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  from_memory_id TEXT NOT NULL,
  relation TEXT NOT NULL,
  to_memory_id TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  UNIQUE(from_memory_id, relation, to_memory_id)
);
```

Suggested relations:

```text
duplicate_of
updates
conflicts_with
different_context_from
related_to
supersedes
```

### raw_sources

```sql
CREATE TABLE raw_sources (
  id TEXT PRIMARY KEY,
  adapter TEXT NOT NULL,
  original_pointer TEXT,
  archived_pointer TEXT,
  source_hash TEXT NOT NULL,
  byte_size INTEGER,
  discovered_at INTEGER NOT NULL,
  indexed_at INTEGER,
  extraction_state TEXT NOT NULL,
  metadata_json TEXT NOT NULL
);
```

`extraction_state`:

```text
cold | indexed | extracted | failed | ignored
```

### review_queue

```sql
CREATE TABLE review_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  memory_id TEXT,
  raw_source_id TEXT,
  reason TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  resolved_at INTEGER,
  resolution TEXT
);
```

### events

Events remain append-only JSONL in v0.2, but may also be mirrored into SQLite for diagnostics.

Example:

```json
{"event":"memory_promoted","memory_id":"mem_x","from":"candidate","to":"active","ts":0}
```

## Scope JSON

Scope is intentionally extensible.

```json
{
  "level": "project",
  "project": "memcarry",
  "repository": "al-hub/memcarry",
  "task": null,
  "agent": null,
  "topic": "memory architecture"
}
```

Conflict detection should compare only memories with meaningfully overlapping scope.

## Provenance rules

1. Every promoted memory must link to at least one evidence row.
2. Evidence must preserve an immutable pointer/hash to its origin when possible.
3. A memory may have multiple evidence records.
4. Multiple derived observations sharing one origin use one `evidence_group`.
5. Confidence cannot increase merely because multiple agents repeated the same evidence.
6. High-impact memories with only inferred evidence should remain `unverified` or `needs_review`.

## Promotion policy

Typical transitions:

```text
candidate/unverified
  → active/verified
  → superseded/verified
  → archived/verified
```

Alternative branches:

```text
candidate → quarantined
candidate → active/needs_review
active → active/conflict
active → quarantined
```

## Quarantine reasons

Use machine-readable reason codes where possible:

```text
noise
ambiguous_context
unsupported_inference
possible_prompt_injection
secret_like
malformed_import
duplicate_source
low_information
policy_blocked
```

## Confidence guidance

Confidence is not a substitute for review state.

Suggested interpretation:

```text
0.90–1.00  strong direct evidence
0.70–0.89  likely, good evidence
0.50–0.69  plausible / incomplete
<0.50      weak; normally not promoted
```

Explicit user decisions may receive high confidence, but temporal/scope checks still apply.

## Migration from v1

For each v1 memory:

- create one v2 `memory`
- create one `evidence` from `source_agent/source_type/source_pointer/source_hash/evidence_group`
- link through `memory_evidence`
- map status:

```text
candidate     → lifecycle=candidate, review_state=unverified
confirmed     → lifecycle=active, review_state=verified
needs_review  → lifecycle=active, review_state=needs_review
conflict      → lifecycle=active, review_state=conflict
superseded    → lifecycle=superseded, review_state=verified
stale         → lifecycle=active, review_state=needs_review
rejected      → lifecycle=quarantined, review_state=unverified
```

Migration must be lossless and keep the original v1 database until validation completes.
