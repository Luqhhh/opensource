# Sorted merge: removed collate

Official more-itertools 5.0.0 docstring: [L363–L364](https://github.com/more-itertools/more-itertools/blob/53c2c692d3175e4487235213465afb14a211ec3c/more_itertools/more.py#L363-L364), [L373–L375](https://github.com/more-itertools/more-itertools/blob/53c2c692d3175e4487235213465afb14a211ec3c/more_itertools/more.py#L373-L375), [L381–L382](https://github.com/more-itertools/more-itertools/blob/53c2c692d3175e4487235213465afb14a211ec3c/more_itertools/more.py#L381-L382). Target source: 9.0.0 (ffcfe0b4e63c75fe1470b8b25a29b0e698a9a587).

The original doctest statements and expected results are stored in `../original/collate.doctest`. This Markdown form adds the documented import and wraps bare REPL expressions in `print(...)`; call arguments, data, and statements are otherwise unchanged.

Evaluator contract: preserve a reusable callable named `collate`, so the documented examples and additional supported inputs can be checked. This sentence is evaluator-authored context, not copied upstream documentation.

```python
from more_itertools import collate
print(list(collate('ACDZ', 'AZ', 'JKL')))
key = lambda s: int(s)  # Sort by numeric value, not by string
print(list(collate(['1', '10'], ['2', '11'], key=key)))
print(list(collate([5, 3, 1], [4, 2, 0], reverse=True)))
```
