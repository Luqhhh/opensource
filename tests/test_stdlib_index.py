"""Verify static candidate corpus and redistribution notices without importing APIs."""

import ast
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from exampleproof.stdlib_index import (STDLIB_FILE_NOTICES, STDLIB_INDEX,
                                      STDLIB_LICENSE, STDLIB_PROVENANCE)


ROOT = Path(__file__).resolve().parents[1]
RESOURCE = ROOT / "benchmarks/semantic_v2/resources/cpython-3.10.12"


class StandardLibraryIndexTests(unittest.TestCase):
    def test_index_matches_every_public_top_level_function_and_real_lines(self):
        compressed = (RESOURCE / "stdlib-sources.json.gz").read_bytes()
        self.assertEqual(hashlib.sha256(compressed).hexdigest(), STDLIB_PROVENANCE["corpus_sha256"])
        sources = json.loads(gzip.decompress(compressed))
        self.assertEqual(len(sources), STDLIB_PROVENANCE["module_count"])
        expected = []
        for filename, text in sorted(sources.items()):
            self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), STDLIB_PROVENANCE["source_sha256"][filename])
            self.assertFalse(Path(filename).name.startswith("_"))
            self.assertEqual(len(Path(filename).parts), 2)
            for node in ast.parse(text).body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                    expected.append((filename, node.lineno, node.name))
        self.assertEqual([(entry[0], entry[1], entry[3]) for entry in STDLIB_INDEX], expected)
        for filename, start, end, name, excerpt in STDLIB_INDEX:
            self.assertEqual(excerpt, "".join(sources[filename].splitlines(keepends=True)[start - 1:end]))

    def test_license_and_source_notices_ship_inside_data_module(self):
        self.assertEqual(STDLIB_LICENSE, (RESOURCE / "LICENSE").read_text())
        self.assertIn("PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2", STDLIB_LICENSE)
        for name in ("stdlib/ast.py", "stdlib/codecs.py", "stdlib/socketserver.py"):
            self.assertRegex(STDLIB_FILE_NOTICES[name].lower(), "copyright|license")

    def test_offline_regeneration_is_byte_identical(self):
        spec = importlib.util.spec_from_file_location("stdlib_index_generator", ROOT / "scripts/build_stdlib_index.py")
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "data.py"
            generator.generate(RESOURCE, output)
            self.assertEqual(output.read_bytes(), (ROOT / "exampleproof/stdlib_index.py").read_bytes())


if __name__ == "__main__":
    unittest.main()
