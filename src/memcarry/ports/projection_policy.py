from __future__ import annotations

from typing import Protocol

from memcarry.domain.recall import MemoryCandidate


class ProjectionPolicy(Protocol):
    def priority(self, memory: MemoryCandidate) -> int:
        ...
