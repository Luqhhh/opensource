# Healthy fruit query

Evaluator-authored development_v2 adaptation; not a newly held-out upstream example.
Keep db and the Query instance Fruit available. Insert the original two records and preserve equality, count-greater-than, and empty-result queries without mutating stored data. Retain only the default table. Emit no stdout.

```python
from tinydb import TinyDB, Query
db = TinyDB('db.json')
db.insert({'type': 'apple', 'count': 7})
db.insert({'type': 'peach', 'count': 3})
Fruit = Query()
db.search(Fruit.type == 'peach')
db.search(Fruit.count > 5)
```
