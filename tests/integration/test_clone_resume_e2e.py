import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_memory_hub.cli.continuity import build_continuity_command
from agent_memory_hub.infrastructure.git.repository_inspector import GitRepositoryInspector


def run_git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


class CloneResumeE2E(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)

        self.clone_a = base / "clone-a"
        self.clone_a.mkdir()
        run_git("init", "-b", "main", str(self.clone_a))
        run_git("config", "user.email", "clone@example.com", cwd=self.clone_a)
        run_git("config", "user.name", "Clone E2E", cwd=self.clone_a)
        (self.clone_a / "README.md").write_text("clone resume\n", encoding="utf-8")
        run_git("add", "README.md", cwd=self.clone_a)
        run_git("commit", "-m", "initial", cwd=self.clone_a)

        self.clone_b = base / "clone-b"
        run_git("clone", str(self.clone_a), str(self.clone_b))
        remote = "git@github.com:al-hub/clone-resume-e2e.git"
        run_git("remote", "add", "origin", remote, cwd=self.clone_a)
        run_git("remote", "set-url", "origin", remote, cwd=self.clone_b)

        inspector = GitRepositoryInspector()
        self.context_a = inspector.inspect(str(self.clone_a))
        self.context_b = inspector.inspect(str(self.clone_b))
        self.assertEqual(
            self.context_a.repository.canonical_id,
            self.context_b.repository.canonical_id,
        )
        self.assertEqual(self.context_a.head_sha, self.context_b.head_sha)
        self.assertNotEqual(self.context_a.checkout_id, self.context_b.checkout_id)
        self.assertFalse(self.context_a.is_linked_worktree)
        self.assertFalse(self.context_b.is_linked_worktree)

        self.home = base / "memory"
        self.home.mkdir()
        repo_id = self.context_a.repository.canonical_id
        con = sqlite3.connect(self.home / "memory.db")
        con.executescript(
            """
            CREATE TABLE memories(
              id TEXT PRIMARY KEY,
              statement TEXT NOT NULL,
              type TEXT NOT NULL,
              lifecycle TEXT NOT NULL,
              review_state TEXT NOT NULL,
              confidence REAL NOT NULL,
              scope TEXT NOT NULL,
              scope_ref TEXT,
              updated_at INTEGER NOT NULL
            );
            """
        )
        con.execute(
            "INSERT INTO memories VALUES(?,?,?,?,?,?,?,?,?)",
            (
                "shared",
                "Clone resume marker: repository decision survives a fresh clone.",
                "decision",
                "active",
                "verified",
                0.99,
                "repository",
                repo_id,
                1,
            ),
        )
        con.commit()
        con.close()
        self.command = build_continuity_command(self.home, token_budget=1000)

    def tearDown(self):
        self.tmp.cleanup()

    def run_context(
        self,
        cwd: Path,
        session_id: str,
        *,
        source: str | None,
        message: str,
        session_has_context: bool,
    ):
        return json.loads(
            self.command.run(
                message=message,
                cwd=str(cwd),
                session_id=session_id,
                session_has_context=session_has_context,
                session_source=source,
                agent="codex",
                token_budget=1000,
                json_output=True,
            )
        )

    def test_fresh_clone_with_same_repository_and_head_resumes(self):
        first = self.run_context(
            self.clone_a,
            "session-a",
            source="startup",
            message="continue clone resume marker",
            session_has_context=True,
        )
        self.assertEqual(first["mode"], "resume")
        self.assertFalse(first["state"]["clone_resume"])

        second = self.run_context(
            self.clone_b,
            "session-b",
            source="startup",
            message="",
            session_has_context=False,
        )
        self.assertEqual(second["mode"], "resume")
        self.assertTrue(second["state"]["clone_resume"])
        self.assertIn("compatible new clone", second["reason"])

        text = "\n".join(item["statement"] for item in second["items"])
        self.assertIn("repository decision survives a fresh clone", text)

    def test_linked_worktree_does_not_use_clone_resume_fallback(self):
        self.run_context(
            self.clone_a,
            "session-a",
            source="startup",
            message="continue clone resume marker",
            session_has_context=True,
        )

        linked = Path(self.tmp.name) / "linked"
        run_git(
            "worktree",
            "add",
            "-b",
            "feature/linked",
            str(linked),
            cwd=self.clone_a,
        )

        result = self.run_context(
            linked,
            "session-linked",
            source="startup",
            message="",
            session_has_context=False,
        )
        self.assertEqual(result["mode"], "onboarding")
        self.assertFalse(result["state"]["clone_resume"])


if __name__ == "__main__":
    unittest.main()
