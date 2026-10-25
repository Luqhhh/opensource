"""Compatibility checks for the public RepoPath entry point; no model calls."""

import contextlib
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from exampleproof.cli import main as legacy_main
from repopath.cli import main


class RepoPathEntrypointTests(unittest.TestCase):
    def test_both_entrypoints_reuse_existing_learning_storage(self):
        for entry in (main, legacy_main):
            with self.subTest(entry=entry.__module__), patch("exampleproof.learn_server.serve") as serve:
                self.assertEqual(entry(["learn", "--provider", "none"]), 0)
                self.assertEqual(serve.call_args.args[0], Path.home() / ".local/share/exampleproof-learning")
                self.assertEqual(serve.call_args.args[2], "none")

    def test_repopath_honors_explicit_data_directory(self):
        with patch("exampleproof.learn_server.serve") as serve:
            self.assertEqual(main(["learn", "--provider", "none", "--data", "/tmp/repopath-selected-data"]), 0)
            self.assertEqual(serve.call_args.args[0], Path("/tmp/repopath-selected-data"))

    def test_help_keeps_the_invoked_command_name(self):
        for entry, command in ((main, "repopath"), (legacy_main, "exampleproof")):
            output = io.StringIO()
            with self.subTest(command=command), contextlib.redirect_stdout(output):
                with self.assertRaises(SystemExit) as result:
                    entry(["--help"])
                self.assertEqual(result.exception.code, 0)
                self.assertIn("usage: " + command, output.getvalue())
                self.assertIn("源途 · RepoPath", output.getvalue())

    def test_repopath_errors_identify_the_new_command(self):
        output = io.StringIO()
        with patch("exampleproof.learn_server.serve", side_effect=ValueError("test failure")), contextlib.redirect_stderr(output):
            self.assertEqual(main(["learn", "--provider", "none"]), 2)
        self.assertEqual(output.getvalue(), "repopath: test failure\n")

    def test_early_argument_errors_identify_the_new_command(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(SystemExit) as result:
            main(["learn", "--deadline-seconds", "invalid"])
        self.assertEqual(result.exception.code, 2)
        self.assertIn("usage: repopath", output.getvalue())
        self.assertIn("repopath: error:", output.getvalue())


if __name__ == "__main__":
    unittest.main()
