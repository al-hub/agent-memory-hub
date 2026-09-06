#!/usr/bin/env python3
"""SessionStart hook entry point for Codex, Claude Code, and Gemini CLI."""
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

from agent_memory_hub.cli.hook_command import SessionStartHookCommand  # noqa: E402
from agent_memory_hub.cli.session_hook import AgentKind, SessionHookAdapter  # noqa: E402


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="memory-hub-session-start-hook")
    p.add_argument("--agent", choices=[x.value for x in AgentKind], required=True)
    p.add_argument("--home", default=os.environ.get("AGENT_MEMORY_HUB_HOME", "~/.agent-memory-hub"))
    p.add_argument("--token-budget", type=int, default=1000)
    return p


def main() -> int:
    args = parser().parse_args()
    adapter = SessionHookAdapter(args.agent)
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
        print(adapter.render_output(""))
        print(f"agent-memory-hub SessionStart hook warning: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
