import json
from pathlib import Path
import tempfile
import unittest

from exampleproof.config import load_config, safe_path
from exampleproof.extract import extract_markdown
from exampleproof.guard import validate_candidate


class CanonicalPathTests(unittest.TestCase):
    def test_aliases_and_control_characters_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'docs').mkdir()
            (root / 'docs' / 'example.md').write_text('Example')
            aliases = ('./docs/example.md', 'docs//example.md', 'docs/./example.md',
                       'docs/example.md/', 'docs/../docs/example.md', 'docs\\example.md',
                       'docs/example\n.md', 'docs/example\t.md', 'docs/example\x00.md')
            for name in aliases:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    safe_path(root, name)
            self.assertEqual(safe_path(root, 'docs/example.md'), root / 'docs' / 'example.md')

    def test_document_alias_cannot_create_duplicate_examples(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('```python\nprint(1)\n```\n')
            (root / 'exampleproof.json').write_text(json.dumps({
                'documents': ['README.md', './README.md'],
            }))
            with self.assertRaises(ValueError):
                load_config(root)

    def test_boolean_is_not_a_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('Example')
            (root / 'exampleproof.json').write_text('{"timeout_seconds": true}')
            with self.assertRaisesRegex(ValueError, 'timeout'):
                load_config(root)


class IndentedFenceTests(unittest.TestCase):
    def test_fence_indentation_is_removed_without_losing_python_indentation(self):
        text = '# Example\n   ```python\n   if True:\n       print(1)\n   ```\n'
        example = extract_markdown(text, 'README.md')[0]
        self.assertEqual(example.code, 'if True:\n    print(1)\n')
        self.assertEqual((example.start_line, example.end_line), (3, 4))
        compile(example.code, '<example>', 'exec')

    def test_remove_up_to_fence_indentation_on_each_line_and_preserve_crlf(self):
        text = '  ~~~python\r\n  values = [\r\n  1,\r\n 2,\r\n]\r\n\r\n  ~~~\r\n'
        example = extract_markdown(text, 'README.md')[0]
        self.assertEqual(example.code, 'values = [\r\n1,\r\n2,\r\n]\r\n\r\n')
        compile(example.code, '<example>', 'exec')

    def test_fences_at_column_zero_preserve_all_code_whitespace(self):
        text = '```python\nvalues = [\n  1,\n]\n```\n'
        self.assertEqual(extract_markdown(text, 'README.md')[0].code, 'values = [\n  1,\n]\n')


class CandidateIntegrityTests(unittest.TestCase):
    def test_process_control_aliases_are_rejected(self):
        candidates = (
            'from os import _exit as stop\nstop(0)\nassert False\n',
            'import os\nstop = os._exit\nstop(0)\nassert False\n',
            'from sys import exit as stop\nstop(0)\nassert False\n',
            'run = exec\nrun("pass")\nassert False\n',
            'from builtins import exec as run\nrun("pass")\nassert False\n',
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.assertIsNotNone(validate_candidate('broken()\nassert False\n', candidate))

    def test_nested_assignment_targets_cannot_mutate_objects(self):
        candidates = (
            '(module.value, x) = (1, 2)\nassert True\n',
            '[x, [values[0]]] = [1, [2]]\nassert True\n',
            '(x, *module.values) = (1, 2, 3)\nassert True\n',
            '(x, *values[0]) = (1, 2, 3)\nassert True\n',
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.assertIsNotNone(validate_candidate('broken()\nassert True\n', candidate))

    def test_nested_local_unpacking_is_supported(self):
        candidate = '(first, [second, *remaining]) = (1, [2, 3, 4])\nassert first == 1\n'
        self.assertIsNone(validate_candidate('first = old()\nassert first == 1\n', candidate))


if __name__ == '__main__':
    unittest.main()
