# Healthy incomplete final chunk

Official more-itertools 5.0.0 docstring: [L101–L102](https://github.com/more-itertools/more-itertools/blob/53c2c692d3175e4487235213465afb14a211ec3c/more_itertools/more.py#L101-L102). Target source: 9.0.0 (ffcfe0b4e63c75fe1470b8b25a29b0e698a9a587).

The original doctest statements and expected results are stored in `../original/healthy_chunked.doctest`. This Markdown form adds the documented import and wraps bare REPL expressions in `print(...)`; call arguments, data, and statements are otherwise unchanged.

```python
from more_itertools import chunked
print(list(chunked([1, 2, 3, 4, 5, 6, 7, 8], 3)))
```
