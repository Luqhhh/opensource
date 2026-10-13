# peek path info

Historical upstream example: https://github.com/pallets/werkzeug/blob/22a254fca2ad0130adbbcbd11d3de51bcb04a08b/src/werkzeug/wsgi.py#L310-L332

Keep the reusable callable peek_path_info. Return the next decoded segment without mutating the environment, including repeated calls and slashes. Preserve the pinned implementation boundary behavior: empty paths return an empty string; charset=None returns bytes. Retain the upstream printed results.

```python
from werkzeug.wsgi import peek_path_info
env = {'SCRIPT_NAME': '/foo', 'PATH_INFO': '/a/b'}
print(repr(peek_path_info(env)))
print(repr(peek_path_info(env)))
```
