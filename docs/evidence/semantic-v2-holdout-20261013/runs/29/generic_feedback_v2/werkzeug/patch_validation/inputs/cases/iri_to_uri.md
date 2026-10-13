# iri to uri

Historical upstream example: https://github.com/pallets/werkzeug/blob/22a254fca2ad0130adbbcbd11d3de51bcb04a08b/src/werkzeug/urls.py#L759-L795

Retain the reusable iri_to_uri callable. Convert Unicode hostnames and paths to URI form while preserving existing percent escapes; retain doctest output.

```python
from werkzeug.urls import iri_to_uri
print(repr(iri_to_uri('http://\u2603.net/p\xe5th?q=\xe8ry%DF')))
```
