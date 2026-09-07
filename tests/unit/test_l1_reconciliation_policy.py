import unittest

from memcarry.domain.l1_governance import (
    EvidenceStrength,
    GovernedClaim,
    IncomingClaim,
    ReconciliationAction,
    ReconciliationPolicy,
    evidence_strength_for,
)


class L1ReconciliationPolicyTest(unittest.TestCase):
    def setUp(self):
        self.policy = ReconciliationPolicy()

    def existing(self, **overrides):
        values = dict(
            semantic_key="fts-design",
            value_hash="single-index",
            memory_type="decision",
            repository_id="github.com/al-hub/memcarry",
            observed_at="2026-09-01T00:00:00Z",
            head_sha="head-a",
            review_state="verified",
            evidence_strength=EvidenceStrength.STRONG,
        )
        values.update(overrides)
        return GovernedClaim(**values)

    def incoming(self, **overrides):
        values = dict(
            semantic_key="fts-design",
            value_hash="single-index",
            memory_type="decision",
            repository_id="github.com/al-hub/memcarry",
            observed_at="2026-09-07T00:00:00Z",
            head_sha="head-a",
            evidence_strength=EvidenceStrength.MEDIUM,
        )
        values.update(overrides)
        return IncomingClaim(**values)

    def test_direct_sources_are_strong_and_agent_inference_is_weak(self):
        self.assertEqual(evidence_strength_for("git_commit"), EvidenceStrength.STRONG)
        self.assertEqual(evidence_strength_for("test_result"), EvidenceStrength.STRONG)
        self.assertEqual(evidence_strength_for("agent_summary"), EvidenceStrength.MEDIUM)
        self.assertEqual(evidence_strength_for("agent_inference"), EvidenceStrength.WEAK)

    def test_same_semantic_value_attaches_evidence_without_new_memory(self):
        outcome = self.policy.reconcile(self.existing(), self.incoming(), current_head="head-a")
        self.assertEqual(outcome.action, ReconciliationAction.ATTACH_EVIDENCE)
        self.assertEqual(outcome.existing_review_state, "verified")

    def test_project_state_newer_value_supersedes_older_state(self):
        outcome = self.policy.reconcile(
            self.existing(memory_type="project_state", value_hash="old"),
            self.incoming(memory_type="project_state", value_hash="new"),
            current_head="head-a",
        )
        self.assertEqual(outcome.action, ReconciliationAction.SUPERSEDE)

    def test_stable_decision_disagreement_is_conflict_not_overwrite(self):
        outcome = self.policy.reconcile(
            self.existing(value_hash="fast-path-rejected"),
            self.incoming(value_hash="fast-path-adopted", evidence_strength=EvidenceStrength.STRONG),
            current_head="head-a",
        )
        self.assertEqual(outcome.action, ReconciliationAction.RECORD_CONFLICT)
        self.assertEqual(outcome.existing_review_state, "conflict")

    def test_weak_l1_contradiction_does_not_downgrade_verified_strong_memory(self):
        outcome = self.policy.reconcile(
            self.existing(value_hash="single-index", review_state="verified", evidence_strength=EvidenceStrength.STRONG),
            self.incoming(value_hash="two-index", evidence_strength=EvidenceStrength.WEAK),
            current_head="head-a",
        )
        self.assertEqual(outcome.action, ReconciliationAction.RECORD_CONTRADICTION)
        self.assertEqual(outcome.existing_review_state, "verified")
        self.assertEqual(outcome.incoming_review_state, "needs_review")

    def test_different_repository_is_kept_separate(self):
        outcome = self.policy.reconcile(
            self.existing(),
            self.incoming(repository_id="github.com/al-hub/other"),
            current_head="head-a",
        )
        self.assertEqual(outcome.action, ReconciliationAction.KEEP_SEPARATE)

    def test_old_head_project_state_is_needs_review_before_reconciliation(self):
        outcome = self.policy.reconcile(
            self.existing(memory_type="project_state", value_hash="old"),
            self.incoming(memory_type="project_state", value_hash="new", head_sha="head-old"),
            current_head="head-current",
        )
        self.assertEqual(outcome.action, ReconciliationAction.MARK_STALE)
        self.assertEqual(outcome.incoming_review_state, "needs_review")


if __name__ == "__main__":
    unittest.main()
