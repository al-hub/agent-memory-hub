from __future__ import annotations

import math
import re

from memcarry.continuity.projection_policies import ContinuityProjectionPolicy
from memcarry.domain.continuity import ContinuityMode
from memcarry.domain.projection import ContextItem, ContextPack
from memcarry.domain.recall import MemoryCandidate
from memcarry.ports.projection_policy import ProjectionPolicy


class ContextProjector:
    """Pure bounded projection from governed memory candidates to an agent context pack."""

    _BLOCKED_LIFECYCLES = {"superseded", "quarantined"}
    _HEAD_SENSITIVE_TYPES = {"project_state"}
    _REVIEW_PRIORITY = {
        "verified": 0,
        "unverified": 1,
        "needs_review": 2,
        "conflict": 3,
    }

    def _normalize(self, statement: str) -> str:
        return re.sub(r"\s+", " ", statement.strip().lower())

    def _estimate_tokens(self, text: str) -> int:
        # Deterministic dependency-free approximation. Replace behind a port if exact
        # tokenizer accounting becomes necessary for a target agent.
        return max(1, math.ceil(len(text) / 4))

    def _warning(self, memory: MemoryCandidate, *, stale_head: bool = False) -> str | None:
        warnings: list[str] = []
        if stale_head and memory.memory_type in self._HEAD_SENSITIVE_TYPES:
            warnings.append("STALE_HEAD: repository HEAD changed; revalidate this state against current code.")
        if memory.review_state == "conflict":
            warnings.append("CONFLICT: unresolved memory; do not treat as verified truth.")
        elif memory.review_state == "needs_review":
            warnings.append("NEEDS_REVIEW: context is not yet verified.")
        elif memory.review_state == "unverified":
            warnings.append("UNVERIFIED: use cautiously and verify when material.")
        return " ".join(warnings) if warnings else None

    def _item_cost(self, item: ContextItem) -> int:
        warning = f" {item.warning}" if item.warning else ""
        rendered = f"[{item.memory_type}/{item.scope}/{item.review_state}] {item.statement}{warning}"
        return self._estimate_tokens(rendered)

    def _stale_penalty(self, memory: MemoryCandidate, *, stale_head: bool) -> int:
        if stale_head and memory.memory_type in self._HEAD_SENSITIVE_TYPES:
            return 100
        return 0

    def project(
        self,
        candidates: list[MemoryCandidate] | tuple[MemoryCandidate, ...],
        *,
        mode: ContinuityMode,
        token_budget: int = 1000,
        policy: ProjectionPolicy | None = None,
        stale_head: bool = False,
    ) -> ContextPack:
        budget = max(1, token_budget)
        policy = policy or ContinuityProjectionPolicy(mode)

        eligible = [m for m in candidates if m.lifecycle not in self._BLOCKED_LIFECYCLES]
        eligible.sort(
            key=lambda m: (
                policy.priority(m) + self._stale_penalty(m, stale_head=stale_head),
                self._REVIEW_PRIORITY.get(m.review_state, 9),
                m.scope_rank,
                -m.confidence,
                m.lexical_rank,
                m.id,
            )
        )

        deduped: list[MemoryCandidate] = []
        seen: set[str] = set()
        for memory in eligible:
            key = self._normalize(memory.statement)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(memory)

        items: list[ContextItem] = []
        used = 0
        truncated = False
        for memory in deduped:
            item = ContextItem(
                memory_id=memory.id,
                statement=memory.statement.strip(),
                memory_type=memory.memory_type,
                scope=memory.scope,
                review_state=memory.review_state,
                confidence=memory.confidence,
                warning=self._warning(memory, stale_head=stale_head),
            )
            cost = self._item_cost(item)
            if used + cost > budget:
                truncated = True
                continue
            items.append(item)
            used += cost

        if len(items) < len(deduped):
            truncated = True

        return ContextPack(
            mode=mode,
            items=tuple(items),
            estimated_tokens=used,
            token_budget=budget,
            truncated=truncated,
        )
