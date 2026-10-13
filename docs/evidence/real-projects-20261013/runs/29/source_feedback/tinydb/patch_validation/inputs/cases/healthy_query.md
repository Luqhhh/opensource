# TinyDB 3.15.2 documentation on TinyDB 4.8.2: healthy_query

Insert the fruit records and query peaches and records with count greater than five. This is a healthy control; preserve its behavior.
The executable block joins the listed upstream doctest commands, with only the REPL prompts removed.

```python
from tinydb import TinyDB, Query
db = TinyDB('db.json')
db.insert({'type': 'apple', 'count': 7})
db.insert({'type': 'peach', 'count': 3})
Fruit = Query()
db.search(Fruit.type == 'peach')
db.search(Fruit.count > 5)
```
