from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agent_memory_hub.domain.context import ExecutionContext


class ContinuityMode(str, Enum):
    NO_RECALL = "no_recall"
    RECALL = "recall"
    ONBOARDING = "onboarding"
    RESUME = "resume"
    HANDOFF = "handoff"


@dataclass(frozen=True, slots=True)
class ContinuityRequest:
    message: str
    context: ExecutionContext
    repository_known: bool = False
    session_has_context: bool = True
    session_reset: bool = False


@dataclass(frozen=True, slots=True)
class ContinuityDecision:
    mode: ContinuityMode
    reason: str
