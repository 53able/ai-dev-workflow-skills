---
status: approved
---

# TASKS: 2026-11-01-invoice-rounding

## 方針

税の計算を shop/order.py に寄せ、shop/invoice.py は Order の値を表示するだけにする。

## 任せる範囲

## 停止条件

## タスク

- [x] T1: 税を明細ごとに切り捨てる
  - Done when: 105円の明細2つで税が20円になり、請求書の明細に税が出るテストが通る
  - 依存: なし
  - AC: AC1
- [x] T2: 請求書の合計を Order の支払額に揃える
  - Done when: 割引のある注文で、請求書の合計と Order.total() が一致するテストが通る
  - 依存: T1
  - AC: AC2
- [x] T3: 送料に税を掛ける
  - Done when: 送料500円の注文で送料の税が50円になり、請求書に出るテストが通る
  - 依存: T2
  - AC: AC3

## 承認

> この3点で承認します。（2026-11-01 依頼者）

## メモ

- legacy/report.py が読みにくいので書き直したい
