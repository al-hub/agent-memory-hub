import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "memory_hub.py"


class ScopeAwareRecallIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.home = self.base / "hub"
        self.repo = self.base / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-b", "main", str(self.repo)], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Test"], check=True)
        (self.repo / "README.md").write_text("demo\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-m", "init"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(self.repo), "remote", "add", "origin", "git@github.com:al-hub/demo.git"], check=True)
        self.run_cli("init")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        result = subprocess.run(
            [sys.executable, str(CLI), "--home", str(self.home), *args],
            text=True,
            capture_output=True,
            env=env,
        )
        if result.returncode != 0:
            self.fail(f"CLI failed: {result.args}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        return result

    def test_context_recall_includes_global_and_current_repository_but_excludes_foreign_repository(self):
        self.run_cli("add", "Shared generic SQLite lesson", "--type", "lesson", "--status", "confirmed")
        self.run_cli(
            "add", "Demo repository uses FTS5 fast path",
            "--type", "decision", "--status", "confirmed",
            "--scope", "repository", "--context-cwd", str(self.repo),
        )
        self.run_cli(
            "add", "Foreign repository uses another search engine",
            "--type", "decision", "--status", "confirmed",
            "--scope", "repository", "--scope-ref", "github.com/al-hub/foreign",
        )

        data = json.loads(self.run_cli("recall", "repository search SQLite FTS5", "--json", "--context-cwd", str(self.repo)).stdout)
        statements = {m["statement"] for m in data["memories"]}
        self.assertIn("Shared generic SQLite lesson", statements)
        self.assertIn("Demo repository uses FTS5 fast path", statements)
        self.assertNotIn("Foreign repository uses another search engine", statements)

    def test_branch_scope_is_derived_from_current_repository_context(self):
        self.run_cli(
            "add", "Main branch keeps compatibility shim",
            "--type", "constraint", "--status", "confirmed",
            "--scope", "branch", "--context-cwd", str(self.repo),
        )
        data = json.loads(self.run_cli("recall", "compatibility shim", "--json", "--context-cwd", str(self.repo)).stdout)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["memories"][0]["scope"], "branch")
        self.assertIn("::branch::main", data["memories"][0]["scope_ref"])


if __name__ == "__main__":
    unittest.main()
