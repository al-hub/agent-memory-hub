from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EvidenceStrength(str, Enum):
    WEAK = "weak"
    MEDIUM = "medium"
    STRONG = "strong"


class ReconciliationAction(str, Enum):
    ATTACH_EVIDENCE = "attach_evidence"
    SUPERSEDE = "supersede"
    RECORD_CONFLICT = "record_conflict"
    RECORD_CONTRADICTION = "record_contradiction"
    KEEP_SEPARATE = "keep_separate"
    MARK_STALE = "mark_stale"


_STRONG_SOURCE_TYPES = {
    "git_commit",
    "test_result",
    "user_explicit",
    "direct_file",
}
_MEDIUM_SOURCE_TYPES = {
    "agent_summary",
    "tool_output",
    "session_summary",
}


def evidence_strength_for(source_type: str) -> EvidenceStrength:
    normalized = source_type.strip().lower()
    if normalized in _STRONG_SOURCE_TYPES:
        return EvidenceStrength.STRONG
    if normalized in _MEDIUM_SOURCE_TYPES:
        return EvidenceStrength.MEDIUM
    return EvidenceStrength.WEAK


@dataclass(frozen=True, slots=True)
class GovernedClaim:
    semantic_key: str
    value_hash: str
    memory_type: str
    repository_id: str | None
    observed_at: str
    head_sha: str | None
    review_state: str
    evidence_strength: EvidenceStrength


@dataclass(frozen=True, slots=True)
class IncomingClaim:
    semantic_key: str
    value_hash: str
    memory_type: str
    repository_id: str | None
    observed_at: str
    head_sha: str | None
    evidence_strength: EvidenceStrength


@dataclass(frozen=True, slots=True)
class ReconciliationOutcome:
    action: ReconciliationAction
    existing_review_state: str
    incoming_review_state: str


class ReconciliationPolicy:
    """Pure deterministic policy for comparing governed L2 with incoming L1 claims."""

    _TEMPORAL_TYPES = {"project_state", "episode"}

    def reconcile(
        self,
        existing: GovernedClaim,
        incoming: IncomingClaim,
        *,
        current_head: str | None,
    ) -> ReconciliationOutcome:
        if existing.repository_id != incoming.repository_id:
            return ReconciliationOutcome(
                ReconciliationAction.KEEP_SEPARATE,
                existing.review_state,
                "unverified",
            )

        if current_head and incoming.head_sha and incoming.head_sha != current_head:
            return ReconciliationOutcome(
                ReconciliationAction.MARK_STALE,
                existing.review_state,
                "needs_review",
            )

        if existing.semantic_key != incoming.semantic_key:
            return ReconciliationOutcome(
                ReconciliationAction.KEEP_SEPARATE,
                existing.review_state,
                "unverified",
            )

        if existing.value_hash == incoming.value_hash:
            return ReconciliationOutcome(
                ReconciliationAction.ATTACH_EVIDENCE,
                existing.review_state,
                "unverified",
            )

        if (
            existing.review_state == "verified"
            and existing.evidence_strength == EvidenceStrength.STRONG
            and incoming.evidence_strength == EvidenceStrength.WEAK
        ):
            return ReconciliationOutcome(
                ReconciliationAction.RECORD_CONTRADICTION,
                "verified",
                "needs_review",
            )

        if existing.memory_type in self._TEMPORAL_TYPES and incoming.memory_type == existing.memory_type:
            if incoming.observed_at > existing.observed_at:
                return ReconciliationOutcome(
                    ReconciliationAction.SUPERSEDE,
                    existing.review_state,
                    "unverified",
                )

        return ReconciliationOutcome(
            ReconciliationAction.RECORD_CONFLICT,
            "conflict",
            "conflict",
        )
