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

from agent_memory_hub.application.scope_resolver import ScopeResolver
from agent_memory_hub.application.scope_storage import scope_storage_ref
from agent_memory_hub.cli.continuity import build_continuity_command
from agent_memory_hub.domain.context import ScopeLevel
from agent_memory_hub.infrastructure.git.repository_inspector import GitRepositoryInspector


def run_git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def worktree_scope_ref(context) -> str:
    scope = next(
        value for value in ScopeResolver().resolve(context)
        if value.level == ScopeLevel.WORKTREE
    )
    return scope_storage_ref(scope)


class RealMultiWorktreeE2E(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.repo = base / "repo"
        self.repo.mkdir()
        run_git("init", "-b", "main", str(self.repo))
        run_git("config", "user.email", "worktree@example.com", cwd=self.repo)
        run_git("config", "user.name", "Worktree E2E", cwd=self.repo)
        run_git("remote", "add", "origin", "git@github.com:al-hub/worktree-e2e.git", cwd=self.repo)
        (self.repo / "README.md").write_text("worktree\n", encoding="utf-8")
        run_git("add", "README.md", cwd=self.repo)
        run_git("commit", "-m", "initial", cwd=self.repo)

        self.alpha = base / "alpha"
        self.beta = base / "beta"
        run_git("worktree", "add", "-b", "feature-alpha", str(self.alpha), cwd=self.repo)
        run_git("worktree", "add", "-b", "feature-beta", str(self.beta), cwd=self.repo)

        inspector = GitRepositoryInspector()
        self.alpha_context = inspector.inspect(str(self.alpha))
        self.beta_context = inspector.inspect(str(self.beta))
        self.assertEqual(
            self.alpha_context.repository.canonical_id,
            self.beta_context.repository.canonical_id,
        )
        self.assertNotEqual(self.alpha_context.worktree_id, self.beta_context.worktree_id)

        self.home = base / "memory"
        self.home.mkdir()
        repo_id = self.alpha_context.repository.canonical_id
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
        rows = [
            (
                "shared",
                "Continuity marker: shared repository decision stays visible in every worktree.",
                "decision", "active", "verified", 0.99,
                "repository", repo_id, 1,
            ),
            (
                "alpha-state",
                "Continuity marker: alpha worktree next task is allocator profiling.",
                "project_state", "active", "verified", 0.98,
                "worktree", worktree_scope_ref(self.alpha_context), 2,
            ),
            (
                "beta-state",
                "Continuity marker: beta worktree next task is parser cleanup.",
                "project_state", "active", "verified", 0.98,
                "worktree", worktree_scope_ref(self.beta_context), 3,
            ),
        ]
        con.executemany("INSERT INTO memories VALUES(?,?,?,?,?,?,?,?,?)", rows)
        con.commit()
        con.close()
        self.command = build_continuity_command(self.home, token_budget=1000)

    def tearDown(self):
        self.tmp.cleanup()

    def run_context(self, cwd: Path, session_id: str, *, source=None, message="continue continuity marker"):
        return json.loads(
            self.command.run(
                message=message,
                cwd=str(cwd),
                session_id=session_id,
                session_has_context=True,
                session_source=source,
                agent="codex",
                token_budget=1000,
                json_output=True,
            )
        )

    def test_real_git_worktrees_are_isolated_but_share_repository_memory(self):
        alpha = self.run_context(self.alpha, "alpha-session")
        alpha_text = "\n".join(item["statement"] for item in alpha["items"])
        self.assertIn("shared repository decision", alpha_text)
        self.assertIn("alpha worktree next task", alpha_text)
        self.assertNotIn("beta worktree next task", alpha_text)

        beta = self.run_context(self.beta, "beta-session")
        beta_text = "\n".join(item["statement"] for item in beta["items"])
        self.assertIn("shared repository decision", beta_text)
        self.assertIn("beta worktree next task", beta_text)
        self.assertNotIn("alpha worktree next task", beta_text)

        state = json.loads((self.home / "continuity-state.json").read_text(encoding="utf-8"))
        self.assertEqual(len(state), 2)

    def test_head_change_marks_only_changed_worktree_stale(self):
        self.run_context(self.alpha, "alpha-session")
        self.run_context(self.beta, "beta-session")

        (self.alpha / "CHANGE.md").write_text("alpha new head\n", encoding="utf-8")
        run_git("add", "CHANGE.md", cwd=self.alpha)
        run_git("commit", "-m", "advance alpha", cwd=self.alpha)

        alpha = self.run_context(
            self.alpha,
            "alpha-session",
            source="resume",
            message="",
        )
        self.assertTrue(alpha["state"]["stale_head"])
        alpha_state = next(item for item in alpha["items"] if item["memory_id"] == "alpha-state")
        self.assertIn("stale_head", (alpha_state["warning"] or "").lower())

        beta = self.run_context(
            self.beta,
            "beta-session",
            source="resume",
            message="",
        )
        self.assertFalse(beta["state"]["stale_head"])
        beta_state = next(item for item in beta["items"] if item["memory_id"] == "beta-state")
        self.assertIsNone(beta_state["warning"])


if __name__ == "__main__":
    unittest.main()
