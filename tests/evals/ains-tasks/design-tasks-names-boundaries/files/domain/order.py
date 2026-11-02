"""注文。金額は整数の円で扱う。"""


class OrderError(Exception):
    """注文の状態に合わない操作。"""


class Order:
    def __init__(self, order_id: str, buyer_email: str, items: list[tuple[str, int, int]]):
        """items は (sku, 単価, 数量) の一覧。"""
        self.order_id = order_id
        self.buyer_email = buyer_email
        self.items = list(items)
        self.status = 'new'

    def total(self) -> int:
        return sum(price * qty for _, price, qty in self.items)

    def confirm(self) -> None:
        """注文を確定する。品目が無い注文と、確定済みの注文は確定できない。"""
        if not self.items:
            raise OrderError(f'{self.order_id}: 品目がありません')
        if self.status == 'confirmed':
            raise OrderError(f'{self.order_id}: 確定済みです')
        self.status = 'confirmed'
