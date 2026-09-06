#!/usr/bin/env python3
"""SessionStart hook entry point for Codex, Claude Code, Gemini CLI, and AGY."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from memcarry.cli.hook_command import SessionStartHookCommand  # noqa: E402
from memcarry.cli.session_hook_protocol import (  # noqa: E402
    SUPPORTED_AGENTS,
    render_session_start_output,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="memcarry-session-start-hook")
    p.add_argument("--agent", choices=SUPPORTED_AGENTS, required=True)
    p.add_argument("--home", default=os.environ.get("MEMCARRY_HOME") or os.environ.get("AGENT_MEMORY_HUB_HOME") or "~/.memcarry")
    p.add_argument("--token-budget", type=int, default=1000)
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        payload = json.load(sys.stdin)
        command = SessionStartHookCommand(
            Path(args.home).expanduser(),
            args.agent,
            token_budget=max(1, args.token_budget),
        )
        print(command.handle(payload))
    except Exception as exc:
        # Hooks should fail open: continuity must never prevent the coding agent from starting.
        print(render_session_start_output(""))
        print(f"memcarry SessionStart hook warning: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
