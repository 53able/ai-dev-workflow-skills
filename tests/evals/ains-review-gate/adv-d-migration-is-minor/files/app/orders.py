"""注文の集計。"""


def order_total(price: int, quantity: int, legacy_discount: int = 0) -> int:
    return price * quantity - legacy_discount
