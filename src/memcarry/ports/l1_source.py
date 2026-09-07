from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from memcarry.domain.l1_ingestion import L1Record
from memcarry.domain.l1_source import L1SourceFingerprint


class L1SourceAdapter(Protocol):
    @property
    def source_id(self) -> str:
        ...

    def fingerprint(self) -> L1SourceFingerprint:
        ...

    def iter_records(
        self,
        *,
        repository_id: str | None = None,
        after_cursor: str | None = None,
    ) -> Iterable[L1Record]:
        ...
