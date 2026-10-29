---
tags: [ains, inferred]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

/ains-tdd shop/pricing.py の apply_discount は、割引率が100%以上のとき負の金額を返すバグがあります。ains-tdd で直してください。

Input files: shop/pricing.py, tests/test_pricing.py, tests/test_invoice.py, AGENTS.md
