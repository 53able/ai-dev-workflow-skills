---
tags: [ains]
max_turns: 30
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

/ains-spec docs/changes/2026-10-21-notify の仕様を更新してください。いま対象外にしている SMS 通知の ON/OFF も、同じ変更の範囲に入れたいです。

Input files: app/settings.py, app/notifier.py, tests/test_settings.py, AGENTS.md, docs/changes/2026-10-21-notify/
