import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "memory_hub.py"


class MemoryHubSmokeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "hub"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, check=True):
        cmd = [sys.executable, str(CLI), "--home", str(self.home), *args]
        return subprocess.run(cmd, text=True, capture_output=True, check=check)

    def test_init_add_recall_duplicate_and_doctor(self):
        self.assertIn("Initialized", self.run_cli("init").stdout)
        first = self.run_cli(
            "add", "Rust implementation uses a separate repository",
            "--type", "decision", "--status", "confirmed", "--confidence", "0.96",
            "--source-agent", "codex", "--source-pointer", "conversation:2026-09-02",
        )
        self.assertIn("Added: mem_", first.stdout)
        dup = self.run_cli(
            "add", "Rust implementation uses a separate repository",
            "--type", "decision", "--status", "confirmed",
        )
        self.assertIn("Duplicate:", dup.stdout)
        recalled = self.run_cli("recall", "Rust repository", "--json")
        data = json.loads(recalled.stdout)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["memories"][0]["status"], "confirmed")
        self.assertEqual(data["memories"][0]["source"]["agent"], "codex")
        self.assertIn("sqlite integrity: ok", self.run_cli("doctor").stdout)

    def test_conflict_and_supersession(self):
        self.run_cli("init")
        a = self.run_cli("add", "Use a single repository", "--type", "decision", "--status", "confirmed").stdout
        aid = a.split("Added: ", 1)[1].split()[0]
        b = self.run_cli(
            "add", "Use separate repositories", "--type", "decision", "--status", "confirmed",
            "--conflicts-with", aid,
        ).stdout
        bid = b.split("Added: ", 1)[1].split()[0]
        old = json.loads(self.run_cli("inspect", aid).stdout)
        self.assertEqual(old["status"], "conflict")
        self.assertTrue(any(r["to_id"] == bid for r in old["relations"]))
        self.run_cli("resolve", bid, "--status", "confirmed")
        self.run_cli("resolve", aid, "--status", "superseded", "--superseded-by", bid)
        old2 = json.loads(self.run_cli("inspect", aid).stdout)
        self.assertEqual(old2["status"], "superseded")
        self.assertEqual(old2["superseded_by"], bid)

    def test_import_l1_is_needs_review(self):
        source = Path(self.tmp.name) / "AGENTS.md"
        source.write_text("# Project\n\nUse SQLite for local state.\n\n# Decision\n\nKeep raw evidence.", encoding="utf-8")
        dry = self.run_cli("import-l1", "--source", str(source), "--source-agent", "codex", "--dry-run")
        self.assertIn("dry run", dry.stdout.lower())
        self.run_cli("import-l1", "--source", str(source), "--source-agent", "codex")
        recalled = json.loads(self.run_cli("recall", "SQLite", "--json").stdout)
        self.assertGreaterEqual(recalled["count"], 1)
        self.assertEqual(recalled["memories"][0]["status"], "needs_review")
        self.assertTrue((self.home / "raw").exists())


if __name__ == "__main__":
    unittest.main()
