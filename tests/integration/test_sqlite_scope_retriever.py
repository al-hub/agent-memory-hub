import sqlite3
import tempfile
import unittest
from pathlib import Path

from memcarry.domain.context import ExecutionContext, RepositoryIdentity
from memcarry.domain.recall import RecallQuery
from memcarry.infrastructure.sqlite.retriever import SQLiteMemoryReader


class SQLiteScopeRetrieverTest(unittest.TestCase):
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
        CREATE VIRTUAL TABLE memory_fts USING fts5(id UNINDEXED, statement);
        """)
        rows = [
            ("g", "SQLite is the local state store", "fact", "active", "verified", .95, "global", None, 1),
            ("r", "FTS5 is the repository fast path", "decision", "active", "verified", .95, "repository", "github.com/al-hub/demo", 2),
            ("b", "Main branch keeps the compatibility shim", "constraint", "active", "verified", .95, "branch", "github.com/al-hub/demo::branch::main", 3),
            ("w", "Current worktree benchmarks FTS5 allocation", "project_state", "active", "verified", .95, "worktree", "github.com/al-hub/demo::worktree::wt:abc", 4),
            ("f", "Foreign repository uses FTS5 differently", "decision", "active", "verified", .99, "repository", "github.com/al-hub/foreign", 5),
            ("s", "Old FTS5 strategy", "decision", "superseded", "verified", .99, "repository", "github.com/al-hub/demo", 6),
        ]
        con.executemany("INSERT INTO memories VALUES(?,?,?,?,?,?,?,?,?)", rows)
        con.executemany("INSERT INTO memory_fts(id,statement) VALUES(?,?)", [(r[0], r[1]) for r in rows])
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

    def test_recall_includes_visible_scopes_and_excludes_foreign_and_superseded(self):
        reader = SQLiteMemoryReader(self.db)
        hits = reader.recall(RecallQuery("FTS5 SQLite compatibility benchmarks", self.context, limit=10))
        ids = [x.id for x in hits]
        self.assertIn("g", ids)
        self.assertIn("r", ids)
        self.assertIn("b", ids)
        self.assertIn("w", ids)
        self.assertNotIn("f", ids)
        self.assertNotIn("s", ids)

    def test_more_specific_scope_ranks_before_repository_and_global(self):
        reader = SQLiteMemoryReader(self.db)
        hits = reader.recall(RecallQuery("FTS5 SQLite", self.context, limit=10))
        rank = {x.id: x.scope_rank for x in hits}
        self.assertLess(rank["w"], rank["r"])
        self.assertLess(rank["r"], rank["g"])

    def test_type_filter_is_applied_before_projection(self):
        reader = SQLiteMemoryReader(self.db)
        hits = reader.recall(RecallQuery("FTS5", self.context, memory_type="decision", limit=10))
        self.assertEqual([x.id for x in hits], ["r"])

    def test_empty_query_browses_visible_scopes_for_session_start_projection(self):
        reader = SQLiteMemoryReader(self.db)
        hits = reader.recall(RecallQuery("", self.context, limit=10))
        ids = [x.id for x in hits]
        self.assertEqual(ids[:3], ["w", "b", "r"])
        self.assertIn("g", ids)
        self.assertNotIn("f", ids)
        self.assertNotIn("s", ids)


if __name__ == "__main__":
    unittest.main()
