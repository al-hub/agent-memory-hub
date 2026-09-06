import unittest

from memcarry.domain.context import ResolvedScope, ScopeLevel
from memcarry.application.scope_storage import scope_storage_ref


class ScopeStorageTest(unittest.TestCase):
    def test_repository_scope_uses_canonical_repository_id(self):
        scope = ResolvedScope(ScopeLevel.REPOSITORY, "github.com/al-hub/demo", "github.com/al-hub/demo")
        self.assertEqual(scope_storage_ref(scope), "github.com/al-hub/demo")

    def test_branch_scope_is_repository_qualified(self):
        a = ResolvedScope(ScopeLevel.BRANCH, "main", "github.com/al-hub/a")
        b = ResolvedScope(ScopeLevel.BRANCH, "main", "github.com/al-hub/b")
        self.assertNotEqual(scope_storage_ref(a), scope_storage_ref(b))
        self.assertEqual(scope_storage_ref(a), "github.com/al-hub/a::branch::main")

    def test_worktree_and_task_are_repository_qualified(self):
        wt = ResolvedScope(ScopeLevel.WORKTREE, "wt:123", "github.com/al-hub/a")
        task = ResolvedScope(ScopeLevel.TASK, "benchmark", "github.com/al-hub/a")
        self.assertEqual(scope_storage_ref(wt), "github.com/al-hub/a::worktree::wt:123")
        self.assertEqual(scope_storage_ref(task), "github.com/al-hub/a::task::benchmark")

    def test_global_scope_has_no_ref(self):
        self.assertIsNone(scope_storage_ref(ResolvedScope(ScopeLevel.GLOBAL)))


if __name__ == "__main__":
    unittest.main()
