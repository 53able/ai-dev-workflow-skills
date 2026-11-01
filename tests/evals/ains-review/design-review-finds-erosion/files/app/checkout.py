"""会計。"""
from domain import money
from domain.order import Order
from infra.db import Database

STORE_NAME = 'サンプル商店'


def checkout(db: Database, order: Order) -> int:
    """税込みの支払額（セント）を返し、注文を保存する。"""
    amount = order.total() + money.tax(order.total())
    db.save_order(order.order_id, order.customer_id, amount)
    return amount
