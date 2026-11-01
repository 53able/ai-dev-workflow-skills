"""注文。金額は整数の円。"""
from dataclasses import dataclass, field

SHIPPING_FEE = 500
FREE_SHIPPING_THRESHOLD = 5000


@dataclass
class Line:
    sku: str
    unit_price: int
    qty: int


@dataclass
class Order:
    number: int
    lines: list[Line] = field(default_factory=list)

    def subtotal(self) -> int:
        return sum(line.unit_price * line.qty for line in self.lines)

    def shipping(self) -> int:
        return 0 if self.subtotal() >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE
