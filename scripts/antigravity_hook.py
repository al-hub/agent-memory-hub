#!/usr/bin/env python3
"""Antigravity CLI PreInvocation adapter for Memcarry continuity context."""
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


def main() -> int:
    parser = argparse.ArgumentParser(prog="memcarry-antigravity-hook")
    parser.add_argument("--home", default=os.environ.get("MEMCARRY_HOME") or os.environ.get("AGENT_MEMORY_HUB_HOME") or "~/.memcarry")
    parser.add_argument("--event", default="pre-invocation")
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        if args.event != "pre-invocation" or payload.get("invocationNum", 0) != 0:
            print("{}")
            return 0
        workspaces = payload.get("workspacePaths") or []
        cwd = workspaces[0] if workspaces else os.getcwd()
        session_id = payload.get("conversationId")
        if not isinstance(session_id, str) or not session_id:
            print("{}")
            return 0
        synthetic = {"hook_event_name": "SessionStart", "session_id": session_id, "cwd": cwd, "source": "startup"}
        raw = SessionStartHookCommand(Path(args.home).expanduser(), "agy").handle(synthetic)
        context = json.loads(raw).get("hookSpecificOutput", {}).get("additionalContext", "")
        if context:
            print(json.dumps({"injectSteps": [{"ephemeralMessage": context}]}, ensure_ascii=False, separators=(",", ":")))
        else:
            print("{}")
    except Exception as exc:
        print("{}")
        print(f"memcarry Antigravity hook warning: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
