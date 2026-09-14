"""Small persistent mapping for pending internal writeback, never action replay."""
from collections.abc import MutableMapping
from pathlib import Path
import json
import sqlite3


class PendingMap(MutableMapping):
    def __init__(self, path, namespace, encode=lambda x: x, decode=lambda x: x):
        self.path, self.namespace, self.encode, self.decode = path, namespace, encode, decode
        self.memory = {}
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with self.connect() as db:
                db.execute("CREATE TABLE IF NOT EXISTS outbox (namespace TEXT, id TEXT, payload TEXT NOT NULL, PRIMARY KEY(namespace,id))")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def __getitem__(self, key):
        if not self.path:
            return self.memory[key]
        with self.connect() as db:
            row = db.execute("SELECT payload FROM outbox WHERE namespace=? AND id=?", (self.namespace, key)).fetchone()
        if row is None:
            raise KeyError(key)
        return self.decode(json.loads(row[0]))

    def __setitem__(self, key, value):
        if not self.path:
            self.memory[key] = value
            return
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO outbox VALUES (?,?,?)", (self.namespace, key, json.dumps(self.encode(value))))

    def __delitem__(self, key):
        if not self.path:
            del self.memory[key]
            return
        with self.connect() as db:
            cursor = db.execute("DELETE FROM outbox WHERE namespace=? AND id=?", (self.namespace, key))
            if not cursor.rowcount:
                raise KeyError(key)

    def __iter__(self):
        if not self.path:
            return iter(list(self.memory))
        with self.connect() as db:
            keys = [r[0] for r in db.execute("SELECT id FROM outbox WHERE namespace=? ORDER BY rowid", (self.namespace,))]
        return iter(keys)

    def __len__(self):
        if not self.path:
            return len(self.memory)
        with self.connect() as db:
            return db.execute("SELECT count(*) FROM outbox WHERE namespace=?", (self.namespace,)).fetchone()[0]
