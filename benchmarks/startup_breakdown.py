#!/usr/bin/env python3
"""Fresh-process startup/import/composition breakdown for memcarry.

The measurements are diagnostic and intentionally not additive. Each fresh-process
case launches a new Python interpreter; internal cases time one operation after the
relevant imports have completed inside that child process.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "benchmarks"
SRC = ROOT / "src"
for value in (str(BENCH_DIR), str(SRC)):
    if value not in sys.path:
        sys.path.insert(0, value)

from continuity_baseline import create_database, create_repo, summarize_ms  # noqa: E402
from memcarry.infrastructure.sqlite.scope_index import ensure_single_index_scope_fts  # noqa: E402


def _python_env() -> dict[str, str]:
    env = os.environ.copy()
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC) if not current else str(SRC) + os.pathsep + current
    return env


def _wall_ms(code: str, env: dict[str, str]) -> float:
    started = time.perf_counter_ns()
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed = (time.perf_counter_ns() - started) / 1_000_000.0
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return elapsed


def _reported_ms(code: str, env: dict[str, str]) -> float:
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    try:
        return float(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise RuntimeError(f"invalid startup benchmark output: {result.stdout!r}") from exc


def _measure(fn, iterations: int, *, warmup: int = 1) -> dict[str, float | int]:
    for _ in range(max(0, warmup)):
        fn()
    values = [fn() for _ in range(max(1, iterations))]
    return summarize_ms(values)


def collect_startup_breakdown(
    *,
    iterations: int = 10,
    fixture_root: Path | None = None,
) -> dict:
    iterations = max(1, iterations)
    env = _python_env()
    root_parent = fixture_root
    if root_parent is not None:
        root_parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="memcarry-startup-", dir=root_parent) as td:
        base = Path(td)
        home = base / "memory"
        repo, context = create_repo(base)
        db = home / "memory.db"
        create_database(db, context, 1000)
        # Prompt recall sees an already migrated scope index in normal steady use.
        ensure_single_index_scope_fts(db)

        fresh_cases = {
            "python_empty": "pass",
            "import_sqlite3": "import sqlite3",
            "import_session_adapter": "import memcarry.cli.session_hook",
            "import_session_continuity": "import memcarry.cli.session_continuity",
            "import_hook_command": "import memcarry.cli.hook_command",
            "import_continuity": "import memcarry.cli.continuity",
        }
        fresh = {
            name: _measure(lambda c=code: _wall_ms(c, env), iterations)
            for name, code in fresh_cases.items()
        }

        home_literal = repr(str(home))
        repo_literal = repr(str(repo))
        db_literal = repr(str(db))
        internal_cases = {
            "build_session_start_after_import": (
                "import time; from pathlib import Path; "
                "from memcarry.cli.session_continuity import build_session_start_command; "
                f"h=Path({home_literal}); t=time.perf_counter_ns(); "
                "build_session_start_command(h); print((time.perf_counter_ns()-t)/1_000_000)"
            ),
            "build_continuity_after_import": (
                "import time; from pathlib import Path; "
                "from memcarry.cli.continuity import build_continuity_command; "
                f"h=Path({home_literal}); t=time.perf_counter_ns(); "
                "build_continuity_command(h); print((time.perf_counter_ns()-t)/1_000_000)"
            ),
            "git_inspect_after_import": (
                "import time; from memcarry.infrastructure.git.repository_inspector "
                "import GitRepositoryInspector; "
                f"r={repo_literal}; t=time.perf_counter_ns(); "
                "GitRepositoryInspector().inspect(r); print((time.perf_counter_ns()-t)/1_000_000)"
            ),
            "scope_index_check_after_import": (
                "import time; from pathlib import Path; "
                "from memcarry.infrastructure.sqlite.scope_index "
                "import ensure_single_index_scope_fts; "
                f"d=Path({db_literal}); t=time.perf_counter_ns(); "
                "ensure_single_index_scope_fts(d); print((time.perf_counter_ns()-t)/1_000_000)"
            ),
        }
        internal = {
            name: _measure(lambda c=code: _reported_ms(c, env), iterations)
            for name, code in internal_cases.items()
        }

        return {
            "benchmark": "memcarry-startup-breakdown-v2",
            "iterations": iterations,
            "fresh_process_wall": fresh,
            "internal_after_import": internal,
            "note": "diagnostic; phases are not additive",
        }


def _print(report: dict) -> None:
    print("Startup/process breakdown (p50/p95 ms; diagnostic, not additive)")
    print("  fresh Python process wall time:")
    for name, values in report["fresh_process_wall"].items():
        print(f"    {name:28s} {values['p50_ms']:8.2f}/{values['p95_ms']:.2f}")
    print("  internal operation after imports:")
    for name, values in report["internal_after_import"].items():
        print(f"    {name:28s} {values['p50_ms']:8.2f}/{values['p95_ms']:.2f}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="memcarry-startup-breakdown")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--output")
    args = parser.parse_args()
    report = collect_startup_breakdown(iterations=max(1, args.iterations))
    _print(report)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"JSON: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
