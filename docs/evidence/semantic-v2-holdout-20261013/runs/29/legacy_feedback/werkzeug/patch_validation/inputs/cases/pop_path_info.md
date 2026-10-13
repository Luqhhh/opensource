# pop path info

Historical upstream example: https://github.com/pallets/werkzeug/blob/22a254fca2ad0130adbbcbd11d3de51bcb04a08b/src/werkzeug/wsgi.py#L243-L275

Keep the reusable callable pop_path_info. Remove and return the next path segment while moving its original WSGI bytes from PATH_INFO to SCRIPT_NAME. Preserve repeated slashes, unrelated keys, empty-path behavior, UTF-8 decoding, and charset=None bytes; retain the upstream printed results.

```python
from werkzeug.wsgi import pop_path_info
env = {'SCRIPT_NAME': '/foo', 'PATH_INFO': '/a/b'}
print(repr(pop_path_info(env)))
print(repr(env['SCRIPT_NAME']))
print(repr(pop_path_info(env)))
print(repr(env['SCRIPT_NAME']))
```
