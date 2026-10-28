#!/usr/bin/env bash
# 変更ファイルと差分を規則ファイルに照合し、人間の確認が必須かを決定的に判定する。
#
# usage: route-review.sh <rules-file> [base-ref] [head-ref]
#   base-ref 省略時は origin/main、無ければ main。コミット済み・index・作業ツリーの変更と未追跡ファイルを対象に含める。
#   base-ref は PR のマージ先にする。リポジトリのルートへ移ってから列挙する。
#   head-ref 指定時は base/head をコミットへ固定し、merge-base..head のコミット済み差分だけを照合する。
#   このモードは index・作業ツリー・未追跡を含めず、規則は base の blob だけを読む。
#
# 規則ファイルの書式（1行1規則、# で始まる行と空行は無視）:
#   path    | <bash glob>        | <理由>
#   content | <拡張正規表現>     | <理由>
# 最初と最後の | で分割するため、パターン内の | はそのまま書ける。理由には | を含めない。
# glob の * は / も跨ぐ（例: src/auth/* は src/auth/a/b.ts にも一致する）。
# content は追加・削除された行（+/-）に対して照合する。
# path の照合は大文字小文字を区別しない（*auth* は src/AuthController.ts にも一致する）。
#
# 制約（差分の中身で判定を外せないようにするため）:
#   - rename は削除と追加として照合する（--no-renames。移動したファイルは全行を照合する）。
#   - 色、外部 diff、textconv、-diff 属性は無視する（--no-color --no-ext-diff --no-textconv --text）。
#   - 差分中の NUL は空白に置き換えてから照合する。ロケールは C で照合する。
#   - 規則は base の版を使う。base に規則ファイルが無ければ（規則の導入・移動）exit 10。
#     そのため規則の追加はマージ後の変更から効く。
#   - gitlink（サブモジュール）の変更は exit 10。.gitmodules の ignore 設定は無視する。
#   - git のいずれかが失敗した、または未追跡のパスを差分にできない（入れ子のリポジトリ、
#     ディレクトリを指すリンク、読めないファイル）ときは exit 3。
#
# exit code:
#   0  必須確認の規則に一致なし（AIのリスク評価へ進めてよい。不明なら人へ戻す）
#   10 必須確認の規則に一致あり、規則ファイルが base に無い、またはサブモジュールの変更（AIの判定で解除しない）
#   3  規則ファイルが無い、有効な規則が0件、差分を取得できない、変更が0件、規則の書式が不正（UNVERIFIED。人へ戻す）
set -u
export LC_ALL=C

rules="${1:-}"
base="${2:-}"
head="${3:-}"
target_mode=0
if (( $# > 3 )); then
  echo "UNVERIFIED: 引数は <rules-file> [base-ref] [head-ref]" >&2
  exit 3
fi
if (( $# == 3 )); then
  target_mode=1
  if [[ -z "$rules" || "$rules" == *$'\n'* || -z "$base" || -z "$head" || "$base" == -* || "$head" == -* ]]; then
    echo "UNVERIFIED: committed-target の規則パスと base/head を指定する" >&2
    exit 3
  fi
fi

if (( ! target_mode )) && [[ -z "$rules" || ! -f "$rules" ]]; then
  echo "UNVERIFIED: 規則ファイルが見つからない: ${rules:-<未指定>}" >&2
  exit 3
fi

if (( target_mode )); then
  top=$(git rev-parse --show-toplevel) || { echo "UNVERIFIED: リポジトリのルートを求められない" >&2; exit 3; }
  top=$(cd "$top" && pwd -P) || exit 3
  prefix=$(git rev-parse --show-prefix) || exit 3
  case "$rules" in
    "$top"/*) rel="${rules#"$top"/}" ;;
    /*) echo "UNVERIFIED: 規則パスがリポジトリ外: $rules" >&2; exit 3 ;;
    *) rel="$prefix$rules" ;;
  esac
  case "/$rel/" in
    *'/../'*|*'/./'*|*'//'*) echo "UNVERIFIED: 規則パスを正規化して指定する: $rules" >&2; exit 3 ;;
  esac
  # 未作成の規則パスも許すが、既存の親リンクでリポジトリ外へ出ない。
  IFS=/ read -r -a rule_parts <<<"$rel"
  parent="$top"
  for (( i=0; i<${#rule_parts[@]}-1; i++ )); do
    parent="$parent/${rule_parts[i]}"
    if [[ -d "$parent" ]]; then
      parent=$(cd "$parent" && pwd -P) || exit 3
      if [[ "$parent" != "$top" && "$parent" != "$top/"* ]]; then
        echo "UNVERIFIED: 規則パスがリポジトリ外: $rules" >&2; exit 3
      fi
    elif [[ -e "$parent" || -L "$parent" ]]; then
      echo "UNVERIFIED: 規則の親ディレクトリを解決できない: $rules" >&2; exit 3
    fi
  done
  rel="${parent#"$top"}/${rule_parts[${#rule_parts[@]}-1]}"; rel="${rel#/}"
else
# ルートへ移る前に、規則ファイルの位置を解決する
rules_dir=$(cd "$(dirname "$rules")" && pwd -P) || { echo "UNVERIFIED: 規則ファイルの場所を解決できない: $rules" >&2; exit 3; }
rules_abs="$rules_dir/$(basename "$rules")"
prefix=$(cd "$rules_dir" && git rev-parse --show-prefix) || { echo "UNVERIFIED: 規則ファイルのリポジトリ内のパスを求められない: $rules" >&2; exit 3; }
rel="$prefix$(basename "$rules")"

top=$(git rev-parse --show-toplevel) || { echo "UNVERIFIED: リポジトリのルートを求められない" >&2; exit 3; }
fi
cd "$top" || exit 3

if [[ -z "$base" ]]; then
  if git rev-parse --verify -q origin/main >/dev/null; then base=origin/main
  elif git rev-parse --verify -q main >/dev/null; then base=main
  else
    echo "UNVERIFIED: base-ref を決められない。引数で指定する" >&2
    exit 3
  fi
fi

if (( target_mode )); then
  # --end-of-options と ^{commit} で option/blob/tree を排除する。
  # 曖昧な ref の警告も単一 OID ではないため拒否する。
  oid_re='^([0-9a-f]{40}|[0-9a-f]{64})$'
  base_oid=$(git -c core.warnAmbiguousRefs=true rev-parse --verify --end-of-options "$base^{commit}" 2>&1) || {
    echo "UNVERIFIED: base をコミットに解決できない: $base" >&2; exit 3;
  }
  head_oid=$(git -c core.warnAmbiguousRefs=true rev-parse --verify --end-of-options "$head^{commit}" 2>&1) || {
    echo "UNVERIFIED: head をコミットに解決できない: $head" >&2; exit 3;
  }
  if [[ ! "$base_oid" =~ $oid_re || ! "$head_oid" =~ $oid_re ]]; then
    echo "UNVERIFIED: base/head が一意なコミットではない" >&2; exit 3
  fi
  merge_base=$(git merge-base --all "$base_oid" "$head_oid" 2>/dev/null) || {
    echo "UNVERIFIED: base/head に共通の履歴がない" >&2; exit 3;
  }
  if [[ ! "$merge_base" =~ $oid_re ]]; then
    echo "UNVERIFIED: merge-base が一意ではない" >&2; exit 3
  fi
else
merge_base=$(git merge-base "$base" HEAD 2>/dev/null) || {
  echo "UNVERIFIED: $base と HEAD の merge-base を取得できない" >&2
  exit 3
}
fi

tmp=$(mktemp -d) || { echo "UNVERIFIED: 一時ディレクトリを作れない" >&2; exit 3; }
trap 'rm -rf "$tmp"' EXIT

# 規則は base の版を読む。変更の中で規則を消したり差し替えたりしても判定を外せないようにする。
rules_missing=0
rules_ref="$base"
if (( target_mode )); then rules_ref="$base_oid"; fi
if git cat-file -e "$rules_ref:$rel" 2>/dev/null; then
  git show "$rules_ref:$rel" >"$tmp/rules" || { echo "UNVERIFIED: base の規則ファイルを読めない: $base:$rel" >&2; exit 3; }
  rules_src="$tmp/rules"
else
  rules_missing=1
  if (( target_mode )); then
    : >"$tmp/rules"; rules_src="$tmp/rules"
  else
    rules_src="$rules_abs"
  fi
fi

DIFF_OPTS=(--no-renames --no-color --no-ext-diff --no-textconv --text --ignore-submodules=none)

# コミット済み（merge-base..HEAD）、index、作業ツリーの3つの差分の和集合を照合する。
# stage やコミットのあとで作業ツリーだけ戻しても変更を見落とさないようにする。
NAME_OPTS=(--no-renames --ignore-submodules=none)
if (( target_mode )); then
  git diff "${NAME_OPTS[@]}" --name-only -z "$merge_base" "$head_oid" >"$tmp/names" \
    || { echo "UNVERIFIED: 変更ファイルの一覧を取得できない" >&2; exit 3; }
  git diff "${NAME_OPTS[@]}" --raw "$merge_base" "$head_oid" >"$tmp/rawmode" \
    || { echo "UNVERIFIED: 変更ファイルのモードを取得できない" >&2; exit 3; }
  git diff "${DIFF_OPTS[@]}" "$merge_base" "$head_oid" >"$tmp/raw" \
    || { echo "UNVERIFIED: 差分を取得できない" >&2; exit 3; }
  : >"$tmp/untracked"
else
{ git diff "${NAME_OPTS[@]}" --name-only -z "$merge_base" HEAD \
  && git diff "${NAME_OPTS[@]}" --name-only -z --cached "$merge_base" \
  && git diff "${NAME_OPTS[@]}" --name-only -z "$merge_base"; } >"$tmp/names" \
  || { echo "UNVERIFIED: 変更ファイルの一覧を取得できない" >&2; exit 3; }
{ git diff "${NAME_OPTS[@]}" --raw "$merge_base" HEAD \
  && git diff "${NAME_OPTS[@]}" --raw --cached "$merge_base" \
  && git diff "${NAME_OPTS[@]}" --raw "$merge_base"; } >"$tmp/rawmode" \
  || { echo "UNVERIFIED: 変更ファイルのモードを取得できない" >&2; exit 3; }
{ git diff "${DIFF_OPTS[@]}" "$merge_base" HEAD \
  && git diff "${DIFF_OPTS[@]}" --cached "$merge_base" \
  && git diff "${DIFF_OPTS[@]}" "$merge_base"; } >"$tmp/raw" \
  || { echo "UNVERIFIED: 差分を取得できない" >&2; exit 3; }
git ls-files -z --others --exclude-standard >"$tmp/untracked" \
  || { echo "UNVERIFIED: 未追跡ファイルの一覧を取得できない" >&2; exit 3; }

while IFS= read -r -d '' f; do
  if [[ -d "$f" ]] || [[ ! -f "$f" && ! -L "$f" ]]; then
    echo "UNVERIFIED: 未追跡のパスを差分にできない: $f" >&2
    exit 3
  fi
  git diff --no-index "${DIFF_OPTS[@]}" /dev/null -- "$f" >>"$tmp/raw"; rc=$?
  if (( rc != 0 && rc != 1 )); then
    echo "UNVERIFIED: 差分を取得できない: $f" >&2
    exit 3
  fi
done <"$tmp/untracked"

fi

cat "$tmp/names" "$tmp/untracked" | sort -zu >"$tmp/files"
ps=("${PIPESTATUS[@]}")
if (( ps[0] != 0 || ps[1] != 0 )); then
  echo "UNVERIFIED: 変更ファイルの一覧を作れない" >&2
  exit 3
fi
nfiles=$(tr -cd '\000' <"$tmp/files" | wc -c | tr -d ' ')
if [[ "$nfiles" == 0 ]]; then
  echo "UNVERIFIED: $base との差分が0件（統合済み、または base の指定違い）。判定できないため人へ戻す" >&2
  exit 3
fi

# 差分の見出し（diff --git から @@ まで）を除き、hunk 内の追加・削除行だけを取り出す
tr '\000' ' ' <"$tmp/raw" | awk '/^diff --git /{h=1; next} /^@@/{h=0; next} !h && /^[+-]/' >"$tmp/lines"
ps=("${PIPESTATUS[@]}")
if (( ps[0] != 0 || ps[1] != 0 )); then
  echo "UNVERIFIED: 差分の行を取り出せない" >&2
  exit 3
fi

trim() { local s="$1"; s="${s#"${s%%[![:space:]]*}"}"; printf '%s' "${s%"${s##*[![:space:]]}"}"; }

shopt -s nocasematch
hits=0
echo "| 規則 | 一致 | 理由 |"
echo "|---|---|---|"

if (( rules_missing )); then
  echo "| base の規則 | \`$rel\` | 規則ファイルが base に無い（規則の導入・移動） |"; hits=$((hits+1))
fi

grep -qE '^:(160000 [0-7]{6}|[0-7]{6} 160000) ' "$tmp/rawmode"; rc=$?
if (( rc == 0 )); then
  echo "| gitlink | mode 160000 | サブモジュールの変更 |"; hits=$((hits+1))
elif (( rc > 1 )); then
  echo "UNVERIFIED: サブモジュールの変更を判定できない" >&2
  exit 3
fi

nrules=0
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$(trim "$line")" || "$(trim "$line")" == \#* ]] && continue
  nrules=$((nrules+1))
  # パターン内の | を許すため、最初と最後の | で分割する
  if [[ "$line" != *"|"*"|"* ]]; then
    echo "UNVERIFIED: 規則の書式が不正（<種別> | <パターン> | <理由> が必要）: $line" >&2
    exit 3
  fi
  rest="${line#*|}"
  kind=$(trim "${line%%|*}"); pattern=$(trim "${rest%|*}"); reason=$(trim "${rest##*|}")
  case "$kind" in
    path)
      while IFS= read -r -d '' f; do
        # shellcheck disable=SC2053
        if [[ "$f" == $pattern ]]; then
          echo "| path \`$pattern\` | \`$f\` | $reason |"; hits=$((hits+1))
        fi
      done <"$tmp/files"
      ;;
    content)
      m=$(grep -E -m1 -- "$pattern" "$tmp/lines"); rc=$?
      if (( rc == 0 )); then
        echo "| content \`${pattern//|/\\|}\` | \`${m:0:80}\` | $reason |"; hits=$((hits+1))
      elif (( rc > 1 )); then
        echo "UNVERIFIED: 正規表現を評価できない: $pattern" >&2
        exit 3
      fi
      ;;
    *)
      echo "UNVERIFIED: 不明な規則種別: $kind" >&2
      exit 3
      ;;
  esac
done <"$rules_src"
if (( nrules == 0 && !(target_mode && rules_missing) )); then
  echo "UNVERIFIED: 有効な規則が無い（空、またはコメント・空行だけ）: $rel" >&2
  exit 3
fi

echo
if (( target_mode )); then
  echo "scope: committed-target  base: $base ($base_oid)  head: $head ($head_oid)  merge-base: $merge_base  規則: $rel  変更ファイル数: $nfiles"
else
  echo "base: $base ($merge_base)  規則: $rel  変更ファイル数: $nfiles"
fi
if (( hits > 0 )); then
  echo "判定: HUMAN_REQUIRED（一致 $hits 件）"
  exit 10
fi
echo "判定: NO_MANDATORY_MATCH（AIのリスク評価へ。不明なら人へ戻す）"
exit 0
