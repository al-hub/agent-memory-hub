from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from memcarry.domain.l1_ingestion import L1Record
from memcarry.infrastructure.sqlite.governed_l1_store import SQLiteGovernedL1Store


class L1CoreCloseoutIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "memory.db"
        self.store = SQLiteGovernedL1Store(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _insert_scoped_memory(self, *, scope: str, scope_ref: str) -> None:
        con = sqlite3.connect(self.db_path)
        try:
            con.execute(
                """
                INSERT INTO memories(
                    id, statement, normalized_hash, type, status, confidence,
                    context_quality, created_at, updated_at, lifecycle,
                    review_state, scope, scope_ref
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    f"mem_{scope}",
                    f"{scope} memory",
                    f"hash-{scope}",
                    "fact",
                    "confirmed",
                    1.0,
                    "clear",
                    1,
                    1,
                    "active",
                    "verified",
                    scope,
                    scope_ref,
                ),
            )
            con.commit()
        finally:
            con.close()

    def test_repository_family_memory_marks_repository_known(self):
        repo = "al-hub/memcarry"
        for scope, ref in (
            ("repository", repo),
            ("branch", f"{repo}::branch::main"),
            ("worktree", f"{repo}::worktree::/tmp/memcarry-wt"),
            ("task", f"{repo}::task::bootstrap"),
        ):
            with self.subTest(scope=scope):
                fresh = Path(self.tmp.name) / f"{scope}.db"
                scoped_store = SQLiteGovernedL1Store(fresh)
                con = sqlite3.connect(fresh)
                try:
                    con.execute(
                        """
                        INSERT INTO memories(
                            id, statement, normalized_hash, type, status, confidence,
                            context_quality, created_at, updated_at, lifecycle,
                            review_state, scope, scope_ref
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            f"mem_{scope}", scope, f"h-{scope}", "fact", "confirmed", 1.0,
                            "clear", 1, 1, "active", "verified", scope, ref,
                        ),
                    )
                    con.commit()
                finally:
                    con.close()
                self.assertTrue(scoped_store.has_repository(repo))

    def test_other_repository_family_does_not_mark_repository_known(self):
        self._insert_scoped_memory(scope="branch", scope_ref="other/repo::branch::main")
        self.assertFalse(self.store.has_repository("al-hub/memcarry"))

    def test_evidence_preserves_temporal_and_git_provenance_per_record(self):
        record = L1Record(
            source_agent="claude",
            source_id="session-1:record-7",
            observed_at="2026-08-31T13:00:00Z",
            content="Use single-index scope-first FTS",
            kind="agent_summary",
            repository_id="al-hub/memcarry",
            branch="feature/scope-index",
            head_sha="abc123",
            source_path="/home/user/.claude/history/session-1.jsonl",
            memory_type="decision",
            semantic_key="fts-design",
        )

        self.store.ingest_record(record, current_head="abc123")

        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            evidence = con.execute(
                "SELECT observed_at, branch, head_sha, repository_id FROM evidence"
            ).fetchone()
        finally:
            con.close()
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["observed_at"], record.observed_at)
        self.assertEqual(evidence["branch"], record.branch)
        self.assertEqual(evidence["head_sha"], record.head_sha)
        self.assertEqual(evidence["repository_id"], record.repository_id)

    def test_existing_evidence_schema_is_migrated_non_destructively(self):
        legacy_db = Path(self.tmp.name) / "legacy.db"
        con = sqlite3.connect(legacy_db)
        try:
            con.executescript(
                """
                CREATE TABLE memories(
                    id TEXT PRIMARY KEY, statement TEXT NOT NULL, normalized_hash TEXT NOT NULL,
                    type TEXT NOT NULL, status TEXT NOT NULL, confidence REAL NOT NULL,
                    context_quality TEXT NOT NULL, source_agent TEXT, source_type TEXT,
                    source_pointer TEXT, source_hash TEXT, evidence_group TEXT,
                    valid_from TEXT, valid_until TEXT, superseded_by TEXT,
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                    lifecycle TEXT, review_state TEXT, scope TEXT, scope_ref TEXT
                );
                CREATE TABLE raw_sources(
                    id TEXT PRIMARY KEY, source_agent TEXT, source_type TEXT NOT NULL,
                    source_pointer TEXT, content_hash TEXT NOT NULL, evidence_group TEXT,
                    local_snapshot TEXT, extraction_state TEXT NOT NULL DEFAULT 'cold',
                    captured_at INTEGER NOT NULL, UNIQUE(content_hash, source_pointer)
                );
                CREATE TABLE evidence(
                    id TEXT PRIMARY KEY, memory_id TEXT NOT NULL, raw_source_id TEXT,
                    source_agent TEXT, source_type TEXT, source_pointer TEXT,
                    source_hash TEXT, evidence_group TEXT, excerpt TEXT, confidence REAL,
                    created_at INTEGER NOT NULL, UNIQUE(memory_id, source_hash, source_pointer)
                );
                INSERT INTO memories VALUES(
                    'm1','legacy','h1','fact','confirmed',1.0,'clear',NULL,NULL,NULL,NULL,NULL,
                    NULL,NULL,NULL,1,1,'active','verified','repository','al-hub/memcarry'
                );
                INSERT INTO evidence VALUES(
                    'e1','m1',NULL,'codex','agent_summary','/tmp/source','s1','g1','legacy',0.6,1
                );
                """
            )
            con.commit()
        finally:
            con.close()

        SQLiteGovernedL1Store(legacy_db)
        con = sqlite3.connect(legacy_db)
        try:
            columns = {row[1] for row in con.execute("PRAGMA table_info(evidence)")}
            count = con.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
        finally:
            con.close()

        self.assertTrue({"observed_at", "branch", "head_sha", "repository_id"}.issubset(columns))
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
