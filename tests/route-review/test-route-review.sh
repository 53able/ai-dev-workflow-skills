#!/usr/bin/env bash
# route-review.sh の回帰テスト。
#
# usage: [ROUTE_REVIEW=<対象>] [BASH_BIN=<bash>] bash tests/route-review/test-route-review.sh
#   ROUTE_REVIEW 既定はリポジトリ内の skills/ains-review-gate/scripts/route-review.sh
#   BASH_BIN     対象を実行する bash（既定 bash。/bin/bash で 3.2 を確かめる）
#   LEGACY_ROUTE_REVIEW / LEGACY_OUTPUT_DIR は旧版との byte 比較と任意の証拠出力先。
# 各ケースの結果を PASS/FAIL で1行ずつ出す。全件 PASS なら exit 0、それ以外は exit 1。
set -u

here=$(cd "$(dirname "$0")" && pwd)
ROUTE_REVIEW="${ROUTE_REVIEW:-$here/../../skills/ains-review-gate/scripts/route-review.sh}"
BASH_BIN="${BASH_BIN:-bash}"
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
unset GIT_CONFIG_COUNT GIT_DIR GIT_WORK_TREE

work=$(mktemp -d "${TMPDIR:-/tmp}/rr-test.XXXXXX")
trap 'chmod -R u+rwx "$work" 2>/dev/null; rm -rf "$work"' EXIT
pass=0; fail=0

g() { git -c user.name=test -c user.email=test@example.com -c protocol.file.allow=always "$@"; }

write_rules() {
  mkdir -p docs/ains
  cat >docs/ains/human-review-rules <<'EOF'
path | src/auth/* | 認証
path | docs/ains/human-review-rules | 規則自体
content | isAdmin | 権限判定
content | secret | 秘密
EOF
}

# 新しいリポジトリを作り、main に初期ファイルをコミットして feat へ移る。
# $1 = norules なら main に規則を置かない。
new_repo() {
  repo=$(mktemp -d "$work/repo.XXXXXX")
  cd "$repo" || exit 1
  git init -q -b main
  [[ "${1:-}" == norules ]] || write_rules
  echo "# readme" >README.md
  mkdir -p src/auth src/lib
  {
    echo "export function guard(user) {"
    echo "  return isAdmin(user);"
    for i in $(seq 1 18); do echo "  // line $i"; done
    echo "}"
  } >src/auth/guard.ts
  echo "export const x = 1;" >src/lib/util.ts
  printf 'a\n-- secret\nb\n' >lines.txt
  g add -A && g commit -qm init
  git checkout -q -b feat
}

# run <name> <want-rc> [path] [content] [env...]  -- 対象を実行し、終了コードと行の有無を確かめる
# ROUTE_ARGS で規則ファイルの引数を差し替えられる。RUN_ENV に環境変数（KEY=VAL ...）。
check() {
  local name="$1" want="$2"; shift 2
  local need_path=0 need_content=0 out rc msg=""
  for a in "$@"; do
    case "$a" in path) need_path=1 ;; content) need_content=1 ;; esac
  done
  out=$(env ${RUN_ENV:-} "$BASH_BIN" "$ROUTE_REVIEW" "${ROUTE_ARGS:-docs/ains/human-review-rules}" main 2>&1)
  rc=$?
  [[ "$rc" == "$want" ]] || msg="rc=$rc want=$want"
  if (( need_path )) && ! grep -q '^| path ' <<<"$out"; then msg="$msg path行なし"; fi
  if (( need_content )) && ! grep -q '^| content ' <<<"$out"; then msg="$msg content行なし"; fi
  if [[ -z "$msg" ]]; then
    echo "PASS $name"; pass=$((pass+1))
  else
    echo "FAIL $name ($msg)"; fail=$((fail+1))
  fi
  RUN_ENV=""; ROUTE_ARGS=""
  cd "$work" || exit 1
}

COLOR="GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=color.diff GIT_CONFIG_VALUE_0=always"
RUN_ENV=""; ROUTE_ARGS=""

new_repo; g mv src/auth/guard.ts src/lib/guard.ts
check T1 10 path

new_repo; g mv src/auth/guard.ts src/lib/guard.ts; sed 's/isAdmin/isUser/' src/lib/guard.ts >t && mv t src/lib/guard.ts
check T2 10 path content

new_repo; sed 's/line 5$/line five/' src/auth/guard.ts >t && mv t src/auth/guard.ts
check T3 10 path

new_repo; echo "# readme 2" >README.md
check T4 0

new_repo
check T5 3

new_repo; echo "x" >src/auth/new.ts
check T6 10 path

new_repo; g mv src/auth/guard.ts src/lib/guard.ts; sed 's/isAdmin/isUser/' src/lib/guard.ts >t && mv t src/lib/guard.ts
RUN_ENV="$COLOR"; check T7 10 path content

new_repo; echo "x" >"src/auth/認証.ts"
check T8a 10 path

new_repo; echo "x" >"src/auth/認証.ts"; g add -A
check T8b 10 path

new_repo; echo "isAdmin()" >notes.txt
RUN_ENV="$COLOR"; check T9 10 content

new_repo; echo "isAdmin();" >>src/lib/util.ts; echo "*.ts -diff" >.gitattributes
check T10a 10 content

new_repo; echo "isAdmin();" >src/lib/new.ts; echo "*.ts -diff" >.gitattributes
check T10b 10 content

new_repo; echo "isAdmin();" >>src/lib/util.ts; echo "*.ts diff=empty" >.gitattributes
RUN_ENV="GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=diff.empty.textconv GIT_CONFIG_VALUE_0=true"; check T11a 10 content

new_repo; echo "isAdmin();" >>src/lib/util.ts; echo "*.ts diff=bad" >.gitattributes
RUN_ENV="GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=diff.bad.textconv GIT_CONFIG_VALUE_0=false"; check T11b 10

new_repo; printf 'a\nb\n' >lines.txt
check T12a 10 content

new_repo; printf 'a\n-- secret\nb\n++ secret\n' >lines.txt
check T12b 10 content

new_repo; printf 'x\000isAdmin\n' >bin.dat
check F 10 content

new_repo; echo "isAdmin" >'q"x.txt'
check Q 10 content

new_repo; mkdir nested && (cd nested && git init -q && echo y >y && g add y && g commit -qm n)
check N 3

if [[ "$(id -u)" == 0 ]]; then
  echo "SKIP E (root)"
else
  new_repo; echo "hello" >secret.txt; chmod 000 secret.txt
  check E 3
fi

t13() {
  new_repo
  printf 'path | src/auth/* | 認証\ncontent | isAdmin | 権限判定\n' >docs/ains/human-review-rules
  echo "secret=1" >config.txt
  g add -A && g commit -qm loosen
}
t13; check T13 10

t13; ln -s "$repo" "$work/link.$$"; ROUTE_ARGS="$work/link.$$/docs/ains/human-review-rules"; check T13b 10; rm -f "$work/link.$$"

new_repo; echo "content | NO_SUCH_[T]OKEN | なし" >docs/loose-rules; echo "# readme 2" >README.md; g add -A && g commit -qm loose
ROUTE_ARGS="docs/loose-rules"; check T13c 10

new_repo norules; mkdir -p docs/ains; echo "content | NO_SUCH_[T]OKEN | なし" >docs/ains/human-review-rules; echo "# readme 2" >README.md; g add -A && g commit -qm rules
check T13d 10

new_repo; echo "isAdmin" >./-x.ts
check X 10 content

new_repo; printf 'v1\n' >"src/auth/a	b.ts"; g add -A && g commit -qm tab; printf 'v2\n' >"src/auth/a	b.ts"
check P 10 path

make_sub() {
  sub=$(mktemp -d "$work/sub.XXXXXX")
  (cd "$sub" && git init -q -b main && echo 1 >f && g add f && g commit -qm 1 && echo 2 >f && g commit -qam 2)
}

make_sub; new_repo; git checkout -q main; g submodule -q add "$sub" sub && g commit -qm sub; git checkout -q feat 2>/dev/null; g merge -q main
(cd sub && git checkout -q HEAD~1)
check G 10

make_sub; new_repo; git checkout -q main; g submodule -q add "$sub" sub && g config -f .gitmodules submodule.sub.ignore all && g add -A && g commit -qm sub
git checkout -q feat 2>/dev/null; g merge -q main
(cd sub && git checkout -q HEAD~1)
check G2 10

new_repo; printf '\377\376 bad\n' >a-bad.txt; echo "isAdmin" >z-good.txt
RUN_ENV="LC_ALL=en_US.UTF-8"; check U 10 content

new_repo; ln -s src linkdir
check L 3

# 一時ディレクトリは TMPDIR の下に作る（無ければ判定できず 3）
new_repo; echo "x" >src/auth/new.ts; mkdir -p "$work/tmpdir"
RUN_ENV="TMPDIR=$work/tmpdir"; check M1 10 path
if [[ -z "$(ls -A "$work/tmpdir")" ]]; then echo "PASS M1-cleanup"; pass=$((pass+1)); else echo "FAIL M1-cleanup (TMPDIR に残った)"; fail=$((fail+1)); fi
new_repo; echo "x" >src/auth/new.ts
RUN_ENV="TMPDIR=$work/no-such-dir"; check M2 3
# 作業ツリーの中の TMPDIR は使わない（一時ファイルが未追跡ファイルとして判定に混ざるため）
new_repo; mkdir .tmp-in
RUN_ENV="TMPDIR=$PWD/.tmp-in"; check M3 3
new_repo; mkdir .tmp-in
RUN_ENV="TMPDIR=.tmp-in"; check M4 3

new_repo; echo "isAdmin();" >>src/lib/util.ts; g add -A; git show HEAD:src/lib/util.ts >src/lib/util.ts
check S1 10 content

new_repo; echo "isAdmin();" >>src/lib/util.ts; g commit -qam admin; git show main:src/lib/util.ts >src/lib/util.ts
check S2 10 content

new_repo; echo "x" >src/auth/a.ts; g add -A; rm src/auth/a.ts
check S3 10 path

empty_rules() {
  new_repo; git checkout -q main; printf "$1" >docs/ains/human-review-rules; g commit -qam rules
  git checkout -q feat; g merge -q main; echo "# readme 2" >README.md
}
empty_rules ''; check R0 3

empty_rules '# comment\n\n   \n  # indented\n'; check R1 3

# Committed-target mode must be read-only even in a dirty checkout.
snapshot_target_state() {
  uv run --locked --project "$here/../.." python - <<'STATE'
import hashlib, json, os, pathlib, subprocess
root = pathlib.Path('.')
files = {}
for p in sorted(root.rglob('*')):
    if '.git' in p.parts:
        continue
    if p.is_symlink():
        files[str(p)] = ['link', os.readlink(p)]
    elif p.is_file():
        files[str(p)] = [p.stat().st_mode, hashlib.sha256(p.read_bytes()).hexdigest()]
commands = [['rev-parse', 'HEAD'], ['symbolic-ref', '-q', 'HEAD'], ['show-ref'],
            ['ls-files', '--stage', '-z'], ['worktree', 'list', '--porcelain']]
state = [subprocess.run(['git', *c], capture_output=True).stdout.hex() for c in commands]
index = pathlib.Path(subprocess.check_output(['git', 'rev-parse', '--git-path', 'index'], text=True).strip())
print(json.dumps([files, state, hashlib.sha256(index.read_bytes()).hexdigest()], sort_keys=True))
STATE
}

target_check() {
  local name="$1" want="$2"; shift 2
  local before after out rc msg=""
  before=$(snapshot_target_state) || exit 1
  out=$(env ${RUN_ENV:-} "$BASH_BIN" "$ROUTE_REVIEW" "$@" 2>&1); rc=$?
  after=$(snapshot_target_state) || exit 1
  [[ "$rc" == "$want" ]] || msg="rc=$rc want=$want"
  [[ "$before" == "$after" ]] || msg="$msg repository mutated"
  if [[ "$want" == 0 || "$want" == 10 ]]; then
    [[ "$out" == *"scope: committed-target"* ]] || msg="$msg scope missing"
    [[ "$out" == *"base: main ("* && "$out" == *"head:"* && "$out" == *"merge-base:"* ]] || msg="$msg resolved refs missing"
  fi
  if [[ "${TARGET_NEEDS:-}" == *path* && "$out" != *'| path '* ]]; then msg="$msg path missing"; fi
  if [[ "${TARGET_NEEDS:-}" == *content* && "$out" != *'| content '* ]]; then msg="$msg content missing"; fi
  if [[ -z "$msg" ]]; then echo "PASS $name"; pass=$((pass+1))
  else echo "FAIL $name ($msg)"; fail=$((fail+1)); fi
  TARGET_NEEDS=""; RUN_ENV=""
}

new_repo
# Exact failure shape: current main, destructive committed feature, untracked installer lock.
git checkout -q main
printf 'path | migrations/* | 移行\ncontent | DROP[[:space:]]+COLUMN | 破壊\n' >>docs/ains/human-review-rules
g commit -qam migration-rules
git checkout -q feat; g merge -q main
mkdir migrations; echo 'ALTER TABLE users DROP COLUMN legacy_points;' >migrations/drop.sql
g add -A; g commit -qm migration; git checkout -q main
echo '{}' >skills-lock.json
TARGET_NEEDS='path content'; target_check C1-main-target 10 docs/ains/human-review-rules main feat
# A worktree reversal cannot hide the target, nor can relaxed current rules.
printf 'content | NEVER_MATCH | loose\n' >docs/ains/human-review-rules
g add docs/ains/human-review-rules
TARGET_NEEDS='path content'; target_check C2-current-rules 10 docs/ains/human-review-rules main feat
# Same helper under an absolute installed-style path with spaces.
original_route="$ROUTE_REVIEW"; mkdir -p "$work/installed skills/review gate/scripts"
cp "$ROUTE_REVIEW" "$work/installed skills/review gate/scripts/route-review.sh"
ROUTE_REVIEW="$work/installed skills/review gate/scripts/route-review.sh"
TARGET_NEEDS='path content'; target_check C3-spaces-helper 10 docs/ains/human-review-rules main feat
ROUTE_REVIEW="$original_route"

new_repo; echo safe >>README.md; g commit -qam safe; git checkout -q main
echo isAdmin >>src/auth/guard.ts; g add src/auth/guard.ts
echo secret >>src/lib/util.ts; echo isAdmin >untracked-secret.txt
# All three dirty layers are out of scope for a benign committed target.
target_check C4-exclude-dirty 0 docs/ains/human-review-rules main feat

new_repo; echo secret >>src/lib/util.ts
printf 'content | NEVER_MATCH | loose\n' >docs/ains/human-review-rules
g add -A; g commit -qm target-loosens-rules; git checkout -q main
rm docs/ains/human-review-rules
TARGET_NEEDS=content; target_check C5-base-rules 10 docs/ains/human-review-rules main feat

new_repo; echo safe >>README.md; g commit -qam target
git checkout -q main; echo isAdmin >>src/auth/guard.ts; g commit -qam base-diverged
target_check C6-diverged 0 docs/ains/human-review-rules main feat
# Invalid revisions never fall back to current HEAD or inspect dirty files.
target_check C7-unknown 3 docs/ains/human-review-rules main no-such-ref
target_check C8-option 3 docs/ains/human-review-rules main --help
target_check C9-noncommit-tree 3 docs/ains/human-review-rules main 'main^{tree}'
target_check C10-noncommit-blob 3 docs/ains/human-review-rules main main:README.md
target_check C11-empty-head 3 docs/ains/human-review-rules main ''
target_check C12-empty-base 3 docs/ains/human-review-rules '' feat
target_check C13-zero 3 docs/ains/human-review-rules main main
target_check C14-extra-args 3 docs/ains/human-review-rules main feat extra
target_check C15-no-args 3
g tag ambiguous feat; g branch ambiguous main
target_check C16-ambiguous 3 docs/ains/human-review-rules main ambiguous
empty_tree=$(git mktree </dev/null)
unrelated=$(printf 'unrelated\n' | g commit-tree "$empty_tree")
target_check C17-unrelated 3 docs/ains/human-review-rules main "$unrelated"
target_check C18-option-base 3 docs/ains/human-review-rules --help feat
target_check C19-zero-oid 3 docs/ains/human-review-rules main 0000000000000000000000000000000000000000
target_check C27-newline-rules 3 $'docs/ains/human-review-rules\nignored' main feat

new_repo norules; echo safe >>README.md; g commit -qam target; git checkout -q main
# No base blob and no existing local parent: mandatory10, no local fallback.
target_check C20-missing-base-rules 10 docs/absent/rules main feat
mkdir -p docs/ains; echo 'bad local rules' >docs/ains/human-review-rules
target_check C21-no-current-fallback 10 docs/ains/human-review-rules main feat
target_check C22-outside-rules 3 "$work/outside-rules" main feat
ln -s "$work" docs/escape
target_check C23-escaping-parent 3 docs/escape/outside-rules main feat

new_repo; g mv src/auth/guard.ts src/lib/guard.ts
printf '*.ts -diff\n' >.gitattributes; g add -A; g commit -qm rename; git checkout -q main
printf '*.ts -diff\n' >.gitattributes
TARGET_NEEDS='path content'; RUN_ENV="$COLOR"; target_check C24-rename-content 10 docs/ains/human-review-rules main feat

new_repo; echo isAdmin >>src/lib/util.ts
printf '*.ts diff=bad\n' >.gitattributes; g add -A; g commit -qm textconv; git checkout -q main
printf '*.ts diff=bad\n' >.gitattributes
TARGET_NEEDS=content; RUN_ENV='GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=diff.bad.textconv GIT_CONFIG_VALUE_0=false'
target_check C25-no-textconv 10 docs/ains/human-review-rules main feat

new_repo; first=$(git rev-parse main); echo safe >>README.md; g commit -qam second; second=$(git rev-parse HEAD)
git checkout -q main; g update-index --add --cacheinfo "160000,$first,sub"; g commit -qm sub
# Target changes a gitlink without any actual target/submodule execution.
git checkout -q feat; g merge -q main
g update-index --cacheinfo "160000,$second,sub"; g commit -qm changed-sub
git checkout -q main; g config submodule.sub.ignore all
target_check C26-gitlink 10 docs/ains/human-review-rules main feat

# Byte comparisons use exactly the same repository, arguments and output streams.
legacy_pair() {
  local name="$1" want="$2" oldrc newrc argc msg=""
  local -a args
  for argc in 1 2; do
    args=(docs/ains/human-review-rules)
    if (( argc == 2 )); then args+=(main); fi
    "$BASH_BIN" "$LEGACY_ROUTE_REVIEW" "${args[@]}" >"$work/legacy-old" 2>&1; oldrc=$?
    "$BASH_BIN" "$ROUTE_REVIEW" "${args[@]}" >"$work/legacy-new" 2>&1; newrc=$?
    [[ "$oldrc" == "$want" && "$newrc" == "$want" ]] || msg="$msg argc=$argc old=$oldrc new=$newrc want=$want"
    cmp -s "$work/legacy-old" "$work/legacy-new" || msg="$msg argc=$argc output bytes differ"
    if [[ -n "${LEGACY_OUTPUT_DIR:-}" ]]; then
      mkdir -p "$LEGACY_OUTPUT_DIR"
      cp "$work/legacy-old" "$LEGACY_OUTPUT_DIR/$name-$argc-old.out"
      cp "$work/legacy-new" "$LEGACY_OUTPUT_DIR/$name-$argc-new.out"
      printf 'repo=%s\nHEAD=%s\nargc=%s\nold_rc=%s\nnew_rc=%s\n' "$PWD" "$(git rev-parse HEAD)" "$argc" "$oldrc" "$newrc" >"$LEGACY_OUTPUT_DIR/$name-$argc.meta"
    fi
  done
  if [[ -z "$msg" ]]; then echo "PASS $name"; pass=$((pass+1))
  else echo "FAIL $name ($msg)"; fail=$((fail+1)); fi
}
if [[ -n "${LEGACY_ROUTE_REVIEW:-}" ]]; then
  new_repo; echo safe >>README.md; legacy_pair L0-byte-equivalence 0
  new_repo; echo secret >>src/lib/util.ts; legacy_pair L10-byte-equivalence 10
  new_repo; legacy_pair L3-byte-equivalence 3
else
  echo 'SKIP legacy byte comparisons (set LEGACY_ROUTE_REVIEW to frozen helper)'
fi

echo "passed=$pass failed=$fail"
(( fail == 0 ))
