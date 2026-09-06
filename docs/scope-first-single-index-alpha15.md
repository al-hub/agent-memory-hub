# Single-index scope-first FTS — alpha.15

This document records the storage-efficient scope-first experiment and the production adoption decision.

The question was narrow:

> Can the validated scope-first speedup be kept without maintaining a second full statement FTS index?

## Three-way experiment

The same governed memories, query, top-8 limit, and repository/worktree context were used for three layouts:

```text
A. broad
   memory_fts(id, statement)

B. two-index scope-first
   memory_fts(id, statement)
   + memory_fts_scoped(id, statement, scope_key)

C. single-index scope-first
   memory_fts(id, statement, scope_key)
```

`scope_key` is a tokenizer-safe deterministic token derived from `(scope, scope_ref)`.

The scope-first query intersects scope postings and statement postings inside FTS5 before the governed-memory join.

## Three-way results

GitHub Actions Ubuntu 24.04, Python 3.12, 5 warmups, 30 iterations.

Workflow run: `34028561380`
Artifact: `scope-first-fts-three-way`

Ordered top-8 result IDs were identical for all three readers at every tier.

| Memories | Broad p50 | Two-index p50 | Single-index p50 | Single speedup | Two-index extra | Single-index extra |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1k | 1.032 ms | 0.344 ms | 0.324 ms | 3.19x | 0.23 MiB | 0.03 MiB |
| 10k | 9.142 ms | 0.877 ms | 0.811 ms | 11.27x | 2.11 MiB | 0.33 MiB |
| 50k | 42.121 ms | 2.502 ms | 2.449 ms | 17.20x | 9.86 MiB | 0.46 MiB |
| 100k | 85.547 ms | 4.494 ms | 4.450 ms | 19.22x | 21.10 MiB | 3.02 MiB |

The single-index layout is slightly faster than the two-index candidate in this run and removes most of the storage duplication.

At 100k:

```text
broad lexical recall        85.55 ms p50
single-index scope-first     4.45 ms p50
speedup                     19.22x
extra storage vs broad       3.02 MiB
```

## Production continuity result

After switching `build_continuity_command()` to the single-index scope-first reader, the full continuity baseline was repeated.

Workflow run: `34028753120`
Artifact: `continuity-benchmark-baseline`

The most important end-to-end change is prompt-facing resume/handoff at large archive sizes:

| Memories | Resume p50 | Handoff p50 | NO_RECALL p50 | SessionStart resume p50 | Codex hook p50 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1k | 10.361 ms | 10.228 ms | 9.087 ms | 9.722 ms | 89.184 ms |
| 10k | 10.345 ms | 10.264 ms | 8.651 ms | 11.989 ms | 93.028 ms |
| 50k | 13.256 ms | 12.996 ms | 8.723 ms | 22.136 ms | 103.489 ms |
| 100k | 16.547 ms | 16.538 ms | 8.723 ms | 34.983 ms | 116.151 ms |

For comparison, the pre-adoption 100k baseline had resume/handoff around 146 ms p50. The production path is now about 16.5 ms while preserving the flat NO_RECALL behavior.

SessionStart remains a different workload because an empty query intentionally uses bounded scope browse rather than lexical FTS. Hook latency therefore remains dominated by process/Git startup plus scope browse and is not expected to receive the same lexical speedup.

## Non-destructive migration

Production continuity now calls `ensure_single_index_scope_fts()` before composing the reader.

The governed `memories` table is canonical and is never rewritten by this migration.

Migration behavior:

```text
missing DB / incompatible store
  → fail safe; normal broad/LIKE fallback remains available

legacy memory_fts(id, statement)
  → rebuild only the FTS cache as
    memory_fts(id, statement, scope_key)

already migrated index
  → no full rebuild
```

FTS rowids are aligned to `memories.rowid`.

## Legacy writer synchronization

The compatibility `scripts/memcarry_store.py` writer can still insert only `(id, statement)` into the FTS table. To avoid a correctness gap, migration installs a tiny `scope_fts_dirty` table and triggers on `memories` insert/update/delete.

```text
legacy write
  ↓
mark one memory row dirty
  ↓
next continuity entry
  ↓
repair only dirty FTS row(s)
  ↓
scope-first recall
```

The dirty-row repair removes any legacy null-scope FTS entry, recomputes the deterministic scope token, preserves the memory rowid, and handles updates/deletes. The expensive work stays off the normal clean read path.

## Adoption decision

Single-index scope-first FTS is now the production continuity reader.

Reasons:

- ordered result parity passed at 1k/10k/50k/100k;
- repository/worktree isolation and governance-filter regression tests pass;
- legacy two-column FTS remains readable through migration/fallback;
- dirty insert/update/delete synchronization is covered by integration tests;
- 100k lexical speedup is ~19x in the controlled three-way run;
- storage overhead is ~3 MiB at 100k rather than ~21 MiB for the duplicate-index experiment;
- Python 3.10/3.12/3.13 and Node installer CI pass.

## Reproduce

Three-way comparison:

```bash
python3 benchmarks/scope_first_three_way.py \
  --sizes 1000,10000,50000,100000 \
  --warmup 5 \
  --iterations 30 \
  --output scope-first-three-way-results.json
```

Production continuity baseline:

```bash
python3 benchmarks/continuity_baseline.py \
  --sizes 1000,10000,50000,100000 \
  --warmup 5 \
  --iterations 30 \
  --subprocess-iterations 10 \
  --output benchmark-results.json
```

These remain reference measurements, not latency guarantees or hard CI performance gates.
