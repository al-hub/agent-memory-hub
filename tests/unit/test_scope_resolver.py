import unittest

from agent_memory_hub.application.scope_resolver import ScopeResolver
from agent_memory_hub.domain.context import ExecutionContext, RepositoryIdentity, ScopeLevel


class ScopeResolverTest(unittest.TestCase):
    def setUp(self):
        self.repo = RepositoryIdentity(
            canonical_id="github.com/al-hub/demo",
            root="/tmp/demo",
            common_dir="/tmp/demo/.git",
            remote="git@github.com:al-hub/demo.git",
        )
        self.ctx = ExecutionContext(
            repository=self.repo,
            worktree_id="wt:abc",
            branch="feature/test",
            head_sha="a" * 40,
            task="scope-retrieval",
        )
        self.resolver = ScopeResolver()

    def test_specificity_order_prefers_task_then_worktree_then_branch_then_repository(self):
        scopes = self.resolver.resolve(self.ctx)
        self.assertEqual(
            [s.level for s in scopes],
            [
                ScopeLevel.TASK,
                ScopeLevel.WORKTREE,
                ScopeLevel.BRANCH,
                ScopeLevel.REPOSITORY,
                ScopeLevel.GLOBAL,
            ],
        )

    def test_repository_scope_is_visible_in_any_worktree_of_same_repo(self):
        scope = self.resolver.resolve(self.ctx)[3]
        other = ExecutionContext(
            repository=self.repo,
            worktree_id="wt:other",
            branch="main",
            head_sha="b" * 40,
        )
        self.assertTrue(self.resolver.matches(scope, other))

    def test_worktree_scope_does_not_leak_to_other_worktree(self):
        scope = self.resolver.resolve(self.ctx)[1]
        other = ExecutionContext(
            repository=self.repo,
            worktree_id="wt:other",
            branch="feature/test",
            head_sha="b" * 40,
        )
        self.assertFalse(self.resolver.matches(scope, other))

    def test_same_branch_in_different_repository_does_not_match(self):
        scope = self.resolver.resolve(self.ctx)[2]
        other_repo = RepositoryIdentity(
            canonical_id="github.com/al-hub/other",
            root="/tmp/other",
            common_dir="/tmp/other/.git",
        )
        other = ExecutionContext(
            repository=other_repo,
            worktree_id="wt:other",
            branch="feature/test",
        )
        self.assertFalse(self.resolver.matches(scope, other))


if __name__ == "__main__":
    unittest.main()
