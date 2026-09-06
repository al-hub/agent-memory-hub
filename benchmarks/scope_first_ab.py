#!/usr/bin/env python3
"""A/B benchmark for broad FTS vs scope-first FTS retrieval.

This experiment keeps the existing broad reader as the control. The experimental
reader adds a second FTS5 column containing a deterministic token for each memory's
(scope, scope_ref), allowing FTS5 to intersect scope postings with lexical postings
before joining governed memory rows.

Result parity is part of the benchmark contract. A speedup is not considered valid
if the ordered result ids differ from the control reader.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BENCHMARKS = ROOT / "benchmarks"
for path in (SRC, BENCHMARKS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import continuity_baseline as baseline  # noqa: E402
from agent_memory_hub.domain.recall import RecallQuery  # noqa: E402
from agent_memory_hub.infrastructure.sqlite.retriever import SQLiteMemoryReader  # noqa: E402
from agent_memory_hub.infrastructure.sqlite.scope_first_retriever import (  # noqa: E402
    ScopeFirstSQLiteMemoryReader,
)
from agent_memory_hub.infrastructure.sqlite.scope_key import scope_fts_token  # noqa: E402


def parse_sizes(raw: str) -> list[int]:
    return baseline.parse_sizes(raw)


def build_scoped_fts(db_path: Path) -> float:
    """Build the experimental scoped FTS table and return wall-clock milliseconds."""
    started = time.perf_counter_ns()
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "CREATE VIRTUAL TABLE memory_fts_scoped USING fts5("
            "id UNINDEXED, statement, scope_key)"
        )
        rows = con.execute(
            "SELECT id, statement, scope, scope_ref FROM memories ORDER BY rowid"
        ).fetchall()
        con.executemany(
            "INSERT INTO memory_fts_scoped(id,statement,scope_key) VALUES(?,?,?)",
            [
                (memory_id, statement, scope_fts_token(scope, scope_ref))
                for memory_id, statement, scope, scope_ref in rows
            ],
        )
        con.commit()
    finally:
        con.close()
    return (time.perf_counter_ns() - started) / 1_000_000.0


def benchmark_tier(memory_count: int, *, warmup: int, iterations: int) -> dict:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="agent-memory-hub-scope-ab-") as td:
        base = Path(td)
        repo, context = baseline.create_repo(base)
        _ = repo
        db_path = base / "memory.db"
        baseline.create_database(db_path, context, memory_count)
        before_bytes = db_path.stat().st_size
        build_ms = build_scoped_fts(db_path)
        after_bytes = db_path.stat().st_size

        query = RecallQuery("architecture implementation", context, limit=8)
        broad_reader = SQLiteMemoryReader(db_path)
        scoped_reader = ScopeFirstSQLiteMemoryReader(db_path)

        broad_timings, broad_last = baseline.measure(
            lambda: broad_reader.recall(query),
            warmup=warmup,
            iterations=iterations,
        )
        scoped_timings, scoped_last = baseline.measure(
            lambda: scoped_reader.recall(query),
            warmup=warmup,
            iterations=iterations,
        )

        broad_ids = [item.id for item in broad_last]
        scoped_ids = [item.id for item in scoped_last]
        broad_summary = baseline.summarize_ms(broad_timings)
        scoped_summary = baseline.summarize_ms(scoped_timings)
        broad_p50 = float(broad_summary["p50_ms"])
        scoped_p50 = float(scoped_summary["p50_ms"])

        return {
            "memory_count": memory_count,
            "db_bytes_before_scoped_fts": before_bytes,
            "db_bytes_after_scoped_fts": after_bytes,
            "scoped_fts_extra_bytes": after_bytes - before_bytes,
            "scoped_fts_build_ms": round(build_ms, 3),
            "same_result_ids": broad_ids == scoped_ids,
            "broad": {**broad_summary, "result_ids": broad_ids},
            "scope_first": {**scoped_summary, "result_ids": scoped_ids},
            "p50_speedup": round(broad_p50 / scoped_p50, 3) if scoped_p50 > 0 else 0.0,
            "p95_speedup": round(
                float(broad_summary["p95_ms"]) / float(scoped_summary["p95_ms"]),
                3,
            )
            if float(scoped_summary["p95_ms"]) > 0
            else 0.0,
        }


def main() -> int:
    parser = argparse.ArgumentParser(prog="scope-first-fts-ab")
    parser.add_argument("--sizes", default="1000,10000,50000,100000")
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--output")
    args = parser.parse_args()

    result = {
        "benchmark": "agent-memory-hub-scope-first-fts-ab-v1",
        "measurement_policy": (
            "experimental A/B; broad FTS remains production control until parity and practical "
            "scale results justify adoption"
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
        extra_mib = tier["scoped_fts_extra_bytes"] / (1024 * 1024)
        print(f"\nMemory tier: {size:,} | result ids: {parity}")
        print(
            f"  broad       p50={tier['broad']['p50_ms']:8.3f} ms "
            f"p95={tier['broad']['p95_ms']:8.3f} ms"
        )
        print(
            f"  scope-first p50={tier['scope_first']['p50_ms']:8.3f} ms "
            f"p95={tier['scope_first']['p95_ms']:8.3f} ms"
        )
        print(
            f"  speedup     p50={tier['p50_speedup']:8.2f}x "
            f"p95={tier['p95_speedup']:8.2f}x"
        )
        print(
            f"  scoped FTS build={tier['scoped_fts_build_ms']:8.1f} ms "
            f"extra storage={extra_mib:8.2f} MiB"
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
