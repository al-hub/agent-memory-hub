import unittest

from memcarry.application.l1_ingestion_state_detector import L1IngestionStateDetector
from memcarry.domain.l1_ingestion import IngestionMode, IngestionObservation, L1Record


class L1IngestionStateDetectorTest(unittest.TestCase):
    def setUp(self):
        self.detector = L1IngestionStateDetector()

    def test_empty_store_bootstraps_current_repository(self):
        mode = self.detector.detect(
            IngestionObservation(
                repository_id="github.com/al-hub/demo",
                store_empty=True,
                repository_known=False,
                source_changed=True,
            )
        )
        self.assertEqual(mode, IngestionMode.BOOTSTRAP)

    def test_first_seen_repository_uses_targeted_onboard_import(self):
        mode = self.detector.detect(
            IngestionObservation(
                repository_id="github.com/al-hub/demo",
                store_empty=False,
                repository_known=False,
                source_changed=True,
            )
        )
        self.assertEqual(mode, IngestionMode.ONBOARD)

    def test_known_repository_with_changed_source_reconciles(self):
        mode = self.detector.detect(
            IngestionObservation(
                repository_id="github.com/al-hub/demo",
                store_empty=False,
                repository_known=True,
                source_changed=True,
            )
        )
        self.assertEqual(mode, IngestionMode.RECONCILE)

    def test_known_repository_with_unchanged_source_is_noop(self):
        mode = self.detector.detect(
            IngestionObservation(
                repository_id="github.com/al-hub/demo",
                store_empty=False,
                repository_known=True,
                source_changed=False,
            )
        )
        self.assertEqual(mode, IngestionMode.NONE)

    def test_interrupted_ingestion_resumes_before_other_modes(self):
        mode = self.detector.detect(
            IngestionObservation(
                repository_id="github.com/al-hub/demo",
                store_empty=False,
                repository_known=True,
                source_changed=False,
                interrupted=True,
            )
        )
        self.assertEqual(mode, IngestionMode.RESUME_INGEST)

    def test_non_repository_context_does_not_ingest(self):
        mode = self.detector.detect(
            IngestionObservation(
                repository_id=None,
                store_empty=True,
                repository_known=False,
                source_changed=True,
            )
        )
        self.assertEqual(mode, IngestionMode.NONE)


class L1RecordTest(unittest.TestCase):
    def test_record_keeps_provenance_and_source_context(self):
        record = L1Record(
            source_agent="claude",
            source_id="session-42",
            observed_at="2026-09-08T10:00:00+09:00",
            content="single-index FTS adopted",
            kind="decision",
            repository_id="github.com/al-hub/memcarry",
            branch="main",
            head_sha="abc123",
            source_path="~/.claude/history/session-42.jsonl",
        )

        self.assertEqual(record.source_agent, "claude")
        self.assertEqual(record.source_id, "session-42")
        self.assertEqual(record.kind, "decision")
        self.assertEqual(record.repository_id, "github.com/al-hub/memcarry")
        self.assertEqual(record.head_sha, "abc123")
        self.assertIn("claude", record.provenance_key)
        self.assertIn("session-42", record.provenance_key)


if __name__ == "__main__":
    unittest.main()
