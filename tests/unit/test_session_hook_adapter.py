import json
import unittest

from agent_memory_hub.cli.session_hook import AgentKind, SessionHookAdapter


class SessionHookAdapterTest(unittest.TestCase):
    def test_codex_session_start_normalizes_session_identity_and_resume_source(self):
        adapter = SessionHookAdapter(AgentKind.CODEX)
        invocation = adapter.parse({
            "hook_event_name": "SessionStart",
            "session_id": "codex-123",
            "cwd": "/tmp/repo",
            "source": "resume",
            "transcript_path": "/tmp/transcript.jsonl",
        })
        self.assertEqual(invocation.session_id, "codex-123")
        self.assertEqual(invocation.cwd, "/tmp/repo")
        self.assertEqual(invocation.session_source, "resume")
        self.assertTrue(invocation.session_has_context)

    def test_claude_clear_is_treated_as_empty_session(self):
        adapter = SessionHookAdapter(AgentKind.CLAUDE)
        invocation = adapter.parse({
            "hook_event_name": "SessionStart",
            "session_id": "claude-123",
            "cwd": "/tmp/repo",
            "source": "clear",
            "transcript_path": "/tmp/claude.jsonl",
        })
        self.assertFalse(invocation.session_has_context)
        self.assertEqual(invocation.session_source, "clear")

    def test_gemini_startup_is_empty_session_for_onboarding(self):
        adapter = SessionHookAdapter(AgentKind.GEMINI)
        invocation = adapter.parse({
            "hook_event_name": "SessionStart",
            "session_id": "gemini-123",
            "cwd": "/tmp/repo",
            "source": "startup",
            "transcript_path": "/tmp/gemini.json",
        })
        self.assertFalse(invocation.session_has_context)

    def test_compact_keeps_session_context_but_requests_resume_refresh(self):
        adapter = SessionHookAdapter(AgentKind.CODEX)
        invocation = adapter.parse({
            "hook_event_name": "SessionStart",
            "session_id": "codex-123",
            "cwd": "/tmp/repo",
            "source": "compact",
        })
        self.assertTrue(invocation.session_has_context)
        self.assertEqual(invocation.session_source, "compact")

    def test_invalid_event_is_rejected(self):
        adapter = SessionHookAdapter(AgentKind.CLAUDE)
        with self.assertRaises(ValueError):
            adapter.parse({
                "hook_event_name": "PostToolUse",
                "session_id": "s1",
                "cwd": "/tmp/repo",
            })

    def test_missing_required_identity_is_rejected(self):
        adapter = SessionHookAdapter(AgentKind.GEMINI)
        with self.assertRaises(ValueError):
            adapter.parse({"hook_event_name": "SessionStart", "cwd": "/tmp/repo", "source": "startup"})

    def test_hook_output_is_valid_session_start_context_json(self):
        adapter = SessionHookAdapter(AgentKind.CODEX)
        rendered = adapter.render_output("- [decision] Use FTS5 first")
        payload = json.loads(rendered)
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertEqual(payload["hookSpecificOutput"]["additionalContext"], "- [decision] Use FTS5 first")

    def test_empty_context_omits_additional_context(self):
        adapter = SessionHookAdapter(AgentKind.CLAUDE)
        payload = json.loads(adapter.render_output(""))
        self.assertEqual(payload, {"hookSpecificOutput": {"hookEventName": "SessionStart"}})


if __name__ == "__main__":
    unittest.main()
