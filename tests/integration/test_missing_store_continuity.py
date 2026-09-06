import tempfile
import unittest
from pathlib import Path

from memcarry.domain.context import ExecutionContext, RepositoryIdentity
from memcarry.domain.recall import RecallQuery
from memcarry.infrastructure.sqlite.repository_knowledge import SQLiteRepositoryKnowledgeReader
from memcarry.infrastructure.sqlite.retriever import SQLiteMemoryReader


class MissingStoreContinuityTest(unittest.TestCase):
    def test_missing_database_is_treated_as_unknown_repository_and_empty_recall(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "missing" / "memory.db"
            repo = RepositoryIdentity(
                canonical_id="github.com/al-hub/demo",
                root="/tmp/demo",
                common_dir="/tmp/demo/.git",
            )
            context = ExecutionContext(repository=repo, branch="main")

            self.assertFalse(SQLiteRepositoryKnowledgeReader(db).has_repository(repo.canonical_id))
            self.assertEqual(
                SQLiteMemoryReader(db).recall(RecallQuery("continue", context, limit=8)),
                [],
            )


if __name__ == "__main__":
    unittest.main()
