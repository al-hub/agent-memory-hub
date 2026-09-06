from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agent_memory_hub.domain.continuity import ContinuityMode


@dataclass(frozen=True, slots=True)
class ContextItem:
    memory_id: str
    statement: str
    memory_type: str
    scope: str
    review_state: str
    confidence: float
    warning: Optional[str] = None


@dataclass(frozen=True, slots=True)
class ContextPack:
    mode: ContinuityMode
    items: tuple[ContextItem, ...]
    estimated_tokens: int
    token_budget: int
    truncated: bool
