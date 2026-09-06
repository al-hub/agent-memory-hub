from __future__ import annotations

from dataclasses import dataclass

from memcarry.domain.continuity import (
    ContinuityDecision,
    ContinuityMode,
    ContinuityRequest,
)
from memcarry.domain.recall import MemoryCandidate, RecallQuery
from memcarry.ports.memory_reader import MemoryReader


@dataclass(frozen=True, slots=True)
class ContinuityRecallResult:
    decision: ContinuityDecision
    memories: tuple[MemoryCandidate, ...]


class ContinuityRecallService:
    """Application service that keeps NO_RECALL on a zero-read fast path."""

    def __init__(self, gate, memory_reader: MemoryReader):
        self._gate = gate
        self._memory_reader = memory_reader

    def handle(self, request: ContinuityRequest) -> ContinuityRecallResult:
        decision = self._gate.decide(request)
        if decision.mode == ContinuityMode.NO_RECALL:
            return ContinuityRecallResult(decision, ())

        limit = 12 if decision.mode == ContinuityMode.ONBOARDING else 8
        query = RecallQuery(
            text=request.message,
            context=request.context,
            limit=limit,
        )
        memories = tuple(self._memory_reader.recall(query))
        return ContinuityRecallResult(decision, memories)
