from __future__ import annotations

from agent_memory_hub.domain.context import ResolvedScope, ScopeLevel


def scope_storage_ref(scope: ResolvedScope) -> str | None:
    """Encode a resolved scope into the single v2-compatible scope_ref column.

    Repository-local scopes must include repository identity so equal branch/task
    names in unrelated repositories never collide.
    """
    if scope.level == ScopeLevel.GLOBAL:
        return None
    if scope.level == ScopeLevel.REPOSITORY:
        return scope.repository_id or scope.ref
    if scope.level in {ScopeLevel.WORKTREE, ScopeLevel.BRANCH, ScopeLevel.TASK}:
        if not scope.repository_id or not scope.ref:
            raise ValueError(f"{scope.level.value} scope requires repository_id and ref")
        return f"{scope.repository_id}::{scope.level.value}::{scope.ref}"
    return scope.ref
