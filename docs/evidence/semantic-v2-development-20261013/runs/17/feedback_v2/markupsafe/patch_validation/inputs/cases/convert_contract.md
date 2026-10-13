# Reusable soft conversion without HTML escaping

Evaluator-authored development_v2 adaptation; not a newly held-out upstream example.
Keep a reusable callable named convert that converts non-strings with str(), preserves existing str/str-subclass/Markup objects by identity, and performs no HTML escaping. Cover ordinary/empty/Unicode/HTML-sensitive strings, numbers, booleans, None and objects defining __str__ or __html__. The displayed escaped Markup must remain Markup('&lt;User 1&gt;'). This authored binding task expands the upstream soft-conversion contract; it is not a mechanical excerpt.

```python
from markupsafe import escape, soft_unicode
convert = soft_unicode
value = escape('<User 1>')
print(repr(escape(convert(value))))
```
