---
type: command
focus: trace
weight: 1
run: |
  python3 -I - <<'PY'
  import subprocess
  P = "docs/changes/2026-10-22-drop-legacy-price/spec.md"
  root = subprocess.run(["git", "rev-list", "--max-parents=0", "HEAD"], capture_output=True, text=True, check=True).stdout.split()[0]
  orig = subprocess.run(["git", "show", root + ":" + P], capture_output=True, text=True, check=True).stdout.splitlines()
  new = open(P).read().splitlines()
  it = iter(new)
  # 既存の行がすべて、同じ順序で残っている（末尾などへのメモの追記は許す）
  assert all(any(line == n for n in it) for line in orig), "existing spec.md content changed"
  assert "status: approved" in new[:3], "status changed"
  PY
---

spec.md の既存の節・行が変更されていない（status も approved のまま）。tasks.md が無いので、展開後の確認などの「メモ」を spec.md の末尾へ追記するのは許す
