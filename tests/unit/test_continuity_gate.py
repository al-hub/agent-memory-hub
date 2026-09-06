import unittest

from agent_memory_hub.continuity.gate import ContinuityGate
from agent_memory_hub.domain.context import ExecutionContext, RepositoryIdentity
from agent_memory_hub.domain.continuity import ContinuityMode, ContinuityRequest


class ContinuityGateTest(unittest.TestCase):
    def setUp(self):
        repo = RepositoryIdentity(
            canonical_id="github.com/al-hub/demo",
            root="/tmp/demo",
            common_dir="/tmp/demo/.git",
            remote="git@github.com:al-hub/demo.git",
        )
        self.context = ExecutionContext(repository=repo, worktree_id="wt:abc", branch="main")
        self.gate = ContinuityGate()

    def test_plain_stateless_request_does_not_recall(self):
        decision = self.gate.decide(ContinuityRequest("README 오타 하나 고쳐줘", self.context))
        self.assertEqual(decision.mode, ContinuityMode.NO_RECALL)

    def test_continue_phrase_triggers_resume(self):
        decision = self.gate.decide(ContinuityRequest("전에 하던 성능 최적화 이어서 해줘", self.context))
        self.assertEqual(decision.mode, ContinuityMode.RESUME)

    def test_cross_agent_phrase_triggers_handoff(self):
        decision = self.gate.decide(ContinuityRequest("Claude가 하던 작업을 Codex에서 이어서 해", self.context))
        self.assertEqual(decision.mode, ContinuityMode.HANDOFF)

    def test_known_repository_with_empty_session_triggers_onboarding(self):
        decision = self.gate.decide(ContinuityRequest(
            "테스트부터 시작해줘",
            self.context,
            repository_known=True,
            session_has_context=False,
        ))
        self.assertEqual(decision.mode, ContinuityMode.ONBOARDING)

    def test_session_reset_in_known_repo_triggers_resume(self):
        decision = self.gate.decide(ContinuityRequest(
            "계속 진행하자",
            self.context,
            repository_known=True,
            session_has_context=False,
            session_reset=True,
        ))
        self.assertEqual(decision.mode, ContinuityMode.RESUME)

    def test_explicit_past_decision_question_triggers_recall(self):
        decision = self.gate.decide(ContinuityRequest("전에 SQLite로 결정했던 이유가 뭐였지?", self.context))
        self.assertEqual(decision.mode, ContinuityMode.RECALL)

    def test_no_repository_does_not_auto_onboard(self):
        decision = self.gate.decide(ContinuityRequest(
            "이거 설명해줘",
            ExecutionContext(),
            repository_known=True,
            session_has_context=False,
        ))
        self.assertEqual(decision.mode, ContinuityMode.NO_RECALL)

    def test_handoff_has_priority_over_resume_wording(self):
        decision = self.gate.decide(ContinuityRequest(
            "Claude에서 하던 걸 여기서 이어서 해줘",
            self.context,
            session_reset=True,
        ))
        self.assertEqual(decision.mode, ContinuityMode.HANDOFF)


if __name__ == "__main__":
    unittest.main()
