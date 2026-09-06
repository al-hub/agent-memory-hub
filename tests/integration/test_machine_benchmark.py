import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "benchmarks" / "machine_benchmark.py"


class MachineBenchmarkIntegrationTest(unittest.TestCase):
    def test_small_machine_report_contains_environment_process_cold_and_startup_breakdown(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "report.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--sizes", "50",
                    "--warmup", "0",
                    "--iterations", "1",
                    "--subprocess-iterations", "1",
                    "--output", str(output),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["benchmark"], "agent-memory-hub-practical-machine-v2")
            self.assertIn("wsl", report["environment"])
            self.assertIn("filesystem", report["environment"])
            self.assertIn("startup_breakdown", report)
            startup = report["startup_breakdown"]
            self.assertIn("python_empty", startup["fresh_process_wall"])
            self.assertIn("import_hook_command", startup["fresh_process_wall"])
            self.assertIn("build_continuity_after_import", startup["internal_after_import"])
            self.assertEqual(len(report["tiers"]), 1)
            tier = report["tiers"][0]
            self.assertEqual(tier["memory_count"], 50)
            self.assertIn("resume_prompt", tier["scenarios"])
            self.assertIn("process_cold", tier)
            self.assertIn("resume_prompt", tier["process_cold"])
            self.assertIn("p50_ms", tier["process_cold"]["resume_prompt"])
            self.assertIn("Startup/process breakdown", result.stdout)
            self.assertIn("JSON:", result.stdout)


if __name__ == "__main__":
    unittest.main()
