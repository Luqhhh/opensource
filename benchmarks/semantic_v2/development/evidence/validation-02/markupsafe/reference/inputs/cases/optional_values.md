# Healthy optional escaped values

Evaluator-authored development_v2 adaptation; not a newly held-out upstream example.
The harness imports the public markupsafe namespace. Keep escape and escape_silent callable. Preserve displayed Markup('None') and Markup(''); escape_silent(None) returns empty Markup, HTML-sensitive text is escaped, and numeric zero is converted to Markup('0').

```python
print(repr(escape(None)))
print(repr(escape_silent(None)))
```
