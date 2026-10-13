# TinyDB 3.15.2 documentation on TinyDB 4.8.2: purge_named_table

Create the named table table_name, then remove that table while keeping the default table and its fruit records intact.
The executable block joins the listed upstream doctest commands, with only the REPL prompts removed.

```python
from tinydb import TinyDB, Query
db = TinyDB('db.json')
db.insert({'type': 'apple', 'count': 7})
db.insert({'type': 'peach', 'count': 3})
table = db.table('table_name')
table.insert({'value': True})
table.all()
db.purge_table('table_name')
```
