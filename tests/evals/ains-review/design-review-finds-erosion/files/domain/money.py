"""金額は整数のセント（1ドル = 100セント）で扱う。

税の計算と表示はこのモジュールの関数を使い、呼出し側で単位の換算や税率を持たない。
"""

TAX_RATE_PERCENT = 10


def tax(cents: int) -> int:
    """税額（セント、1セント未満は切り捨て）。"""
    return cents * TAX_RATE_PERCENT // 100


def format_usd(cents: int) -> str:
    """表示用の文字列。例: 1234 -> '$12.34'。"""
    return f'${cents // 100}.{cents % 100:02d}'
