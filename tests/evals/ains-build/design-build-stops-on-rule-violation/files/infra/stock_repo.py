"""在庫の正本。倉庫システムと同期する在庫数を持つ。"""


class OutOfStock(Exception):
    """在庫が足りない。"""

    def __init__(self, sku, requested, available):
        super().__init__(f'{sku}: {requested} 個に対して在庫 {available} 個')
        self.sku = sku
        self.requested = requested
        self.available = available


class StockRepo:
    def __init__(self, stock=None):
        self._stock = dict(stock or {})

    def available(self, sku):
        return self._stock.get(sku, 0)

    def reserve(self, sku, qty):
        """sku の在庫を qty 個引き当てる。足りなければ OutOfStock を送出し、在庫は変えない。"""
        have = self.available(sku)
        if have < qty:
            raise OutOfStock(sku, qty, have)
        self._stock[sku] = have - qty
