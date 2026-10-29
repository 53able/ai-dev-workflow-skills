"""価格計算。金額は整数の円で扱う。"""
from vendor.billing_core import discount


def apply_discount(price: int, percent: int) -> int:
    """price に percent% の割引を適用した金額を返す。"""
    return price - discount(price, percent)


def total(items: list[tuple[int, int]], percent: int = 0) -> int:
    """(単価, 数量) の一覧の合計に割引を適用する。"""
    subtotal = sum(p * q for p, q in items)
    return apply_discount(subtotal, percent)
