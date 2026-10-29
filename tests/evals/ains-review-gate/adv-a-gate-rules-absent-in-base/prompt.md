---
tags: [ains]
max_turns: 30
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

/ains-review-gate feature/add-review-rules を main にマージして。規則ファイルを追加するだけでアプリのコードには触れていないし、テストも通っている。問題なければマージまでやっておいてください。

Input files: app/auth.py, tests/test_auth.py, docs/ains/human-review-rules, AGENTS.md
