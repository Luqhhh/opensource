# Escape optional values

Treat optional None values as empty strings while escaping ordinary values.
The harness imports the public `markupsafe` namespace, matching the documented module context.

```python
print(repr(escape(None)))
print(repr(escape_silent(None)))
```
