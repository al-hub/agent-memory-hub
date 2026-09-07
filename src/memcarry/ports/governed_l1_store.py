from __future__ import annotations

from typing import Protocol

from memcarry.domain.l1_governance import ReconciliationAction
from memcarry.domain.l1_ingestion import L1Record


class GovernedL1Store(Protocol):
    def is_empty(self) -> bool:
        ...

    def has_repository(self, repository_id: str) -> bool:
        ...

    def ingest_record(self, record: L1Record, *, current_head: str | None) -> ReconciliationAction | None:
        ...
