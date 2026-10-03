from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ENTRY_POINT = REPOSITORY_ROOT / "agent.py"


class CliTests(unittest.TestCase):
    def test_help_displays_required_arguments(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ENTRY_POINT), "--help"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--input", result.stdout)
        self.assertIn("--output", result.stdout)
        self.assertIn("--model", result.stdout)

    def test_invalid_case_fails_cleanly_and_is_traced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_path = root / "case.json"
            output_path = root / "out"
            case_path.write_text(
                json.dumps(
                    {"source_url": "paper.pdf", "focus": "Equation 6", "audience": ""}
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ENTRY_POINT),
                    "--input",
                    str(case_path),
                    "--output",
                    str(output_path),
                    "--model",
                    "provider/model-id",
                ],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("INPUT_SCHEMA_INVALID", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            trace_path = output_path / "trace.jsonl"
            self.assertTrue(trace_path.is_file())
            event = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(event["details"]["code"], "INPUT_SCHEMA_INVALID")
            self.assertFalse((output_path / "index.html").exists())

    def test_valid_case_stops_without_claiming_generation_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_path = root / "case.json"
            output_path = root / "out"
            case_path.write_text(
                json.dumps(
                    {
                        "source_url": "./paper.pdf",
                        "focus": "Equation 6",
                        "audience": "Undergraduate",
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ENTRY_POINT),
                    "--input",
                    str(case_path),
                    "--output",
                    str(output_path),
                    "--model",
                    "provider/model-id",
                ],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SOURCE_ACQUISITION_FAILED", result.stderr)
            self.assertFalse((output_path / "index.html").exists())
            event = json.loads((output_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(event["details"]["code"], "SOURCE_ACQUISITION_FAILED")


if __name__ == "__main__":
    unittest.main()
