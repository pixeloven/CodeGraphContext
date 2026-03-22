from __future__ import annotations

import aiosqlite


class OrderRepository:
    """Thin persistence layer over an aiosqlite database."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def init_db(self) -> None:
        """Create the orders table if it does not already exist."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    name       TEXT    NOT NULL,
                    quantity   INTEGER NOT NULL,
                    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            await db.commit()

    async def find_all(self) -> list[dict]:
        """Return every order row as a dict."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT id, name, quantity, created_at FROM orders")
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def create(self, data: dict) -> dict:
        """Insert a new order and return it (with generated id and created_at)."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "INSERT INTO orders (name, quantity) VALUES (?, ?)",
                (data["name"], data["quantity"]),
            )
            await db.commit()
            order_id = cursor.lastrowid

            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, name, quantity, created_at FROM orders WHERE id = ?",
                (order_id,),
            )
            row = await cursor.fetchone()
            return dict(row)
