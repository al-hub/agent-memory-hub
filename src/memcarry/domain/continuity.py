from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from memcarry.domain.context import ExecutionContext


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
    stale_head: bool = False
    session_source: str | None = None
    agent_changed: bool = False
    previous_agent: str | None = None
    current_agent: str | None = None
    clone_resume: bool = False


@dataclass(frozen=True, slots=True)
class ContinuityDecision:
    mode: ContinuityMode
    reason: str
