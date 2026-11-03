"""A small thread-safe in-memory store, seeded with sample data on startup."""

from __future__ import annotations

import copy
import threading
from typing import Any

from . import seed_data


class Collection:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows: dict[int, dict[str, Any]] = {r["id"]: copy.deepcopy(r) for r in rows}
        self._next_id = max(self._rows, default=0) + 1
        self._lock = threading.Lock()

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [copy.deepcopy(r) for r in self._rows.values()]

    def get(self, item_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._rows.get(item_id)
            return copy.deepcopy(row) if row else None

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            row = {"id": self._next_id, **data}
            self._rows[self._next_id] = row
            self._next_id += 1
            return copy.deepcopy(row)

    def update(self, item_id: int, changes: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            row = self._rows.get(item_id)
            if row is None:
                return None
            row.update(changes)
            return copy.deepcopy(row)

    def delete(self, item_id: int) -> bool:
        with self._lock:
            return self._rows.pop(item_id, None) is not None


class Store:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.companies = Collection(seed_data.COMPANIES)
        self.contacts = Collection(seed_data.CONTACTS)
        self.deals = Collection(seed_data.DEALS)


store = Store()
