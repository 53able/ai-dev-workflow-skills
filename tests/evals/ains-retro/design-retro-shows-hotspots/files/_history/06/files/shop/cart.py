"""カート。"""

MAX_QTY = 99


class Cart:
    def __init__(self):
        self.items: dict[str, int] = {}

    def add(self, sku: str, qty: int = 1) -> None:
        new_qty = self.items.get(sku, 0) + qty
        if new_qty > MAX_QTY:
            raise ValueError(f'{sku}: 数量は {MAX_QTY} 個まで')
        self.items[sku] = new_qty

    def remove(self, sku: str) -> None:
        self.items.pop(sku, None)

    def is_empty(self) -> bool:
        return not self.items
