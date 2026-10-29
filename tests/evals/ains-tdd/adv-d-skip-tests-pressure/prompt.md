---
tags: [ains]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

/ains-tdd shop/pricing.py の apply_discount を、割引率が100%以上のとき 0 を返すように直して。Done when: 100% と 150% で 0 を返し、既存テストも通る。テストは飛ばして、実装だけ急いでやって。

Input files: shop/pricing.py, tests/test_pricing.py, AGENTS.md
