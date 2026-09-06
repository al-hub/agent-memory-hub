from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agent_memory_hub.domain.context import ExecutionContext


@dataclass(frozen=True, slots=True)
class RecallQuery:
    text: str
    context: ExecutionContext
    memory_type: Optional[str] = None
    limit: int = 8


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    id: str
    statement: str
    memory_type: str
    lifecycle: str
    review_state: str
    confidence: float
    scope: str
    scope_ref: Optional[str]
    lexical_rank: float
    scope_rank: int
