from __future__ import annotations

from dataclasses import dataclass

from agent_memory_hub.domain.context import ExecutionContext
from agent_memory_hub.domain.continuity import ContinuityRequest


@dataclass(frozen=True, slots=True)
class ContinuityObservation:
    message: str
    context: ExecutionContext
    session_id: str | None = None
    session_has_context: bool = True
    session_source: str | None = None
    agent: str | None = None


@dataclass(frozen=True, slots=True)
class ContinuityState:
    repository_known: bool
    session_reset: bool
    session_has_context: bool
    stale_head: bool
    agent_changed: bool = False
    previous_agent: str | None = None
    current_agent: str | None = None

    def to_request(self, observation: ContinuityObservation) -> ContinuityRequest:
        return ContinuityRequest(
            message=observation.message,
            context=observation.context,
            repository_known=self.repository_known,
            session_has_context=self.session_has_context,
            session_reset=self.session_reset,
            stale_head=self.stale_head,
            session_source=observation.session_source,
            agent_changed=self.agent_changed,
            previous_agent=self.previous_agent,
            current_agent=self.current_agent,
        )
