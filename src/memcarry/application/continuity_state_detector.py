from __future__ import annotations

from memcarry.domain.continuity_state import ContinuityObservation, ContinuityState
from memcarry.ports.continuity_state import (
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

        compatible_previous = None
        clone_resume = False
        if (
            repository_known
            and previous is None
            and observation.context.checkout_id
            and observation.context.head_sha
            and not observation.context.is_linked_worktree
        ):
            load_compatible = getattr(self._state_store, "load_compatible_checkout", None)
            if load_compatible is not None:
                compatible_previous = load_compatible(
                    repository_id,
                    observation.context.checkout_id,
                    observation.context.head_sha,
                    observation.context.branch,
                )
                clone_resume = compatible_previous is not None

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
        continuity_previous = previous or compatible_previous
        previous_agent = continuity_previous.agent if continuity_previous else None
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
                branch=observation.context.branch,
                checkout_id=observation.context.checkout_id,
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
            clone_resume=clone_resume,
        )
