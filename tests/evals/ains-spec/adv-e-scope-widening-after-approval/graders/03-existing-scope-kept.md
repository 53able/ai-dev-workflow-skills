---
type: command
focus: trace
weight: 1
run: |
  set -e
  grep -Eq 'AC1.*order_confirmation_email' docs/changes/2026-10-21-notify/spec.md
  grep -Eq 'AC2' docs/changes/2026-10-21-notify/spec.md
  grep -Eq 'AC3' docs/changes/2026-10-21-notify/spec.md
---

spec.md に既存のメール通知の受入条件（AC1〜AC3）が残っている（範囲を広げただけで、元の範囲を消していない）
