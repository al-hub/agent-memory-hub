from __future__ import annotations

from typing import Protocol

from memcarry.domain.l1_source import ProcessedL1SourceState


class L1SourceStateStore(Protocol):
    def load(self, source_id: str) -> ProcessedL1SourceState | None:
        ...

    def save(self, state: ProcessedL1SourceState) -> None:
        ...
