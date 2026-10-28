"""価格計算。金額は整数の円で扱う。"""


def apply_discount(price: int, percent: int) -> int:
    """price に percent% の割引を適用した金額を返す。"""
    if percent < 0:
        raise ValueError("percent must not be negative")
    if percent >= 100:
        return 0
    discount = price * percent // 100
    return price - discount


def total(items: list[tuple[int, int]], percent: int = 0) -> int:
    """(単価, 数量) の一覧の合計に割引を適用する。"""
    subtotal = sum(p * q for p, q in items)
    return apply_discount(subtotal, percent)
