import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from exampleproof.runner import SandboxRunner


class RunnerIntegrityTests(unittest.TestCase):
    token = b"a" * 32

    def simulated_run(self, receipt=None, stdout=b"", stderr=b"", returncode=0, spec=None):
        """Simulate Bubblewrap I/O without executing a snippet on the host."""
        def start(command, **kwargs):
            if receipt is not None:
                receipt_path = Path(command[command.index("--bind") + 1])
                receipt_path.write_bytes(receipt)
            kwargs["stdout"].write(stdout)
            kwargs["stderr"].write(stderr)
            process = Mock(returncode=returncode)
            process.wait.return_value = returncode
            return process

        with patch("exampleproof.runner.shutil.which", return_value="/usr/bin/bwrap"), \
                patch("exampleproof.runner.os.urandom", return_value=self.token), \
                patch("exampleproof.runner.subprocess.Popen", side_effect=start):
            return SandboxRunner({}).run("assert True", spec or {})

    def test_zero_exit_requires_a_completion_receipt(self):
        result = self.simulated_run()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.status, "failed")
        self.assertIn("did not complete", result.stderr)

    def test_wrong_truncated_and_oversized_receipts_fail(self):
        for receipt in (b"b" * 32, self.token[:-1], self.token + b"extra"):
            with self.subTest(receipt=receipt):
                self.assertEqual(self.simulated_run(receipt=receipt).status, "failed")

    def test_receipt_is_separate_from_expected_stdout(self):
        result = self.simulated_run(receipt=self.token, stdout=b"42\n",
                                    spec={"expected_stdout": "42\n"})
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.stdout, "42\n")
        self.assertEqual(result.stderr, "")
        forged_output = self.simulated_run(stdout=self.token, stderr=self.token)
        self.assertEqual(forged_output.status, "failed")

    def test_receipt_does_not_override_failed_exit_or_wrong_output(self):
        failed_exit = self.simulated_run(receipt=self.token, returncode=1)
        self.assertEqual(failed_exit.status, "failed")
        wrong_output = self.simulated_run(receipt=self.token, stdout=b"42\n",
                                         spec={"expected_stdout": "43\n"})
        self.assertEqual(wrong_output.status, "failed")

    def test_sandbox_startup_failure_stays_blocked(self):
        result = self.simulated_run(stderr=b"bwrap: namespaces unavailable", returncode=1)
        self.assertEqual(result.status, "blocked")

    def test_source_paths_cannot_escape_temporary_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            outside = Path(temporary) / "untouched.py"
            outside.write_text("original", encoding="utf-8")
            for name in (str(outside), "../escape.py", "package/../../escape.py", "", "."):
                with self.subTest(name=name), patch("exampleproof.runner.subprocess.Popen") as start:
                    result = SandboxRunner({name: "replacement"}).run("pass", {})
                    self.assertEqual(result.status, "blocked")
                    self.assertIn("Source path", result.stderr)
                    start.assert_not_called()
            self.assertEqual(outside.read_text(encoding="utf-8"), "original")


@unittest.skipUnless(os.environ.get("EXAMPLEPROOF_SANDBOX_TESTS") == "1",
                     "Set EXAMPLEPROOF_SANDBOX_TESTS=1 to test actual Bubblewrap execution")
class SandboxIntegrityTests(unittest.TestCase):
    def test_low_level_zero_exit_cannot_bypass_original_assertions(self):
        for code in ("import os\nos._exit(0)\nassert False",
                     "from os import _exit as stop\nstop(0)\nassert False"):
            with self.subTest(code=code):
                result = SandboxRunner({}).run(code, {})
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.status, "failed", result.stderr)
                self.assertEqual(result.oracle, "original_top_level_assertions")

    def test_setup_example_and_checks_must_all_complete(self):
        early_exit = "import os\nos._exit(0)"
        cases = (
            ("assert False", {"setup": early_exit}),
            (early_exit, {"checks": "assert False"}),
            ("value = 42", {"checks": early_exit + "\nassert False"}),
            (early_exit, {"expected_stdout": ""}),
        )
        for code, spec in cases:
            with self.subTest(code=code, spec=spec):
                result = SandboxRunner({}).run(code, spec)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.status, "failed", result.stderr)
                self.assertIn("did not complete", result.stderr)

    def test_imported_source_cannot_exit_before_assertions(self):
        result = SandboxRunner({"early_exit.py": "import os\nos._exit(0)"}).run(
            "import early_exit\nassert False", {})
        self.assertEqual(result.status, "failed", result.stderr)

    def test_completed_checks_preserve_namespace_and_stdout(self):
        result = SandboxRunner({"package/value.py": "answer = 42"}).run(
            "from package.value import answer\nvalue = answer + offset\nprint(value)",
            {"setup": "offset = 1", "checks": "assert value == 43", "expected_stdout": "43\n"})
        self.assertEqual(result.status, "passed", result.stderr)
        self.assertEqual(result.stdout, "43\n")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
