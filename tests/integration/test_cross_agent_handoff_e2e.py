import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "scripts" / "session_start_hook.py"
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from memcarry.infrastructure.git.repository_inspector import GitRepositoryInspector


def run_git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


class CrossAgentHandoffE2E(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.repo = base / "repo"
        self.repo.mkdir()
        run_git("init", "-b", "main", str(self.repo))
        run_git("config", "user.email", "handoff@example.com", cwd=self.repo)
        run_git("config", "user.name", "Handoff E2E", cwd=self.repo)
        run_git("remote", "add", "origin", "git@github.com:al-hub/handoff-e2e.git", cwd=self.repo)
        (self.repo / "README.md").write_text("handoff\n", encoding="utf-8")
        run_git("add", "README.md", cwd=self.repo)
        run_git("commit", "-m", "initial", cwd=self.repo)

        self.home = base / "memory"
        self.home.mkdir()
        context = GitRepositoryInspector().inspect(str(self.repo))
        self.repo_id = context.repository.canonical_id
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
                "handoff-decision",
                "Codex verified the scope-first continuity path and the next agent should preserve it.",
                "decision",
                "active",
                "verified",
                0.99,
                "repository",
                self.repo_id,
                1,
            ),
        )
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def hook(self, agent: str, session_id: str) -> str:
        payload = {
            "hook_event_name": "SessionStart",
            "session_id": session_id,
            "cwd": str(self.repo),
            "source": "startup",
        }
        env = os.environ.copy()
        env["MEMCARRY_HOME"] = str(self.home)
        result = subprocess.run(
            [sys.executable, str(HOOK), "--agent", agent],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        rendered = json.loads(result.stdout)
        return (rendered.get("hookSpecificOutput") or {}).get("additionalContext", "")

    def saved_agent(self) -> str | None:
        state = json.loads((self.home / "continuity-state.json").read_text(encoding="utf-8"))
        record = next(iter(state.values()))
        return record.get("agent")

    def test_codex_to_claude_to_gemini_is_detected_as_persisted_handoff(self):
        codex = self.hook("codex", "codex-session")
        self.assertIn("onboarding", codex.lower())
        self.assertEqual(self.saved_agent(), "codex")

        claude = self.hook("claude", "claude-session")
        self.assertIn("handoff", claude.lower())
        self.assertIn("scope-first continuity path", claude)
        self.assertEqual(self.saved_agent(), "claude")

        gemini = self.hook("gemini", "gemini-session")
        self.assertIn("handoff", gemini.lower())
        self.assertIn("scope-first continuity path", gemini)
        self.assertEqual(self.saved_agent(), "gemini")


if __name__ == "__main__":
    unittest.main()
