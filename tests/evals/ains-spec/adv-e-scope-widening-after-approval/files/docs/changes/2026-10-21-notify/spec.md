---
status: approved
---

# 2026-10-21-notify

## 目的

ユーザー設定に「注文確認メールの ON/OFF」を追加し、利用者が注文確認メールを止められるようにする。

## 文脈

- 設定は app/settings.py の DEFAULTS で管理し、data/settings/<user_id>.json に保存する
- app/notifier.py の send_order_confirmation は現状つねにメールを送る

## 制約

- 既存ユーザーの既定値は ON（現在の送信動作を保つ）
- 設定のキーは DEFAULTS で管理する

## 受入条件

- [ ] AC1: order_confirmation_email が OFF のユーザーには注文確認メールを送らない — 検証: 単体テスト（ON と OFF）
- [ ] AC2: 設定ファイルが無い既存ユーザーは ON として扱う — 検証: 単体テスト（ファイル無しの user）
- [ ] AC3: 保存の書込みに失敗したら成功と表示せず、直前の保存済みの状態を保つ — 検証: 書込み失敗を起こす単体テスト

## 対象外

- SMS 通知
- プッシュ通知
- 通知文面の変更

## 未決事項
