from __future__ import annotations

import json
from pathlib import Path

from memcarry.cli.session_continuity import build_session_start_command
from memcarry.cli.session_hook_protocol import (
    normalize_agent,
    parse_session_start,
    render_session_start_output,
)


class SessionStartHookCommand:
    """Bridge supported agent SessionStart hooks to the lightweight continuity path."""

    def __init__(self, home: str | Path, agent, *, token_budget: int = 1000):
        self._home = Path(home).expanduser()
        self._agent = normalize_agent(agent)
        self._token_budget = max(1, token_budget)

    def _context_text(self, payload: dict) -> str:
        items = payload.get("items") or []
        if not items:
            return ""

        lines = [
            f"Memcarry continuity context ({payload.get('mode', 'recall')}):",
            "Treat warnings as uncertainty and revalidate stale state against current code.",
        ]
        for item in items:
            lines.append(
                f"- [{item['type']}/{item['scope']}/{item['review_state']}] {item['statement']}"
            )
            if item.get("warning"):
                lines.append(f"  WARNING: {item['warning']}")
        return "\n".join(lines)

    def handle(self, hook_payload: dict) -> str:
        session_id, cwd, source, has_context, _ = parse_session_start(
            self._agent,
            hook_payload,
        )
        command = build_session_start_command(self._home, token_budget=self._token_budget)
        raw = command.run(
            message="",
            cwd=cwd,
            session_id=session_id,
            session_has_context=has_context,
            session_source=source,
            agent=self._agent,
            token_budget=self._token_budget,
            json_output=True,
        )
        payload = json.loads(raw)
        return render_session_start_output(self._context_text(payload))
