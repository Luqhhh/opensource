import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from exampleproof.cli import main
from exampleproof.config import load_config
from exampleproof.extract import extract_markdown
from exampleproof.models import Execution, Proposal
from exampleproof.pipeline import run_project


class StrictConfigTests(unittest.TestCase):
    def test_unknown_fields_fail_before_execution(self):
        configurations = (
            ({"source_file": []}, "source_file"),
            ({"timeout_second": 5}, "timeout_second"),
            ({"examples": {"README.md#1": {"check": "assert False"}}}, "check"),
            ({"examples": {"README.md#1": {"expected_output": "wrong"}}}, "expected_output"),
        )
        for config, unknown in configurations:
            with self.subTest(config=config), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "README.md").write_text("```python\nassert True\n```\n", encoding="utf-8")
                (root / "exampleproof.json").write_text(json.dumps(config), encoding="utf-8")
                error = io.StringIO()
                with contextlib.redirect_stderr(error), patch("exampleproof.cli.run_project") as run:
                    code = main(["check", str(root), "--output", str(root / "output")])
                self.assertEqual(code, 2)
                self.assertIn(unknown, error.getvalue())
                run.assert_not_called()
                self.assertFalse((root / "output").exists())

    def test_supported_fields_keep_their_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("```python\nprint(value)\n```\n", encoding="utf-8")
            config = {
                "documents": ["README.md"], "source_files": [], "timeout_seconds": 2,
                "examples": {"README.md#1": {
                    "skip": "", "setup": "value = 3", "checks": "assert value == 3",
                    "expected_stdout": "3\n",
                }},
            }
            (root / "exampleproof.json").write_text(json.dumps(config), encoding="utf-8")
            self.assertEqual(load_config(root), config)


class BomExtractionTests(unittest.TestCase):
    def test_initial_bom_preserves_block_ids_and_line_numbers(self):
        document = "\ufeff```python\nprint(1)\n```\n\n~~~python\nprint(2)\n~~~\n"
        examples = extract_markdown(document, "README.md")
        self.assertEqual([example.id for example in examples], ["README.md#1", "README.md#2"])
        self.assertEqual([(example.start_line, example.end_line) for example in examples], [(2, 2), (6, 6)])
        self.assertEqual([example.code for example in examples], ["print(1)\n", "print(2)\n"])

    def test_bom_inside_code_is_preserved(self):
        document = '\ufeff```python\nvalue = "\ufeff"\n```\n'
        self.assertEqual(extract_markdown(document, "README.md")[0].code, 'value = "\ufeff"\n')

    @unittest.skipUnless(shutil.which("git"), "Git is required to verify exported patches")
    def test_bom_patch_round_trip_preserves_bytes_and_widens_fence(self):
        class Runner:
            backend = "test_double"

            def __init__(self):
                self.executions = iter((Execution("failed", oracle="original_top_level_assertions"),
                                        Execution("passed")))

            def run(self, code, spec):
                return next(self.executions)

        class Provider:
            def propose(self, example, before, sources):
                return Proposal('value = """\n```\n"""\nassert True\n', "Synthetic fixture", "test_double")

        for indent in ("", "   "):
            for newline in ("\n", "\r\n"):
                with self.subTest(indent=indent, newline=repr(newline)), tempfile.TemporaryDirectory() as directory:
                    base = Path(directory)
                    original = base / "original"
                    original.mkdir()
                    text = ("\ufeff" + indent + "```python\n" + indent + "old()\n"
                            + indent + "assert True\n" + indent + "```").replace("\n", newline)
                    raw = text.encode("utf-8")
                    document = original / "README.md"
                    document.write_bytes(raw)
                    report, diff = run_project(original, Provider(), Runner())
                    self.assertEqual(report["summary"]["counts"], {"verified_repair": 1})
                    self.assertEqual(report["provenance"]["documents"]["README.md"], hashlib.sha256(raw).hexdigest())
                    self.assertEqual(document.read_bytes(), raw)

                    review = base / "review"
                    shutil.copytree(original, review)
                    for command in (["git", "apply", "--check"], ["git", "apply", "--whitespace=nowarn"]):
                        completed = subprocess.run(command, cwd=review, input=diff.encode("utf-8"),
                                                   capture_output=True, check=False)
                        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
                    repaired = (review / "README.md").read_bytes().decode("utf-8")
                    self.assertTrue(repaired.startswith("\ufeff" + indent + "````python"))
                    self.assertFalse(repaired.endswith("\n"))
                    expected = 'value = """\n```\n"""\nassert True\n'.replace("\n", newline)
                    self.assertEqual(extract_markdown(repaired, "README.md")[0].code, expected)
                    self.assertEqual(document.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
