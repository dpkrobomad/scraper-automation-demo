"""SQLite storage with price history and change detection."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Union

from .core import Item

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  url TEXT PRIMARY KEY, title TEXT NOT NULL, price_gbp REAL NOT NULL,
  in_stock INTEGER NOT NULL, rating INTEGER, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL, title TEXT NOT NULL,
  kind TEXT NOT NULL, old_value TEXT, new_value TEXT, at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Union[str, Path] = "data/items.db"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def upsert(self, items: Iterable[Item]) -> dict:
        """Save items; record new items, price changes and stock changes. Return counts."""
        counts = {"new": 0, "price_changed": 0, "stock_changed": 0, "unchanged": 0}
        ts = now()
        with self.db:
            for it in items:
                row = self.db.execute("SELECT * FROM items WHERE url = ?", (it.url,)).fetchone()
                if row is None:
                    self.db.execute(
                        "INSERT INTO items VALUES (?,?,?,?,?,?,?)",
                        (it.url, it.title, it.price_gbp, int(it.in_stock), it.rating, ts, ts),
                    )
                    self._change(it, "new", None, it.price_gbp, ts)
                    counts["new"] += 1
                    continue
                changed = False
                if abs(row["price_gbp"] - it.price_gbp) > 1e-9:
                    self._change(it, "price", row["price_gbp"], it.price_gbp, ts)
                    counts["price_changed"] += 1
                    changed = True
                if bool(row["in_stock"]) != it.in_stock:
                    self._change(it, "stock", bool(row["in_stock"]), it.in_stock, ts)
                    counts["stock_changed"] += 1
                    changed = True
                if not changed:
                    counts["unchanged"] += 1
                self.db.execute(
                    "UPDATE items SET title=?, price_gbp=?, in_stock=?, rating=?, last_seen=? WHERE url=?",
                    (it.title, it.price_gbp, int(it.in_stock), it.rating, ts, it.url),
                )
        return counts

    def _change(self, it: Item, kind: str, old, new, ts: str) -> None:
        self.db.execute(
            "INSERT INTO changes (url, title, kind, old_value, new_value, at) VALUES (?,?,?,?,?,?)",
            (it.url, it.title, kind, None if old is None else str(old), str(new), ts),
        )

    def last_change_id(self) -> int:
        return self.db.execute("SELECT COALESCE(MAX(id), 0) FROM changes").fetchone()[0]

    def items(self) -> List[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM items ORDER BY title")]

    def changes(self, since: str = "", kinds: Iterable[str] = ("price", "stock")) -> List[dict]:
        kinds = list(kinds)
        q = f"SELECT * FROM changes WHERE at > ? AND kind IN ({','.join('?' * len(kinds))}) ORDER BY id"
        return [dict(r) for r in self.db.execute(q, (since, *kinds))]
