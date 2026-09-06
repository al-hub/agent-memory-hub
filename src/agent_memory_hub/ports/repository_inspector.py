from __future__ import annotations

from typing import Protocol

from agent_memory_hub.domain.context import ExecutionContext


class RepositoryInspector(Protocol):
    """Port for discovering repository/worktree execution context."""

    def inspect(self, cwd: str) -> ExecutionContext:
        ...
