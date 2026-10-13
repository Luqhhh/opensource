# Frozen CPython standard-library retrieval corpus

The corpus is mechanically selected from the official CPython **v3.10.12** source
archive. It is not a copy of this workstation's distribution-patched Python.
The exact URL, release archive digest, corpus digest and per-file SHA-256 values
are recorded in `provenance.json`.

- `stdlib-sources.json.gz` preserves all 153 public flat `Lib/*.py` modules as
  unmodified source text. The gzip timestamp is fixed for reproducibility.
- `LICENSE` preserves the complete CPython license file from that release.
- `exampleproof/stdlib_index.py` contains all 999 public top-level function
  signatures/docstrings as original line slices, full license text, and original
  copyright/license notices found in comments and string literals. These notices
  therefore ship in the installed package as well as the source repository.

Classes, subpackages, C implementations, and private modules/functions are outside
the declared index scope. The corpus was selected by filename and AST structure,
without choosing modules or replacement APIs for particular benchmark answers.
No source file from the frozen corpus is imported or executed during generation
or retrieval; the generator uses its own trusted standard-library dependencies.

To reproduce the index offline without modifying the installed implementation:

```bash
python3 scripts/build_stdlib_index.py --output /tmp/stdlib_index.py
cmp exampleproof/stdlib_index.py /tmp/stdlib_index.py
python3 -m unittest discover -s tests -p test_stdlib_index.py -v
```

The generator's explicit `--download` option rebuilds the raw resources from the
fixed upstream tag. The only changes to Python content are selecting modules and
extracting signatures/docstrings; individual source slices are unchanged.

In semantic method revision 2, a confirmed missing import from a selected project
allocates 4,000 characters to project source and 2,000 to this static index. Other
failures retain a 6,000-character project budget. Unused allocation is not moved
between pools. Candidate evidence is lexical and can be incomplete or irrelevant;
the independent semantic checks still determine whether a proposed repair passes.
