---
status: approved
---

# TASKS: 2026-10-21-notify

## 方針

DEFAULTS に order_confirmation_email を足し、send_order_confirmation の先頭で設定を読んで送るかを決める。

## 任せる範囲

- 任せる：編集、ローカルの検査、作業ブランチへのコミット
- 人の指示で行う：push、PR、マージ、デプロイ、外部への送信、本番データの変更

## 停止条件

- 既存の設定ファイルの形式を変える必要が出たら止めて相談する

## タスク

- [ ] T1: メール通知の ON/OFF 設定を追加する
  - Done when: AC1 と AC2 のテストが通り、既存テストも通る
  - 依存: なし
  - AC: AC1, AC2
- [ ] T2: 保存失敗時の扱いを実装する
  - Done when: AC3 のテストが通る
  - 依存: T1
  - AC: AC3

## メモ
