"""Executable regression checks for architecture and credential boundaries."""
import ast
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
OWNED = (ROOT / "playground" / "model", ROOT / "playground" / "ir", ROOT / "playground" / "computation")
FORBIDDEN_IMPORTS = {"torch", "transformers", "sentence_transformers", "langchain", "llama_index", "openai"}


class SecurityTests(unittest.TestCase):
    def test_no_dynamic_execution_or_forbidden_models(self):
        for directory in OWNED:
            for path in directory.glob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        self.assertNotIn(node.func.id, {"eval", "exec", "compile", "__import__"}, path.name)
                    if isinstance(node, ast.Import):
                        self.assertFalse(any(alias.name.split(".")[0] in FORBIDDEN_IMPORTS for alias in node.names), path.name)
                    if isinstance(node, ast.ImportFrom):
                        self.assertNotIn((node.module or "").split(".")[0], FORBIDDEN_IMPORTS, path.name)
                self.assertNotIn("/embeddings", path.read_text(encoding="utf-8"))

    def test_transport_is_centralized(self):
        for directory in OWNED:
            for path in directory.glob("*.py"):
                if path.name != "client.py":
                    self.assertNotIn("urllib", path.read_text(encoding="utf-8"))
                    self.assertNotIn("openrouter.ai/api", path.read_text(encoding="utf-8"))

    def test_actual_environment_key_absent_from_repository_sources(self):
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            return  # No real key was supplied; synthetic credential leakage tested separately.
        for directory in OWNED + (ROOT / "tests",):
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix in {".py", ".json", ".md", ".jsonl"}:
                    self.assertNotIn(key, path.read_text(encoding="utf-8"), "Credential found in source artifact")
