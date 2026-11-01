"""注文。金額は整数の円。"""
from dataclasses import dataclass, field

SHIPPING_FEE = 500
FREE_SHIPPING_THRESHOLD = 5000
TAX_RATE_PERCENT = 10


@dataclass
class Line:
    sku: str
    unit_price: int
    qty: int
    discount_percent: int = 0

    def amount(self) -> int:
        gross = self.unit_price * self.qty
        return gross - gross * self.discount_percent // 100

    def tax(self) -> int:
        """明細の税額。1円未満は明細ごとに切り捨て。"""
        return self.amount() * TAX_RATE_PERCENT // 100


@dataclass
class Order:
    number: int
    lines: list[Line] = field(default_factory=list)

    def subtotal(self) -> int:
        return sum(line.amount() for line in self.lines)

    def shipping(self) -> int:
        return 0 if self.subtotal() >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE

    def tax(self) -> int:
        """税額。明細ごとに切り捨てた税の合計。"""
        return sum(line.tax() for line in self.lines)

    def display_number(self) -> str:
        return f'ORD-{self.number:06d}'

    def total(self) -> int:
        """支払額。小計、税、送料の合計。"""
        return self.subtotal() + self.tax() + self.shipping()
