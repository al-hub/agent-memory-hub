from __future__ import annotations

from agent_memory_hub.domain.continuity_state import ContinuityObservation, ContinuityState
from agent_memory_hub.ports.continuity_state import (
    ContinuityStateStore,
    RepositoryKnowledgeReader,
    StoredContinuityState,
)


class ContinuityStateDetector:
    """Derive continuity state from L2 repository knowledge and prior local observation."""

    def __init__(self, knowledge_reader: RepositoryKnowledgeReader, state_store: ContinuityStateStore):
        self._knowledge_reader = knowledge_reader
        self._state_store = state_store

    def detect(self, observation: ContinuityObservation) -> ContinuityState:
        repository = observation.context.repository
        if repository is None:
            return ContinuityState(
                repository_known=False,
                session_reset=False,
                session_has_context=observation.session_has_context,
                stale_head=False,
                current_agent=observation.agent,
            )

        repository_id = repository.canonical_id
        worktree_id = observation.context.worktree_id
        repository_known = self._knowledge_reader.has_repository(repository_id)
        previous = self._state_store.load(repository_id, worktree_id)

        session_reset = bool(
            previous
            and previous.session_id
            and observation.session_id
            and previous.session_id != observation.session_id
        )
        stale_head = bool(
            previous
            and previous.head_sha
            and observation.context.head_sha
            and previous.head_sha != observation.context.head_sha
        )
        previous_agent = previous.agent if previous else None
        agent_changed = bool(
            previous_agent
            and observation.agent
            and previous_agent != observation.agent
        )

        self._state_store.save(
            repository_id,
            worktree_id,
            StoredContinuityState(
                session_id=observation.session_id,
                head_sha=observation.context.head_sha,
                agent=observation.agent or previous_agent,
            ),
        )

        return ContinuityState(
            repository_known=repository_known,
            session_reset=session_reset,
            session_has_context=observation.session_has_context,
            stale_head=stale_head,
            agent_changed=agent_changed,
            previous_agent=previous_agent,
            current_agent=observation.agent,
        )
