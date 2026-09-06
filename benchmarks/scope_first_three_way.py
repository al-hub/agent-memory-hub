#!/usr/bin/env python3
"""Three-way benchmark: broad FTS vs two-index scope-first vs single-index scope-first.

The control and both candidates use the same governed memories and query. Ordered
result IDs must match exactly. Storage is measured on separate SQLite files so a
single-index candidate is not penalized by free pages left behind by a dropped FTS.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BENCHMARKS = ROOT / "benchmarks"
for path in (SRC, BENCHMARKS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import continuity_baseline as baseline  # noqa: E402
from memcarry.domain.recall import RecallQuery  # noqa: E402
from memcarry.infrastructure.sqlite.retriever import SQLiteMemoryReader  # noqa: E402
from memcarry.infrastructure.sqlite.scope_first_retriever import (  # noqa: E402
    ScopeFirstSQLiteMemoryReader,
)
from memcarry.infrastructure.sqlite.scope_key import scope_fts_token  # noqa: E402
from memcarry.infrastructure.sqlite.single_index_scope_retriever import (  # noqa: E402
    SingleIndexScopeSQLiteMemoryReader,
)


def parse_sizes(raw: str) -> list[int]:
    return baseline.parse_sizes(raw)


def _memory_rows(con: sqlite3.Connection) -> list[tuple[str, str, str, str | None]]:
    return con.execute(
        "SELECT id,statement,scope,scope_ref FROM memories ORDER BY rowid"
    ).fetchall()


def build_two_index_scope_fts(db_path: Path) -> float:
    started = time.perf_counter_ns()
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "CREATE VIRTUAL TABLE memory_fts_scoped USING fts5("
            "id UNINDEXED, statement, scope_key)"
        )
        con.executemany(
            "INSERT INTO memory_fts_scoped(id,statement,scope_key) VALUES(?,?,?)",
            [
                (memory_id, statement, scope_fts_token(scope, scope_ref))
                for memory_id, statement, scope, scope_ref in _memory_rows(con)
            ],
        )
        con.commit()
    finally:
        con.close()
    return (time.perf_counter_ns() - started) / 1_000_000.0


def migrate_to_single_index_scope_fts(db_path: Path) -> float:
    """Replace broad `memory_fts` with one statement+scope_key FTS and compact DB."""
    started = time.perf_counter_ns()
    con = sqlite3.connect(db_path)
    try:
        rows = _memory_rows(con)
        con.execute("DROP TABLE memory_fts")
        con.execute(
            "CREATE VIRTUAL TABLE memory_fts USING fts5("
            "id UNINDEXED, statement, scope_key)"
        )
        con.executemany(
            "INSERT INTO memory_fts(id,statement,scope_key) VALUES(?,?,?)",
            [
                (memory_id, statement, scope_fts_token(scope, scope_ref))
                for memory_id, statement, scope, scope_ref in rows
            ],
        )
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()
    return (time.perf_counter_ns() - started) / 1_000_000.0


def _measure_reader(reader, query: RecallQuery, *, warmup: int, iterations: int) -> tuple[dict, list[str]]:
    timings, last = baseline.measure(
        lambda: reader.recall(query),
        warmup=warmup,
        iterations=iterations,
    )
    return baseline.summarize_ms(timings), [item.id for item in last]


def _speedup(control: dict, candidate: dict, percentile_name: str) -> float:
    denominator = float(candidate[percentile_name])
    if denominator <= 0:
        return 0.0
    return round(float(control[percentile_name]) / denominator, 3)


def benchmark_tier(memory_count: int, *, warmup: int, iterations: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="memcarry-scope-3way-") as td:
        base = Path(td)
        _repo, context = baseline.create_repo(base)

        broad_db = base / "broad.db"
        two_index_db = base / "two-index.db"
        single_index_db = base / "single-index.db"
        baseline.create_database(broad_db, context, memory_count)
        shutil.copyfile(broad_db, two_index_db)
        shutil.copyfile(broad_db, single_index_db)

        two_index_build_ms = build_two_index_scope_fts(two_index_db)
        single_index_build_ms = migrate_to_single_index_scope_fts(single_index_db)

        query = RecallQuery("architecture implementation", context, limit=8)
        broad_summary, broad_ids = _measure_reader(
            SQLiteMemoryReader(broad_db), query, warmup=warmup, iterations=iterations
        )
        two_summary, two_ids = _measure_reader(
            ScopeFirstSQLiteMemoryReader(two_index_db),
            query,
            warmup=warmup,
            iterations=iterations,
        )
        single_summary, single_ids = _measure_reader(
            SingleIndexScopeSQLiteMemoryReader(single_index_db),
            query,
            warmup=warmup,
            iterations=iterations,
        )

        broad_bytes = broad_db.stat().st_size
        two_bytes = two_index_db.stat().st_size
        single_bytes = single_index_db.stat().st_size
        same_ids = broad_ids == two_ids == single_ids

        return {
            "memory_count": memory_count,
            "same_result_ids": same_ids,
            "broad": {
                **broad_summary,
                "db_bytes": broad_bytes,
                "result_ids": broad_ids,
            },
            "two_index_scope_first": {
                **two_summary,
                "db_bytes": two_bytes,
                "extra_bytes_vs_broad": two_bytes - broad_bytes,
                "build_ms": round(two_index_build_ms, 3),
                "p50_speedup_vs_broad": _speedup(broad_summary, two_summary, "p50_ms"),
                "p95_speedup_vs_broad": _speedup(broad_summary, two_summary, "p95_ms"),
                "result_ids": two_ids,
            },
            "single_index_scope_first": {
                **single_summary,
                "db_bytes": single_bytes,
                "extra_bytes_vs_broad": single_bytes - broad_bytes,
                "build_ms": round(single_index_build_ms, 3),
                "p50_speedup_vs_broad": _speedup(broad_summary, single_summary, "p50_ms"),
                "p95_speedup_vs_broad": _speedup(broad_summary, single_summary, "p95_ms"),
                "result_ids": single_ids,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(prog="scope-first-fts-three-way")
    parser.add_argument("--sizes", default="1000,10000,50000,100000")
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--output")
    args = parser.parse_args()

    result = {
        "benchmark": "memcarry-scope-first-fts-three-way-v1",
        "measurement_policy": (
            "experimental three-way comparison; production remains broad until single-index "
            "parity, storage, migration, and write synchronization are validated"
        ),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "github_actions": os.environ.get("GITHUB_ACTIONS") == "true",
        },
        "query": "architecture implementation",
        "config": {
            "warmup": max(0, args.warmup),
            "iterations": max(1, args.iterations),
        },
        "tiers": [],
    }

    for size in parse_sizes(args.sizes):
        tier = benchmark_tier(
            size,
            warmup=max(0, args.warmup),
            iterations=max(1, args.iterations),
        )
        result["tiers"].append(tier)
        parity = "same" if tier["same_result_ids"] else "DIFFERENT"
        broad = tier["broad"]
        two = tier["two_index_scope_first"]
        single = tier["single_index_scope_first"]
        print(f"\nMemory tier: {size:,} | ordered result ids: {parity}")
        print(
            f"  broad        p50={broad['p50_ms']:8.3f} ms p95={broad['p95_ms']:8.3f} ms "
            f"db={broad['db_bytes'] / (1024*1024):7.2f} MiB"
        )
        print(
            f"  two-index    p50={two['p50_ms']:8.3f} ms p95={two['p95_ms']:8.3f} ms "
            f"speedup={two['p50_speedup_vs_broad']:6.2f}x "
            f"extra={two['extra_bytes_vs_broad'] / (1024*1024):7.2f} MiB"
        )
        print(
            f"  single-index p50={single['p50_ms']:8.3f} ms p95={single['p95_ms']:8.3f} ms "
            f"speedup={single['p50_speedup_vs_broad']:6.2f}x "
            f"extra={single['extra_bytes_vs_broad'] / (1024*1024):7.2f} MiB"
        )

    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
        print(f"\nJSON: {output}")
    else:
        print("\n" + encoded)

    if any(not tier["same_result_ids"] for tier in result["tiers"]):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
