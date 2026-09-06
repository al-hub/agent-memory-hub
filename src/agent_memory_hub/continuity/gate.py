from __future__ import annotations

import re

from agent_memory_hub.domain.continuity import (
    ContinuityDecision,
    ContinuityMode,
    ContinuityRequest,
)


class ContinuityGate:
    """Cheap deterministic gate deciding whether shared memory should be recalled."""

    _AGENTS = ("claude", "codex", "gemini", "antigravity")
    _HANDOFF_ACTION = re.compile(r"(?:하던|작업|이어|handoff|continue)", re.IGNORECASE)
    _RESUME = re.compile(
        r"(?:이어서|이어\s*서|계속\s*(?:진행|해|하자|해줘)?|하던\s*(?:것|거|작업)|resume|continue)",
        re.IGNORECASE,
    )
    _PAST_RECALL = re.compile(
        r"(?:전에|예전에|지난번|아까|기존에|결정했던|정했던|왜\s*.*했지|remember|previous|earlier)",
        re.IGNORECASE,
    )
    _SESSION_RESUME_SOURCES = {"resume", "clear", "compact", "fork"}

    def _is_handoff(self, message: str) -> bool:
        lowered = message.lower()
        has_agent = any(agent in lowered for agent in self._AGENTS)
        return has_agent and bool(self._HANDOFF_ACTION.search(message))

    def decide(self, request: ContinuityRequest) -> ContinuityDecision:
        message = request.message.strip()

        if request.context.repository is None:
            return ContinuityDecision(ContinuityMode.NO_RECALL, "no repository context")

        if request.repository_known and request.agent_changed:
            previous = request.previous_agent or "previous-agent"
            current = request.current_agent or "current-agent"
            return ContinuityDecision(
                ContinuityMode.HANDOFF,
                f"persisted agent transition {previous}->{current}",
            )

        if self._is_handoff(message):
            return ContinuityDecision(ContinuityMode.HANDOFF, "cross-agent continuity wording")

        if request.repository_known and request.session_source in self._SESSION_RESUME_SOURCES:
            return ContinuityDecision(
                ContinuityMode.RESUME,
                f"SessionStart source={request.session_source}",
            )

        if request.session_reset and request.repository_known:
            return ContinuityDecision(ContinuityMode.RESUME, "known repository after session reset")

        if request.repository_known and request.clone_resume:
            return ContinuityDecision(
                ContinuityMode.RESUME,
                "known repository in compatible new clone",
            )

        if self._RESUME.search(message):
            return ContinuityDecision(ContinuityMode.RESUME, "resume wording")

        if request.repository_known and not request.session_has_context:
            return ContinuityDecision(ContinuityMode.ONBOARDING, "known repository with empty session context")

        if self._PAST_RECALL.search(message):
            return ContinuityDecision(ContinuityMode.RECALL, "explicit reference to prior context")

        return ContinuityDecision(ContinuityMode.NO_RECALL, "no continuity signal")
