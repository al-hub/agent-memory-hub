import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "memcarry_store.py"


class MemoryHubSmokeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "hub"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, check=True):
        cmd = [sys.executable, str(CLI), "--home", str(self.home), *args]
        result = subprocess.run(cmd, text=True, capture_output=True, check=False)
        if check and result.returncode:
            self.fail(
                "CLI failed\n"
                f"command: {' '.join(cmd)}\n"
                f"returncode: {result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        return result

    def test_init_add_recall_duplicate_and_doctor(self):
        out = self.run_cli("init").stdout
        self.assertIn("Schema: v2", out)
        first = self.run_cli(
            "add", "Rust implementation uses a separate repository",
            "--type", "decision", "--status", "confirmed", "--confidence", "0.96",
            "--scope", "project", "--scope-ref", "samsung-internal-rs",
            "--source-agent", "codex", "--source-pointer", "conversation:2026-09-02",
        )
        self.assertIn("Added: mem_", first.stdout)
        dup = self.run_cli(
            "add", "Rust implementation uses a separate repository",
            "--type", "decision", "--status", "confirmed",
            "--source-agent", "claude", "--source-pointer", "conversation:2026-09-03",
        )
        self.assertIn("Duplicate:", dup.stdout)
        self.assertIn("evidence merged", dup.stdout)
        data = json.loads(self.run_cli("recall", "Rust repository", "--json").stdout)
        self.assertEqual(data["count"], 1)
        m = data["memories"][0]
        self.assertEqual(m["status"], "confirmed")
        self.assertEqual(m["lifecycle"], "active")
        self.assertEqual(m["review_state"], "verified")
        self.assertEqual(m["scope"], "project")
        self.assertGreaterEqual(len(m["evidence"]), 2)
        doctor = self.run_cli("doctor").stdout
        self.assertIn("sqlite integrity: ok", doctor)
        self.assertIn("schema: v2", doctor)

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
        self.assertEqual(old["review_state"], "conflict")
        self.assertTrue(any(r["to_id"] == bid for r in old["relations"]))
        self.run_cli("resolve", bid, "--lifecycle", "active", "--review-state", "verified")
        self.run_cli("resolve", aid, "--lifecycle", "superseded", "--review-state", "verified", "--superseded-by", bid)
        old2 = json.loads(self.run_cli("inspect", aid).stdout)
        self.assertEqual(old2["lifecycle"], "superseded")
        self.assertEqual(old2["status"], "superseded")
        self.assertEqual(old2["superseded_by"], bid)

    def test_import_l1_registers_raw_source_and_needs_review(self):
        source = Path(self.tmp.name) / "AGENTS.md"
        source.write_text("# Project\n\nUse SQLite for local state.\n\n# Decision\n\nKeep raw evidence.", encoding="utf-8")
        dry = self.run_cli("import-l1", "--source", str(source), "--source-agent", "codex", "--dry-run")
        self.assertIn("dry run", dry.stdout.lower())
        self.run_cli("import-l1", "--source", str(source), "--source-agent", "codex", "--scope", "project", "--scope-ref", "demo")
        recalled = json.loads(self.run_cli("recall", "SQLite", "--json").stdout)
        self.assertGreaterEqual(recalled["count"], 1)
        m = recalled["memories"][0]
        self.assertEqual(m["review_state"], "needs_review")
        self.assertEqual(m["lifecycle"], "candidate")
        self.assertEqual(m["scope_ref"], "demo")
        self.assertTrue(m["evidence"][0]["raw_source_id"])
        with sqlite3.connect(self.home / "memory.db") as con:
            self.assertEqual(con.execute("SELECT count(*) FROM raw_sources").fetchone()[0], 1)
        self.assertTrue((self.home / "raw").exists())

    def test_non_destructive_v1_migration_backfills_evidence(self):
        self.home.mkdir(parents=True)
        db = self.home / "memory.db"
        con = sqlite3.connect(db)
        con.executescript("""
        CREATE TABLE memories(
          id TEXT PRIMARY KEY, statement TEXT NOT NULL, normalized_hash TEXT NOT NULL,
          type TEXT NOT NULL, status TEXT NOT NULL, confidence REAL NOT NULL,
          context_quality TEXT NOT NULL, source_agent TEXT, source_type TEXT,
          source_pointer TEXT, source_hash TEXT, evidence_group TEXT,
          valid_from TEXT, valid_until TEXT, superseded_by TEXT,
          created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
        );
        CREATE TABLE relations(id INTEGER PRIMARY KEY AUTOINCREMENT, from_id TEXT NOT NULL, relation TEXT NOT NULL, to_id TEXT NOT NULL, created_at INTEGER NOT NULL, UNIQUE(from_id,relation,to_id));
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta VALUES('schema_version','1');
        """)
        con.execute("INSERT INTO memories VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            "mem_old", "Keep raw evidence", "hash1", "decision", "confirmed", .9, "clear",
            "codex", "conversation", "old:1", "sourcehash", "session:1", None, None, None, 1, 1,
        ))
        con.commit(); con.close()

        status = self.run_cli("status").stdout
        self.assertIn("Schema: v2", status)
        old = json.loads(self.run_cli("inspect", "mem_old").stdout)
        self.assertEqual(old["lifecycle"], "active")
        self.assertEqual(old["review_state"], "verified")
        self.assertEqual(len(old["evidence"]), 1)
        with sqlite3.connect(db) as con:
            cols = {r[1] for r in con.execute("PRAGMA table_info(memories)")}
            self.assertIn("status", cols)  # legacy column remains
            self.assertIn("lifecycle", cols)
            self.assertIn("review_state", cols)
            self.assertEqual(con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], "2")


if __name__ == "__main__":
    unittest.main()
