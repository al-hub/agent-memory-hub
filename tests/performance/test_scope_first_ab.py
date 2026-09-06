import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "scope_first_ab",
    ROOT / "benchmarks" / "scope_first_ab.py",
)
AB = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(AB)


class ScopeFirstABBenchmarkTest(unittest.TestCase):
    def test_small_ab_run_preserves_results_and_reports_speedup(self):
        result = AB.benchmark_tier(100, warmup=0, iterations=1)
        self.assertEqual(result["memory_count"], 100)
        self.assertGreater(result["db_bytes_before_scoped_fts"], 0)
        self.assertGreaterEqual(
            result["db_bytes_after_scoped_fts"],
            result["db_bytes_before_scoped_fts"],
        )
        self.assertTrue(result["same_result_ids"])
        self.assertEqual(
            result["broad"]["result_ids"],
            result["scope_first"]["result_ids"],
        )
        self.assertGreater(result["broad"]["p50_ms"], 0)
        self.assertGreater(result["scope_first"]["p50_ms"], 0)
        self.assertGreater(result["p50_speedup"], 0)
        self.assertGreaterEqual(result["scoped_fts_build_ms"], 0)

    def test_parse_sizes_matches_baseline_rules(self):
        self.assertEqual(AB.parse_sizes("1000,10000"), [1000, 10000])
        with self.assertRaises(ValueError):
            AB.parse_sizes("0")


if __name__ == "__main__":
    unittest.main()
