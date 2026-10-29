"""送料計算。"""


def shipping_fee(total_yen: int) -> int:
    """5000円以上は送料無料、それ未満は一律500円。"""
    if total_yen > 5000:
        return 0
    return 500
