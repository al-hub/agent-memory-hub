from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class IngestionMode(str, Enum):
    NONE = "none"
    BOOTSTRAP = "bootstrap"
    ONBOARD = "onboard"
    RECONCILE = "reconcile"
    RESUME_INGEST = "resume_ingest"


@dataclass(frozen=True, slots=True)
class IngestionObservation:
    repository_id: str | None
    store_empty: bool
    repository_known: bool
    source_changed: bool
    interrupted: bool = False


@dataclass(frozen=True, slots=True)
class L1Record:
    source_agent: str
    source_id: str
    observed_at: str
    content: str
    kind: str
    repository_id: str | None = None
    branch: str | None = None
    head_sha: str | None = None
    source_path: str | None = None

    @property
    def provenance_key(self) -> str:
        return f"{self.source_agent}:{self.source_id}"
