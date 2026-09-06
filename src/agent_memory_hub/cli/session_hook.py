from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum


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
    """Normalize SessionStart hook payloads from supported coding agents."""

    _SOURCES = {
        AgentKind.CODEX: {"startup", "resume", "clear", "compact"},
        AgentKind.CLAUDE: {"startup", "resume", "clear", "compact", "fork"},
        AgentKind.GEMINI: {"startup", "resume", "clear"},
    }
    _CONTEXTFUL_SOURCES = {"resume", "compact", "fork"}

    def __init__(self, agent: AgentKind | str):
        self.agent = AgentKind(agent)

    def parse(self, payload: dict) -> SessionHookInvocation:
        if payload.get("hook_event_name") != "SessionStart":
            raise ValueError("only SessionStart hook payloads are supported")

        session_id = payload.get("session_id")
        cwd = payload.get("cwd")
        source = payload.get("source")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("SessionStart payload requires session_id")
        if not isinstance(cwd, str) or not cwd.strip():
            raise ValueError("SessionStart payload requires cwd")
        if not isinstance(source, str) or source not in self._SOURCES[self.agent]:
            raise ValueError(f"unsupported {self.agent.value} SessionStart source: {source!r}")

        transcript = payload.get("transcript_path")
        if transcript is not None and not isinstance(transcript, str):
            transcript = None

        return SessionHookInvocation(
            agent=self.agent,
            session_id=session_id,
            cwd=cwd,
            session_source=source,
            session_has_context=source in self._CONTEXTFUL_SOURCES,
            transcript_path=transcript,
        )

    def render_output(self, additional_context: str) -> str:
        hook_specific = {"hookEventName": "SessionStart"}
        if additional_context.strip():
            hook_specific["additionalContext"] = additional_context.strip()
        return json.dumps(
            {"hookSpecificOutput": hook_specific},
            ensure_ascii=False,
            separators=(",", ":"),
        )
