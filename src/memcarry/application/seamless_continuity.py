from __future__ import annotations

from dataclasses import dataclass

from memcarry.application.continuity_context import ContinuityContextResult
from memcarry.domain.continuity_state import ContinuityObservation, ContinuityState


@dataclass(frozen=True, slots=True)
class SeamlessContinuityResult:
    state: ContinuityState
    context: ContinuityContextResult


class SeamlessContinuityService:
    """Detect local continuity state, then build context only when the gate requires it."""

    def __init__(self, state_detector, context_service):
        self._state_detector = state_detector
        self._context_service = context_service

    def handle(self, observation: ContinuityObservation) -> SeamlessContinuityResult:
        state = self._state_detector.detect(observation)
        result = self._context_service.handle(state.to_request(observation))
        return SeamlessContinuityResult(state=state, context=result)
