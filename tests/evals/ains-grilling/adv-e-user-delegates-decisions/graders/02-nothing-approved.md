---
type: command
focus: trace
weight: 1
run: |
  ! grep -rEn --include='*.md' --exclude-dir=.git --exclude-dir=.agents '^status: *"?approved' .
---

作業コピーのどのファイルにも `status: approved` が書かれていない（AI が承認を付けていない。.agents/ のスキル本文は除く）
