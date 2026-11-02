---
type: llm
focus: trace
weight: 1
---

docs/changes/2026-11-02-order-confirmation-mail/tasks.md の方針とタスクが、実装が1つしかない不要な抽象を計画していないかを判定する。

fail にする計画（どれか1つでも当たれば fail）:
- 通知経路の interface や抽象を新しく作る（例: Notifier、NotificationChannel、MailSender、Protocol、ABC・抽象基底クラス）
- Strategy、Factory、登録表（registry）、プラグイン、経路の切替設定など、複数の経路を差し替えるための仕組みを作る
- 「将来 SMS を足せるように」など、spec の対象外（SMS などメール以外の経路）を理由にした拡張点を作る

例外: spec.md・AGENTS.md・ADR に既にある規則を守るのに、その抽象が必要だと方針に書いている場合は fail にしない。ただし、この fixture の spec.md と AGENTS.md にはそのような規則は無い（AGENTS.md は Python のバージョンとテストコマンドだけ）。同じ tasks.md で新しく宣言した規則は根拠として数えない。

pass にする計画: 既存の infra/smtp_client.py の SmtpClient（SmtpClient.send）を app 層（app/place_order.py）から使ってメールを送る。テストで SmtpClient を差し替える（unittest.mock、テスト用の偽物を引数で渡すなど）のは抽象の追加として数えない。place_order が SmtpClient を引数で受け取るだけの変更も数えない。

tasks.md が無い場合は fail。
