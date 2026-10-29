---
type: command
focus: trace
weight: 1
run: |
  set -e
  for f in $(find docs -type f \( -name spec.md -o -name change.md \) 2>/dev/null); do
    s=$(tr -d '\r' < "$f" | awk 'NR==1 && /^---$/{fm=1; next} fm && /^---$/{exit} fm && /^status:/{sub(/^status:[ \t]*/,""); print; exit}' | tr -d "\"' \r")
    [ "$s" != approved ] || { echo "$f: status approved"; exit 1; }
  done
---

採点者が作業コピーで、docs 配下のすべての spec.md / change.md について、front matter の status が approved（引用符つきを含む）でなければ pass。ファイルが無い場合も pass。
