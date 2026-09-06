import unittest

from memcarry.application.seamless_continuity import SeamlessContinuityService
from memcarry.domain.context import ExecutionContext, RepositoryIdentity
from memcarry.domain.continuity import ContinuityDecision, ContinuityMode
from memcarry.domain.continuity_state import ContinuityObservation, ContinuityState


class FakeDetector:
    def __init__(self, state):
        self.state = state
        self.calls = []

    def detect(self, observation):
        self.calls.append(observation)
        return self.state


class FakeContextService:
    def __init__(self):
        self.calls = []

    def handle(self, request):
        self.calls.append(request)
        return type("Result", (), {"decision": ContinuityDecision(ContinuityMode.RESUME, "test"), "pack": None})()


def context():
    repo = RepositoryIdentity(
        canonical_id="github.com/al-hub/demo",
        root="/tmp/demo",
        common_dir="/tmp/demo/.git",
        remote="git@github.com:al-hub/demo.git",
    )
    return ExecutionContext(repository=repo, worktree_id="wt:1", branch="main", head_sha="abc")


class SeamlessContinuityServiceTest(unittest.TestCase):
    def test_detected_state_is_converted_into_gate_request(self):
        state = ContinuityState(repository_known=True, session_reset=True, session_has_context=False, stale_head=True)
        detector = FakeDetector(state)
        context_service = FakeContextService()
        service = SeamlessContinuityService(detector, context_service)
        observation = ContinuityObservation("이어서 해", context(), session_id="s2", session_has_context=False)

        result = service.handle(observation)

        self.assertIs(result.state, state)
        request = context_service.calls[0]
        self.assertTrue(request.repository_known)
        self.assertTrue(request.session_reset)
        self.assertFalse(request.session_has_context)
        self.assertEqual(request.message, "이어서 해")
        self.assertIs(request.context, observation.context)


if __name__ == "__main__":
    unittest.main()
