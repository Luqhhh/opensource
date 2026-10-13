#!/usr/bin/env python3
"""Generate a static public-function index from a pinned CPython release.

Only AST parsing is used on the downloaded corpus; its source files are never
imported or executed. --download
refreshes the raw, deterministic source archive and license from the fixed tag;
ordinary generation is offline and reproduces all candidate entries.
"""

import argparse
import ast
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import tokenize
from urllib.request import urlopen


RELEASE = "3.10.12"
URL = f"https://codeload.github.com/python/cpython/tar.gz/refs/tags/v{RELEASE}"
ROOT = Path(__file__).resolve().parents[1]
RESOURCE = ROOT / "benchmarks/semantic_v2/resources" / ("cpython-" + RELEASE)
SCOPE = "All public flat Lib/*.py modules in CPython v3.10.12; every public top-level function signature and docstring. No classes, subpackages, C builtins, or private modules/functions."


def digest(data):
    return hashlib.sha256(data).hexdigest()


def download(destination):
    with urlopen(URL, timeout=120) as response:
        release = response.read(32_000_001)
    if len(release) > 32_000_000:
        raise ValueError("CPython archive exceeds download cap")
    sources = {}
    prefix = f"cpython-{RELEASE}/"
    with tarfile.open(fileobj=io.BytesIO(release), mode="r:gz") as archive:
        license_data = archive.extractfile(prefix + "LICENSE").read()
        for member in sorted(archive.getmembers(), key=lambda value: value.name):
            relative = member.name.removeprefix(prefix + "Lib/")
            if (not member.isfile() or not member.name.startswith(prefix + "Lib/")
                    or "/" in relative or relative.startswith("_") or not relative.endswith(".py")):
                continue
            data = archive.extractfile(member).read()
            encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
            sources["stdlib/" + relative] = data.decode(encoding)
    destination.mkdir(parents=True, exist_ok=True)
    corpus = json.dumps(sources, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
    compressed = gzip.compress(corpus, mtime=0)
    (destination / "stdlib-sources.json.gz").write_bytes(compressed)
    (destination / "LICENSE").write_bytes(license_data)
    provenance = {"release": RELEASE, "url": URL, "release_archive_sha256": digest(release),
                  "scope": SCOPE, "module_count": len(sources), "corpus_sha256": digest(compressed),
                  "source_sha256": {name: digest(text.encode()) for name, text in sources.items()},
                  "license_sha256": digest(license_data),
                  "changes": "Selected public flat Python modules, then mechanically extracted public top-level signatures/docstrings as exact line slices; source text is unmodified."}
    (destination / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")


def notices(text):
    """Keep source-local copyright/license comment blocks with redistributions."""
    lines = text.splitlines(keepends=True)
    found, group = [], []
    def finish():
        if group:
            excerpt = "".join(lines[group[0] - 1:group[-1]])
            if re.search(r"copyright|licen[sc]e|permission|redistribut|all rights reserved", excerpt, re.I):
                found.append(excerpt)
            group.clear()
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT:
            if group and token.start[0] > group[-1] + 1:
                finish()
            group.append(token.start[0])
    finish()
    for node in ast.walk(ast.parse(text)):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and re.search(r"copyright|licen[sc]e|permission|redistribut|all rights reserved", node.value, re.I)):
            excerpt = "".join(lines[node.lineno - 1:node.end_lineno])
            if excerpt not in found:
                found.append(excerpt)
    return "\n".join(found)


def entries(sources):
    result = []
    for filename, text in sorted(sources.items()):
        lines = text.splitlines(keepends=True)
        for node in ast.parse(text).body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name.startswith("_"):
                continue
            first = node.body[0]
            is_doc = isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str)
            end = first.end_lineno if is_doc else max(node.lineno, first.lineno - 1)
            result.append((filename, node.lineno, end, node.name, "".join(lines[node.lineno - 1:end])))
    return tuple(result)


def generate(resource, output):
    corpus_path = resource / "stdlib-sources.json.gz"
    compressed = corpus_path.read_bytes()
    sources = json.loads(gzip.decompress(compressed))
    provenance = json.loads((resource / "provenance.json").read_text())
    if provenance["corpus_sha256"] != digest(compressed):
        raise ValueError("Frozen standard-library corpus digest differs")
    if provenance["source_sha256"] != {name: digest(text.encode()) for name, text in sources.items()}:
        raise ValueError("Frozen standard-library source digests differ")
    license_text = (resource / "LICENSE").read_text()
    if digest(license_text.encode()) != provenance["license_sha256"]:
        raise ValueError("Frozen CPython license digest differs")
    indexed = entries(sources)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        stream.write('"""Generated public CPython source excerpts; regenerate with scripts/build_stdlib_index.py.\n\n'
                     'All entries are immutable source line slices, never executable indexed APIs.\n'
                     'PSF license and source-local notices are retained below.\n"""\n\n')
        for key, value in (("STDLIB_PROVENANCE", provenance), ("STDLIB_LICENSE", license_text),
                           ("STDLIB_FILE_NOTICES", {name: note for name, text in sources.items() if (note := notices(text))})):
            stream.write(key + " = " + repr(value) + "\n\n")
        stream.write("STDLIB_INDEX = (\n")
        for entry in indexed:
            stream.write("    " + repr(entry) + ",\n")
        stream.write(")\n")
    print(json.dumps({"modules": len(sources), "functions": len(indexed), "index_bytes": output.stat().st_size,
                      "index_sha256": digest(output.read_bytes()), "output": str(output)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", type=Path, default=RESOURCE)
    parser.add_argument("--output", type=Path, default=ROOT / "exampleproof/stdlib_index.py")
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if args.download:
        download(args.resources)
    generate(args.resources, args.output)


if __name__ == "__main__":
    main()
