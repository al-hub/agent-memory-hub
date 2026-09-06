from __future__ import annotations

from memcarry.domain.context import ExecutionContext, ResolvedScope, ScopeLevel


class ScopeResolver:
    """Resolve current visibility from most specific scope to global."""

    def resolve(self, context: ExecutionContext) -> list[ResolvedScope]:
        scopes: list[ResolvedScope] = []
        repo_id = context.repository.canonical_id if context.repository else None

        if context.task:
            scopes.append(ResolvedScope(ScopeLevel.TASK, context.task, repo_id))
        if context.worktree_id:
            scopes.append(ResolvedScope(ScopeLevel.WORKTREE, context.worktree_id, repo_id))
        if context.branch:
            scopes.append(ResolvedScope(ScopeLevel.BRANCH, context.branch, repo_id))
        if repo_id:
            scopes.append(ResolvedScope(ScopeLevel.REPOSITORY, repo_id, repo_id))
        scopes.append(ResolvedScope(ScopeLevel.GLOBAL))
        return scopes

    def matches(self, scope: ResolvedScope, context: ExecutionContext) -> bool:
        if scope.level == ScopeLevel.GLOBAL:
            return True

        repo_id = context.repository.canonical_id if context.repository else None
        if scope.repository_id and scope.repository_id != repo_id:
            return False

        if scope.level == ScopeLevel.REPOSITORY:
            return scope.ref == repo_id
        if scope.level == ScopeLevel.WORKTREE:
            return scope.ref == context.worktree_id
        if scope.level == ScopeLevel.BRANCH:
            return scope.ref == context.branch
        if scope.level == ScopeLevel.TASK:
            return scope.ref == context.task
        return False
