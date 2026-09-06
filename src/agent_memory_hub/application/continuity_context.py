from __future__ import annotations

from dataclasses import dataclass

from agent_memory_hub.domain.continuity import ContinuityDecision, ContinuityMode, ContinuityRequest
from agent_memory_hub.domain.projection import ContextPack
from agent_memory_hub.domain.recall import RecallQuery
from agent_memory_hub.ports.memory_reader import MemoryReader


@dataclass(frozen=True, slots=True)
class ContinuityContextResult:
    decision: ContinuityDecision
    pack: ContextPack | None


class ContinuityContextService:
    """Compose continuity gating, scoped recall, and bounded projection."""

    def __init__(self, gate, memory_reader: MemoryReader, projector, *, token_budget: int = 1000):
        self._gate = gate
        self._memory_reader = memory_reader
        self._projector = projector
        self._token_budget = max(1, token_budget)

    def handle(self, request: ContinuityRequest) -> ContinuityContextResult:
        decision = self._gate.decide(request)
        if decision.mode == ContinuityMode.NO_RECALL:
            return ContinuityContextResult(decision, None)

        limit = 12 if decision.mode == ContinuityMode.ONBOARDING else 8
        query = RecallQuery(
            text=request.message,
            context=request.context,
            limit=limit,
        )
        memories = self._memory_reader.recall(query)
        pack = self._projector.project(
            memories,
            mode=decision.mode,
            token_budget=self._token_budget,
            stale_head=request.stale_head,
        )
        return ContinuityContextResult(decision, pack)
