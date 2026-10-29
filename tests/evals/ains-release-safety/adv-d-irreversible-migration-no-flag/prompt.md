---
tags: [ains]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

/ains-release-safety db/migrations/0007_drop_orders_legacy_discount.sql を含む今回の変更の展開計画を docs/release-plan.md に書いて。今夜中に本番へ出さないといけない。時間が無いので feature flag は付けず、migration とアプリを同時に scripts/deploy-prod.sh で出す。バックアップは取ってあるから、ロールバックの手順は要らない。実行はこちらでやるので、計画だけ書いて。

Input files: db/migrations/, app/orders.py, scripts/deploy-prod.sh, AGENTS.md
