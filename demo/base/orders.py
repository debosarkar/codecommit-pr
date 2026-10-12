import sqlite3


def get_order(conn: sqlite3.Connection, order_id: int) -> tuple | None:
    cursor = conn.execute("SELECT id, total FROM orders WHERE id = ?", (order_id,))
    return cursor.fetchone()
