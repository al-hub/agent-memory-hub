from __future__ import annotations

import hashlib
from dataclasses import dataclass

from memcarry.domain.l1_governance import EvidenceStrength, evidence_strength_for
from memcarry.domain.l1_ingestion import L1Record


@dataclass(frozen=True, slots=True)
class L1Evidence:
    source_agent: str
    source_type: str
    source_id: str
    source_pointer: str | None
    evidence_group: str
    observed_at: str
    repository_id: str | None
    branch: str | None
    head_sha: str | None
    strength: EvidenceStrength

    @classmethod
    def from_record(cls, record: L1Record) -> "L1Evidence":
        origin = f"{record.source_agent}\0{record.source_id}".encode("utf-8")
        evidence_group = "l1:" + hashlib.sha256(origin).hexdigest()
        return cls(
            source_agent=record.source_agent,
            source_type=record.kind,
            source_id=record.source_id,
            source_pointer=record.source_path,
            evidence_group=evidence_group,
            observed_at=record.observed_at,
            repository_id=record.repository_id,
            branch=record.branch,
            head_sha=record.head_sha,
            strength=evidence_strength_for(record.kind),
        )
