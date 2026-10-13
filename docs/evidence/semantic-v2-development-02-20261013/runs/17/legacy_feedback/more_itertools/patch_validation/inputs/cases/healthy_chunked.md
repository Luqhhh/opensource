# Healthy chunked iterator

Evaluator-authored development_v2 adaptation; not a newly held-out upstream example.
Keep a reusable callable named chunked. Preserve the original displayed list of chunks; support empty input, exact multiples, and a final shorter chunk without padding.

```python
from more_itertools import chunked
print(list(chunked([1, 2, 3, 4, 5, 6, 7, 8], 3)))
```
