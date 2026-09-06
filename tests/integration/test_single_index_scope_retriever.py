import sqlite3
import tempfile
import unittest
from pathlib import Path

from agent_memory_hub.domain.context import ExecutionContext, RepositoryIdentity
from agent_memory_hub.domain.recall import RecallQuery
from agent_memory_hub.infrastructure.sqlite.retriever import SQLiteMemoryReader
from agent_memory_hub.infrastructure.sqlite.scope_key import scope_fts_token
from agent_memory_hub.infrastructure.sqlite.single_index_scope_retriever import (
    SingleIndexScopeSQLiteMemoryReader,
)


class SingleIndexScopeSQLiteMemoryReaderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "memory.db"
        con = sqlite3.connect(self.db)
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
        CREATE VIRTUAL TABLE memory_fts USING fts5(id UNINDEXED, statement, scope_key);
        """)
        rows = [
            ("g", "SQLite is the local state store", "fact", "active", "verified", .95, "global", None, 1),
            ("r", "FTS5 is the repository fast path", "decision", "active", "verified", .95, "repository", "github.com/al-hub/demo", 2),
            ("b", "Main branch keeps the compatibility shim", "constraint", "active", "verified", .95, "branch", "github.com/al-hub/demo::branch::main", 3),
            ("w", "Current worktree benchmarks FTS5 allocation", "project_state", "active", "verified", .95, "worktree", "github.com/al-hub/demo::worktree::wt:abc", 4),
            ("f", "Foreign repository benchmarks FTS5 allocation", "decision", "active", "verified", .99, "repository", "github.com/al-hub/foreign", 5),
            ("s", "Old FTS5 strategy", "decision", "superseded", "verified", .99, "repository", "github.com/al-hub/demo", 6),
            ("q", "Quarantined FTS5 strategy", "decision", "quarantined", "verified", .99, "repository", "github.com/al-hub/demo", 7),
        ]
        con.executemany("INSERT INTO memories VALUES(?,?,?,?,?,?,?,?,?)", rows)
        con.executemany(
            "INSERT INTO memory_fts(id,statement,scope_key) VALUES(?,?,?)",
            [(r[0], r[1], scope_fts_token(r[6], r[7])) for r in rows],
        )
        con.commit()
        con.close()

        repo = RepositoryIdentity(
            canonical_id="github.com/al-hub/demo",
            root="/tmp/demo",
            common_dir="/tmp/demo/.git",
            remote="git@github.com:al-hub/demo.git",
        )
        self.context = ExecutionContext(repository=repo, worktree_id="wt:abc", branch="main")

    def tearDown(self):
        self.tmp.cleanup()

    def test_single_index_matches_broad_reader_ordered_results(self):
        query = RecallQuery("FTS5 SQLite compatibility benchmarks", self.context, limit=10)
        broad = SQLiteMemoryReader(self.db).recall(query)
        single = SingleIndexScopeSQLiteMemoryReader(self.db).recall(query)
        self.assertEqual([x.id for x in single], [x.id for x in broad])

    def test_single_index_preserves_scope_and_governance_filters(self):
        hits = SingleIndexScopeSQLiteMemoryReader(self.db).recall(
            RecallQuery("FTS5 allocation strategy", self.context, limit=10)
        )
        ids = [x.id for x in hits]
        self.assertIn("w", ids)
        self.assertNotIn("f", ids)
        self.assertNotIn("s", ids)
        self.assertNotIn("q", ids)

    def test_existing_broad_reader_remains_compatible_with_scope_key_column(self):
        hits = SQLiteMemoryReader(self.db).recall(
            RecallQuery("FTS5 SQLite", self.context, limit=10)
        )
        ids = [x.id for x in hits]
        self.assertIn("g", ids)
        self.assertIn("r", ids)
        self.assertIn("w", ids)
        self.assertNotIn("f", ids)

    def test_empty_query_keeps_existing_bounded_scope_browse(self):
        reader = SingleIndexScopeSQLiteMemoryReader(self.db)
        hits = reader.recall(RecallQuery("", self.context, limit=10))
        ids = [x.id for x in hits]
        self.assertEqual(ids[:3], ["w", "b", "r"])
        self.assertIn("g", ids)
        self.assertNotIn("f", ids)

    def test_legacy_two_column_memory_fts_falls_back_to_broad_reader(self):
        con = sqlite3.connect(self.db)
        con.execute("DROP TABLE memory_fts")
        con.execute("CREATE VIRTUAL TABLE memory_fts USING fts5(id UNINDEXED, statement)")
        rows = con.execute("SELECT id,statement FROM memories").fetchall()
        con.executemany("INSERT INTO memory_fts(id,statement) VALUES(?,?)", rows)
        con.commit()
        con.close()

        query = RecallQuery("FTS5 SQLite", self.context, limit=10)
        broad = SQLiteMemoryReader(self.db).recall(query)
        single = SingleIndexScopeSQLiteMemoryReader(self.db).recall(query)
        self.assertEqual([x.id for x in single], [x.id for x in broad])


if __name__ == "__main__":
    unittest.main()
