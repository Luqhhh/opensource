# Drop one named table and preserve other records

Evaluator-authored development_v2 adaptation; not a newly held-out upstream example.
Keep db and a reusable drop_named(name) callable bound to this database. Remove only the requested named table and its records; preserve default, archive and empty_archive tables and data. Handle missing/empty tables and repeated calls, invalidate table caches so recreation starts at ID 1, and persist after reopen. The fixture includes multiple Unicode/false/null records. Emit no stdout.

```python
from tinydb import TinyDB, Query
db = TinyDB('db.json')
db.insert({'type': 'apple', 'count': 7})
db.insert({'type': 'peach', 'count': 3})
table = db.table('table_name')
table.insert({'value': True})
table.all()
drop_named = db.purge_table
drop_named('table_name')
```
