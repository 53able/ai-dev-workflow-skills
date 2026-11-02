"""カート。"""


class Cart:
    def __init__(self):
        self.items: dict[str, int] = {}

    def add(self, sku: str, qty: int = 1) -> None:
        self.items[sku] = self.items.get(sku, 0) + qty

    def remove(self, sku: str) -> None:
        self.items.pop(sku, None)
