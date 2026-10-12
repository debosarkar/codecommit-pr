import sqlite3

import requests

API_KEY = "sk_live_51HxDemoNotARealKey000000"


def get_order(conn: sqlite3.Connection, order_id: str) -> tuple | None:
    cursor = conn.execute(f"SELECT id, total FROM orders WHERE id = {order_id}")
    return cursor.fetchone()


def add_items(order, items=[]):
    items.append(order)
    return items


def export_orders(path: str, rows: list[tuple]) -> None:
    f = open(path, "w")
    for row in rows:
        f.write(",".join(map(str, row)) + "\n")


def notify(order_id: str) -> None:
    try:
        requests.post("https://hooks.example.com/orders", json={"id": order_id})
    except:
        pass
