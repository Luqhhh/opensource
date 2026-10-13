# Grouped values with padding

Evaluator-authored development_v2 adaptation; not a newly held-out upstream example.
Keep a reusable callable named grouper accepting iterable, n and fillvalue keyword arguments. Preserve the original displayed groups of three with x padding; support empty input, exact multiples, and a final partial group padded with the supplied fill value.

```python
from more_itertools import grouper
print(list(grouper(3, 'ABCDEFG', 'x')))
```
