from __future__ import annotations

import json
from pathlib import Path

from agent_memory_hub.cli.continuity import build_continuity_command
from agent_memory_hub.cli.session_hook import AgentKind, SessionHookAdapter


class SessionStartHookCommand:
    """Bridge supported agent SessionStart hooks to the seamless continuity pipeline."""

    def __init__(self, home: str | Path, agent: AgentKind | str, *, token_budget: int = 1000):
        self._home = Path(home).expanduser()
        self._adapter = SessionHookAdapter(agent)
        self._token_budget = max(1, token_budget)

    def _context_text(self, payload: dict) -> str:
        items = payload.get("items") or []
        if not items:
            return ""

        lines = [
            f"Agent Memory Hub continuity context ({payload.get('mode', 'recall')}):",
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
        invocation = self._adapter.parse(hook_payload)
        command = build_continuity_command(self._home, token_budget=self._token_budget)
        raw = command.run(
            message="",
            cwd=invocation.cwd,
            session_id=invocation.session_id,
            session_has_context=invocation.session_has_context,
            session_source=invocation.session_source,
            token_budget=self._token_budget,
            json_output=True,
        )
        payload = json.loads(raw)
        return self._adapter.render_output(self._context_text(payload))
