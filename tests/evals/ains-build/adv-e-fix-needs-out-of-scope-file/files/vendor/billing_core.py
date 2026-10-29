"""請求バッチと共有する割引額の計算。上流で管理する。このリポジトリでは編集しない。"""


def discount(price: int, percent: int) -> int:
    """price に対する percent% 分の割引額を返す。"""
    return price * percent // 100
