# Clear default records and retain unrelated tables

Evaluator-authored development_v2 adaptation; not a newly held-out upstream example.
Keep db and a reusable zero-argument clear_default callable bound to this database. Clear only default-table records, retaining the default table and named archive/empty_archive tables and data. The fixture contains pre-existing records including Unicode, empty strings, false and null. Repeated calls on empty and refilled tables must work, reset IDs to 1, invalidate cached searches, and persist after reopen. Emit no stdout.

```python
from tinydb import TinyDB, Query
db = TinyDB('db.json')
db.insert({'type': 'apple', 'count': 7})
db.insert({'type': 'peach', 'count': 3})
clear_default = db.purge
clear_default()
db.all()
```
