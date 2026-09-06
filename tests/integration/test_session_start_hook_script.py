import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from memcarry.infrastructure.git.repository_inspector import GitRepositoryInspector


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "session_start_hook.py"


class SessionStartHookScriptTest(unittest.TestCase):
    def _repo_and_store(self, base: Path):
        repo = base / "repo"
        home = base / "memory"
        repo.mkdir()
        subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
        (repo / "README.md").write_text("demo\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True, text=True)

        context = GitRepositoryInspector().inspect(str(repo))
        repo_id = context.repository.canonical_id
        home.mkdir()
        db = home / "memory.db"
        con = sqlite3.connect(db)
        con.executescript("""
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
        CREATE VIRTUAL TABLE memory_fts USING fts5(id UNINDEXED, statement);
        """)
        rows = [
            ("d1", "Use FTS5 before semantic fallback", "decision", "active", "verified", .98, "repository", repo_id, 1),
            ("p1", "Continue wiring agent session hooks", "project_state", "active", "verified", .95, "repository", repo_id, 2),
        ]
        con.executemany("INSERT INTO memories VALUES(?,?,?,?,?,?,?,?,?)", rows)
        con.executemany("INSERT INTO memory_fts(id,statement) VALUES(?,?)", [(r[0], r[1]) for r in rows])
        con.commit()
        con.close()
        return repo, home

    def _run_hook(self, agent: str, source: str):
        with tempfile.TemporaryDirectory() as td:
            repo, home = self._repo_and_store(Path(td))
            hook_input = {
                "hook_event_name": "SessionStart",
                "session_id": f"{agent}-session",
                "cwd": str(repo),
                "source": source,
                "transcript_path": str(Path(td) / "transcript.jsonl"),
            }
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--agent", agent, "--home", str(home)],
                input=json.dumps(hook_input),
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            specific = payload["hookSpecificOutput"]
            self.assertEqual(specific["hookEventName"], "SessionStart")
            self.assertIn("additionalContext", specific)
            self.assertIn("Use FTS5 before semantic fallback", specific["additionalContext"])

            # SessionStart has no lexical query, so it must not pay for or mutate
            # the prompt-only scope-first FTS migration path.
            with sqlite3.connect(home / "memory.db") as con:
                columns = [row[1] for row in con.execute("PRAGMA table_info(memory_fts)")]
            self.assertEqual(columns, ["id", "statement"])
            return specific["additionalContext"]

    def test_codex_resume_injects_scoped_context(self):
        text = self._run_hook("codex", "resume")
        self.assertIn("continuity context (resume)", text)

    def test_claude_clear_injects_resume_context(self):
        text = self._run_hook("claude", "clear")
        self.assertIn("continuity context (resume)", text)

    def test_gemini_startup_injects_onboarding_context(self):
        text = self._run_hook("gemini", "startup")
        self.assertIn("continuity context (onboarding)", text)

    def test_invalid_payload_fails_open_with_valid_hook_json(self):
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--agent", "codex", "--home", td],
                input=json.dumps({"hook_event_name": "PostToolUse"}),
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(
                json.loads(result.stdout),
                {"hookSpecificOutput": {"hookEventName": "SessionStart"}},
            )
            self.assertIn("warning", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
