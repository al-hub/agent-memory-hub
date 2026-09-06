import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "continuity_baseline",
    ROOT / "benchmarks" / "continuity_baseline.py",
)
BENCH = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BENCH)


class ContinuityBaselineHarnessTest(unittest.TestCase):
    def test_percentile_uses_linear_interpolation(self):
        values = [1.0, 2.0, 3.0, 4.0]
        self.assertEqual(BENCH.percentile(values, 0.50), 2.5)
        self.assertAlmostEqual(BENCH.percentile(values, 0.95), 3.85)

    def test_parse_sizes_rejects_empty_or_non_positive_tiers(self):
        self.assertEqual(BENCH.parse_sizes("1000, 10000"), [1000, 10000])
        with self.assertRaises(ValueError):
            BENCH.parse_sizes("")
        with self.assertRaises(ValueError):
            BENCH.parse_sizes("0,100")

    def test_small_real_pipeline_benchmark_returns_expected_scenarios(self):
        result = BENCH.benchmark_tier(
            100,
            warmup=0,
            iterations=1,
            subprocess_iterations=1,
        )
        self.assertEqual(result["memory_count"], 100)
        self.assertGreater(result["db_bytes"], 0)
        scenarios = result["scenarios"]
        expected = {
            "no_recall",
            "resume_prompt",
            "handoff_prompt",
            "session_start_onboarding",
            "session_start_resume",
            "stale_head_resume",
            "hook_codex_resume",
            "hook_claude_clear",
            "hook_gemini_startup",
        }
        self.assertEqual(set(scenarios), expected)
        self.assertEqual(scenarios["no_recall"]["mode"], "no_recall")
        self.assertEqual(scenarios["resume_prompt"]["mode"], "resume")
        self.assertEqual(scenarios["handoff_prompt"]["mode"], "handoff")
        self.assertEqual(scenarios["session_start_onboarding"]["mode"], "onboarding")
        self.assertEqual(scenarios["session_start_resume"]["mode"], "resume")
        self.assertTrue(scenarios["stale_head_resume"]["stale_head"])


if __name__ == "__main__":
    unittest.main()
