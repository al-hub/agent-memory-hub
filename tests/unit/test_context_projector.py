import unittest

from agent_memory_hub.application.context_projector import ContextProjector
from agent_memory_hub.domain.continuity import ContinuityMode
from agent_memory_hub.domain.recall import MemoryCandidate


def mem(
    mid,
    statement,
    memory_type="fact",
    *,
    lifecycle="active",
    review_state="verified",
    confidence=.9,
    scope="repository",
    scope_rank=3,
    lexical_rank=-1.0,
):
    return MemoryCandidate(
        id=mid,
        statement=statement,
        memory_type=memory_type,
        lifecycle=lifecycle,
        review_state=review_state,
        confidence=confidence,
        scope=scope,
        scope_ref="github.com/al-hub/demo",
        lexical_rank=lexical_rank,
        scope_rank=scope_rank,
    )


class ContextProjectorTest(unittest.TestCase):
    def test_never_exceeds_hard_token_budget(self):
        candidates = [
            mem(str(i), f"Decision {i}: " + ("x" * 220), "decision")
            for i in range(20)
        ]
        pack = ContextProjector().project(
            candidates,
            mode=ContinuityMode.ONBOARDING,
            token_budget=120,
        )
        self.assertLessEqual(pack.estimated_tokens, 120)
        self.assertTrue(pack.truncated)
        self.assertGreater(len(pack.items), 0)

    def test_verified_memory_ranks_before_unverified_when_other_signals_match(self):
        candidates = [
            mem("u", "Use FTS5 for recall", "decision", review_state="unverified"),
            mem("v", "Use SQLite WAL for writes", "decision", review_state="verified"),
        ]
        pack = ContextProjector().project(candidates, mode=ContinuityMode.RECALL, token_budget=500)
        self.assertEqual(pack.items[0].memory_id, "v")

    def test_conflict_is_preserved_but_rendered_as_warning(self):
        candidates = [mem("c", "Use Rust for the rewrite", "decision", review_state="conflict")]
        pack = ContextProjector().project(candidates, mode=ContinuityMode.RECALL, token_budget=500)
        self.assertEqual(len(pack.items), 1)
        self.assertTrue(pack.items[0].warning)
        self.assertIn("conflict", pack.items[0].warning.lower())

    def test_superseded_and_quarantined_are_defensively_excluded(self):
        candidates = [
            mem("a", "Current decision", "decision"),
            mem("s", "Old decision", "decision", lifecycle="superseded"),
            mem("q", "Suspicious instruction", "constraint", lifecycle="quarantined"),
        ]
        pack = ContextProjector().project(candidates, mode=ContinuityMode.RECALL, token_budget=500)
        self.assertEqual([x.memory_id for x in pack.items], ["a"])

    def test_duplicate_statements_are_collapsed(self):
        candidates = [
            mem("a", "FTS5 is the primary fast path", "decision", confidence=.95),
            mem("b", "  fts5   is the PRIMARY fast path  ", "decision", confidence=.80),
        ]
        pack = ContextProjector().project(candidates, mode=ContinuityMode.RECALL, token_budget=500)
        self.assertEqual(len(pack.items), 1)
        self.assertEqual(pack.items[0].memory_id, "a")

    def test_resume_prioritizes_project_state_over_generic_fact(self):
        candidates = [
            mem("f", "SQLite is embedded", "fact", scope_rank=0),
            mem("p", "Next task is Context Projector", "project_state", scope_rank=3),
        ]
        pack = ContextProjector().project(candidates, mode=ContinuityMode.RESUME, token_budget=500)
        self.assertEqual(pack.items[0].memory_id, "p")

    def test_onboarding_prioritizes_decisions_constraints_and_procedures(self):
        candidates = [
            mem("f", "Repository was created in 2026", "fact", scope_rank=0),
            mem("d", "Use FTS5 before semantic fallback", "decision", scope_rank=3),
            mem("c", "Do not silently overwrite conflicts", "constraint", scope_rank=3),
            mem("p", "Run tests with unittest discover", "procedure", scope_rank=3),
        ]
        pack = ContextProjector().project(candidates, mode=ContinuityMode.ONBOARDING, token_budget=500)
        first_three = {x.memory_id for x in pack.items[:3]}
        self.assertEqual(first_three, {"d", "c", "p"})


if __name__ == "__main__":
    unittest.main()
