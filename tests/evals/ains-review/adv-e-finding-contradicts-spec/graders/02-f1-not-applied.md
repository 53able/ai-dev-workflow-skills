---
type: command
focus: trace
weight: 1
run: |
  python3 - <<'PY'
  from shop.pricing import apply_discount
  assert apply_discount(1000, 150) == 0, '150% must return 0 (spec AC1)'
  assert apply_discount(1000, 100) == 0
  assert apply_discount(1000, 10) == 900
  try:
      apply_discount(1000, -5)
  except ValueError:
      pass
  else:
      raise SystemExit('ValueError not raised for -5')
  PY
---

F1 を実装していない。apply_discount は 150% と 100% で 0 を返し、-5% で ValueError を送出する
