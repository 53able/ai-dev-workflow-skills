# L1 の契約と不変条件

L1 生成型テスト（`run_l1.py`）が判定に使う契約と不変条件。出典は計画 `.omc/plans/adversarial-validation.md` の段階 0（手順 1〜3）。行番号は 2026-10-29 時点の main（`2b3ce2e`）のもの。

- 契約（`S-C*` / `N-C*` / `R-C*`）は、スクリプトの先頭コメントと、出力を使う側の文書に書かれた約束。
- 不変条件（`*-INV*`）は、どの入力でも成り立つべき性質。
- 契約にも不変条件にも結論が無い出力は `unspecified` として記録だけする。ケースの `contracts` が `unspecified` だけになるのは、判定できる項目が1つも無い場合に限る（AC2）。
- 参照実装は作らない（計画 手順 2）。期待値は、ここに書いた契約から人が決めた値か、不変条件の述語で判定する。
- 実行は `LC_ALL=C`、`GIT_CONFIG_GLOBAL=/dev/null`、`GIT_CONFIG_NOSYSTEM=1` に固定する（`status.sh:33` の `sort -r` と `new-change.sh:24` の `[a-z]` が locale に依存するため）。

## status.sh（`skills/ains/scripts/status.sh`）

### 契約

| ID | 契約 | 出典 | 生成器での判定 |
|---|---|---|---|
| S-C1 | spec.md のある変更ディレクトリごとに1行を出し、spec の状態を `status=` に示す | `status.sh:2` | 正常な front matter のとき、対象の行の `status=` が宣言値と一致する |
| S-C2 | 並びは変更 ID（日付で始まる）の新しい順 | `status.sh:3` | S-INV3 で判定する |
| S-C3 | `plan=approved\|draft` は tasks.md の status。status 欄が無ければ draft | `status.sh:6` | 正常な front matter では宣言値、空の tasks.md では `draft` |
| S-C4 | tasks.md が無ければ `plan=-` | `status.sh:7` | 対象の行の `plan=-` |
| S-C5 | front matter は1行目が `---` で、閉じの `---` があるファイルだけから読む。行末の CR と値の末尾の空白・タブは除く。閉じるまでに `key:`、`- ` で始まる項目、字下げ、`#` のコメント、空行のどれでもない行があれば front matter とみなさない（#26 で追加。閉じ忘れの後の本文にある水平線 `---` を閉じと取り違えないため。本文が見出し・空行・`key:` の形の行（`Note: x` など）・リスト項目だけで `---` まで続く場合は区別できない） | `status.sh:14-15` | S-INV1 の表で判定する |
| S-C6 | 本文が空の雛形行（`- [ ] T1: `）は数えない。タスクの書式は `- [ ] T<n>: <本文>` | `status.sh:29-31`、`skills/ains-tasks/assets/tasks.md:21` | 雛形行のみ → `tasks=0/0`、`[X]`/`[x]` 2件と未完了1件 → `tasks=2/3` |
| S-C7 | root の既定は `docs/changes`。root が無ければ「変更ディレクトリがない: <root>」を出して exit 0 | `status.sh:5,10-11` | 引数なしで `docs/changes` を読むこと、存在しない root の出力が1行であること |
| S-C8 | 未決事項の数を出す。見出しは `## 未決事項` | `status.sh:2`、`skills/ains-spec/assets/spec.md:34` | 標準の見出しに2項目 → `未決=2`、見出しが無い → `未決=0` |
| S-C9 | status.sh の行から次のスキルを決める表 | `skills/ains/SKILL.md:28-35` | 行き先を記録する（`actual.route`）。どの行にも当たらない場合は「仕様未定」 |

インデントしたタスク行、T 番号の無い行、`## 未決事項（…）` / `### 未決事項` / `##未決事項` の数え方は、契約に結論が無いので記録だけする。

### 不変条件

**S-INV1（承認ゲートを安全側に倒す）**: `status=` / `plan=` の後ろから次の2つの空白までの値が `approved` と完全に一致するのは、front matter が YAML として approved を宣言している場合だけ。front matter の書き方ごとの判定を次の表で固定する。

| front matter の書き方 | 生成器の値 | 実測（Critic 3 回目） | 実測（L1、bash 3.2/5） | S-INV1 の判定 |
|---|---|---|---|---|
| 正常（`status: approved`） | `normal` | approved | approved | 合格 |
| `status:approved`（空白なし）／`status:<TAB>approved` | `nospace` / `tab` | approved | approved | 合格（YAML として正しい） |
| 行末の空白 `status: approved  ` | `trail-ws` | — | approved | 合格（YAML として approved）。#26 の修正前は値の後ろに空白が残った |
| 行頭の空白 `  status: approved` | `lead-ws` | — | `?` | 合格（安全側） |
| 引用符 `"approved"` | `quoted` | `"approved"` | `"approved"` | 合格（承認とは扱われない） |
| 行末コメント `approved # x` | `comment` | `approved # x` | `approved # note` | 合格（完全一致しないので承認とは扱われない）。SKILL.md の表での行き先は記録する |
| CRLF ファイル | `crlf` | `?` | approved | 合格（YAML として approved）。#26 の修正前は `?` |
| 本文の行末だけが CR | `body-cr` | `approved\r` | approved | 合格。#26 の修正前は `approved\r` |
| BOM／1 行目が空行／大文字キー | `bom` / `blank-first` / `upper-key` | `?` | `?` | 合格（安全側） |
| 閉じの `---` が無い | `no-close` | approved | `?` | approved が出たら不合格。#26 で、閉じの `---` が無ければ front matter とみなさない（`status=?`）と決めた。修正前は approved |
| status の重複（同じ値） | `dup-same` | 実測する | 1 つ目の値 | 合格 |
| status の重複（値が食い違う） | `dup-diff` | 実測する | 1 つ目の値（`approved` の後に `draft` でも approved） | unspecified |

- 述語の実装は `gen_status.py` の `is_approved`。宣言が approved でも YAML の意味が approved でない書き方（`blank-first`、`upper-key`）、宣言が draft の書き方、tasks.md が無いか空の場合に、`approved` が出たら不合格とする。
- tasks.md にも同じ書き方を当て、`plan=` を同じ述語で判定する。比較用に毎回置く `2026-01-01-base`（`status: draft`）の行が approved になっても不合格とする。
- 計画 手順 3 の扱い: 引用符などで `approved` と出ない場合も、SKILL.md の表での行き先はケースごとに記録する。

**S-INV2**: ` status=` を含む出力行の数は、spec.md のある変更ディレクトリの数と一致する。ディレクトリの数え方は bash の `root/*/` の glob と同じ（隠しディレクトリは除く、symlink は重複を除かずに数える、壊れた symlink は除く）。メッセージ行（`status.sh:11,34`）は数えない。改行入りのディレクトリ名は unspecified。

**S-INV3**: 日付形式（`YYYY-MM-DD` で始まる）の名前どうしで日付が異なる場合は、新しい順に並ぶ。それ以外の名前の並びは unspecified。

**S-INV4**: 常に exit 0（`status.sh:11,35`）。

## new-change.sh（`skills/ains-spec/scripts/new-change.sh`）

### 契約

| ID | 契約 | 出典 | 生成器での判定 |
|---|---|---|---|
| N-C1 | slug は小文字英数字とハイフン（`^[a-z0-9][a-z0-9-]*$`）。作成先は `<root>/<日付>-<slug>`、既定の root は `docs/changes`。出力は作成したディレクトリのパス | `new-change.sh:4-6,24-29,36` | 正しい slug で作れる root のとき exit 0、stdout が `<root>/<実行の直前か直後の日付>-<slug>` |
| N-C2 | spec.md の雛形を置き、`{{CHANGE_ID}}` をディレクトリ名に置き換える | `new-change.sh:2,34` | spec.md が雛形（`skills/ains-spec/assets/spec.md`）を埋めた内容と一致する |
| N-C3 | `--root` には値が必要（`-` で始まる値は値と見なさない）。不明なオプションは exit 2 | `new-change.sh:15-18` | `--root -r` は exit 2 で何も作らない |
| N-C4 | 既存の spec.md（symlink を含む）は上書きせず、`skip (exists)` を stderr に出す | `new-change.sh:2,31-32` | exit 0 と stderr |
| N-C5 | exit 0 のとき、出力は作成したディレクトリのパス | `new-change.sh:6,36` | stdout の最終行が spec.md を持つディレクトリ |
| N-C6 | 作成先を作れない場合（root が既存のファイル、書き込めないディレクトリ）は exit ≠ 0 で、何も作らない | 契約 `:6`（作ったディレクトリを出力する）からの推論。人が決めた期待値 | exit ≠ 0 と、作業ディレクトリが変わらないこと |

日付は、実行の直前と直後に同じ TZ で求めた日付のどちらでも合格にする（計画 手順 6）。書き込めない場所は `chmod 555` だけで作る。

### 不変条件

**N-INV1**: どの入力でも、既存の spec.md と symlink の参照先の内容は変わらない。壊れた symlink の参照先を作らない（`tests/scripts/test_new_change.py` の `test_existing_spec_symlink_does_not_create_missing_target` と同じ性質）。

**N-INV2**: slug の引数が1つで不正な場合は exit 2 で、何も作らない。#27 で、slug を複数渡した場合と、244 文字を超える slug（日付を付けると 255 バイトを超える）も同じく exit 2 で何も作らないと決めた。

## route-review.sh（`skills/ains-review-gate/scripts/route-review.sh`）

生成器（`gen_route_review.py`）は、ここに書いた番号で判定する。exit 3 と 10 の条件が重なる組は、順序が契約に無いので exit 3 / 10 のどちらも許す。

### 契約

| ID | 契約 | 出典 |
|---|---|---|
| R-C1 | 引数は `<rules-file> [base-ref] [head-ref]`。4つ以上は exit 3 | `route-review.sh:4,38-42` |
| R-C2 | 作業ツリーモード（引数 1〜2 個）: base 省略時は origin/main、無ければ main。コミット済み・index・作業ツリー・未追跡を対象にする。リポジトリのルートへ移って列挙する | `route-review.sh:5-6,162-175` |
| R-C3 | committed-target モード（引数 3 個）: merge-base..head のコミット済み差分だけを照合する。index・作業ツリー・未追跡は含めず、規則は base の blob だけを読む。規則パスは正規化して指定し、リポジトリ外は exit 3 | `route-review.sh:7-8,43-49,56-121`、`skills/ains-review-gate/SKILL.md:19` |
| R-C4 | 規則の書式: 1行1規則、`#` 行と空行は無視。最初と最後の `\|` で分割する。path は bash glob（`*` は `/` も跨ぐ、大文字小文字を区別しない）、content は追加・削除行への拡張正規表現 | `route-review.sh:10-16` |
| R-C5 | rename は削除と追加として照合する。色、外部 diff、textconv、`-diff` 属性は無視する。NUL は空白に置き換える。ロケールは C | `route-review.sh:18-21` |
| R-C6 | exit 0: 規則に一致なし。exit 10: 規則に一致、規則ファイルが base に無い、gitlink の変更。exit 3: 規則ファイルが無い、有効な規則が 0 件、差分を取得できない、変更が 0 件、規則の書式が不正、git が失敗、未追跡のパスを差分にできない | `route-review.sh:22-31` |

### 不変条件

**R-INV1**: そのモードの対象範囲に含まれる変更が、base 版の path 規則に一致すれば exit ≠ 0。対象範囲は、作業ツリーモードではコミット済み・index・作業ツリー・未追跡（gitignore を除く、`route-review.sh:174`）、committed-target モードでは merge-base..head のコミット済み差分だけ（`:7-8`）。glob の一致は Python の fnmatch で判定しない（否定の `[^a]` の解釈や、`*` が `/` を跨ぐ扱いが bash と違う）。bash の `shopt -s nocasematch; [[ $path == $glob ]]` を、`--bash` で指定した bash で呼ぶ小さなヘルパーで判定する。

**R-INV2（exit の優先順位）**: 次の順序で期待する exit を決める。

1. exit 3 の条件が1つでもあれば exit 3。条件は、引数、ref、merge-base、差分の取得、未追跡のパスを差分にできない、変更が 0 件、規則の書式、有効な規則が 0 件（`route-review.sh:25-26,31`）。
2. 1 に当たらないときに限り、base に規則ファイルが無い場合と gitlink の変更がある場合は exit 10（`:22-24,30`）。
3. 1・2 に当たらず、規則に一致すれば exit 10、一致しなければ exit 0。

この順序は実装（`:222-228` で gitlink を数えたあと、`:231-268` で書式の誤りを見つけると exit 3）と、Critic の実測（gitlink かつ規則の書式が不正なら exit 3）から読み取ったもので、契約の文言には書かれていない。findings 文書では「仕様未定（優先順位）」として1件記録する。exit 3 と 10 の条件が重なるケースは、どちらの exit も合格とする（実装の挙動を写した判定にしないため）。

**R-INV3**: committed-target モードは、head 側の規則の変更で判定を緩められない（規則は base の blob だけを読む。`:8`）。
