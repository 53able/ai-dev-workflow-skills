"""会計。"""
from app import receipt
from domain import money
from domain.order import Order
from infra.db import Database

STORE_NAME = 'サンプル商店'


def checkout(db: Database, order: Order, client_name: str) -> tuple[int, str]:
    """税込みの支払額（セント）と領収書の本文を返し、注文と領収書を保存する。"""
    amount = order.total() + money.tax(order.total())
    db.save_order(order.order_id, order.customer_id, amount)
    text = receipt.build_receipt(order, buyer_name=client_name)
    order.archive_receipt(db.conn, text)
    return amount, text
