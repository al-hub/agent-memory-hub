from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class L1SourceFingerprint:
    source_id: str
    size: int
    mtime_ns: int
    digest: str | None = None
    cursor: str | None = None

    def changed_from(self, previous: "L1SourceFingerprint | None") -> bool:
        if previous is None:
            return True
        if self.source_id != previous.source_id:
            return True
        if self.size != previous.size or self.mtime_ns != previous.mtime_ns:
            return True
        if self.digest is not None and previous.digest is not None:
            return self.digest != previous.digest
        return False


@dataclass(frozen=True, slots=True)
class ProcessedL1SourceState:
    fingerprint: L1SourceFingerprint
    repository_id: str | None
    complete: bool
