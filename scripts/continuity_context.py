#!/usr/bin/env python3
"""Thin compatibility entry point for seamless memcarry continuity."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from memcarry.cli.continuity import build_continuity_command  # noqa: E402


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="memcarry-context")
    p.add_argument("message", help="Current user/task message used by the continuity gate")
    p.add_argument("--home", default=os.environ.get("MEMCARRY_HOME") or os.environ.get("AGENT_MEMORY_HUB_HOME") or "~/.memcarry")
    p.add_argument("--cwd", default=os.getcwd(), help="Current repository/worktree directory")
    p.add_argument("--session-id", help="Stable current agent session id when available")
    p.add_argument(
        "--empty-session",
        action="store_true",
        help="Mark current agent session as having little/no usable L1 context",
    )
    p.add_argument("--token-budget", type=int, default=1000)
    p.add_argument("--json", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    home = Path(args.home).expanduser()
    command = build_continuity_command(home, token_budget=max(1, args.token_budget))
    rendered = command.run(
        message=args.message,
        cwd=args.cwd,
        session_id=args.session_id,
        session_has_context=not args.empty_session,
        token_budget=max(1, args.token_budget),
        json_output=args.json,
    )
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
