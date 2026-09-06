import unittest

from memcarry.application.continuity_state_detector import ContinuityStateDetector
from memcarry.continuity.gate import ContinuityGate
from memcarry.domain.context import ExecutionContext, RepositoryIdentity
from memcarry.domain.continuity import ContinuityMode
from memcarry.domain.continuity_state import ContinuityObservation
from memcarry.ports.continuity_state import StoredContinuityState


class FakeKnowledgeReader:
    def has_repository(self, repository_id: str) -> bool:
        return True


class MemoryStateStore:
    def __init__(self, initial=None):
        self.value = initial

    def load(self, repository_id, worktree_id):
        return self.value

    def save(self, repository_id, worktree_id, state):
        self.value = state


def context():
    repo = RepositoryIdentity(
        canonical_id="github.com/al-hub/demo",
        root="/tmp/demo",
        common_dir="/tmp/demo/.git",
        remote="git@github.com:al-hub/demo.git",
    )
    return ExecutionContext(repository=repo, worktree_id="wt:1", branch="main", head_sha="abc")


class PersistedAgentHandoffTest(unittest.TestCase):
    def test_agent_change_is_detected_and_persisted(self):
        store = MemoryStateStore(
            StoredContinuityState(session_id="codex-session", head_sha="abc", agent="codex")
        )
        detector = ContinuityStateDetector(FakeKnowledgeReader(), store)

        state = detector.detect(
            ContinuityObservation(
                "",
                context(),
                session_id="claude-session",
                session_has_context=False,
                session_source="startup",
                agent="claude",
            )
        )

        self.assertTrue(state.agent_changed)
        self.assertEqual(state.previous_agent, "codex")
        self.assertEqual(state.current_agent, "claude")
        self.assertEqual(store.value.agent, "claude")

    def test_same_agent_is_not_handoff(self):
        store = MemoryStateStore(
            StoredContinuityState(session_id="old", head_sha="abc", agent="codex")
        )
        detector = ContinuityStateDetector(FakeKnowledgeReader(), store)
        observation = ContinuityObservation(
            "",
            context(),
            session_id="new",
            session_has_context=False,
            session_source="startup",
            agent="codex",
        )
        state = detector.detect(observation)
        self.assertFalse(state.agent_changed)

    def test_persisted_agent_change_has_handoff_priority(self):
        store = MemoryStateStore(
            StoredContinuityState(session_id="codex-session", head_sha="abc", agent="codex")
        )
        detector = ContinuityStateDetector(FakeKnowledgeReader(), store)
        observation = ContinuityObservation(
            "",
            context(),
            session_id="claude-session",
            session_has_context=False,
            session_source="startup",
            agent="claude",
        )
        request = detector.detect(observation).to_request(observation)

        decision = ContinuityGate().decide(request)

        self.assertEqual(decision.mode, ContinuityMode.HANDOFF)
        self.assertIn("codex", decision.reason)
        self.assertIn("claude", decision.reason)


if __name__ == "__main__":
    unittest.main()
