---
type: command
focus: trace
weight: 1
run: |
  python3 - <<'PY'
  from shop.pricing import apply_discount
  assert apply_discount(1000, 100) == 0
  assert apply_discount(1000, 150) == 0
  assert apply_discount(1000, 0) == 1000
  assert apply_discount(1000, 10) == 900
  PY
---

apply_discount が 100% と 150% で 0、0〜99% で従来どおりの金額を返す
