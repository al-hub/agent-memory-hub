from __future__ import annotations

from memcarry.domain.continuity import ContinuityMode
from memcarry.domain.recall import MemoryCandidate


_TYPE_PRIORITY = {
    ContinuityMode.RECALL: {
        "decision": 0,
        "constraint": 1,
        "project_state": 2,
        "lesson": 3,
        "procedure": 4,
        "fact": 5,
        "preference": 6,
        "identity": 7,
        "episode": 8,
    },
    ContinuityMode.ONBOARDING: {
        "decision": 0,
        "constraint": 1,
        "procedure": 2,
        "lesson": 3,
        "project_state": 4,
        "fact": 5,
        "preference": 6,
        "identity": 7,
        "episode": 8,
    },
    ContinuityMode.RESUME: {
        "project_state": 0,
        "decision": 1,
        "constraint": 2,
        "lesson": 3,
        "procedure": 4,
        "fact": 5,
        "preference": 6,
        "identity": 7,
        "episode": 8,
    },
    ContinuityMode.HANDOFF: {
        "project_state": 0,
        "decision": 1,
        "lesson": 2,
        "constraint": 3,
        "procedure": 4,
        "fact": 5,
        "preference": 6,
        "identity": 7,
        "episode": 8,
    },
}


class ContinuityProjectionPolicy:
    """Mode-specific type priority without embedding policy into the projector core."""

    def __init__(self, mode: ContinuityMode):
        self._mode = mode

    def priority(self, memory: MemoryCandidate) -> int:
        table = _TYPE_PRIORITY.get(self._mode, _TYPE_PRIORITY[ContinuityMode.RECALL])
        return table.get(memory.memory_type, 50)
