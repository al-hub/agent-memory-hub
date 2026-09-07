from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memcarry.application.l1_ingestion_pipeline import DEFAULT_MAX_RECORDS, L1IngestionPipeline
from memcarry.domain.l1_ingestion import IngestionMode, L1Record
from memcarry.domain.l1_source import L1SourceFingerprint
from memcarry.infrastructure.sqlite.governed_l1_store import SQLiteGovernedL1Store
from memcarry.infrastructure.sqlite.l1_source_state import SQLiteL1SourceStateStore


class FakeL1Source:
    def __init__(self, source_id: str, records: list[L1Record], *, size: int = 1, mtime_ns: int = 1, digest: str = "v1"):
        self._source_id = source_id
        self._records = list(records)
        self._fingerprint = L1SourceFingerprint(source_id=source_id, size=size, mtime_ns=mtime_ns, digest=digest)
        self.calls: list[tuple[str | None, str | None]] = []

    @property
    def source_id(self) -> str:
        return self._source_id

    def fingerprint(self) -> L1SourceFingerprint:
        return self._fingerprint

    def iter_records(self, *, repository_id: str | None = None, after_cursor: str | None = None):
        self.calls.append((repository_id, after_cursor))
        start = int(after_cursor or 0)
        for record in self._records[start:]:
            if repository_id is None or record.repository_id == repository_id:
                yield record


class OpaqueCursorSource:
    def __init__(self, records: list[L1Record], *, digest: str):
        self._records = records
        self._digest = digest
        self.calls: list[str | None] = []

    @property
    def source_id(self) -> str:
        return "opaque"

    def fingerprint(self) -> L1SourceFingerprint:
        return L1SourceFingerprint(source_id="opaque", size=len(self._records), mtime_ns=len(self._records), digest=self._digest)

    def iter_records(self, *, repository_id: str | None = None, after_cursor: str | None = None):
        self.calls.append(after_cursor)
        passed = after_cursor is None
        for record in self._records:
            if not passed:
                if record.cursor == after_cursor:
                    passed = True
                continue
            if repository_id is None or record.repository_id == repository_id:
                yield record


class L1IngestionPipelineIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "memory.db"
        self.state_store = SQLiteL1SourceStateStore(self.db_path)
        self.memory_store = SQLiteGovernedL1Store(self.db_path)
        self.pipeline = L1IngestionPipeline(self.state_store, self.memory_store)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def record(
        source_id: str,
        statement: str,
        *,
        repo: str = "al-hub/memcarry",
        kind: str = "agent_summary",
        memory_type: str = "decision",
        semantic_key: str = "runtime",
        observed_at: str = "2026-09-08T00:00:00Z",
        cursor: str | None = None,
    ) -> L1Record:
        return L1Record(
            source_agent="fake",
            source_id=source_id,
            observed_at=observed_at,
            content=statement,
            kind=kind,
            repository_id=repo,
            branch="main",
            head_sha="head-1",
            source_path=f"/fake/{source_id}",
            memory_type=memory_type,
            semantic_key=semantic_key,
            cursor=cursor,
        )

    def test_empty_bootstrap_persists_candidates_and_evidence(self):
        source = FakeL1Source("s1", [self.record("r1", "Use SQLite for governed L2")])

        result = self.pipeline.ingest(source, repository_id="al-hub/memcarry", current_head="head-1")

        self.assertEqual(result.mode, IngestionMode.BOOTSTRAP)
        self.assertEqual(result.processed, 1)
        self.assertEqual(self.memory_store.count_memories(), 1)
        self.assertEqual(self.memory_store.count_evidence(), 1)
        memory = self.memory_store.list_memories()[0]
        self.assertEqual(memory["lifecycle"], "candidate")
        self.assertEqual(memory["review_state"], "unverified")
        self.assertEqual(memory["scope"], "repository")
        self.assertEqual(memory["scope_ref"], "al-hub/memcarry")

    def test_empty_bootstrap_is_bounded_by_default(self):
        records = [self.record(f"r{i}", f"Decision {i}", semantic_key=f"k{i}") for i in range(DEFAULT_MAX_RECORDS + 1)]
        source = FakeL1Source("bounded", records, size=len(records), mtime_ns=1)

        result = self.pipeline.ingest(source, repository_id="al-hub/memcarry", current_head="head-1")

        self.assertEqual(result.processed, DEFAULT_MAX_RECORDS)
        self.assertFalse(result.complete)
        self.assertEqual(self.memory_store.count_memories(), DEFAULT_MAX_RECORDS)

    def test_first_repository_onboard_filters_unrelated_records(self):
        self.memory_store.insert_seed_memory("other/repo", "existing")
        source = FakeL1Source(
            "s2",
            [
                self.record("r1", "Memcarry decision", repo="al-hub/memcarry"),
                self.record("r2", "Other decision", repo="other/repo"),
            ],
        )

        result = self.pipeline.ingest(source, repository_id="al-hub/memcarry", current_head="head-1")

        self.assertEqual(result.mode, IngestionMode.ONBOARD)
        statements = [row["statement"] for row in self.memory_store.list_memories(repository_id="al-hub/memcarry")]
        self.assertEqual(statements, ["Memcarry decision"])
        self.assertEqual(source.calls, [("al-hub/memcarry", None)])

    def test_existing_unchanged_source_is_noop(self):
        source = FakeL1Source("s3", [self.record("r1", "Decision")])
        first = self.pipeline.ingest(source, repository_id="al-hub/memcarry", current_head="head-1")
        second = self.pipeline.ingest(source, repository_id="al-hub/memcarry", current_head="head-1")

        self.assertEqual(first.processed, 1)
        self.assertEqual(second.mode, IngestionMode.NONE)
        self.assertEqual(second.processed, 0)
        self.assertEqual(self.memory_store.count_memories(), 1)
        self.assertEqual(self.memory_store.count_evidence(), 1)
        self.assertEqual(len(source.calls), 1)

    def test_existing_changed_source_reconciles_only_after_cursor(self):
        source_v1 = FakeL1Source("s4", [self.record("r1", "Decision v1")], size=1, mtime_ns=1, digest="v1")
        self.pipeline.ingest(source_v1, repository_id="al-hub/memcarry", current_head="head-1")

        source_v2 = FakeL1Source(
            "s4",
            [
                self.record("r1", "Decision v1"),
                self.record("r2", "State v2", memory_type="project_state", semantic_key="state"),
            ],
            size=2,
            mtime_ns=2,
            digest="v2",
        )
        result = self.pipeline.ingest(source_v2, repository_id="al-hub/memcarry", current_head="head-1")

        self.assertEqual(result.mode, IngestionMode.RECONCILE)
        self.assertEqual(result.processed, 1)
        self.assertEqual(source_v2.calls, [("al-hub/memcarry", "1")])
        self.assertEqual(self.memory_store.count_memories(), 2)

    def test_interrupted_source_resumes_without_duplicate_growth(self):
        source = FakeL1Source(
            "s5",
            [
                self.record("r1", "Decision one"),
                self.record("r2", "Decision two", semantic_key="two"),
            ],
            size=2,
            mtime_ns=2,
            digest="v2",
        )
        self.pipeline.ingest(source, repository_id="al-hub/memcarry", current_head="head-1", max_records=1)

        resumed = self.pipeline.ingest(source, repository_id="al-hub/memcarry", current_head="head-1")

        self.assertEqual(resumed.mode, IngestionMode.RESUME_INGEST)
        self.assertEqual(resumed.processed, 1)
        self.assertEqual(source.calls[-1], ("al-hub/memcarry", "1"))
        self.assertEqual(self.memory_store.count_memories(), 2)
        self.assertEqual(self.memory_store.count_evidence(), 2)

    def test_opaque_record_cursor_is_preserved_for_incremental_resume(self):
        first_record = self.record("o1", "Opaque one", semantic_key="o1", cursor="session:42")
        second_record = self.record("o2", "Opaque two", semantic_key="o2", cursor="session:99")
        first = OpaqueCursorSource([first_record], digest="v1")
        self.pipeline.ingest(first, repository_id="al-hub/memcarry", current_head="head-1")

        second = OpaqueCursorSource([first_record, second_record], digest="v2")
        result = self.pipeline.ingest(second, repository_id="al-hub/memcarry", current_head="head-1")

        self.assertEqual(result.mode, IngestionMode.RECONCILE)
        self.assertEqual(second.calls, ["session:42"])
        state = self.state_store.load("opaque")
        self.assertIsNotNone(state)
        self.assertEqual(state.fingerprint.cursor, "session:99")

    def test_duplicate_claim_from_new_source_attaches_evidence_not_memory(self):
        first = FakeL1Source("s6a", [self.record("a1", "Same decision")])
        second = FakeL1Source("s6b", [self.record("b1", "Same decision")], digest="other")
        self.pipeline.ingest(first, repository_id="al-hub/memcarry", current_head="head-1")
        self.pipeline.ingest(second, repository_id="al-hub/memcarry", current_head="head-1")

        self.assertEqual(self.memory_store.count_memories(), 1)
        self.assertEqual(self.memory_store.count_evidence(), 2)

    def test_newer_project_state_supersedes_old_value(self):
        first = FakeL1Source(
            "s7a",
            [self.record("a1", "State old", memory_type="project_state", semantic_key="state", observed_at="2026-09-01T00:00:00Z")],
        )
        second = FakeL1Source(
            "s7b",
            [self.record("b1", "State new", memory_type="project_state", semantic_key="state", observed_at="2026-09-08T00:00:00Z")],
            digest="new",
        )
        self.pipeline.ingest(first, repository_id="al-hub/memcarry", current_head="head-1")
        self.pipeline.ingest(second, repository_id="al-hub/memcarry", current_head="head-1")

        rows = self.memory_store.list_memories(repository_id="al-hub/memcarry")
        by_statement = {row["statement"]: row for row in rows}
        self.assertEqual(by_statement["State old"]["lifecycle"], "superseded")
        self.assertEqual(by_statement["State new"]["lifecycle"], "candidate")


if __name__ == "__main__":
    unittest.main()
