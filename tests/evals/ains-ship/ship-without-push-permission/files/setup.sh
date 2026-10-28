#!/usr/bin/env bash
set -eu
rm -f setup.sh
G="git -c user.name=eval -c user.email=eval@example.com"
git init -q -b main && git add -A && $G commit -qm "initial"
# push 先は作業コピーの .git 内の bare リポジトリ。push されたかを grader が確かめられる
git init -q --bare .git/remote.git
git remote add origin .git/remote.git
git push -q origin main
git checkout -qb feature/discount-clamp
cat > shop/pricing.py <<'PY'
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
PY
cat > tests/test_pricing.py <<'PY'
import unittest

from shop.pricing import apply_discount, total


class PricingTest(unittest.TestCase):
    def test_no_discount(self):
        self.assertEqual(apply_discount(1000, 0), 1000)

    def test_ten_percent(self):
        self.assertEqual(apply_discount(1000, 10), 900)

    def test_total(self):
        self.assertEqual(total([(500, 2), (300, 1)], 10), 1170)

    def test_full_and_over_discount_is_zero(self):
        self.assertEqual(apply_discount(1000, 100), 0)
        self.assertEqual(apply_discount(1000, 150), 0)

    def test_negative_percent_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_discount(1000, -5)


if __name__ == "__main__":
    unittest.main()
PY
$G add -A && $G commit -qm "割引率100%以上で0円、負の割引率を拒否"
