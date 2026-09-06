import tempfile
import unittest
from pathlib import Path

from agent_memory_hub.continuity.fingerprint import canonical_repository_id, normalize_git_remote


class RepositoryFingerprintTest(unittest.TestCase):
    def test_https_and_ssh_remotes_normalize_to_same_repository(self):
        self.assertEqual(
            normalize_git_remote("https://github.com/al-hub/agent-memory-hub.git"),
            normalize_git_remote("git@github.com:al-hub/agent-memory-hub.git"),
        )
        self.assertEqual(
            normalize_git_remote("https://github.com/al-hub/agent-memory-hub.git"),
            "github.com/al-hub/agent-memory-hub",
        )

    def test_ssh_url_normalizes(self):
        self.assertEqual(
            normalize_git_remote("ssh://git@github.com/al-hub/agent-memory-hub.git"),
            "github.com/al-hub/agent-memory-hub",
        )

    def test_same_remote_is_stable_across_worktrees(self):
        a = canonical_repository_id(remote="git@github.com:al-hub/agent-memory-hub.git", common_dir="/tmp/repo/.git")
        b = canonical_repository_id(remote="https://github.com/al-hub/agent-memory-hub", common_dir="/tmp/other-worktree/.git")
        self.assertEqual(a, b)

    def test_local_repository_without_remote_uses_stable_common_dir_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            common = Path(tmp) / ".git"
            common.mkdir()
            first = canonical_repository_id(remote=None, common_dir=str(common))
            second = canonical_repository_id(remote=None, common_dir=str(common))
            self.assertEqual(first, second)
            self.assertTrue(first.startswith("local:"))

    def test_empty_remote_is_rejected_by_normalizer(self):
        with self.assertRaises(ValueError):
            normalize_git_remote("")


if __name__ == "__main__":
    unittest.main()
