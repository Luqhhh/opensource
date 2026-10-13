# Python-derived recipes attribution

The unmodified `more_itertools/recipes.py` files state that their functions were
imported from the recipes section of the Python `itertools` documentation and
retain that attribution in their module docstrings.

The upstream more-itertools MIT license is preserved alongside those files.
For the attributed Python-derived material, `cpython-3.7.0/LICENSE` additionally
preserves the complete Python Software Foundation License Version 2 and the
historical Python copyright and license notices from CPython 3.7.0, commit
`1bf9cc509326bc42cd8cb1650eb9bf64550d817e`:

https://github.com/python/cpython/blob/1bf9cc509326bc42cd8cb1650eb9bf64550d817e/LICENSE

Its exact source URL and SHA-256 are recorded in `../provenance.json`.
This archive predates the more-itertools 5.0.0 release and preserves the PSF
license text for historical recipes. It does not establish that every recipe
was taken from this particular CPython version: the complete per-function
ancestry has not been traced. In particular, we do not classify all historical
recipe code as 0BSD based on the license of newer Python documentation examples.

No archived Python or more-itertools source code has been modified. ExampleProof
only adds documented extraction wrappers and evaluator-owned checks outside the
copied source files.
