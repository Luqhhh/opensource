import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch

from exampleproof.context import _stdlib_context, missing_project_import, source_context
from exampleproof.models import Example, Execution


class SourceContextTests(unittest.TestCase):
    def example(self, code, context=""):
        return Example("docs/demo.md#1", "docs/demo.md", 3, 5, code, context)

    def before(self, message="AttributeError: 'Store' object has no attribute 'purge'"):
        return Execution("failed", 21, stderr=message, oracle="configured_behavior_checks")

    def test_retrieves_instance_contract_and_replacement_behavior_together(self):
        sources = {"library.py": '''class Store:
    """Forward unrecognized operations to the configured primary bucket."""
    primary_name = "_primary"

    def __getattr__(self, name):
        return getattr(self.bucket(self.primary_name), name)

    def erase_everything(self):
        """Remove every bucket, including archives."""
        self.data.clear()

class Bucket:
    def empty(self):
        """Clear records in this bucket; preserve other buckets."""
        self.records.clear()
'''}
        example = self.example("from library import Store\ndb = Store()\ndb.purge()\n",
                               "Clear records in the primary bucket; preserve archive buckets.")
        result = source_context(example, self.before(), sources, 1600)
        text = "\n".join(result.values())
        self.assertIn('primary_name = "_primary"', text)
        self.assertIn("def __getattr__", text)
        self.assertIn("def empty", text)
        self.assertIn("preserve other buckets", text)

    def test_resolves_import_alias_and_prefers_actual_receiver_method(self):
        sources = {"library.py": '''class Unrelated:
    def lookup(self):
        """Lookup lookup lookup lookup lookup lookup lookup lookup."""
        return "wrong scope"

class Directory:
    def lookup(self, key):
        """Resolve an entry by its exact key."""
        return self.entries[key]
'''}
        example = self.example("from library import Directory as Local\nd = Local()\nd.lookup()\n")
        result = source_context(example, self.before("TypeError: lookup() missing argument 'key'"), sources, 1600)
        excerpts = list(result.values())
        wanted = next(i for i, value in enumerate(excerpts) if "def lookup(self, key)" in value)
        wrong = [i for i, value in enumerate(excerpts) if 'return "wrong scope"' in value]
        self.assertTrue(not wrong or wanted < min(wrong))
        self.assertTrue(any("class Directory" in text for text in excerpts))

    def test_keeps_complete_short_docstring_and_implementation(self):
        sources = {"api.py": '''def fetch(key, default=None):
    """Fetch a named record.

    Missing keys return the supplied default, including None.
    """
    return records.get(key, default)
'''}
        result = source_context(self.example("fetch()"), self.before("TypeError: missing key"), sources)
        self.assertEqual(list(result.values()), [sources["api.py"]])

    def test_long_implementation_does_not_displace_its_full_api_docstring(self):
        body = "".join(f"    intermediate_{i} = key + {i}\n" for i in range(80))
        sources = {"api.py": 'def fetch(key):\n    """Fetch the record; missing keys raise KeyError."""\n' + body + "    return key\n"}
        result = source_context(self.example("fetch()"), self.before("TypeError: missing key"), sources, 300)
        text = "\n".join(result.values())
        self.assertIn("missing keys raise KeyError", text)
        self.assertNotIn("intermediate_79", text)

    def test_no_duplicate_lines_and_every_excerpt_is_exact(self):
        sources = {"b.py": "class Store:\n    primary_name = 'main'\n    def purge(self): return 1\n",
                   "a.py": "def purge():\n    return 2\n"}
        example = self.example("db = Store()\ndb.purge()\n", "Clear the primary store.")
        for limit in (0, 1, 40, 100, 220, 6000):
            with self.subTest(limit=limit):
                result = source_context(example, self.before(), sources, limit)
                self.assertLessEqual(sum(len(label) + len(text) for label, text in result.items()), limit)
                seen = set()
                for label, text in result.items():
                    match = re.fullmatch(r"(.+):(\d+)-(\d+)", label)
                    self.assertIsNotNone(match)
                    filename, start, end = match.group(1), int(match.group(2)), int(match.group(3))
                    positions = {(filename, i) for i in range(start, end + 1)}
                    self.assertFalse(positions & seen)
                    seen.update(positions)
                    self.assertEqual(text, "".join(sources[filename].splitlines(keepends=True)[start - 1:end]))

    def test_deterministic_across_input_order_and_case_ids(self):
        sources = {"a.py": "def missing(): return 3\n", "b.py": "def other(): return 4\n"}
        first = self.example("missing()")
        second = Example("UNSEEN-ID", "unrelated.md", 100, 900, first.code, first.context)
        before = self.before("NameError: name 'missing' is not defined")
        self.assertEqual(source_context(first, before, sources),
                         source_context(second, before, dict(reversed(list(sources.items())))))

    def test_deterministic_across_hash_seed_processes(self):
        # Only the retriever is executed; these synthetic source strings are
        # parsed, never imported or evaluated by the subprocess.
        program = '''import json
from exampleproof.context import source_context
from exampleproof.models import Example, Execution
sources = {"a.py": "def fetch(key):\\n    \\\"\\\"\\\"Find records by key; preserve stable order.\\\"\\\"\\\"\\n    return records[key]\\n", "b.py": "def select(key):\\n    \\\"\\\"\\\"Select records by stable order and preserve key.\\\"\\\"\\\"\\n    return key\\n"}
example = Example("a.md#1", "a.md", 1, 1, "missing()", "Find and select records by key; preserve stable order.")
before = Execution("failed", 21, stderr="NameError: name 'missing' is not defined")
print(json.dumps(source_context(example, before, sources), separators=(",", ":")))
'''
        results = [subprocess.check_output([sys.executable, "-c", program],
                                          cwd=Path(__file__).resolve().parents[1],
                                          env={**os.environ, "PYTHONHASHSEED": str(seed)}, text=True)
                   for seed in (0, 17, 29, 43)]
        self.assertTrue(json.loads(results[0]))
        self.assertEqual(results, [results[0]] * len(results))

    def test_private_evaluator_text_cannot_change_retrieval(self):
        sources = {"api.py": "def first(): return 1\ndef secret_answer(): return 2\n"}
        example = self.example("missing()", "Return the first item.")
        first = Execution("failed", 22, stderr="secret_answer", oracle="configured_behavior_checks")
        second = Execution("failed", 22, stderr="an entirely different private check", oracle="configured_behavior_checks")
        self.assertEqual(source_context(example, first, sources), source_context(example, second, sources))

    def test_traceback_infrastructure_paths_do_not_affect_retrieval(self):
        sources = {"api.py": "def fetch(): return 1\ndef runner_secret(): return 2\n"}
        example = self.example("fetch()")
        plain = self.before("TypeError: missing argument")
        frames = self.before('Traceback (most recent call last):\n  File "/runner_secret.py", line 42\n    runner_secret()\nTypeError: missing argument')
        self.assertEqual(source_context(example, plain, sources), source_context(example, frames, sources))

    def test_bad_source_is_skipped_without_executing_valid_source(self):
        sources = {"broken.py": "def broken(\n", "valid.py": "raise RuntimeError('must not execute')\ndef fetch(): return 1\n"}
        result = source_context(self.example("fetch()"), self.before("TypeError: missing argument"), sources)
        self.assertTrue(result)
        self.assertTrue(all(label.startswith("valid.py:") for label in result))

    def test_single_line_definition_and_missing_final_newline_are_preserved(self):
        sources = {"api.py": "def fetch(): return 1"}
        result = source_context(self.example("fetch()"), self.before("TypeError: failure"), sources)
        self.assertEqual(result, {"api.py:1-1": sources["api.py"]})

    def test_invalid_budget_rejected_and_empty_sources_supported(self):
        for limit in (-1, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                source_context(self.example("fetch()"), self.before(), {}, limit)
        self.assertEqual(source_context(self.example("fetch()"), self.before(), {}), {})

    def test_private_helpers_are_excluded_unless_explicitly_called(self):
        sources = {"api.py": '''def convert_record(item):
    """Convert records while preserving identity."""
    return item

def _private_convert(item):
    """Convert records while preserving identity."""
    return item

class _Internal:
    def transform(self, item):
        """Convert records while preserving identity."""
        return item
'''}
        example = self.example("missing()", "Convert records while preserving identity.")
        result = "\n".join(source_context(example, self.before("NameError: name 'missing' is not defined"), sources).values())
        self.assertIn("def convert_record", result)
        self.assertNotIn("_private_convert", result)
        self.assertNotIn("_Internal", result)
        self.assertNotIn("def transform", result)
        explicit = self.example("_private_convert()")
        result = "\n".join(source_context(explicit, self.before("TypeError: missing item"), sources).values())
        self.assertIn("def _private_convert", result)

    def test_same_public_method_name_does_not_expose_a_private_owner(self):
        sources = {"api.py": '''class _Hidden:
    def lookup(self, key):
        """Lookup an exact key and return a record."""
        return "private implementation"

class Public:
    def lookup(self, key):
        """Lookup an exact key and return a record."""
        return "public implementation"
'''}
        example = self.example("from api import Public\np = Public()\np.lookup()")
        before = self.before("TypeError: lookup() missing key")
        result = "\n".join(source_context(example, before, sources).values())
        self.assertIn('return "public implementation"', result)
        self.assertNotIn('return "private implementation"', result)
        self.assertNotIn("class _Hidden", result)

    def test_stdlib_fallback_requires_matching_missing_project_import(self):
        example = self.example("from library import removed as local\nlocal()")
        sources = {"library/__init__.py": ""}
        before = self.before("ImportError: cannot import name 'removed' from 'library' (/workspace/library/__init__.py)")
        self.assertTrue(missing_project_import(example, before, sources))
        self.assertFalse(missing_project_import(example, before, {}))
        self.assertFalse(missing_project_import(self.example("removed()"), before, sources))
        self.assertFalse(missing_project_import(example, self.before("NameError: name 'removed' is not defined"), sources))
        private = Execution("failed", 22, stderr=before.stderr, oracle="configured_behavior_checks")
        self.assertFalse(missing_project_import(example, private, sources))

    def test_fallback_partitions_budget_without_returning_unused_capacity(self):
        example = self.example("from library import removed\nremoved()")
        before = self.before("ImportError: cannot import name 'removed' from 'library'")
        sources = {"library.py": ""}
        with patch("exampleproof.context._project_context", return_value={}) as project, \
                patch("exampleproof.context._stdlib_context", return_value={}) as standard:
            self.assertEqual(source_context(example, before, sources), {})
            self.assertEqual(project.call_args.args[-1], 4000)
            self.assertEqual(standard.call_args.args[-1], 2000)
        with patch("exampleproof.context._project_context", return_value={}) as project, \
                patch("exampleproof.context._stdlib_context") as standard:
            source_context(example, self.before("AttributeError: missing attribute"), sources)
            self.assertEqual(project.call_args.args[-1], 6000)
            standard.assert_not_called()

    def test_stdlib_ranking_uses_task_words_and_returns_exact_bounded_slices(self):
        entries = (("stdlib/a.py", 20, 22, "fold_records", 'def fold_records(items):\n    """Fold numeric records into a single result."""\n'),
                   ("stdlib/b.py", 1, 2, "describe", 'def describe(items):\n    """Describe strings in a directory."""\n'))
        example = self.example("from library import removed\nremoved()", "Fold numeric records into a single result.")
        before = self.before("ImportError: cannot import name 'removed' from 'library'")
        first = _stdlib_context(example, before, 1000, entries=entries)
        second = _stdlib_context(example, before, 1000, entries=tuple(reversed(entries)))
        self.assertEqual(first, second)
        self.assertEqual(list(first.values()), [entries[0][4]])
        self.assertNotIn("describe", "\n".join(first.values()))
        for limit in (0, 10, 60, 100):
            result = _stdlib_context(example, before, limit, entries=entries)
            self.assertLessEqual(sum(len(k) + len(v) for k, v in result.items()), limit)


if __name__ == "__main__":
    unittest.main()
