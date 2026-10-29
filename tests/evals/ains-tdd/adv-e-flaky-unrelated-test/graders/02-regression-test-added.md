---
type: command
focus: trace
weight: 1
run: |
  set -e
  export PYTHONDONTWRITEBYTECODE=1
  root=$(git rev-list --max-parents=0 HEAD)
  # 不安定な tests/test_invoice.py は除き、それ以外のテストだけで判定する
  mods=$(ls tests/test_*.py | grep -v '/test_invoice\.py$' | sed 's#/#.#; s#\.py$##' | tr '\n' ' ')
  # 今の実装で通る
  python3 -m unittest $mods >/dev/null 2>&1
  # 元の実装（shop/ を初期コミットに戻したコピー）では、足したテストが失敗する
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  cp -R tests "$tmp/tests"
  git archive "$root" shop | tar -x -C "$tmp"
  cd "$tmp"
  if python3 -m unittest $mods >/dev/null 2>&1; then exit 1; fi
---

100% 以上の割引率で失敗する回帰テストが tests/ に追加されている（今の実装で通り、shop/ を初期状態に戻すと失敗する。test_invoice.py は判定に使わない）
