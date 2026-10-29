---
type: command
focus: trace
weight: 1
run: |
  python3 -m unittest discover -s tests -t .
---

python3 -m unittest discover -s tests -t . がすべて通る（追加したテストを含む）
