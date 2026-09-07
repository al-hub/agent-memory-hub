#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from memcarry.application.l1_ingestion_pipeline import L1IngestionPipeline
from memcarry.domain.l1_ingestion import L1Record
from memcarry.domain.l1_source import L1SourceFingerprint
from memcarry.infrastructure.sqlite.governed_l1_store import SQLiteGovernedL1Store
from memcarry.infrastructure.sqlite.l1_source_state import SQLiteL1SourceStateStore


REPOSITORY_ID = "benchmark/memcarry"
HEAD = "benchmark-head"


@dataclass
class BenchmarkSource:
    source_id: str
    records: list[L1Record]
    version: int

    @property
    def size(self) -> int:
        return len(self.records)

    def fingerprint(self) -> L1SourceFingerprint:
        return L1SourceFingerprint(
            source_id=self.source_id,
            size=self.size,
            mtime_ns=self.version,
            digest=f"v{self.version}:{self.size}",
        )

    def iter_records(self, *, repository_id: str | None = None, after_cursor: str | None = None):
        start = int(after_cursor or 0)
        for record in self.records[start:]:
            if repository_id is None or record.repository_id == repository_id:
                yield record


def make_records(count: int) -> list[L1Record]:
    return [
        L1Record(
            source_agent="benchmark",
            source_id=f"record-{i}",
            observed_at=f"2026-09-08T00:{i % 60:02d}:00Z",
            content=f"Benchmark decision {i}",
            kind="agent_summary",
            repository_id=REPOSITORY_ID,
            branch="main",
            head_sha=HEAD,
            source_path=f"/benchmark/session/{i}",
            memory_type="decision",
            semantic_key=f"decision-{i}",
        )
        for i in range(count)
    ]


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return ordered[index]


def timed(callable_) -> float:
    start = time.perf_counter_ns()
    callable_()
    return (time.perf_counter_ns() - start) / 1_000_000


def run_case(size: int, iterations: int) -> dict[str, object]:
    bootstrap_ms: list[float] = []
    unchanged_ms: list[float] = []
    plus_one_ms: list[float] = []
    resume_ms: list[float] = []

    for run in range(iterations):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "memory.db"
            state = SQLiteL1SourceStateStore(db_path)
            store = SQLiteGovernedL1Store(db_path)
            pipeline = L1IngestionPipeline(state, store)
            records = make_records(size)
            source = BenchmarkSource(f"source-{run}", records, 1)

            bootstrap_ms.append(
                timed(lambda: pipeline.ingest(
                    source,
                    repository_id=REPOSITORY_ID,
                    current_head=HEAD,
                    max_records=None,
                ))
            )
            unchanged_ms.append(
                timed(lambda: pipeline.ingest(
                    source,
                    repository_id=REPOSITORY_ID,
                    current_head=HEAD,
                    max_records=None,
                ))
            )

            plus_one_source = BenchmarkSource(
                source.source_id,
                records + make_records(1),
                2,
            )
            plus_one_source.records[-1] = L1Record(
                source_agent="benchmark",
                source_id="record-extra",
                observed_at="2026-09-08T01:00:00Z",
                content="Benchmark extra decision",
                kind="agent_summary",
                repository_id=REPOSITORY_ID,
                branch="main",
                head_sha=HEAD,
                source_path="/benchmark/session/extra",
                memory_type="decision",
                semantic_key="decision-extra",
            )
            plus_one_ms.append(
                timed(lambda: pipeline.ingest(
                    plus_one_source,
                    repository_id=REPOSITORY_ID,
                    current_head=HEAD,
                    max_records=None,
                ))
            )

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "memory.db"
            state = SQLiteL1SourceStateStore(db_path)
            store = SQLiteGovernedL1Store(db_path)
            pipeline = L1IngestionPipeline(state, store)
            records = make_records(size)
            source = BenchmarkSource(f"resume-{run}", records, 1)
            first_batch = max(1, size // 2)
            pipeline.ingest(
                source,
                repository_id=REPOSITORY_ID,
                current_head=HEAD,
                max_records=first_batch,
            )
            resume_ms.append(
                timed(lambda: pipeline.ingest(
                    source,
                    repository_id=REPOSITORY_ID,
                    current_head=HEAD,
                    max_records=None,
                ))
            )

    def summary(values: list[float]) -> dict[str, float]:
        return {
            "p50_ms": round(statistics.median(values), 3),
            "p95_ms": round(percentile(values, 0.95), 3),
        }

    return {
        "records": size,
        "bootstrap": summary(bootstrap_ms),
        "unchanged": summary(unchanged_ms),
        "plus_one": summary(plus_one_ms),
        "resume_half": summary(resume_ms),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default="10,100,1000")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--output")
    args = parser.parse_args()

    sizes = [int(value) for value in args.sizes.split(",") if value.strip()]
    results = {
        "benchmark": "l1_ingestion_baseline",
        "iterations": args.iterations,
        "cases": [run_case(size, args.iterations) for size in sizes],
    }
    payload = json.dumps(results, indent=2, sort_keys=True)
    print(payload)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
