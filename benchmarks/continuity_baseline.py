#!/usr/bin/env python3
"""Reproducible local baseline for practical agent continuity latency.

This benchmark measures three views of the same real-world path:
1. end-to-end in-process continuity scenarios
2. isolated local phases (Git/state/SQLite/projection)
3. SessionStart hook subprocess latency (Python startup included)

It is a baseline recorder, not a CI performance gate. Shared CI runners are noisy;
compare distributions and trends rather than treating one run as a promise.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from memcarry.application.context_projector import ContextProjector  # noqa: E402
from memcarry.cli.continuity import build_continuity_command  # noqa: E402
from memcarry.domain.continuity import ContinuityMode  # noqa: E402
from memcarry.domain.recall import RecallQuery  # noqa: E402
from memcarry.infrastructure.filesystem.continuity_state_store import JsonContinuityStateStore  # noqa: E402
from memcarry.infrastructure.git.repository_inspector import GitRepositoryInspector  # noqa: E402
from memcarry.infrastructure.sqlite.repository_knowledge import SQLiteRepositoryKnowledgeReader  # noqa: E402
from memcarry.infrastructure.sqlite.retriever import SQLiteMemoryReader  # noqa: E402
from memcarry.ports.continuity_state import StoredContinuityState  # noqa: E402

HOOK_SCRIPT = ROOT / "scripts" / "session_start_hook.py"
ANTIGRAVITY_HOOK_SCRIPT = ROOT / "scripts" / "antigravity_hook.py"


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    weight = pos - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


def summarize_ms(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "min_ms": round(min(values), 3) if values else 0.0,
        "p50_ms": round(percentile(values, 0.50), 3),
        "p95_ms": round(percentile(values, 0.95), 3),
        "mean_ms": round(statistics.fmean(values), 3) if values else 0.0,
        "max_ms": round(max(values), 3) if values else 0.0,
    }


def run_git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def create_repo(base: Path) -> tuple[Path, object]:
    repo = base / "repo"
    repo.mkdir()
    run_git("init", "-b", "main", str(repo))
    run_git("config", "user.email", "benchmark@example.com", cwd=repo)
    run_git("config", "user.name", "Memcarry Benchmark", cwd=repo)
    run_git("remote", "add", "origin", "git@github.com:al-hub/memcarry-benchmark.git", cwd=repo)
    (repo / "README.md").write_text("benchmark\n", encoding="utf-8")
    run_git("add", "README.md", cwd=repo)
    run_git("commit", "-m", "benchmark baseline", cwd=repo)
    context = GitRepositoryInspector().inspect(str(repo))
    return repo, context


def create_database(db_path: Path, context, memory_count: int) -> None:
    repo_id = context.repository.canonical_id
    branch_ref = f"{repo_id}::branch::{context.branch}"
    worktree_ref = f"{repo_id}::worktree::{context.worktree_id}"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE memories(
          id TEXT PRIMARY KEY,
          statement TEXT NOT NULL,
          type TEXT NOT NULL,
          lifecycle TEXT NOT NULL,
          review_state TEXT NOT NULL,
          confidence REAL NOT NULL,
          scope TEXT NOT NULL,
          scope_ref TEXT,
          updated_at INTEGER NOT NULL
        );
        CREATE VIRTUAL TABLE memory_fts USING fts5(id UNINDEXED, statement);
        """
    )

    types = ("decision", "constraint", "project_state", "lesson", "procedure", "fact")
    rows: list[tuple] = []
    visible_count = min(64, max(16, memory_count // 100))
    for i in range(memory_count):
        memory_type = types[i % len(types)]
        lifecycle = "active"
        review = "verified"
        confidence = 0.90 + (i % 9) / 100.0
        updated_at = i + 1

        if i < visible_count:
            scope_kind = i % 4
            if scope_kind == 0:
                scope, scope_ref = "worktree", worktree_ref
            elif scope_kind == 1:
                scope, scope_ref = "branch", branch_ref
            elif scope_kind == 2:
                scope, scope_ref = "repository", repo_id
            else:
                scope, scope_ref = "global", None
            statement = (
                f"Architecture implementation continuity memory {i}: "
                f"keep scoped local FTS5 and bounded context for {memory_type}."
            )
        else:
            foreign = f"github.com/example/project-{i % 97}"
            scope, scope_ref = "repository", foreign
            statement = (
                f"Unrelated project memory {i}: architecture implementation detail "
                f"for foreign repository {i % 97}."
            )

        if i == visible_count - 2:
            lifecycle = "superseded"
        elif i == visible_count - 1:
            lifecycle = "quarantined"

        rows.append(
            (
                f"m{i:07d}", statement, memory_type, lifecycle, review,
                confidence, scope, scope_ref, updated_at,
            )
        )

    con.executemany("INSERT INTO memories VALUES(?,?,?,?,?,?,?,?,?)", rows)
    con.executemany(
        "INSERT INTO memory_fts(id,statement) VALUES(?,?)",
        [(row[0], row[1]) for row in rows],
    )
    con.commit()
    con.close()


def measure(fn, *, warmup: int, iterations: int, before_each=None) -> tuple[list[float], object]:
    last = None
    for _ in range(warmup):
        if before_each:
            before_each()
        last = fn()
    timings: list[float] = []
    for _ in range(iterations):
        if before_each:
            before_each()
        started = time.perf_counter_ns()
        last = fn()
        timings.append((time.perf_counter_ns() - started) / 1_000_000.0)
    return timings, last


def payload_meta(rendered: str) -> dict:
    payload = json.loads(rendered)
    return {
        "mode": payload.get("mode"),
        "estimated_tokens": payload.get("estimated_tokens", 0),
        "items": len(payload.get("items") or []),
        "stale_head": bool((payload.get("state") or {}).get("stale_head")),
    }


def benchmark_tier(memory_count: int, *, warmup: int, iterations: int, subprocess_iterations: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="memcarry-bench-") as td:
        base = Path(td)
        home = base / "memory"
        repo, context = create_repo(base)
        db_path = home / "memory.db"
        create_database(db_path, context, memory_count)

        command = build_continuity_command(home, token_budget=1000)
        state_store = JsonContinuityStateStore(home / "continuity-state.json")
        repo_id = context.repository.canonical_id
        worktree_id = context.worktree_id
        head1 = context.head_sha

        scenarios = {}

        def command_case(message: str, *, session_id: str, has_context: bool = True, source: str | None = None):
            return command.run(
                message=message,
                cwd=str(repo),
                session_id=session_id,
                session_has_context=has_context,
                session_source=source,
                token_budget=1000,
                json_output=True,
            )

        def checkpoint(session_id: str | None, head_sha: str):
            state_store.save(
                repo_id,
                worktree_id,
                StoredContinuityState(session_id=session_id, head_sha=head_sha),
            )

        cases = {
            "no_recall": (
                lambda: command_case("rename local variable", session_id="bench-steady"),
                lambda: checkpoint("bench-steady", head1),
            ),
            "resume_prompt": (
                lambda: command_case("continue architecture implementation", session_id="bench-steady"),
                lambda: checkpoint("bench-steady", head1),
            ),
            "handoff_prompt": (
                lambda: command_case("Claude continue architecture implementation", session_id="bench-steady"),
                lambda: checkpoint("bench-steady", head1),
            ),
            "session_start_onboarding": (
                lambda: command_case("", session_id="bench-startup", has_context=False, source="startup"),
                lambda: checkpoint(None, head1),
            ),
            "session_start_resume": (
                lambda: command_case("", session_id="bench-resume", has_context=True, source="resume"),
                lambda: checkpoint("bench-resume", head1),
            ),
        }

        for name, (fn, prepare) in cases.items():
            timings, last = measure(
                fn,
                warmup=warmup,
                iterations=iterations,
                before_each=prepare,
            )
            scenarios[name] = {**summarize_ms(timings), **payload_meta(last)}

        # Isolated phase timings are diagnostic and are NOT additive. Each measures
        # one component repeatedly with its normal local I/O behavior.
        inspector = GitRepositoryInspector()
        knowledge_reader = SQLiteRepositoryKnowledgeReader(db_path)
        memory_reader = SQLiteMemoryReader(db_path)
        projector = ContextProjector()
        checkpoint("phase-session", head1)
        browse_query = RecallQuery("", context, limit=12)
        fts_query = RecallQuery("architecture implementation", context, limit=8)
        browse_candidates = memory_reader.recall(browse_query)

        isolated_phases = {}
        phase_cases = {
            "python_startup": (
                lambda: subprocess.run(
                    [sys.executable, "-c", "pass"],
                    check=True,
                    capture_output=True,
                    text=True,
                ),
                min(warmup, 2),
                subprocess_iterations,
            ),
            "git_inspect": (lambda: inspector.inspect(str(repo)), warmup, iterations),
            "repository_known": (lambda: knowledge_reader.has_repository(repo_id), warmup, iterations),
            "checkpoint_load": (lambda: state_store.load(repo_id, worktree_id), warmup, iterations),
            "checkpoint_save": (
                lambda: checkpoint("phase-session", head1),
                warmup,
                iterations,
            ),
            "sqlite_scope_browse": (lambda: memory_reader.recall(browse_query), warmup, iterations),
            "sqlite_fts_recall": (lambda: memory_reader.recall(fts_query), warmup, iterations),
            "project_resume": (
                lambda: projector.project(
                    browse_candidates,
                    mode=ContinuityMode.RESUME,
                    token_budget=1000,
                ),
                warmup,
                iterations,
            ),
        }
        for name, (fn, phase_warmup, phase_iterations) in phase_cases.items():
            timings, _ = measure(
                fn,
                warmup=phase_warmup,
                iterations=max(1, phase_iterations),
            )
            isolated_phases[name] = summarize_ms(timings)

        # Make HEAD stale, then restore the old checkpoint before every timed call.
        (repo / "CHANGE.md").write_text("new head\n", encoding="utf-8")
        run_git("add", "CHANGE.md", cwd=repo)
        run_git("commit", "-m", "advance head", cwd=repo)
        head2 = run_git("rev-parse", "HEAD", cwd=repo)

        stale_timings, stale_last = measure(
            lambda: command_case("", session_id="bench-stale", has_context=True, source="resume"),
            warmup=warmup,
            iterations=iterations,
            before_each=lambda: checkpoint("bench-stale", head1),
        )
        scenarios["stale_head_resume"] = {**summarize_ms(stale_timings), **payload_meta(stale_last)}

        def hook_case(agent: str, source: str, session_id: str):
            payload = json.dumps(
                {
                    "hook_event_name": "SessionStart",
                    "session_id": session_id,
                    "cwd": str(repo),
                    "source": source,
                }
            )
            env = os.environ.copy()
            env["MEMCARRY_HOME"] = str(home)
            result = subprocess.run(
                [sys.executable, str(HOOK_SCRIPT), "--agent", agent],
                input=payload,
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr or result.stdout)
            return result.stdout.strip()

        def antigravity_hook_case(session_id: str):
            payload = json.dumps(
                {
                    "conversationId": session_id,
                    "workspacePaths": [str(repo)],
                    "invocationNum": 0,
                }
            )
            env = os.environ.copy()
            env["MEMCARRY_HOME"] = str(home)
            result = subprocess.run(
                [sys.executable, str(ANTIGRAVITY_HOOK_SCRIPT), "--home", str(home), "--event", "pre-invocation"],
                input=payload,
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr or result.stdout)
            return result.stdout.strip()

        hook_cases = (
            ("hook_codex_resume", "codex", "resume", "hook-codex", "hook-codex"),
            ("hook_claude_clear", "claude", "clear", "hook-claude", "hook-claude"),
            ("hook_gemini_startup", "gemini", "startup", "hook-gemini", None),
        )
        for name, agent, source, session_id, prior_session in hook_cases:
            timings, last = measure(
                lambda a=agent, s=source, sid=session_id: hook_case(a, s, sid),
                warmup=min(warmup, 2),
                iterations=subprocess_iterations,
                before_each=lambda sid=prior_session: checkpoint(sid, head2),
            )
            hook_output = json.loads(last)
            additional = (hook_output.get("hookSpecificOutput") or {}).get("additionalContext", "")
            scenarios[name] = {
                **summarize_ms(timings),
                "additional_context_bytes": len(additional.encode("utf-8")),
            }

        timings, last = measure(
            lambda: antigravity_hook_case("hook-agy"),
            warmup=min(warmup, 2),
            iterations=subprocess_iterations,
            before_each=lambda: checkpoint("hook-agy", head2),
        )
        agy_output = json.loads(last)
        injected = agy_output.get("injectSteps") or []
        context = "\n".join(
            step.get("ephemeralMessage", "")
            for step in injected
            if isinstance(step, dict)
        )
        scenarios["hook_agy_pre_invocation"] = {
            **summarize_ms(timings),
            "additional_context_bytes": len(context.encode("utf-8")),
        }

        return {
            "memory_count": memory_count,
            "db_bytes": db_path.stat().st_size,
            "visible_memory_target": min(64, max(16, memory_count // 100)),
            "scenarios": scenarios,
            "isolated_phases": isolated_phases,
        }


def parse_sizes(raw: str) -> list[int]:
    sizes = [int(value.strip()) for value in raw.split(",") if value.strip()]
    if not sizes or any(value < 1 for value in sizes):
        raise ValueError("sizes must contain positive integers")
    return sizes


def main() -> int:
    p = argparse.ArgumentParser(prog="continuity-baseline")
    p.add_argument("--sizes", default="1000,10000,50000,100000")
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--iterations", type=int, default=30)
    p.add_argument("--subprocess-iterations", type=int, default=10)
    p.add_argument("--output")
    args = p.parse_args()

    sizes = parse_sizes(args.sizes)
    result = {
        "benchmark": "memcarry-continuity-baseline-v2",
        "measurement_policy": "reference baseline only; not a performance promise or CI gate",
        "percentiles": {
            "p50": "median: 50% of runs complete at or below this latency",
            "p95": "tail indicator: 95% of runs complete at or below this latency",
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "github_actions": os.environ.get("GITHUB_ACTIONS") == "true",
            "runner_os": os.environ.get("RUNNER_OS"),
            "runner_arch": os.environ.get("RUNNER_ARCH"),
        },
        "config": {
            "warmup": max(0, args.warmup),
            "iterations": max(1, args.iterations),
            "subprocess_iterations": max(1, args.subprocess_iterations),
            "token_budget": 1000,
        },
        "tiers": [],
    }

    for size in sizes:
        tier = benchmark_tier(
            size,
            warmup=max(0, args.warmup),
            iterations=max(1, args.iterations),
            subprocess_iterations=max(1, args.subprocess_iterations),
        )
        result["tiers"].append(tier)
        print(f"\nMemory tier: {size:,} ({tier['db_bytes'] / 1024:.1f} KiB)")
        for name, values in tier["scenarios"].items():
            print(
                f"  {name:26s} p50={values['p50_ms']:8.3f} ms "
                f"p95={values['p95_ms']:8.3f} ms"
            )
        print("  isolated phases (diagnostic, not additive):")
        for name, values in tier["isolated_phases"].items():
            print(
                f"    {name:24s} p50={values['p50_ms']:8.3f} ms "
                f"p95={values['p95_ms']:8.3f} ms"
            )

    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
        print(f"\nJSON: {output}")
    else:
        print("\n" + encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
