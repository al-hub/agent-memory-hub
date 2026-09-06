from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredContinuityState:
    session_id: str | None = None
    head_sha: str | None = None
    agent: str | None = None


class RepositoryKnowledgeReader(Protocol):
    def has_repository(self, repository_id: str) -> bool:
        ...


class ContinuityStateStore(Protocol):
    def load(self, repository_id: str, worktree_id: str | None) -> StoredContinuityState | None:
        ...

    def save(self, repository_id: str, worktree_id: str | None, state: StoredContinuityState) -> None:
        ...
