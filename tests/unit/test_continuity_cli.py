import json
import unittest

from memcarry.cli.continuity import ContinuityCommand
from memcarry.domain.context import ExecutionContext, RepositoryIdentity
from memcarry.domain.continuity import ContinuityDecision, ContinuityMode
from memcarry.domain.continuity_state import ContinuityState
from memcarry.domain.projection import ContextItem, ContextPack
from memcarry.application.continuity_context import ContinuityContextResult
from memcarry.application.seamless_continuity import SeamlessContinuityResult


class FakeInspector:
    def __init__(self, context):
        self.context = context
        self.calls = []

    def inspect(self, cwd):
        self.calls.append(cwd)
        return self.context


class FakeService:
    def __init__(self, result):
        self.result = result
        self.observations = []

    def handle(self, observation):
        self.observations.append(observation)
        return self.result


def repo_context():
    repo = RepositoryIdentity(
        canonical_id="github.com/al-hub/demo",
        root="/tmp/demo",
        common_dir="/tmp/demo/.git",
    )
    return ExecutionContext(
        repository=repo,
        worktree_id="wt:abc",
        branch="main",
        head_sha="deadbeef",
    )


def result(mode=ContinuityMode.RESUME, with_pack=True):
    pack = None
    if with_pack:
        pack = ContextPack(
            mode=mode,
            items=(ContextItem(
                memory_id="m1",
                statement="Use FTS5 before semantic fallback",
                memory_type="decision",
                scope="repository",
                review_state="verified",
                confidence=.95,
            ),),
            estimated_tokens=24,
            token_budget=800,
            truncated=False,
        )
    return SeamlessContinuityResult(
        state=ContinuityState(
            repository_known=True,
            session_reset=True,
            session_has_context=False,
            stale_head=False,
        ),
        context=ContinuityContextResult(
            decision=ContinuityDecision(mode, "test"),
            pack=pack,
        ),
    )


class ContinuityCommandTest(unittest.TestCase):
    def test_builds_observation_from_current_cwd_and_session_metadata(self):
        inspector = FakeInspector(repo_context())
        service = FakeService(result())
        command = ContinuityCommand(inspector, service)

        rendered = command.run(
            message="이어서 구현해줘",
            cwd="/tmp/demo/subdir",
            session_id="session-2",
            session_has_context=False,
            token_budget=800,
            json_output=False,
        )

        self.assertEqual(inspector.calls, ["/tmp/demo/subdir"])
        observation = service.observations[0]
        self.assertEqual(observation.message, "이어서 구현해줘")
        self.assertEqual(observation.context.repository.canonical_id, "github.com/al-hub/demo")
        self.assertEqual(observation.session_id, "session-2")
        self.assertFalse(observation.session_has_context)
        self.assertIn("mode: resume", rendered.lower())
        self.assertIn("Use FTS5 before semantic fallback", rendered)

    def test_no_recall_renders_compact_no_context_result(self):
        command = ContinuityCommand(
            FakeInspector(repo_context()),
            FakeService(result(ContinuityMode.NO_RECALL, with_pack=False)),
        )
        rendered = command.run(
            message="rename this local variable",
            cwd="/tmp/demo",
            session_id=None,
            session_has_context=True,
            token_budget=800,
            json_output=False,
        )
        self.assertIn("mode: no_recall", rendered.lower())
        self.assertNotIn("memory_id", rendered)

    def test_json_output_is_machine_readable_and_includes_state_and_pack(self):
        command = ContinuityCommand(FakeInspector(repo_context()), FakeService(result()))
        rendered = command.run(
            message="continue",
            cwd="/tmp/demo",
            session_id="s2",
            session_has_context=False,
            token_budget=800,
            json_output=True,
        )
        payload = json.loads(rendered)
        self.assertEqual(payload["mode"], "resume")
        self.assertTrue(payload["state"]["repository_known"])
        self.assertEqual(payload["items"][0]["memory_id"], "m1")


if __name__ == "__main__":
    unittest.main()
