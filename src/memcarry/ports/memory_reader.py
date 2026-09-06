from __future__ import annotations

from typing import Protocol

from memcarry.domain.recall import MemoryCandidate, RecallQuery


class MemoryReader(Protocol):
    def recall(self, query: RecallQuery) -> list[MemoryCandidate]:
        ...
