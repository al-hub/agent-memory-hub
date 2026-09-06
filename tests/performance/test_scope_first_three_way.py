import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "scope_first_three_way",
    ROOT / "benchmarks" / "scope_first_three_way.py",
)
BENCH = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BENCH)


class ScopeFirstThreeWayHarnessTest(unittest.TestCase):
    def test_small_three_way_benchmark_preserves_ordered_results(self):
        result = BENCH.benchmark_tier(100, warmup=0, iterations=1)
        self.assertEqual(result["memory_count"], 100)
        self.assertTrue(result["same_result_ids"])

        broad = result["broad"]
        two = result["two_index_scope_first"]
        single = result["single_index_scope_first"]
        self.assertEqual(broad["result_ids"], two["result_ids"])
        self.assertEqual(broad["result_ids"], single["result_ids"])
        self.assertGreater(broad["db_bytes"], 0)
        self.assertGreater(two["db_bytes"], broad["db_bytes"])
        self.assertGreater(single["db_bytes"], 0)
        self.assertIn("p50_speedup_vs_broad", single)
        self.assertIn("extra_bytes_vs_broad", single)

    def test_parse_sizes_reuses_baseline_validation(self):
        self.assertEqual(BENCH.parse_sizes("1000, 10000"), [1000, 10000])
        with self.assertRaises(ValueError):
            BENCH.parse_sizes("0")


if __name__ == "__main__":
    unittest.main()
