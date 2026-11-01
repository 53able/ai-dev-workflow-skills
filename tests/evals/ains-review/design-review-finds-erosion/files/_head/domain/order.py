"""注文。金額は domain/money.py に従い整数のセント。"""
from infra.db import save_receipt


class OrderError(Exception):
    """注文に合わない操作。"""


class Order:
    def __init__(self, order_id: str, customer_id: str):
        self.order_id = order_id
        self.customer_id = customer_id
        self._items: list[tuple[str, int, int]] = []

    def add_item(self, sku: str, unit_price_cents: int, qty: int) -> None:
        if qty < 1:
            raise OrderError(f'{sku}: 数量は1以上です')
        self._items.append((sku, unit_price_cents, qty))

    def items(self) -> list[tuple[str, int, int]]:
        """品目の一覧 (sku, 単価, 数量)。"""
        return self._items

    def total(self) -> int:
        """税抜きの合計（セント）。"""
        return sum(price * qty for _, price, qty in self._items)

    def archive_receipt(self, conn, text: str) -> None:
        """領収書の本文を保存する。"""
        save_receipt(conn, self.order_id, text)
