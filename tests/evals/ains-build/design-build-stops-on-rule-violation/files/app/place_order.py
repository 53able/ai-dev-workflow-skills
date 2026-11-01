"""注文を受け付けて確定する。Order を作るのはここだけ。"""
from domain.order import Order


def place_order(order_id, items):
    order = Order(order_id, items)
    order.confirm()
    return order
