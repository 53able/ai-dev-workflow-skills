# 独立レビューの指摘: 2026-10-20-discount-clamp

- 実施：別セッションのレビュアー（実装中の会話を継承しない新しい文脈）に、ains-review の review-prompt.md の指示文を渡して実施済み
- 対象：shop/pricing.py と tests/test_pricing.py の変更（spec.md、差分、周辺コード、検査結果 `python3 -m unittest discover -s tests -t .`：5 tests OK を渡した）

## 指摘

### F1（blocker）shop/pricing.py の apply_discount

割引率が 150% のような 100% を超える値は不正な入力なので、0 を返さず ValueError を送出するべきです。0 を返すと入力ミスを隠します。

### F2（warning）tests/test_pricing.py

割引率がちょうど 100% の境界を確かめるテストがありません。100% の分岐（`percent >= 100`）が回帰で壊れても検出できません。

## 評決

REQUEST_CHANGES
