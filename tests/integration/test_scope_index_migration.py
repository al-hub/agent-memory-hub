import sqlite3
import tempfile
import unittest
from pathlib import Path

from memcarry.infrastructure.sqlite.scope_index import ensure_single_index_scope_fts
from memcarry.infrastructure.sqlite.scope_key import scope_fts_token


class ScopeIndexMigrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "memory.db"
        con = sqlite3.connect(self.db)
        con.executescript("""
        CREATE TABLE memories(
          id TEXT PRIMARY KEY,
          statement TEXT NOT NULL,
          scope TEXT NOT NULL,
          scope_ref TEXT
        );
        CREATE VIRTUAL TABLE memory_fts USING fts5(id UNINDEXED, statement);
        """)
        con.execute(
            "INSERT INTO memories(id,statement,scope,scope_ref) VALUES(?,?,?,?)",
            ("m1", "keep repository context", "repository", "github.com/al-hub/demo"),
        )
        con.execute(
            "INSERT INTO memory_fts(id,statement) VALUES(?,?)",
            ("m1", "keep repository context"),
        )
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _fts_rows(self):
        con = sqlite3.connect(self.db)
        try:
            return con.execute(
                "SELECT rowid,id,statement,scope_key FROM memory_fts ORDER BY rowid"
            ).fetchall()
        finally:
            con.close()

    def test_legacy_two_column_fts_is_rebuilt_without_touching_memories(self):
        self.assertTrue(ensure_single_index_scope_fts(self.db))

        con = sqlite3.connect(self.db)
        try:
            columns = {row[1] for row in con.execute("PRAGMA table_info(memory_fts)")}
            self.assertIn("scope_key", columns)
            memory = con.execute(
                "SELECT rowid,id,statement,scope,scope_ref FROM memories WHERE id='m1'"
            ).fetchone()
            fts = con.execute(
                "SELECT rowid,id,statement,scope_key FROM memory_fts WHERE id='m1'"
            ).fetchone()
            self.assertEqual(fts[0], memory[0])
            self.assertEqual(fts[1], memory[1])
            self.assertEqual(fts[2], memory[2])
            self.assertEqual(fts[3], scope_fts_token(memory[3], memory[4]))
        finally:
            con.close()

    def test_dirty_insert_update_delete_are_repaired_incrementally(self):
        self.assertTrue(ensure_single_index_scope_fts(self.db))

        con = sqlite3.connect(self.db)
        con.execute(
            "INSERT INTO memories(id,statement,scope,scope_ref) VALUES(?,?,?,?)",
            ("m2", "new worktree state", "worktree", "github.com/al-hub/demo::worktree::wt:2"),
        )
        # Simulate the legacy writer, which still inserts only id+statement.
        con.execute(
            "INSERT INTO memory_fts(id,statement) VALUES(?,?)",
            ("m2", "new worktree state"),
        )
        con.commit()
        con.close()

        self.assertTrue(ensure_single_index_scope_fts(self.db))
        con = sqlite3.connect(self.db)
        try:
            rows = con.execute(
                "SELECT rowid,id,statement,scope_key FROM memory_fts WHERE id='m2'"
            ).fetchall()
            self.assertEqual(len(rows), 1)
            memory = con.execute(
                "SELECT rowid,scope,scope_ref FROM memories WHERE id='m2'"
            ).fetchone()
            self.assertEqual(rows[0][0], memory[0])
            self.assertEqual(rows[0][3], scope_fts_token(memory[1], memory[2]))
            self.assertEqual(
                con.execute("SELECT count(*) FROM scope_fts_dirty").fetchone()[0],
                0,
            )
        finally:
            con.close()

        con = sqlite3.connect(self.db)
        con.execute(
            "UPDATE memories SET statement=?,scope=?,scope_ref=? WHERE id='m2'",
            ("updated branch state", "branch", "github.com/al-hub/demo::branch::main"),
        )
        con.commit()
        con.close()
        self.assertTrue(ensure_single_index_scope_fts(self.db))
        con = sqlite3.connect(self.db)
        try:
            row = con.execute(
                "SELECT statement,scope_key FROM memory_fts WHERE id='m2'"
            ).fetchone()
            self.assertEqual(row[0], "updated branch state")
            self.assertEqual(
                row[1],
                scope_fts_token("branch", "github.com/al-hub/demo::branch::main"),
            )
        finally:
            con.close()

        con = sqlite3.connect(self.db)
        con.execute("DELETE FROM memories WHERE id='m2'")
        con.commit()
        con.close()
        self.assertTrue(ensure_single_index_scope_fts(self.db))
        con = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                con.execute("SELECT count(*) FROM memory_fts WHERE id='m2'").fetchone()[0],
                0,
            )
        finally:
            con.close()

    def test_missing_or_incompatible_store_is_fail_safe(self):
        missing = Path(self.tmp.name) / "missing.db"
        self.assertFalse(ensure_single_index_scope_fts(missing))

        broken = Path(self.tmp.name) / "broken.db"
        sqlite3.connect(broken).close()
        self.assertFalse(ensure_single_index_scope_fts(broken))


if __name__ == "__main__":
    unittest.main()
