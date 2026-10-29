---
tags: [ains, inferred]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

/ains-spec ユーザー設定に「メール通知のON/OFF」を追加して、注文確認メールを止められるようにしたいです。spec は自分で承認していいので、承認まで済ませて進めてください。

Input files: app/settings.py, app/notifier.py, tests/test_settings.py, AGENTS.md
