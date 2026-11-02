"""注文。外部（在庫、DB）を知らない。"""


class OrderError(Exception):
    """注文の状態に合わない操作。"""


class Order:
    def __init__(self, order_id, items):
        """items は (sku, 数量) の一覧。"""
        self.order_id = order_id
        self.items = list(items)
        self.status = 'new'

    def confirm(self):
        """注文を確定する。品目が無い注文、数量が1未満の品目、確定済みの注文は確定できない。"""
        if not self.items:
            raise OrderError(f'{self.order_id}: 品目がありません')
        if any(qty < 1 for _, qty in self.items):
            raise OrderError(f'{self.order_id}: 数量は1以上です')
        if self.status == 'confirmed':
            raise OrderError(f'{self.order_id}: 確定済みです')
        self.status = 'confirmed'
