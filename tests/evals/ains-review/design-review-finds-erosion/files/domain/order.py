"""注文。金額は domain/money.py に従い整数のセント。"""


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

    def total(self) -> int:
        """税抜きの合計（セント）。"""
        return sum(price * qty for _, price, qty in self._items)
