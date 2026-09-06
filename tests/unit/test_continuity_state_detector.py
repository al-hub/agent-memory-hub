import unittest

from agent_memory_hub.application.continuity_state_detector import ContinuityStateDetector
from agent_memory_hub.domain.context import ExecutionContext, RepositoryIdentity
from agent_memory_hub.domain.continuity_state import ContinuityObservation
from agent_memory_hub.ports.continuity_state import StoredContinuityState


class FakeKnowledgeReader:
    def __init__(self, known=True):
        self.known = known
        self.calls = []

    def has_repository(self, repository_id: str) -> bool:
        self.calls.append(repository_id)
        return self.known


class MemoryStateStore:
    def __init__(self, initial=None):
        self.value = initial
        self.saved = []

    def load(self, repository_id, worktree_id):
        return self.value

    def save(self, repository_id, worktree_id, state):
        self.value = state
        self.saved.append((repository_id, worktree_id, state))


def context(head="abc"):
    repo = RepositoryIdentity(
        canonical_id="github.com/al-hub/demo",
        root="/tmp/demo",
        common_dir="/tmp/demo/.git",
        remote="git@github.com:al-hub/demo.git",
    )
    return ExecutionContext(repository=repo, worktree_id="wt:1", branch="main", head_sha=head)


class ContinuityStateDetectorTest(unittest.TestCase):
    def test_non_repository_context_is_unknown_and_not_persisted(self):
        reader = FakeKnowledgeReader(known=True)
        store = MemoryStateStore()
        detector = ContinuityStateDetector(reader, store)

        state = detector.detect(ContinuityObservation("hello", ExecutionContext(), session_id="s1"))

        self.assertFalse(state.repository_known)
        self.assertFalse(state.session_reset)
        self.assertFalse(state.stale_head)
        self.assertEqual(reader.calls, [])
        self.assertEqual(store.saved, [])

    def test_known_repository_is_detected_from_l2_reader(self):
        detector = ContinuityStateDetector(FakeKnowledgeReader(known=True), MemoryStateStore())
        state = detector.detect(ContinuityObservation("continue", context(), session_id="s1", session_has_context=False))
        self.assertTrue(state.repository_known)
        self.assertFalse(state.session_reset)
        self.assertFalse(state.session_has_context)

    def test_session_id_change_marks_reset(self):
        store = MemoryStateStore(StoredContinuityState(session_id="old", head_sha="abc"))
        detector = ContinuityStateDetector(FakeKnowledgeReader(known=True), store)
        state = detector.detect(ContinuityObservation("continue", context(), session_id="new"))
        self.assertTrue(state.session_reset)

    def test_same_session_does_not_mark_reset(self):
        store = MemoryStateStore(StoredContinuityState(session_id="same", head_sha="abc"))
        detector = ContinuityStateDetector(FakeKnowledgeReader(known=True), store)
        state = detector.detect(ContinuityObservation("continue", context(), session_id="same"))
        self.assertFalse(state.session_reset)

    def test_head_change_marks_stale_checkpoint(self):
        store = MemoryStateStore(StoredContinuityState(session_id="same", head_sha="old"))
        detector = ContinuityStateDetector(FakeKnowledgeReader(known=True), store)
        state = detector.detect(ContinuityObservation("continue", context(head="new"), session_id="same"))
        self.assertTrue(state.stale_head)

    def test_current_observation_is_saved_for_next_detection(self):
        store = MemoryStateStore()
        detector = ContinuityStateDetector(FakeKnowledgeReader(known=True), store)
        detector.detect(ContinuityObservation("continue", context(head="new"), session_id="s1"))
        self.assertEqual(store.value, StoredContinuityState(session_id="s1", head_sha="new"))


if __name__ == "__main__":
    unittest.main()
