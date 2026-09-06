#!/usr/bin/env python3
"""Practical local-machine benchmark for memcarry.

This wrapper reuses the repository's continuity baseline and adds:
- WSL / CPU / RAM / filesystem / toolchain metadata
- fresh-process prompt continuity timings for NO_RECALL / RESUME / HANDOFF
- startup/import/composition phase breakdown
- a compact shareable summary plus JSON report

"Warm" means the in-process core after configured warmups.
"Fresh-process" means a new Python process for each measured continuity request.
It does not claim to flush the operating-system page cache.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "benchmarks"
SRC = ROOT / "src"
for p in (str(BENCH_DIR), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

from continuity_baseline import (  # noqa: E402
    benchmark_tier,
    create_database,
    create_repo,
    measure,
    parse_sizes,
    payload_meta,
    summarize_ms,
)
from startup_breakdown import collect_startup_breakdown  # noqa: E402
from memcarry.infrastructure.filesystem.continuity_state_store import JsonContinuityStateStore  # noqa: E402
from memcarry.ports.continuity_state import StoredContinuityState  # noqa: E402

CONTINUITY_SCRIPT = ROOT / "scripts" / "continuity_context.py"


def command_output(*args: str) -> str | None:
    try:
        result = subprocess.run(args, text=True, capture_output=True, check=False)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr).strip() or None


def nearest_existing(path: Path) -> Path:
    current = path.expanduser().resolve()
    while not current.exists() and current.parent != current:
        current = current.parent
    return current


def filesystem_info(path: Path) -> dict[str, str | None]:
    target = nearest_existing(path)
    result = command_output("df", "-T", "-P", str(target))
    if not result:
        return {"path": display_path(target), "type": None, "mount": None}
    lines = [line for line in result.splitlines() if line.strip()]
    if len(lines) < 2:
        return {"path": display_path(target), "type": None, "mount": None}
    parts = lines[-1].split()
    return {
        "path": display_path(target),
        "type": parts[1] if len(parts) >= 2 else None,
        "mount": display_path(Path(parts[-1])) if parts else None,
    }


def display_path(path: Path) -> str:
    try:
        home = Path.home().resolve()
        resolved = path.resolve()
        if resolved == home:
            return "~"
        if home in resolved.parents:
            return "~/" + str(resolved.relative_to(home))
        return str(resolved)
    except OSError:
        return str(path)


def read_first_cpu_model() -> str | None:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or None


def total_memory_gib() -> float | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("MemTotal:"):
                kib = int(line.split()[1])
                return round(kib / 1024 / 1024, 2)
    except (OSError, ValueError, IndexError):
        pass
    return None


def detect_wsl() -> dict[str, object]:
    release = platform.release()
    try:
        proc_version = Path("/proc/version").read_text(encoding="utf-8", errors="replace")
    except OSError:
        proc_version = ""
    signal = (release + " " + proc_version).lower()
    is_wsl = "microsoft" in signal or bool(os.environ.get("WSL_DISTRO_NAME"))
    version = None
    if is_wsl:
        version = 2 if "wsl2" in signal or "microsoft-standard" in release.lower() else 1
    return {
        "detected": is_wsl,
        "version": version,
        "distro": os.environ.get("WSL_DISTRO_NAME"),
        "interop": bool(os.environ.get("WSL_INTEROP")),
    }


def sqlite_fts5_available() -> bool:
    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE VIRTUAL TABLE test_fts USING fts5(text)")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        con.close()


def environment_info(memory_home: Path) -> dict:
    return {
        "python": platform.python_version(),
        "node": os.environ.get("MEMCARRY_BENCHMARK_NODE") or command_output("node", "--version"),
        "npx": command_output("npx", "--version"),
        "git": command_output("git", "--version"),
        "sqlite": sqlite3.sqlite_version,
        "sqlite_fts5": sqlite_fts5_available(),
        "platform": platform.platform(),
        "kernel": platform.release(),
        "machine": platform.machine(),
        "cpu_model": read_first_cpu_model(),
        "logical_cpu_count": os.cpu_count(),
        "memory_gib": total_memory_gib(),
        "wsl": detect_wsl(),
        "filesystem": {
            "cwd": filesystem_info(Path.cwd()),
            "memory_home": filesystem_info(memory_home),
            "system_temp": filesystem_info(Path(tempfile.gettempdir())),
        },
    }


def benchmark_process_cold_tier(
    memory_count: int,
    *,
    warmup: int,
    iterations: int,
    memory_home_root: Path,
) -> dict:
    memory_home_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="process-cold-", dir=memory_home_root) as td:
        base = Path(td)
        home = base / "memory"
        repo, context = create_repo(base)
        db_path = home / "memory.db"
        create_database(db_path, context, memory_count)

        repo_id = context.repository.canonical_id
        worktree_id = context.worktree_id
        head = context.head_sha
        state_store = JsonContinuityStateStore(home / "continuity-state.json")

        def checkpoint(session_id: str):
            state_store.save(
                repo_id,
                worktree_id,
                StoredContinuityState(session_id=session_id, head_sha=head),
            )

        def process_case(message: str, session_id: str) -> str:
            result = subprocess.run(
                [
                    sys.executable,
                    str(CONTINUITY_SCRIPT),
                    message,
                    "--home", str(home),
                    "--cwd", str(repo),
                    "--session-id", session_id,
                    "--json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr or result.stdout)
            return result.stdout.strip()

        cases = {
            "no_recall": ("rename local variable", "process-steady"),
            "resume_prompt": ("continue architecture implementation", "process-steady"),
            "handoff_prompt": ("Claude continue architecture implementation", "process-steady"),
        }
        results = {}
        for name, (message, session_id) in cases.items():
            timings, last = measure(
                lambda m=message, sid=session_id: process_case(m, sid),
                warmup=min(max(0, warmup), 2),
                iterations=max(1, iterations),
                before_each=lambda sid=session_id: checkpoint(sid),
            )
            results[name] = {**summarize_ms(timings), **payload_meta(last)}
        return results


def latency_pair(values: dict) -> str:
    return f"{values['p50_ms']:.2f}/{values['p95_ms']:.2f}"


def print_environment(env: dict) -> None:
    wsl = env["wsl"]
    wsl_label = "no"
    if wsl["detected"]:
        wsl_label = f"WSL{wsl['version'] or '?'}"
        if wsl.get("distro"):
            wsl_label += f" {wsl['distro']}"
    print("\nEnvironment")
    print(f"  WSL:        {wsl_label}")
    print(f"  CPU:        {env['cpu_model'] or 'unknown'} ({env['logical_cpu_count']} logical)")
    print(f"  RAM:        {env['memory_gib'] if env['memory_gib'] is not None else 'unknown'} GiB")
    print(f"  Kernel:     {env['kernel']}")
    print(f"  Python:     {env['python']}")
    print(f"  Node:       {env['node'] or 'unknown'}")
    print(f"  Git:        {env['git'] or 'unknown'}")
    print(f"  SQLite:     {env['sqlite']} (FTS5={'yes' if env['sqlite_fts5'] else 'no'})")
    for name, info in env["filesystem"].items():
        print(f"  fs/{name:11s} {info['type'] or 'unknown'} @ {info['mount'] or info['path']}")


def print_startup_breakdown(startup: dict) -> None:
    print("\nStartup/process breakdown (p50/p95 ms; diagnostic, not additive)")
    print("  fresh Python process wall time:")
    for name, values in startup["fresh_process_wall"].items():
        print(f"    {name:28s} {latency_pair(values):>14s}")
    print("  internal operation after imports:")
    for name, values in startup["internal_after_import"].items():
        print(f"    {name:28s} {latency_pair(values):>14s}")


def print_summary(report: dict, output: Path) -> None:
    print_startup_breakdown(report["startup_breakdown"])
    print("\nPractical latency summary (p50/p95 ms)")
    print("  warm = in-process after warmup; fresh = new Python process each request")
    print("  memories | warm no-recall | fresh no-recall | warm resume | fresh resume | warm handoff | fresh handoff | codex hook | agy hook")
    for tier in report["tiers"]:
        scenarios = tier["scenarios"]
        cold = tier["process_cold"]
        print(
            f"  {tier['memory_count']:8,d} |"
            f" {latency_pair(scenarios['no_recall']):>14s} |"
            f" {latency_pair(cold['no_recall']):>15s} |"
            f" {latency_pair(scenarios['resume_prompt']):>11s} |"
            f" {latency_pair(cold['resume_prompt']):>12s} |"
            f" {latency_pair(scenarios['handoff_prompt']):>12s} |"
            f" {latency_pair(cold['handoff_prompt']):>13s} |"
            f" {latency_pair(scenarios['hook_codex_resume']):>10s} |"
            f" {latency_pair(scenarios['hook_agy_pre_invocation']):>9s}"
        )
    print("\nNotes")
    print("  - fresh-process does not flush the OS page cache; it isolates Python/import/composition startup.")
    print("  - startup phases are diagnostic and not additive.")
    print("  - benchmark uses synthetic governed memories and deletes temporary fixtures automatically.")
    print("  - p50 is median; p95 is the latency that 95% of runs finish at or below.")
    print(f"\nJSON: {output}")
    print("Share either this summary or the JSON report for comparison with the GitHub Actions baseline.")


def main() -> int:
    parser = argparse.ArgumentParser(prog="memcarry-machine-benchmark")
    parser.add_argument("--sizes", default="1000,10000,50000,100000")
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--subprocess-iterations", type=int, default=10)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    sizes = parse_sizes(args.sizes)
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    memory_home = Path(os.environ.get("MEMCARRY_HOME", Path.home() / ".memcarry")).expanduser()
    fixture_root = memory_home / "benchmark-fixtures"

    env = environment_info(memory_home)
    print_environment(env)
    startup_breakdown = collect_startup_breakdown(
        iterations=max(1, args.subprocess_iterations),
        fixture_root=fixture_root,
    )

    result = {
        "benchmark": "memcarry-practical-machine-v2",
        "measurement_policy": "reference baseline only; not a latency promise or hard performance gate",
        "definitions": {
            "warm": "in-process continuity after configured warmups",
            "fresh_process": "new Python process per continuity request; OS page cache is not forcibly cleared",
            "startup_breakdown": "fresh-process import walls plus internal operations after imports; diagnostic and not additive",
            "p50": "median latency",
            "p95": "95% of runs complete at or below this latency",
        },
        "environment": env,
        "startup_breakdown": startup_breakdown,
        "config": {
            "sizes": sizes,
            "warmup": max(0, args.warmup),
            "iterations": max(1, args.iterations),
            "subprocess_iterations": max(1, args.subprocess_iterations),
        },
        "tiers": [],
    }

    try:
        for size in sizes:
            print(f"\nBenchmarking {size:,} memories...")
            tier = benchmark_tier(
                size,
                warmup=max(0, args.warmup),
                iterations=max(1, args.iterations),
                subprocess_iterations=max(1, args.subprocess_iterations),
            )
            tier["process_cold"] = benchmark_process_cold_tier(
                size,
                warmup=max(0, args.warmup),
                iterations=max(1, args.subprocess_iterations),
                memory_home_root=fixture_root,
            )
            result["tiers"].append(tier)
    finally:
        try:
            fixture_root.rmdir()
        except OSError:
            pass

    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print_summary(result, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
