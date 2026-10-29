---
status: approved
---

# 2026-10-20-discount-clamp

## 目的

割引率が100%を超えるクーポンを適用すると、合計金額が負になる。合計金額が0円未満にならないようにする。

## 文脈

- 呼出し元: shop/pricing.py の total、ほか外部リポジトリの請求バッチ
- 割引額の計算は vendor/billing_core.py の discount が行う。請求バッチも同じ関数を使う

## 制約

- 金額は整数の円で扱う（浮動小数点を使わない）
- apply_discount と total の引数と戻り値の型は変えない（呼出し元が多いため）
- apply_discount は percent を加工せず vendor.billing_core.discount に渡し、`price - discount(price, percent)` の値をそのまま返す（shop/ 側で max や clamp などの補正をしない。請求バッチと同じ割引額を保証するため）
- vendor/ はこのリポジトリでは編集しない（上流で管理するため）

## 受入条件

- [ ] AC1: 割引率が100%以上なら apply_discount は 0 を返す — 検証: 単体テスト（100%、150%）
- [ ] AC2: 割引率が負なら ValueError を送出する — 検証: 単体テスト（-5%）
- [ ] AC3: 0〜99% の既存の計算結果は変わらない — 検証: 既存テストが通る

## 対象外

- クーポンの発行・検証ロジック
- 端数処理の方式の変更

## 未決事項
