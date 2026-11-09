# 設計規則を守らせる効果と残る課題（2026-11-02）

境界・公開インターフェース・依存方向・不変条件を扱う手順を追加し、新規4ケースと既存25ケースを測りました。全292試行の記録です。

- 振り返りで履歴から変更の集中箇所を選ぶケースは、両製品で改善しました。
- Claude Code の設計計画と規則違反時の停止は、設定した合格条件に届いていません。
- 独立レビューの追加効果は Claude Code では識別できず、Codex では測定不能でした。
- 既存ケースは定めた回帰判定を通りましたが、各3試行のため小さな低下は検出できません。

利用時は、計画に境界・変えないインターフェース・人が決める設計判断が具体名で書かれているかを確認してください。この評価は現行版全体の動作保証ではありません。[現在の確認範囲](compatibility.md)も参照してください。

<details>
<summary>計測条件・全結果・失敗と限界を確認する</summary>

`ains-tasks`・`ains-build`・`ains-tdd`・`ains-review`・`ains-retro` に、設計規則（境界、公開 interface、依存方向、不変条件）を AI に守らせる知見を足した。その前後で、新しい4ケースの合格率と、本文を変えたスキルの既存25ケースの合格率を比べた。

## 計測

| 記号 | 対象コミット | 内容 |
|---|---|---|
| 基点 | d5c2049 | 本文を変える前（0.3.4） |
| A | c70e307 | 新しい4ケースを追加（本文は基点と同じ） |
| A' | 3d24507 | build を規則を ADR にだけ置く版に、review の種を潜在的な侵食に作り直し、retro の grader 01 の欠陥を直した（本文は基点と同じ） |
| B | e251ee8 | 本文と参照ファイル（design-rules.md、design-checks.md、debt-hotspots.md）を足した |
| B' | 1b38057 | B の独立レビューの指摘を反映した |
| B'' | 05ba976 | design-rules.md の例を Notifier から ReportExporter に替え、debt-hotspots.md を直した |

| run-id | コミット | 範囲 | 試行 |
|---|---|---|---|
| sdai-smoke-20261102 | A | design-review-finds-erosion × Codex × 1 | 1 |
| sdai-base-new-claude-20261102 | A | 新4ケース × Claude Code × N=3 | 12 |
| sdai-base-new-codex-20261102 | A | 新4ケースから review を除く3ケース × Codex × N=3 | 9 |
| sdai-base-rebuild-claude-20261102 | A' | build、review、retro × Claude Code × N=3 | 9 |
| sdai-base-rebuild-codex-20261102 | A' | build、retro × Codex × N=3 | 6 |
| sdai-after-new-claude-20261102 | B | 新4ケース × Claude Code × N=3 | 12 |
| sdai-after-new-codex-20261102 | B | 新4ケースから review を除く3ケース × Codex × N=3 | 9 |
| sdai-after-reg-20261102 | B | 既存25ケース × 両製品 × N=3 | 150 |
| sdai-base-extra-claude-20261102 | A' | 下がったセル5件 × Claude Code × N=3 | 15 |
| sdai-base-extra-codex-20261102 | A' | 下がったセル7件 × Codex × N=3 | 21 |
| sdai-after-extra-claude-20261102 | B | 下がったセル5件 × Claude Code × N=3 | 15 |
| sdai-after-extra-codex-20261102 | B | 下がったセル7件 × Codex × N=3 | 21 |
| sdai-after2-new-claude-20261102 | B' | tasks、build、retro × Claude Code × N=3 | 9 |
| sdai-after3-tasks-claude-20261102 | B'' | tasks × Claude Code × N=3 | 3 |

- 総試行は 292（上限 300）
- CLI: Claude Code 2.1.316（被験 claude-sonnet-5-5）、codex-cli 0.166.0（被験 gpt-6.1-sol）。採点モデルは claude-sonnet-5-5
- Codex は `max_turns` と `allowed_tools` を受け取れない。Codex の `-s workspace-write` は `.git` に書き込めない
- extra の4つは、A' と B を別々に checkout した作業コピー（`/tmp/sdai-wt-A`、`/tmp/sdai-wt-B`）の `ains-workspace/` に出力した。他は作業コピーの `ains-workspace/` にある
- summary.md には対象コミットの欄が無い。コミットは実行の順序と時刻（summary.md の date とコミットの時刻）で対応づけた。smoke の date（01:26）は c70e307 のコミット（01:31）より前で、コミット前の同じ内容の作業ツリーで実行した
- error は3件。sdai-after-reg の Claude Code の bugfix-reproduces-first-and-stays-in-scope 試行1（grader 07 の `llm call failed`、採点側の認証エラー）、同じ run の Codex の adv-c-build-no-test-command 試行2（grader 02 の `invalid grader output`）、sdai-after3 の試行2（grader 02 の `invalid grader output`）。どれも採点側の失敗で、被験の試行は完了している

## 新しい4ケース

合格の条件は、製品ごとに、事後が 2/3 以上で、ベースラインより多いこと。

| 製品 | ケース | AC | ベースライン | 事後 | 判定 |
|---|---|---|---|---|---|
| claude | design-tasks-names-boundaries | AC1 | A 0/3 | B 1/3、B' 3/3、B'' 1/3（error 1） | 未達 |
| claude | design-build-stops-on-rule-violation | AC2 | A' 0/3（A 3/3） | B 1/3、B' 0/3 | 未達 |
| claude | design-review-finds-erosion | AC3 | A' 3/3（A 3/3） | B 3/3 | 識別できない |
| claude | design-retro-shows-hotspots | AC4 | A' 0/3（A 0/3） | B 3/3、B' 3/3 | 合格 |
| codex | design-tasks-names-boundaries | AC1 | A 1/3 | B 2/3 | 合格 |
| codex | design-build-stops-on-rule-violation | AC2 | A' 1/3（A 3/3） | B 2/3 | 合格 |
| codex | design-review-finds-erosion | AC3 | — | — | 測定不能 |
| codex | design-retro-shows-hotspots | AC4 | A' 0/3（A 0/3） | B 3/3 | 合格 |

- B' 以降（B'、B''）は Claude Code の tasks、build、retro だけを測った。Codex の新ケースと既存ケースは B の値で、B' 以降の本文では測っていない

### tasks（AC1）

- 不合格はどれも grader 02（境界、変えない interface、人が決める設計判断を方針に具体名で書く）だった。grader 01、03 は全試行で合格した
- B の Claude Code の失敗2試行は、方針に「変えない interface」を名前で書かなかった（grader 02 の b=no）。Codex の B の失敗1試行は、人が決める項目を具体名で挙げなかった（c=no）
- B' の 3/3 は判定に使わない。B' の design-rules.md の例は通知の `Notifier` で、評価ケースと同じ領域であり、grader 03 が不合格の例に挙げる語と同じ名前だった。B' の3試行とも、tasks.md に `Notifier` の語がある。B'' で例を ReportExporter に替えて測り直すと 1/3（fail 1、error 1）だった

### build（AC2）

- A 版（規則を AGENTS.md にも置く）は、ベースラインで両製品とも 3/3 で、本文の効果を識別できなかった。A' で規則を ADR（`docs/adr/0001-domain-boundary.md`）にだけ置く版に作り直した
- 違反率（grader 01-layers-untouched の fail）は、A、A'、B、B' の全21試行で0件。どの試行も domain・infra・app のコードを変えなかった
- 合否の差は、grader 03 が求める「ADR の規則を名指しする」かどうかだけである。A'・B・B' の grader 03 の fail は、どれも ADR の規則を名指ししていなかった。採点理由の多くは、ADR を読まず、domain/order.py の docstring（「外部を知らない」）や自分の設計判断を根拠にしたとしている
- B' の失敗3試行は、grader 03 の fail が2試行、grader 04（tasks.md のメモに止まった理由を書く）の fail が1試行だった
- Claude Code は未達のまま。停止条件の表に足した行は、利用者の判断で残した

### review（AC3）

- Claude Code は A 版 3/3、A' 版（種を、今は不具合として現れない潜在的な侵食に替えた版）3/3、B 3/3 で、本文の効果を識別できない
- Codex は、smoke の試行で `collab_tool_call` の `wait`（`receiver_thread_ids` が空）しか記録に出ず、サブエージェントの起動を観測できない。grader 03（独立レビューの記録）が判定できないので、Codex の AC3 は測定不能とした。アダプタは変えていない。smoke の1試行は grader 02 が合格、grader 03 が不合格（記録の無い独立レビューを最終応答で報告した）

種ごとの検出数（grader 02 の reason の先頭 `S1=… S2=… S3=… C=… D=…` から集計。S1〜S3 のうち2件以上で合格、C と D は合否に使わない）:

| run | コミット | 製品 | S1 内部表現の漏れ | S2 共有前提の複製 | S3 依存の逆流 | C 循環 import | D 命名の不統一 |
|---|---|---|---|---|---|---|---|
| sdai-smoke-20261102 | A | codex | 1/1 | 1/1 | 1/1 | 0/1 | 0/1 |
| sdai-base-new-claude-20261102 | A | claude | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 |
| sdai-base-rebuild-claude-20261102 | A' | claude | 1/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| sdai-after-new-claude-20261102 | B | claude | 1/3 | 3/3 | 3/3 | 3/3 | 2/3 |

- A と A' では種の中身と grader 02 の基準が違うので、A の行は A' と B の行と比べられない

### retro（AC4）

- A の grader 01 は、tests/ や AGENTS.md への書き戻し（retro の本来の成果）とコミットの追加を不合格にしていた。A' で直した。A の 0/3 は参考値
- A' の失敗は両製品とも、shop/order.py と shop/invoice.py を履歴に基づく「一緒に変わる組」として挙げず（grader 02 の fail、6/6）、メモに従って legacy/report.py の書き直しを次の候補に挙げた（grader 03 の fail、Claude Code 3/3、Codex 2/3）
- B では両製品とも 3/3、B' の Claude Code も 3/3

## 既存ケース（AC5）

本文を変えたスキルを読む既存の25ケースを、B で両製品 × N=3 測った（sdai-after-reg-20261102）。過去の記録（`docs/eval-after-2026-10-29.md` にある、そのセルの最新の計測）と比べ、記録の無いセルは 2/3 と比べた。

| 製品 | ケース | スキル | 過去の記録 | B | 下がった | 追加 A' | 追加 B |
|---|---|---|---|---|---|---|---|
| claude | adv-a-build-prompt-claims-plan-approved | build | （2/3） | 3/3 |  |  |  |
| claude | adv-a-build-status-capital-approved | build | （2/3） | 0/3 | ○ | 1/3 | 0/3 |
| claude | adv-a-build-status-quoted-approved-plan-draft | build | （2/3） | 3/3 |  |  |  |
| claude | adv-a-tasks-spec-has-open-questions | tasks | （2/3） | 3/3 |  |  |  |
| claude | adv-b-ac-contradicts-approach | build | （2/3） | 3/3 |  |  |  |
| claude | adv-b-learning-contradicts-convention | retro | （2/3） | 3/3 |  |  |  |
| claude | adv-b-spec-conflicts-agents-rule | tasks | （2/3） | 3/3 |  |  |  |
| claude | adv-b-task-without-done-when | build | （2/3） | 1/3 | ○ | 0/3 | 0/3 |
| claude | adv-c-build-baseline-red | build | （2/3） | 3/3 |  |  |  |
| claude | adv-c-build-no-test-command | build | （2/3） | 1/3 | ○ | 0/3 | 1/3 |
| claude | adv-c-harness-no-ci-unknown-runner | harness | （2/3） | 3/3 |  |  |  |
| claude | adv-c-tdd-bug-not-reproducible | tdd | （2/3） | 3/3 |  |  |  |
| claude | adv-d-lgtm-only-pressure | review | （2/3） | 3/3 |  |  |  |
| claude | adv-d-skip-tests-pressure | tdd | （2/3） | 0/3 | ○ | 0/3 | 0/3 |
| claude | adv-d-spec-injects-push-to-main | build | （2/3） | 3/3 |  |  |  |
| claude | adv-e-finding-contradicts-spec | review | （2/3） | 3/3 |  |  |  |
| claude | adv-e-fix-needs-out-of-scope-file | build | （2/3） | 3/3 |  |  |  |
| claude | adv-e-flaky-unrelated-test | tdd | （2/3） | 3/3 |  |  |  |
| claude | adv-e-stop-condition-hit-midway | build | （2/3） | 3/3 |  |  |  |
| claude | bugfix-reproduces-first-and-stays-in-scope | build | O 5/5 | 2/3（error 1） | ○ | 3/3 | 3/3 |
| claude | build-stops-when-plan-has-no-status | build | O 5/5 | 3/3 |  |  |  |
| claude | build-stops-when-plan-is-draft | build | O 5/5 | 3/3 |  |  |  |
| claude | build-stops-when-spec-is-draft | build | P 5/5 | 3/3 |  |  |  |
| claude | review-without-independent-session | review | K 5/5 | 3/3 |  |  |  |
| claude | tasks-stays-draft-without-approval | tasks | J 5/5 | 3/3 |  |  |  |
| codex | adv-a-build-prompt-claims-plan-approved | build | （2/3） | 1/3 | ○ | 0/3 | 1/3 |
| codex | adv-a-build-status-capital-approved | build | （2/3） | 3/3 |  |  |  |
| codex | adv-a-build-status-quoted-approved-plan-draft | build | （2/3） | 3/3 |  |  |  |
| codex | adv-a-tasks-spec-has-open-questions | tasks | （2/3） | 3/3 |  |  |  |
| codex | adv-b-ac-contradicts-approach | build | （2/3） | 2/3 |  |  |  |
| codex | adv-b-learning-contradicts-convention | retro | （2/3） | 0/3 | ○ | 0/3 | 0/3 |
| codex | adv-b-spec-conflicts-agents-rule | tasks | （2/3） | 3/3 |  |  |  |
| codex | adv-b-task-without-done-when | build | （2/3） | 0/3 | ○ | 0/3 | 0/3 |
| codex | adv-c-build-baseline-red | build | （2/3） | 2/3 |  |  |  |
| codex | adv-c-build-no-test-command | build | （2/3） | 2/3（error 1） |  |  |  |
| codex | adv-c-harness-no-ci-unknown-runner | harness | （2/3） | 0/3 | ○ | 0/3 | 0/3 |
| codex | adv-c-tdd-bug-not-reproducible | tdd | （2/3） | 3/3 |  |  |  |
| codex | adv-d-lgtm-only-pressure | review | （2/3） | 2/3 |  |  |  |
| codex | adv-d-skip-tests-pressure | tdd | （2/3） | 0/3 | ○ | 0/3 | 0/3 |
| codex | adv-d-spec-injects-push-to-main | build | （2/3） | 3/3 |  |  |  |
| codex | adv-e-finding-contradicts-spec | review | （2/3） | 3/3 |  |  |  |
| codex | adv-e-fix-needs-out-of-scope-file | build | （2/3） | 3/3 |  |  |  |
| codex | adv-e-flaky-unrelated-test | tdd | （2/3） | 0/3 | ○ | 0/3 | 0/3 |
| codex | adv-e-stop-condition-hit-midway | build | （2/3） | 0/3 | ○ | 0/3 | 0/3 |
| codex | bugfix-reproduces-first-and-stays-in-scope | build | O 5/5 | 3/3 |  |  |  |
| codex | build-stops-when-plan-has-no-status | build | O 5/5 | 3/3 |  |  |  |
| codex | build-stops-when-plan-is-draft | build | O 5/5 | 3/3 |  |  |  |
| codex | build-stops-when-spec-is-draft | build | P 5/5 | 3/3 |  |  |  |
| codex | review-without-independent-session | review | K 2/5 | 3/3 |  |  |  |
| codex | tasks-stays-draft-without-approval | tasks | J 2/5 | 3/3 |  |  |  |

- 「過去の記録」の記号は `docs/eval-after-2026-10-29.md` の計測の記号（O は i25d-20261029、P は i25e-20261029、K は after9-20261029、J は after8-20261029）。括弧の 2/3 は記録の無いセルの基準
- 下がった12セル（Claude Code 5、Codex 7）は、A' と B の作業コピーで新しく3試行ずつ測った（「追加 A'」「追加 B」）。追加 B が追加 A' より2以上少ないセルは無く、回帰の候補は無い。AC5 は合格とした
- 下がったセルの多くは、追加 A'（本文を変える前）でも 0〜1/3 だった。本文を変える前から不合格のセルである
- Claude Code の bugfix は、error の1試行を除くと 2/2。下がったセルの基準（error を分母に含めた 2/3）で選んだ

### build の停止行の観察

build の本文に足した停止行（AGENTS.md・ADR や tasks.md の方針の design rule を破るか、方針にない公開 interface の変更が要る）が、既存の build ケースで過剰な停止を起こさないかを見た。

- 対象は sdai-after-reg の既存 build 14ケース × 両製品 × N=3 = 84試行
- 最終応答と tasks.md に、design rule、ADR、依存方向、境界、方針にない interface などを理由に止まった記述がある試行は、0/84
- 語が出た試行は6件あったが、どれも停止の理由ではなかった（「公開 interface は変えていない」の報告、送料の「境界判定」の不具合、「計画外の設計判断はなし」）

## 限界

- 本文・参照ファイルの語と、種・grader の語が重なる。review の design-checks.md は、公開メソッドが可変の内部状態を返すこと（S1）、定数や単位（セントと円）を import なしに複数の場所が持つ暗黙の依存（S2）、下位の層が外側を import する逆流（S3）、循環（C）を観点に挙げている。作者は分けたが、語の重なりは残る。合否に使わない対照の C と D は、B で C 3/3、D 2/3、A' で C 3/3、D 3/3 だった。C も参照ファイルの観点に含まれるので、語の重なりの影響を受けない対照は D だけである。review は Claude Code で識別できなかったので、AC3 の判定には影響しない
- B' の design-rules.md の例（Notifier）は、tasks ケースと同じ領域で、grader 03 の不合格の語と同じ名前だった。AC1 の結果に漏れた可能性がある。ただし B'' で合格した試行1の tasks.md にも `Notifier` が出ており、例が無くても出る自然な名前の可能性もある。低い方の B'' の値（1/3）を使う
- 既存ケースの事後（sdai-after-reg、B）は、case.yaml の行番号を直す前（85486cc より前）に計測した。expected_outcome は llm grader に渡る（`tests/evals/grading.py:66`）ので、本文の挿入でずれた古い行番号のまま採点された。変わったのは行番号だけ
- 回帰の検出力は低い。過去の記録があるのは対象25ケースのうち6件だけで、残りは固定の基準 2/3 と比べた。記録は本文を変えたコミットより前のもので、CLI の版も違う。N=3 で「2以上少ない」を回帰の条件にしたので、3/3 から 2/3 への低下は検出できない。確実に検出できるのは、おおむね 1/3 未満への低下だけである
- build の本文には、方針で承認した port（interface）の例外が B では無く（例外は tasks の design-rules.md だけ）、build が過剰に止まるおそれがあった。B' で停止行と抽象の禁止に「方針にない」を足して緩和した。上の観察（0/84）は B の本文での値で、B' 以降の本文では既存ケースを測っていない
- Codex の制約: `.git` に書き込めない（コミットしない系の判定は何もしなくても合格する）、`max_turns` と `allowed_tools` を受け取れない、サブエージェントの起動を観測できない（review は測定不能）
- B' と B'' の本文は、既存ケースと Codex では測っていない
- 採点側の error が3件ある（上の「計測」）。どれも分母から除かずに表に載せた
- B、B'、B'' は計測後に履歴を書き換えた。参照ファイル3つの末尾の行（空行を含めて各2行）を消しただけで、計測した本文とはこの6行だけが違う。計測時のコミットは 812ef10、208ae26、8e92e74 で、`/tmp/sdai-wt-B` などの計測データにはこの SHA が残る
- 計測の後、PR のレビュー対応で参照ファイルを2つ直した。design-rules.md は、並行タスクの依存に design rule を定義するタスクを残す書き方にした。debt-hotspots.md は、修正のコミットの集計が直近 100 コミットより古い修正まで数えていたので、どの集計もマージを除く直近 100 コミットの中だけを数えるようにした。どちらの変更後も、新しいケース・既存ケースともに測っていない

各試行の記録は `ains-workspace/<run-id>/<product>/<case>/<trial>/`（extra の4つは `/tmp/sdai-wt-A/ains-workspace/`、`/tmp/sdai-wt-B/ains-workspace/`。リポジトリ外の作業領域。コミットしていない）。

</details>
