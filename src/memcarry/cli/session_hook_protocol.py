from __future__ import annotations

import json

SUPPORTED_AGENTS = ("codex", "claude", "gemini", "agy")

_SOURCES = {
    "codex": {"startup", "resume", "clear", "compact"},
    "claude": {"startup", "resume", "clear", "compact", "fork"},
    "gemini": {"startup", "resume", "clear"},
    "agy": {"startup", "resume"},
}
_CONTEXTFUL_SOURCES = {"resume", "compact", "fork"}


def normalize_agent(agent) -> str:
    value = getattr(agent, "value", agent)
    if not isinstance(value, str) or value not in _SOURCES:
        raise ValueError(f"unsupported agent: {value!r}")
    return value


def parse_session_start(agent, payload: dict) -> tuple[str, str, str, bool, str | None]:
    agent_name = normalize_agent(agent)
    if payload.get("hook_event_name") != "SessionStart":
        raise ValueError("only SessionStart hook payloads are supported")

    session_id = payload.get("session_id")
    cwd = payload.get("cwd")
    source = payload.get("source")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("SessionStart payload requires session_id")
    if not isinstance(cwd, str) or not cwd.strip():
        raise ValueError("SessionStart payload requires cwd")
    if not isinstance(source, str) or source not in _SOURCES[agent_name]:
        raise ValueError(f"unsupported {agent_name} SessionStart source: {source!r}")

    transcript = payload.get("transcript_path")
    if transcript is not None and not isinstance(transcript, str):
        transcript = None
    return session_id, cwd, source, source in _CONTEXTFUL_SOURCES, transcript


def render_session_start_output(additional_context: str) -> str:
    hook_specific = {"hookEventName": "SessionStart"}
    if additional_context.strip():
        hook_specific["additionalContext"] = additional_context.strip()
    return json.dumps(
        {"hookSpecificOutput": hook_specific},
        ensure_ascii=False,
        separators=(",", ":"),
    )
