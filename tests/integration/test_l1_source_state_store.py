import tempfile
import unittest
from pathlib import Path

from memcarry.domain.l1_source import L1SourceFingerprint, ProcessedL1SourceState
from memcarry.infrastructure.sqlite.l1_source_state import SQLiteL1SourceStateStore


class SQLiteL1SourceStateStoreTest(unittest.TestCase):
    def test_round_trip_preserves_fingerprint_cursor_and_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteL1SourceStateStore(Path(tmp) / "memory.db")
            state = ProcessedL1SourceState(
                fingerprint=L1SourceFingerprint(
                    source_id="claude:session-1",
                    size=1234,
                    mtime_ns=99,
                    digest="abc",
                    cursor="42",
                ),
                repository_id="github.com/al-hub/memcarry",
                complete=False,
            )

            store.save(state)
            loaded = store.load("claude:session-1")

            self.assertEqual(loaded, state)

    def test_save_is_idempotent_and_latest_cursor_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteL1SourceStateStore(Path(tmp) / "memory.db")
            first = ProcessedL1SourceState(
                fingerprint=L1SourceFingerprint("codex:s1", 100, 1, digest="h1", cursor="10"),
                repository_id="github.com/al-hub/memcarry",
                complete=False,
            )
            second = ProcessedL1SourceState(
                fingerprint=L1SourceFingerprint("codex:s1", 150, 2, digest="h2", cursor="20"),
                repository_id="github.com/al-hub/memcarry",
                complete=True,
            )

            store.save(first)
            store.save(second)

            self.assertEqual(store.load("codex:s1"), second)
            self.assertEqual(store.count(), 1)


if __name__ == "__main__":
    unittest.main()
