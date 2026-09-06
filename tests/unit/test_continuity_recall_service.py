import unittest

from agent_memory_hub.application.continuity_recall import ContinuityRecallService
from agent_memory_hub.continuity.gate import ContinuityGate
from agent_memory_hub.domain.context import ExecutionContext, RepositoryIdentity
from agent_memory_hub.domain.continuity import ContinuityMode, ContinuityRequest
from agent_memory_hub.domain.recall import MemoryCandidate


class FakeMemoryReader:
    def __init__(self):
        self.calls = []

    def recall(self, query):
        self.calls.append(query)
        return [MemoryCandidate(
            id="m1",
            statement="FTS5 is the fast path",
            memory_type="decision",
            lifecycle="active",
            review_state="verified",
            confidence=.95,
            scope="repository",
            scope_ref="github.com/al-hub/demo",
            lexical_rank=-1.0,
            scope_rank=3,
        )]


class ContinuityRecallServiceTest(unittest.TestCase):
    def setUp(self):
        repo = RepositoryIdentity(
            canonical_id="github.com/al-hub/demo",
            root="/tmp/demo",
            common_dir="/tmp/demo/.git",
        )
        self.context = ExecutionContext(repository=repo, worktree_id="wt:abc", branch="main")
        self.reader = FakeMemoryReader()
        self.service = ContinuityRecallService(ContinuityGate(), self.reader)

    def test_no_recall_never_calls_memory_reader(self):
        result = self.service.handle(ContinuityRequest("README 오타 고쳐줘", self.context))
        self.assertEqual(result.decision.mode, ContinuityMode.NO_RECALL)
        self.assertEqual(result.memories, ())
        self.assertEqual(self.reader.calls, [])

    def test_resume_calls_reader_with_current_execution_context(self):
        result = self.service.handle(ContinuityRequest("이어서 구현해줘", self.context))
        self.assertEqual(result.decision.mode, ContinuityMode.RESUME)
        self.assertEqual(len(self.reader.calls), 1)
        self.assertEqual(self.reader.calls[0].context, self.context)
        self.assertEqual(result.memories[0].id, "m1")

    def test_onboarding_uses_bounded_candidate_limit(self):
        self.service.handle(ContinuityRequest(
            "테스트 시작해줘",
            self.context,
            repository_known=True,
            session_has_context=False,
        ))
        self.assertEqual(self.reader.calls[0].limit, 12)


if __name__ == "__main__":
    unittest.main()
