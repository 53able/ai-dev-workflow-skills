---
status: approved
---

# 2026-11-02-stock-reservation

## 目的

在庫が無い商品の注文も確定でき、出荷の段階で欠品が分かる。注文の確定時に在庫を引き当て、在庫が足りない注文は確定させない。

## 文脈

- 注文の確定: domain/order.py の Order.confirm()。Order は app/place_order.py の place_order で作られる
- 在庫: infra/stock_repo.py の StockRepo（reserve で引き当てる。足りなければ OutOfStock を送出する）

## 制約

- 標準ライブラリのみ
- 在庫の正本は infra/stock_repo.py の StockRepo とする

## 受入条件

- [ ] AC1: `Order.confirm()` を呼ぶと、各品目の在庫数が数量の分だけ減る — 検証: 単体テスト
- [ ] AC2: 在庫が足りなければ `Order.confirm()` は OutOfStock を送出し、注文は confirmed にならない — 検証: 単体テスト
- [ ] AC3: 既存のテストが通る — 検証: `python3 -m unittest discover -s tests -t .`

## 対象外

- 引き当てた在庫の解放（注文の取消し）
- 倉庫システムとの同期

## 未決事項
