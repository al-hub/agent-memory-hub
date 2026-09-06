import unittest

from agent_memory_hub.application.continuity_context import ContinuityContextService
from agent_memory_hub.domain.context import ExecutionContext, RepositoryIdentity
from agent_memory_hub.domain.continuity import ContinuityDecision, ContinuityMode, ContinuityRequest
from agent_memory_hub.domain.projection import ContextPack
from agent_memory_hub.domain.recall import MemoryCandidate


class FakeGate:
    def __init__(self, decision):
        self.decision = decision
        self.calls = 0

    def decide(self, request):
        self.calls += 1
        return self.decision


class FakeReader:
    def __init__(self, memories=()):
        self.memories = list(memories)
        self.calls = []

    def recall(self, query):
        self.calls.append(query)
        return list(self.memories)


class FakeProjector:
    def __init__(self, pack):
        self.pack = pack
        self.calls = []

    def project(self, candidates, *, mode, token_budget=1000, policy=None):
        self.calls.append((tuple(candidates), mode, token_budget))
        return self.pack


def memory(mid="m1"):
    return MemoryCandidate(
        id=mid,
        statement="Current task state",
        memory_type="project_state",
        lifecycle="active",
        review_state="verified",
        confidence=.95,
        scope="repository",
        scope_ref="github.com/al-hub/demo",
        lexical_rank=0.1,
        scope_rank=0,
    )


class ContinuityContextServiceTest(unittest.TestCase):
    def setUp(self):
        repo = RepositoryIdentity(
            canonical_id="github.com/al-hub/demo",
            root="/tmp/demo",
            common_dir="/tmp/demo/.git",
        )
        self.request = ContinuityRequest(
            message="이어서 구현해줘",
            context=ExecutionContext(repository=repo, branch="main"),
            repository_known=True,
        )

    def test_no_recall_skips_reader_and_projector(self):
        gate = FakeGate(ContinuityDecision(ContinuityMode.NO_RECALL, "stateless"))
        reader = FakeReader([memory()])
        projector = FakeProjector(ContextPack(ContinuityMode.RECALL, (), 0, 1000, False))
        service = ContinuityContextService(gate, reader, projector)

        result = service.handle(self.request)

        self.assertEqual(result.decision.mode, ContinuityMode.NO_RECALL)
        self.assertIsNone(result.pack)
        self.assertEqual(reader.calls, [])
        self.assertEqual(projector.calls, [])

    def test_resume_flows_gate_to_reader_to_projector(self):
        gate = FakeGate(ContinuityDecision(ContinuityMode.RESUME, "resume wording"))
        memories = [memory()]
        reader = FakeReader(memories)
        expected = ContextPack(ContinuityMode.RESUME, (), 0, 900, False)
        projector = FakeProjector(expected)
        service = ContinuityContextService(gate, reader, projector, token_budget=900)

        result = service.handle(self.request)

        self.assertEqual(result.pack, expected)
        self.assertEqual(len(reader.calls), 1)
        self.assertEqual(reader.calls[0].context, self.request.context)
        self.assertEqual(reader.calls[0].limit, 8)
        self.assertEqual(projector.calls, [(tuple(memories), ContinuityMode.RESUME, 900)])

    def test_onboarding_uses_larger_candidate_window_but_same_projection_budget(self):
        gate = FakeGate(ContinuityDecision(ContinuityMode.ONBOARDING, "known repo"))
        reader = FakeReader([memory()])
        expected = ContextPack(ContinuityMode.ONBOARDING, (), 0, 700, False)
        projector = FakeProjector(expected)
        service = ContinuityContextService(gate, reader, projector, token_budget=700)

        result = service.handle(self.request)

        self.assertEqual(result.pack, expected)
        self.assertEqual(reader.calls[0].limit, 12)
        self.assertEqual(projector.calls[0][2], 700)


if __name__ == "__main__":
    unittest.main()
