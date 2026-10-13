# Original soft conversion display regression

Evaluator-authored development_v2 adaptation; not a newly held-out upstream example.
The harness imports markupsafe's public namespace. Preserve value as Markup and all three original displayed lines. This remains a finite display regression: the reusable convert contract is a separate new case.

```python
value = escape('<User 1>')
print(repr(value))
print(repr(escape(str(value))))
print(repr(escape(soft_unicode(value))))
```
