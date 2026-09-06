import sqlite3
import tempfile
import unittest
from pathlib import Path

from agent_memory_hub.infrastructure.filesystem.continuity_state_store import JsonContinuityStateStore
from agent_memory_hub.infrastructure.sqlite.repository_knowledge import SQLiteRepositoryKnowledgeReader
from agent_memory_hub.ports.continuity_state import StoredContinuityState


class ContinuityStateAdaptersTest(unittest.TestCase):
    def test_sqlite_repository_knowledge_detects_repository_family_scopes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "memory.db"
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE memories(id TEXT PRIMARY KEY,lifecycle TEXT,scope TEXT,scope_ref TEXT)")
            con.executemany(
                "INSERT INTO memories VALUES(?,?,?,?)",
                [
                    ("a", "active", "repository", "github.com/al-hub/demo"),
                    ("b", "active", "branch", "github.com/al-hub/other::branch::main"),
                    ("c", "quarantined", "worktree", "github.com/al-hub/blocked::worktree::wt:1"),
                ],
            )
            con.commit(); con.close()

            reader = SQLiteRepositoryKnowledgeReader(db)
            self.assertTrue(reader.has_repository("github.com/al-hub/demo"))
            self.assertTrue(reader.has_repository("github.com/al-hub/other"))
            self.assertFalse(reader.has_repository("github.com/al-hub/blocked"))
            self.assertFalse(reader.has_repository("github.com/al-hub/missing"))

    def test_json_state_store_round_trips_by_repository_and_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "continuity.json"
            store = JsonContinuityStateStore(path)
            state = StoredContinuityState(session_id="s1", head_sha="abc")
            store.save("github.com/al-hub/demo", "wt:1", state)

            self.assertEqual(store.load("github.com/al-hub/demo", "wt:1"), state)
            self.assertIsNone(store.load("github.com/al-hub/demo", "wt:2"))


if __name__ == "__main__":
    unittest.main()
