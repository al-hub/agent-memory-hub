import unittest

from memcarry.application.context_projector import ContextProjector
from memcarry.domain.continuity import ContinuityMode
from memcarry.domain.recall import MemoryCandidate


def mem(mid, statement, memory_type, *, scope_rank=3):
    return MemoryCandidate(
        id=mid,
        statement=statement,
        memory_type=memory_type,
        lifecycle="active",
        review_state="verified",
        confidence=.95,
        scope="repository",
        scope_ref="github.com/al-hub/demo",
        lexical_rank=-1.0,
        scope_rank=scope_rank,
    )


class StaleHeadProjectionTest(unittest.TestCase):
    def test_stale_head_demotes_volatile_project_state_below_stable_decision(self):
        candidates = [
            mem("state", "Next task is to edit the old parser", "project_state", scope_rank=0),
            mem("decision", "FTS5 remains the primary recall path", "decision", scope_rank=3),
        ]
        pack = ContextProjector().project(
            candidates,
            mode=ContinuityMode.RESUME,
            token_budget=500,
            stale_head=True,
        )
        self.assertEqual(pack.items[0].memory_id, "decision")

    def test_stale_head_marks_project_state_with_revalidation_warning(self):
        pack = ContextProjector().project(
            [mem("state", "Benchmark currently fails in allocator", "project_state")],
            mode=ContinuityMode.RESUME,
            token_budget=500,
            stale_head=True,
        )
        self.assertEqual(len(pack.items), 1)
        self.assertIsNotNone(pack.items[0].warning)
        self.assertIn("stale_head", pack.items[0].warning.lower())
        self.assertIn("revalidate", pack.items[0].warning.lower())

    def test_stable_memory_types_are_not_marked_stale(self):
        pack = ContextProjector().project(
            [mem("decision", "Use SQLite WAL for local writes", "decision")],
            mode=ContinuityMode.RESUME,
            token_budget=500,
            stale_head=True,
        )
        self.assertIsNone(pack.items[0].warning)

    def test_non_stale_projection_preserves_existing_resume_priority(self):
        candidates = [
            mem("state", "Next task is Context Projector", "project_state", scope_rank=3),
            mem("decision", "Use FTS5 before semantic fallback", "decision", scope_rank=3),
        ]
        pack = ContextProjector().project(
            candidates,
            mode=ContinuityMode.RESUME,
            token_budget=500,
            stale_head=False,
        )
        self.assertEqual(pack.items[0].memory_id, "state")


if __name__ == "__main__":
    unittest.main()
