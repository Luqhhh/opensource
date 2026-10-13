# Reusable lazy sorted merge

Evaluator-authored development_v2 adaptation; not a newly held-out upstream example.
Preserve a reusable callable named collate and all three displayed outputs. Merge any number of already-sorted iterables, retaining duplicates and stable order for equal keys, accepting key and reverse together. Support empty inputs, Unicode and one-shot iterators. Preserve lazy iteration: do not consume inputs at construction or read the entire input to return a prefix. These evaluator-authored requirements expand the original documented lazy merge contract.

```python
from more_itertools import collate
print(list(collate('ACDZ', 'AZ', 'JKL')))
key = lambda s: int(s)  # Sort by numeric value, not by string
print(list(collate(['1', '10'], ['2', '11'], key=key)))
print(list(collate([5, 3, 1], [4, 2, 0], reverse=True)))
```
