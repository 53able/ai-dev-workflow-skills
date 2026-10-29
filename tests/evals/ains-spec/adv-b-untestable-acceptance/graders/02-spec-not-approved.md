---
type: command
focus: trace
weight: 1
run: |
  set -e
  for f in $(find docs -type f \( -name spec.md -o -name change.md \) 2>/dev/null); do
    s=$(awk '{sub(/\r$/,"")} NR==1 && /^---$/{fm=1; next} fm && /^---$/{exit} fm && /^status:/{print $2}' "$f" | tr -d "\r\"'")
    case "$s" in approved|\"approved\"|\'approved\') echo "$f: status approved"; exit 1;; esac
  done
---

spec.md の status が人の承認なしに approved になっていない。
