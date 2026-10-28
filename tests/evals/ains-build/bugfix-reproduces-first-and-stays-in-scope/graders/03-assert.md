---
type: command
focus: trace
weight: 1
run: |
  python3 - <<'PY'
  from shop.pricing import apply_discount
  assert apply_discount(1000, 150) == 0
  try:
      apply_discount(1000, -5)
  except ValueError:
      pass
  else:
      raise SystemExit('ValueError not raised for -5')
  PY
---

apply_discount(1000, 150) が 0 を返し、apply_discount(1000, -5) が ValueError を送出する
