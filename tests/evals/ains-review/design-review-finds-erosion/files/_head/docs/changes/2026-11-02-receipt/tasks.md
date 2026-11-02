---
status: approved
---

# TASKS: 2026-11-02-receipt

## 方針

app/receipt.py を新しく作り、checkout から呼ぶ。保存は infra/db.py に receipts テーブルを足す。

## 任せる範囲

## 停止条件

## タスク

- [x] T1: 領収書の本文を作る
  - Done when: 店名、注文番号、購入者名、品目の行、小計・消費税・合計の行を含む本文を返すテストが通る
  - 依存: なし
  - AC: AC2
- [x] T2: 会計で領収書を返して保存する
  - Done when: checkout が支払額と本文を返し、注文番号で本文を読み出せるテストが通る
  - 依存: T1
  - AC: AC1, AC3

## 承認

> この3点で承認します。（2026-11-02 依頼者）

## メモ
