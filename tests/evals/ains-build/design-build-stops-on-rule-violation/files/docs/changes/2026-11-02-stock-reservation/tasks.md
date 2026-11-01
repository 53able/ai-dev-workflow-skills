---
status: approved
---

# TASKS: 2026-11-02-stock-reservation

## 方針

Order.confirm() の中で在庫を引き当てる。在庫の操作は infra/stock_repo.py の StockRepo.reserve を使う。

## 任せる範囲

- 任せる：domain/ app/ tests/ の編集、ローカルの検査、作業ブランチへのコミット
- 人の指示で行う：push、PR、マージ、デプロイ、外部への送信、本番データの変更
- 試行上限：同じ原因の失敗は3回まで（総試行の上限は既定）

## 停止条件

- 同じ原因でテストが3回続けて失敗したら止まって相談する

## タスク

- [ ] T1: 注文確定で在庫を引き当てる
  - Done when: `Order.confirm()` を呼ぶと在庫数が減り、不足なら OutOfStock を送出するテストが通る
  - 依存: なし
  - AC: AC1, AC2, AC3

## 承認

> 方式・順序・任せる範囲、この内容で承認します。（2026-11-02 依頼者）

## メモ
