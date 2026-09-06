import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "continuity_context.py"


class ContinuityContextScriptTest(unittest.TestCase):
    def test_uninitialized_store_in_git_repo_returns_machine_readable_empty_pack(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = base / "repo"
            home = base / "memory"
            repo.mkdir()
            subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True, text=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True, text=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "이어서 구현해줘",
                    "--home",
                    str(home),
                    "--cwd",
                    str(repo),
                    "--session-id",
                    "s1",
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["mode"], "resume")
            self.assertFalse(payload["state"]["repository_known"])
            self.assertEqual(payload["items"], [])
            self.assertTrue((home / "continuity-state.json").exists())

    def test_non_git_directory_is_zero_context_instead_of_error(self):
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "rename this variable",
                    "--home",
                    str(Path(td) / "memory"),
                    "--cwd",
                    td,
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["mode"], "no_recall")
            self.assertEqual(payload["items"], [])


if __name__ == "__main__":
    unittest.main()
