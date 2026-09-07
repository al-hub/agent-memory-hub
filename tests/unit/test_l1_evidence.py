import unittest

from memcarry.domain.l1_evidence import L1Evidence
from memcarry.domain.l1_governance import EvidenceStrength
from memcarry.domain.l1_ingestion import L1Record


class L1EvidenceTest(unittest.TestCase):
    def test_record_is_normalized_without_losing_provenance(self):
        record = L1Record(
            source_agent="claude",
            source_id="session-7:message-42",
            observed_at="2026-09-07T00:00:00Z",
            content="single-index FTS adopted",
            kind="agent_summary",
            repository_id="github.com/al-hub/memcarry",
            branch="main",
            head_sha="abc123",
            source_path="~/.claude/history.jsonl",
        )

        evidence = L1Evidence.from_record(record)

        self.assertEqual(evidence.source_agent, "claude")
        self.assertEqual(evidence.source_type, "agent_summary")
        self.assertEqual(evidence.source_pointer, "~/.claude/history.jsonl")
        self.assertEqual(evidence.repository_id, "github.com/al-hub/memcarry")
        self.assertEqual(evidence.head_sha, "abc123")
        self.assertEqual(evidence.strength, EvidenceStrength.MEDIUM)
        self.assertTrue(evidence.evidence_group.startswith("l1:"))

    def test_same_original_record_has_stable_evidence_group(self):
        record = L1Record(
            source_agent="codex",
            source_id="session-1:turn-2",
            observed_at="2026-09-07T00:00:00Z",
            content="tests passed",
            kind="test_result",
        )
        self.assertEqual(
            L1Evidence.from_record(record).evidence_group,
            L1Evidence.from_record(record).evidence_group,
        )


if __name__ == "__main__":
    unittest.main()
