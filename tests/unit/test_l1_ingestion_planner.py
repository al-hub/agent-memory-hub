import unittest

from memcarry.application.l1_ingestion_planner import L1IngestionPlanner
from memcarry.domain.l1_ingestion import IngestionMode
from memcarry.domain.l1_source import L1SourceFingerprint, ProcessedL1SourceState


class MemoryStateStore:
    def __init__(self, state=None):
        self.state = state

    def load(self, source_id):
        if self.state and self.state.fingerprint.source_id == source_id:
            return self.state
        return None

    def save(self, state):
        self.state = state


class L1IngestionPlannerTest(unittest.TestCase):
    def fp(self, *, size=100, mtime=1, digest="a", cursor=None):
        return L1SourceFingerprint("claude:s1", size, mtime, digest=digest, cursor=cursor)

    def test_unchanged_completed_source_is_noop(self):
        previous = ProcessedL1SourceState(
            fingerprint=self.fp(cursor="20"),
            repository_id="github.com/al-hub/memcarry",
            complete=True,
        )
        planner = L1IngestionPlanner(MemoryStateStore(previous))

        plan = planner.plan(
            self.fp(cursor=None),
            repository_id="github.com/al-hub/memcarry",
            store_empty=False,
            repository_known=True,
        )

        self.assertEqual(plan.mode, IngestionMode.NONE)
        self.assertEqual(plan.after_cursor, "20")

    def test_changed_known_source_reconciles_from_saved_cursor(self):
        previous = ProcessedL1SourceState(
            fingerprint=self.fp(cursor="20"),
            repository_id="github.com/al-hub/memcarry",
            complete=True,
        )
        planner = L1IngestionPlanner(MemoryStateStore(previous))

        plan = planner.plan(
            self.fp(size=150, mtime=2, digest="b"),
            repository_id="github.com/al-hub/memcarry",
            store_empty=False,
            repository_known=True,
        )

        self.assertEqual(plan.mode, IngestionMode.RECONCILE)
        self.assertEqual(plan.after_cursor, "20")

    def test_incomplete_previous_run_resumes_before_normal_reconcile(self):
        previous = ProcessedL1SourceState(
            fingerprint=self.fp(cursor="11"),
            repository_id="github.com/al-hub/memcarry",
            complete=False,
        )
        planner = L1IngestionPlanner(MemoryStateStore(previous))

        plan = planner.plan(
            self.fp(size=150, mtime=2, digest="b"),
            repository_id="github.com/al-hub/memcarry",
            store_empty=False,
            repository_known=True,
        )

        self.assertEqual(plan.mode, IngestionMode.RESUME_INGEST)
        self.assertEqual(plan.after_cursor, "11")

    def test_new_source_uses_empty_or_first_semantics(self):
        planner = L1IngestionPlanner(MemoryStateStore())
        empty = planner.plan(
            self.fp(), repository_id="github.com/al-hub/memcarry", store_empty=True, repository_known=False
        )
        first = planner.plan(
            self.fp(), repository_id="github.com/al-hub/memcarry", store_empty=False, repository_known=False
        )
        self.assertEqual(empty.mode, IngestionMode.BOOTSTRAP)
        self.assertEqual(first.mode, IngestionMode.ONBOARD)
        self.assertIsNone(empty.after_cursor)
        self.assertIsNone(first.after_cursor)


if __name__ == "__main__":
    unittest.main()
