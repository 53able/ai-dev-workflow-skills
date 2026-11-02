"""注文を受け付けて確定する。"""
from domain.order import Order
from infra.db import OrderStore


def place_order(store: OrderStore, order_id: str, buyer_email: str, items: list[tuple[str, int, int]]) -> Order:
    order = Order(order_id, buyer_email, items)
    order.confirm()
    store.save(order)
    return order
