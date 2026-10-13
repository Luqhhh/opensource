# TinyDB 3.15.2 documentation on TinyDB 4.8.2: purge_default

Clear all records from the default table of the TinyDB database. Keep the named archive table intact. The sandbox fixture starts with an archive table; the example creates and clears the default table.
The executable block joins the listed upstream doctest commands, with only the REPL prompts removed.

```python
from tinydb import TinyDB, Query
db = TinyDB('db.json')
db.insert({'type': 'apple', 'count': 7})
db.insert({'type': 'peach', 'count': 3})
db.purge()
db.all()
```
