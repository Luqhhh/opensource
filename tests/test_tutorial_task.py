"""Synthetic task-contract guards; the separately archived TinyDB case is real input."""

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from exampleproof.cli import main
from exampleproof.tutorial_task import extract_task_blocks, review_task_edit, validate_tutorial_task


class TutorialTaskTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "project"
        root.mkdir()
        text = "Task\n====\n\n.. code-block:: python\n\n    >>> from pathlib import Path\n    >>> Path('/missing-directory/result.txt').write_text('stored')\n"
        raw = text.encode()
        (root / "README.rst").write_bytes(raw)
        contract = {"schema_version": "tutorial-task-1", "task": "Write a local file", "document": "README.rst", "block": 1,
                    "source_files": [], "checks": "assert Path('result.txt').read_text() == 'stored'\n",
                    "checks_author": "synthetic evaluator fixture"}
        candidate = {"schema_version": "tutorial-task-edit-1", "document_sha256": hashlib.sha256(raw).hexdigest(),
                     "origin": "assistant_authored_candidate", "rationale": "Use a relative file",
                     "original": "'/missing-directory/result.txt'", "replacement": "'result.txt'"}
        return root, raw, contract, candidate

    def test_rst_pycon_outputs_and_continuations_are_preserved(self):
        text = ".. code-block:: python\n\n    >>> values = [\n    ...     1, 2]\n    >>> values\n    [1, 2]\n\nNext\n====\n"
        code, outputs = extract_task_blocks(text, "README.rst")[0]
        self.assertIn("values = [\n    1, 2]", code)
        self.assertEqual(outputs, ("[1, 2]\n",))
        self.assertEqual(extract_task_blocks("```python\nassert 1 == 1\n```\n", "README.md")[0][0], "assert 1 == 1\n")

    def test_exact_hash_and_unique_match_are_required(self):
        root, raw, contract, candidate = self.fixture()
        for changed in (candidate | {"document_sha256": "wrong"}, candidate | {"original": "not in source"}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                review_task_edit(raw, "README.rst", contract, changed)

    def test_candidate_cannot_change_the_frozen_oracle_or_expected_outputs(self):
        root, raw, contract, candidate = self.fixture()
        with self.assertRaisesRegex(ValueError, "Invalid task edit"):
            review_task_edit(raw, "README.rst", contract, candidate | {"checks": "assert True"})
        raw = b".. code-block:: python\n\n    >>> 2 + 2\n    4\n"
        candidate.update(document_sha256=hashlib.sha256(raw).hexdigest(), original="    4\n", replacement="    5\n")
        with self.assertRaisesRegex(ValueError, "expected outputs"):
            review_task_edit(raw, "README.rst", contract, candidate)

    def test_assertion_removal_other_blocks_and_new_directives_are_rejected(self):
        root, raw, contract, candidate = self.fixture()
        variants = [
            (b".. code-block:: python\n\n    >>> assert 2 + 2 == 4\n", "assert 2 + 2 == 4", "pass"),
            (raw + b"\n.. code-block:: python\n\n    >>> print('protected')\n", "print('protected')", "print('changed')"),
            (raw, "Task\n====\n", "Task\n====\n\n.. include:: private.rst\n")]
        for document, original, replacement in variants:
            changed = candidate | {"document_sha256": hashlib.sha256(document).hexdigest(), "original": original, "replacement": replacement}
            with self.subTest(original=original), self.assertRaises(ValueError):
                review_task_edit(document, "README.rst", contract, changed)

    def test_valid_edit_keeps_original_and_exports_rst_patch(self):
        root, raw, contract, candidate = self.fixture()
        old, new, updated, patch_text = review_task_edit(raw, "README.rst", contract, candidate)
        self.assertIn("/missing-directory/", old)
        self.assertNotIn("/missing-directory/", new)
        self.assertEqual((root / "README.rst").read_bytes(), raw)
        self.assertIn("--- a/README.rst", patch_text)
        self.assertIn("'result.txt'", updated.decode())

    def test_no_oracle_or_traversal_is_rejected_before_execution(self):
        root, raw, contract, candidate = self.fixture()
        base = root.parent
        candidate_path = base / "candidate.json"
        candidate_path.write_text(json.dumps(candidate))
        for changed in (contract | {"checks": ""}, contract | {"document": "../README.rst"}):
            contract_path = base / "contract.json"
            contract_path.write_text(json.dumps(changed))
            with patch("exampleproof.tutorial_task.SandboxRunner") as runner, self.assertRaises(ValueError):
                validate_tutorial_task(root, contract_path, candidate_path, base / "output")
            runner.assert_not_called()


@unittest.skipUnless(os.environ.get("EXAMPLEPROOF_SANDBOX_TESTS") == "1", "Requires actual Bubblewrap execution")
class TutorialTaskSandboxTests(unittest.TestCase):
    fixture = TutorialTaskTests.fixture

    def write_inputs(self, root, contract, candidate):
        contract_path, candidate_path = root.parent / "contract.json", root.parent / "candidate.json"
        contract_path.write_text(json.dumps(contract))
        candidate_path.write_text(json.dumps(candidate))
        return contract_path, candidate_path

    def test_cli_validates_before_after_and_applied_patch_with_same_checks(self):
        root, raw, contract, candidate = self.fixture()
        contract_path, candidate_path = self.write_inputs(root, contract, candidate)
        output = root.parent / "validation"
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(["task-check", str(root), "--contract", str(contract_path), "--candidate", str(candidate_path), "--output", str(output)])
        self.assertEqual(code, 0)
        report = json.loads((output / "task-report.json").read_text())
        self.assertEqual(report["before"]["status"], "failed")
        self.assertEqual(report["after"]["status"], "passed")
        self.assertEqual(report["replay"]["status"], "passed")
        self.assertEqual((output / "contract.json").read_bytes(), contract_path.read_bytes())
        self.assertEqual((root / "README.rst").read_bytes(), raw)
        self.assertTrue((output / "adoptable.patch").is_file())
        self.assertFalse(report["independent_human_review"])
        self.assertEqual(report["model_requests"], 0)

    def test_running_candidate_that_misses_task_does_not_get_adoptable_patch(self):
        root, raw, contract, candidate = self.fixture()
        candidate["replacement"] = "'other.txt'"
        contract_path, candidate_path = self.write_inputs(root, contract, candidate)
        output = root.parent / "negative"
        report = validate_tutorial_task(root, contract_path, candidate_path, output)
        self.assertEqual(report["after"]["failure_kind"], "behavior_check")
        self.assertEqual(report["status"], "task_validation_failed")
        self.assertFalse((output / "adoptable.patch").exists())

    def test_already_passing_task_is_not_counted_as_a_successful_improvement(self):
        root, raw, contract, candidate = self.fixture()
        raw = raw.replace(b"'/missing-directory/result.txt'", b"'result.txt'")
        (root / "README.rst").write_bytes(raw)
        candidate.update(document_sha256=hashlib.sha256(raw).hexdigest(), original="'result.txt'", replacement="'./result.txt'")
        contract_path, candidate_path = self.write_inputs(root, contract, candidate)
        output = root.parent / "already-passed"
        report = validate_tutorial_task(root, contract_path, candidate_path, output)
        self.assertEqual(report["before"]["status"], "passed")
        self.assertEqual(report["after"]["status"], "passed")
        self.assertEqual(report["status"], "task_validation_failed")
        self.assertFalse((output / "adoptable.patch").exists())
