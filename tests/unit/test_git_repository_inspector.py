import subprocess
import tempfile
import unittest
from pathlib import Path

from memcarry.infrastructure.git.repository_inspector import GitRepositoryInspector


class GitRepositoryInspectorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        subprocess.run(["git", "init", "-b", "main", str(self.root)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Test"], check=True)
        (self.root / "README.md").write_text("demo\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-m", "init"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "remote", "add", "origin", "git@github.com:al-hub/demo.git"], check=True)
        self.inspector = GitRepositoryInspector()

    def tearDown(self):
        self.tmp.cleanup()

    def test_detects_repository_branch_head_and_remote_identity(self):
        ctx = self.inspector.inspect(str(self.root))
        self.assertIsNotNone(ctx.repository)
        self.assertEqual(ctx.repository.canonical_id, "github.com/al-hub/demo")
        self.assertEqual(ctx.branch, "main")
        self.assertEqual(len(ctx.head_sha), 40)
        self.assertTrue(ctx.worktree_id)
        self.assertTrue(ctx.checkout_id)
        self.assertFalse(ctx.is_linked_worktree)
        self.assertEqual(Path(ctx.repository.root), self.root.resolve())

    def test_linked_worktree_shares_repository_and_checkout_but_has_distinct_worktree_id(self):
        wt = Path(self.tmp.name) / "feature-wt"
        subprocess.run(
            ["git", "-C", str(self.root), "worktree", "add", "-b", "feature/test", str(wt)],
            check=True,
            capture_output=True,
        )
        main_ctx = self.inspector.inspect(str(self.root))
        wt_ctx = self.inspector.inspect(str(wt))
        self.assertEqual(main_ctx.repository.canonical_id, wt_ctx.repository.canonical_id)
        self.assertEqual(main_ctx.repository.common_dir, wt_ctx.repository.common_dir)
        self.assertEqual(main_ctx.checkout_id, wt_ctx.checkout_id)
        self.assertNotEqual(main_ctx.worktree_id, wt_ctx.worktree_id)
        self.assertFalse(main_ctx.is_linked_worktree)
        self.assertTrue(wt_ctx.is_linked_worktree)
        self.assertEqual(wt_ctx.branch, "feature/test")

    def test_non_git_directory_returns_empty_execution_context(self):
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        ctx = self.inspector.inspect(str(outside))
        self.assertIsNone(ctx.repository)
        self.assertIsNone(ctx.worktree_id)
        self.assertIsNone(ctx.branch)
        self.assertIsNone(ctx.head_sha)
        self.assertIsNone(ctx.checkout_id)
        self.assertFalse(ctx.is_linked_worktree)


if __name__ == "__main__":
    unittest.main()
