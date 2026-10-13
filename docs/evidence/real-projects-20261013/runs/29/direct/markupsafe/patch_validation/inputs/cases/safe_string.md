# Preserve safe text on string conversion

Convert an object to text while preserving Markup so it is not escaped twice.
The harness imports the public `markupsafe` namespace, matching the documented module context.

```python
value = escape('<User 1>')
print(repr(value))
print(repr(escape(str(value))))
print(repr(escape(soft_unicode(value))))
```
