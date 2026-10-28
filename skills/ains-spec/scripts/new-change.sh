#!/usr/bin/env bash
# 変更ディレクトリを作り、spec.md の雛形を置く。既存の spec.md は上書きしない。
#
# usage: new-change.sh <slug> [--root <dir>]
#   --root  作成先の親ディレクトリ（既定: docs/changes）
# 出力: 作成したディレクトリのパス
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tpl="$here/../assets/spec.md"

slug="" root="docs/changes"
while (( $# )); do
  case "$1" in
    --root)
      [[ $# -ge 2 && "$2" != -* ]] || { echo "--root には値が必要" >&2; exit 2; }
      root="$2"; shift ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) slug="$1" ;;
  esac
  shift
done

if [[ ! "$slug" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
  echo "usage: new-change.sh <slug: 小文字英数字とハイフン> [--root <dir>]" >&2
  exit 2
fi

dir="$root/$(date +%Y-%m-%d)-$slug"
mkdir -p "$dir"
if [[ -e "$dir/spec.md" || -L "$dir/spec.md" ]]; then
  echo "skip (exists): $dir/spec.md" >&2
else
  sed "s/{{CHANGE_ID}}/$(basename "$dir")/g" "$tpl" >"$dir/spec.md"
fi
echo "$dir"
