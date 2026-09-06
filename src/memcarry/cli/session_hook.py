from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from memcarry.cli.session_hook_protocol import (
    normalize_agent,
    parse_session_start,
    render_session_start_output,
)


class AgentKind(str, Enum):
    CODEX = "codex"
    CLAUDE = "claude"
    GEMINI = "gemini"


@dataclass(frozen=True, slots=True)
class SessionHookInvocation:
    agent: AgentKind
    session_id: str
    cwd: str
    session_source: str
    session_has_context: bool
    transcript_path: str | None = None


class SessionHookAdapter:
    """Compatibility OO adapter over the lightweight SessionStart protocol."""

    def __init__(self, agent: AgentKind | str):
        self.agent = AgentKind(normalize_agent(agent))

    def parse(self, payload: dict) -> SessionHookInvocation:
        session_id, cwd, source, has_context, transcript = parse_session_start(
            self.agent.value,
            payload,
        )
        return SessionHookInvocation(
            agent=self.agent,
            session_id=session_id,
            cwd=cwd,
            session_source=source,
            session_has_context=has_context,
            transcript_path=transcript,
        )

    def render_output(self, additional_context: str) -> str:
        return render_session_start_output(additional_context)
