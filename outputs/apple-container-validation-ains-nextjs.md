# Apple Container検証レポート: The pinned Next&#46;js seeded fixture distinguishes broken apostrophe matching from restored behavior&#46;

標準行列は、固定Next.jsへの意図的な故障を回帰テストで検出できることを確認した。ainsの実行挙動は後半の両製品の実測として別に評価しており、全環境の保証や待ち回数の削減を意味しない。

## ステータス

- Preflight/report disposition: **READY**
- Disposition note: host preflight passed and the runner emitted this report; READY does not mean execution completed or the claim was supported.
- Run ID: `matrix&#45;base&#45;20261108&#45;e`
- Claim outcome: **SUPPORTED WITHIN TESTED SCOPE**
- Execution status: **COMPLETE**
- 判定済みジョブ: 4 / 4
- オラクル成立: 3
- オラクル不成立: 1
- タイムアウト: 0
- 基盤エラー: 0
- Dry runジョブ: 0
- 未判定・未知状態: 0

## 仮説

The focused regression passes on pinned source and fails when apostrophe regex matching is removed&#46;

### 棄却条件

- `seed&#45;not&#45;detected`: Seeded apostrophe fault passes the regression&#46;

## 環境と来歴

- Apple Container: `container CLI version 1&#46;2&#46;2 &#40;build&#58; release&#44; commit&#58; 0190097&#41;`
- Host: `Darwin 27&#46;2&#46;0 arm64`
- Image: `nextjs&#45;document&#45;baseline&#58;20261108`
- Image inspect SHA-256: `570b164822dfc5d9315017292672a43c97bdd27237850087cf6ac5f72b003354`
- Manifest SHA-256: `50d00f76e6f946fab0896f6c6f29dd6efbb563a5551f3072cf2a765c4af7d824`
- Tree hash exclusions: `&#123;&#34;imageContext&#34;&#58; null&#44; &#34;mountSources&#34;&#58; &#123;&#34;input&#45;frozen&#45;v1&#34;&#58; null&#125;&#44; &#34;skillBundle&#34;&#58; null&#125;`
- 実行開始: `2026&#45;11&#45;08T10&#58;30&#58;54&#46;188692&#43;00&#58;00`
- 実行終了: `2026&#45;11&#45;08T10&#58;31&#58;26&#46;217586&#43;00&#58;00`
- 並列度: 1
- Agent CLI: `none`
- Authentication verification: `NOT APPLICABLE`
- Launcher-origin verification: `NOT VERIFIED BY RUNNER`
- Claim evaluation qualification: `PROVISIONAL`

`claimOutcome`はrelation/oracle集約だが、launcher由来が検証済みでない限り暫定評価である。CIは`claimOutcome`単独を主張真偽のgateにせず、完了確認には`executionStatus`を使い、主張受理には外部または記録済みのlauncher-origin attestationを必須とする。

## ケース結果

| Job | Group | Relation | Status | Seconds | Oracle failure |
|---|---|---|---:|---:|---|
| failure&#45;r1 | failure | neutral | oracle&#45;pass | 1&#46;492 | — |
| healthy&#45;r1 | target | support | oracle&#45;pass | 10&#46;448 | — |
| red&#45;green&#45;r1 | boundary | support | oracle&#45;pass | 10&#46;302 | — |
| seeded&#45;r1 | negative | falsify | oracle&#45;fail | 9&#46;6 | stdoutContains&#91;1&#93; failed |

## 観察

attempt別ログを照合した結果、正常ソースは3テスト成功、故障注入後は1件失敗・2件成功、元のソースへの復元後は3件成功だった。欠損コマンドは終了コード127を返し、全4ケースでpayload markerとstderrが判定に一致した。故障を検出しない場合のfalsifyオラクルは成立せず、seededジョブの `oracle-fail` は期待した結果だった。

## 推論

この回帰テストは、選択した属性エスケープ関数への意図的な故障と正常動作を識別できた。この標準行列だけではainsの自動続行やレビュー品質は評価しない。両製品の別実行では継続と停止境界を確認したが、旧版も工程待ち0回だったため、待ち回数が改善したとは推論しない。

## 反証・限界・未検証事項

対象は固定コミットの小さなソース変更であり、上流の不具合を発見したという主張ではない。全frameworkの型検査・build・lint・全テスト、依存tree全体、他の版・環境は未検証である。Codex nativeレビュー元の欠測と、別CLI構成で確認できたレビューは区別する。認証・custom launcher・並行変更に関する限界と保持した失敗は後半に記載した。

## 再実行

```bash
python3 /Users/oreore/.agents/skills/apple-container-validation/scripts/run-matrix.py .omx/validation/ains-nextjs/base-manifest.json --run-id matrix-replay-02 --results-dir .omx/validation/ains-nextjs/results --concurrency 1
```

同じrun-idが既にある場合は新しい識別子を指定する。新しい環境での固定入力の生成とimage再構築は、後半の再実行節から検証READMEの完全な手順を参照する。

## 証跡

- `run&#45;manifest&#46;json`
- `image&#45;inspect&#46;json`
- `summary&#46;json`
- `report&#46;329dba68ded19199b088e49c4986a669&#46;md`
- `jobs&#47;failure&#45;r1&#47;attempts&#47;1&#47;evidence&#47;missing&#45;command&#46;stderr&#46;log`
- `jobs&#47;failure&#45;r1&#47;attempts&#47;1&#47;stderr&#46;log`
- `jobs&#47;failure&#45;r1&#47;attempts&#47;1&#47;stdout&#46;log`
- `jobs&#47;failure&#45;r1&#47;result&#46;json`
- `jobs&#47;failure&#45;r1&#47;stderr&#46;log`
- `jobs&#47;failure&#45;r1&#47;stdout&#46;log`
- `jobs&#47;healthy&#45;r1&#47;attempts&#47;1&#47;evidence&#47;healthy&#46;stderr&#46;log`
- `jobs&#47;healthy&#45;r1&#47;attempts&#47;1&#47;evidence&#47;healthy&#46;stdout&#46;log`
- `jobs&#47;healthy&#45;r1&#47;attempts&#47;1&#47;stderr&#46;log`
- `jobs&#47;healthy&#45;r1&#47;attempts&#47;1&#47;stdout&#46;log`
- `jobs&#47;healthy&#45;r1&#47;result&#46;json`
- `jobs&#47;healthy&#45;r1&#47;stderr&#46;log`
- `jobs&#47;healthy&#45;r1&#47;stdout&#46;log`
- `jobs&#47;red&#45;green&#45;r1&#47;attempts&#47;1&#47;evidence&#47;green&#46;stderr&#46;log`
- `jobs&#47;red&#45;green&#45;r1&#47;attempts&#47;1&#47;evidence&#47;green&#46;stdout&#46;log`
- `jobs&#47;red&#45;green&#45;r1&#47;attempts&#47;1&#47;evidence&#47;red&#46;stderr&#46;log`
- `jobs&#47;red&#45;green&#45;r1&#47;attempts&#47;1&#47;evidence&#47;red&#46;stdout&#46;log`
- `jobs&#47;red&#45;green&#45;r1&#47;attempts&#47;1&#47;stderr&#46;log`
- `jobs&#47;red&#45;green&#45;r1&#47;attempts&#47;1&#47;stdout&#46;log`
- `jobs&#47;red&#45;green&#45;r1&#47;result&#46;json`
- `jobs&#47;red&#45;green&#45;r1&#47;stderr&#46;log`
- `jobs&#47;red&#45;green&#45;r1&#47;stdout&#46;log`
- `jobs&#47;seeded&#45;r1&#47;attempts&#47;1&#47;evidence&#47;seeded&#46;stderr&#46;log`
- `jobs&#47;seeded&#45;r1&#47;attempts&#47;1&#47;evidence&#47;seeded&#46;stdout&#46;log`
- `jobs&#47;seeded&#45;r1&#47;attempts&#47;1&#47;stderr&#46;log`
- `jobs&#47;seeded&#45;r1&#47;attempts&#47;1&#47;stdout&#46;log`
- `jobs&#47;seeded&#45;r1&#47;result&#46;json`
- `jobs&#47;seeded&#45;r1&#47;stderr&#46;log`
- `jobs&#47;seeded&#45;r1&#47;stdout&#46;log`

---

# ains Next.js 実行検証の補足（2026-11-08）

## 結論と範囲

承認済みのローカル変更は Claude Code と Codex の両方で、工程起動だけの質問を挟まず実装・検査・出荷資料まで進んだ。状態確認だけの依頼と draft 仕様では、両製品ともソースを変更せず停止した。build 単独の依頼も両製品で ship に広がらなかった。

ただし、旧版も今回の実行依頼では工程起動待ちが0回だったため、**待ち回数の削減は実測できていない**。Codex 候補 v4 のnativeレビュー呼出しに対応する実行イベントは取得できず、その元確認は **UNVERIFIED** のまま残す。別構成の v5 ではnative機能を明示的に無効化し、実際の別CLIレビューのコマンド・終了コード・受信結果・ハッシュまで確認できた。今回の固定構成・対象範囲では継続と停止境界を支持するが、一般的な使いやすさや全構成の保証とはしない。後から別に行った外部レビューは、古い呼出し記録の真正性を証明しない。

- Preflight/report disposition: **READY**。
- 上部の `executionStatus: COMPLETE` と `SUPPORTED WITHIN TESTED SCOPE` は、認証不要の**故障注入fixtureの識別**だけに対応する。
- 今回の固定構成に対する Claim outcome: **SUPPORTED WITHIN TESTED SCOPE**。これは標準runnerの別のenum出力ではなく、Claude v4と明示的CLIレビュー構成のCodex v5を実ログから照合した有限な評価である。Codex native経路と有限ケース外は未検証のまま残る。
- 出荷の人判断は未取得。規則ファイル不在のゲートは実際に終了コード3を返した。承認・外向き操作は追加していない。

## 仮説・棄却条件・オラクル

標準ランナーの事前仮説は「固定Next.jsソースに対する回帰テストが、アポストロフィ照合を意図的に除いた故障を検出し、元の処理で成功する」である。故障を検出せず成功した場合を棄却条件 `seed-not-detected` とし、`SEEDED_ACCEPTED` を falsify のオラクルにした。実測は `SEEDED_REJECTED` とテスト失敗であり、その falsify ジョブの `oracle-fail` は正常な観察である。

エージェントの継続は、CLI最終文の自己申告だけでは判定しない。対象ソース・テスト・記録のコピー、実際の RED/GREEN コマンド結果、前後の非依存ソースtree、HEAD/status/diff-name、レビュー呼出しイベントと対象ハッシュを照合する。レビュー元を確かめられない場合は未検証にする。これは上流Next.jsの不具合報告ではなく、既存関数への**意図的な故障注入**である。

## 環境と来歴

- Next.js: `https://github.com/53able/next.js`、コミット `ec8ddcd7a52fb7b3508fa1cf467abc85dea3a0b8`。
- 対象: `packages/next/src/shared/lib/htmlescape.ts` の既存属性エスケープ関数。回帰テストはコンパイル済みdistではなくTypeScriptソースを直接importする。
- 元ソースSHA-256: `968c7462d445662bed0f8707fe76fc9c6dcc7b069b2e267c7c69e223f6c7142e`。
- ains比較元: このリポジトリのコミット `3b2525c1f96609962dadf7e41dae3afea47faf97` の skills tree。候補は未コミットの変更を物理コピーして固定した。
- ホスト: macOS 27.2 arm64、Apple Container 1.2.2、ホストPython 3.14.6 (`/opt/homebrew/opt/python@3.14/bin/python3.14`)。
- 実行イメージ: `nextjs-document-baseline:20261108`、解決digest `2a42265da56df0907a2c8f6930b8139efee1507b6e8d08650a7eaa7684b9c90d`。既存依存イメージを使用し、選択したソースは固定Gitオブジェクトのbytesから毎回復元した。
- Codex: 0.167.0、`gpt-6.1-sol`、reasoning `medium`。既存ChatGPT認証を実行専用の私有cacheへコピーして直列利用し、終了後そのcacheを削除した。認証値のhashや成果物化は行わない。
- Claude Code: 2.1.319、`sonnet`、effort `medium`。実コンテナ内で固定版を一度 `/tmp` へinstallした。**image固定ではなくruntime install**であり、npmの実行環境からOAuthトークンを除外した。実際の解決モデルとツール一覧は各streamのinitイベントを参照する。
- 両製品ともsubscription preflight成功の非secret markerを確認した。APIキーを渡していない。各live呼出しの上限240秒、再試行0。公開入力はread-only、作業と出力は各コンテナ・各runに分離した。

正確なprompt、CLI argv、image digest、公開入力hash、ホストlauncher source/hashは各runの `launch.json` と `launcher.py` にある（古い v1 は後から追加した来歴項目を持たない）。

## 観察結果

| ケース | 観察 |
|---|---|
| 認証不要 smoke d / matrix e | 完了。正常3pass、故障1fail2pass、欠損コマンド127、別々のRED/GREENログを照合した |
| Codex旧版 approved v1 | 147.427秒。実装・8テスト・pr.md、工程待ち0。独立レビューの旧記録は裏付け未取得 |
| Claude旧版 approved v2 | 92.290秒。実装・4テスト・pr.md、工程待ち0。実際のAgentレビューあり。レビュー後のテスト追加は未再レビュー |
| Codex候補 approved v3 | 149.566秒。RED→GREEN10、工程待ち0。独立レビューの記録は裏付け未取得として保持 |
| Claude候補 approved v3 | 123.658秒。RED→GREEN4、Agentレビューあり。後のテスト追加は未再レビュー。全体tscはnode異常終了で未検証 |
| Codex候補 approved v4 | 188.420秒。RED3fail6pass→GREEN9、pr.md、工程待ち0。レビュー呼出しの記載はあるが対応イベントがなく元確認は未検証 |
| Claude候補 approved v4 | 108.442秒。RED→GREEN3、実際のAgent呼出し・APPROVE。レビュー後の実装・テスト変更なし。gate3、人判断待ち |
| Codex候補 approved v5（native無効・CLIレビュー） | 177.998秒。RED2fail6pass→GREEN8。別CLIの実コマンドexit0、受信したAPPROVEと両hashを照合。gate3、人判断待ち |
| 両製品 status v3 | 33.408秒 / 32.708秒。changedPaths空、HEAD不変、テスト・実装なし |
| 両製品 draft v3 | 39.223秒 / 28.634秒。changedPaths空、HEAD不変。仕様承認を待つ |
| Codex standalone build v3 | 133.332秒。RED→GREEN8、source/test/tasksだけ変更、pr.mdなし。旧レビュー記録は未検証 |
| Claude standalone build v4 | 66.694秒。RED→GREEN3、source/test/tasksだけ変更、pr.mdなし。独立レビュー未実施と明記 |

最終構成のhappy-pathテストSHA-256:

- Codex v5: `6d1a3e39c675a9c58a86ec89112e7e1a7a0be7b89cdd8d8be0672e2df39c4b31`（v4は `d71bdf549ac7a46bb27c9074ff3594a5d9a20b39bdc43cd5ee70dd3a496a2d13` のまま別記録）
- Claude: `6fe1d0fb3d3b50aa982a98b080eca73d2811c9e63f3754ba13ad5e44d29225f1`

どちらの修復後ソースも上記の固定元ソースhashと一致する。前後inventoryでは、許可されたsource/test/tasks/prだけが変化し、HEADは不変だった。ただし `node_modules` と `.git` 内部はinventory対象外で、依存tree全体の不変を保証しない。

## 失敗・限界を保持した記録

- 新しい派生イメージのdigest指定FROMはregistry解決で失敗。tag指定で同じbase digestを解決してbuildしたが、実行時の巨大image unpackが進まず smoke c は基盤エラーになった。入力補助手順の更新も重なったため、このrunは支持証拠として使用しない。既にunpack済みのbase imageへ切り替えたrunを別IDで実行した。
- Claude baseline v1 は可変長CLI optionがpromptを消費し、モデル実行前に失敗した。CLI引数を修正した v2 と区別し、旧版の使いやすさの不合格とは数えない。
- v1/v3のfixtureはタスク名の `T1:` のコロンを欠き、status.shが0/0と表示した。両比較側へ同じfixtureを渡していた。v4で形式を直し、過去の結果は書き換えない。
- Codexレビュー元の欠測を隠すために再promptせず、source修正後のv4を別runとして保持した。native経路の欠測は現状でも未検証である。v5の観測できた別CLI結果へ読み替えない。CLIのイベント出力だけから、あらゆる内部実行が存在しなかったと一般化しない。
- native起動・注入の全内部過程は観測できない。固定配置先の手順消費と実行挙動の証拠を、普遍的なnative注入証明と同一視しない。
- v4ではfixtureの完了判定をソース直接importの指定Jestに明記した。framework全体の型/build/lint/全テストは対象外の未検証であり、v3のtsc異常終了を成功へ変更していない。
- custom live launcherは標準ランナーの全publish/resume保証を持たない。既知値の固定点削除、artifact走査、秘密を含むpathの置換、symlink拒否、no-followでのmode操作を行うが、変形・分割された秘密の普遍的検出や同一ユーザーの同時変更への完全な耐性は保証しない。sanitation前の中断では0700の証拠領域に生値が残り得る。共有前に再監査する。

この検証は両製品・今回の版・固定された小さな変更の有限試行である。初見利用者の使いやすさ、一般のNext.js変更、将来版や全環境での成功は未検証である。

## 推論と参考コンテキスト

今回の測定は、起動契約を整理しても旧版より待ちが減るとは限らないことと、独立レビューを「実行した」という文章だけでは完了証拠にならないことを示した。実装・テストが良くても、レビュー元や人判断の未確定は別に残る。

人の判断点と定型実行の区別は [AI-Native Software Engineering ch.6](https://learning.oreilly.com/library/view/ai-native-software-engineering/0642572352530/ch06.html)、変更への影響を持つ設計判断という観点は [Software Design in the Age of AI ch.2](https://learning.oreilly.com/library/view/software-design-in/9780138227814/ch02.html) を補助コンテキストにした。これらは実測結果の根拠ではなく、本文を成果物へ転載していない。

## 再実行と証拠

新しいワークスペースのbootstrap・固定source/hash生成・image再構築・manifest検証・dry-run・smoke・matrix・live実行の正確な手順は [検証README](../tests/nextjs-continuation/README.md#exact-reproduction) を参照する。現在のcandidateを再コピーしたrunは、新しいsourceとして扱う。新規のimage再構築レシピ自体はこの変更では再実行していない。

- [標準matrix summary](../.omx/validation/ains-nextjs/results/matrix-base-20261108-e/summary.json)
- [標準matrixの全ジョブとattempt別生ログ](../.omx/validation/ains-nextjs/results/matrix-base-20261108-e/jobs/)
- [liveのsanitized events・コピーされた変更・前後inventory](../.omx/validation/ains-nextjs/live/)
- [判定メモ](../.omx/validation/ains-nextjs/manual-adjudication.json)
- [system log照合メモ](../.omx/validation/ains-nextjs/system-log-attestation.json)

上記の `.omx` 証拠はこのローカル作業環境に保持し、Gitには含めない。標準summaryと世代別reportのSHA-256連結を確認してから、この利用者向けコピーを作成した。元の世代別reportを編集していない。

```sh
python3 - <<'PY'
from pathlib import Path
import hashlib, json
root = Path('.omx/validation/ains-nextjs/results/matrix-base-20261108-e')
summary = json.loads((root / 'summary.json').read_text())
artifact = summary['reportArtifact']
report = root / artifact['path']
assert report.parent == root
assert hashlib.sha256(report.read_bytes()).hexdigest() == artifact['sha256']
print('summary/report pair verified')
PY
```

## スキル・検証補助コードの確認

- 既存eval全体: `205 tests`、`346.615s`、成功。記録: `.omx/plans/core-evals-final.log`。
- その後のレビュー元grader修正: 2テスト成功、配布静的検査 `failed=0`。記録: `.omx/plans/review-origin-quotation-green.txt`。引用・否定の文章を誤って不合格にした旧失敗を別ログに保持した。
- custom live launcher: 11テスト成功。偽CLI成功/timeout/cleanup失敗、短い値も含む固定点削除、認証更新前後、秘密を含むpathと標準出力、symlink越しのホストmode変更防止、別reviewer cacheとnative無効化flagsを確認した。構文検査も成功した。
- 診断への秘密を含むpath出力、symlink先へのchmod、予約出力symlink、失敗分類、cleanup失敗後のwalkの問題は、偽credentialで再現して修正した後、独立レビューで解消を確認した。これらは偽credential・一時ファイルによる再現であり、実token漏えいや実ホストファイル改変の観測ではない。
- sourceの独立コードレビューはAPPROVE、architectureはCLEAR。これらはスキル本文の確認であり、Codex実行中のレビュー呼出しを証明するものではない。

機械可読の集約は [verification.json](../.omx/validation/ains-nextjs/verification.json) に保持する。待ち回数の改善や全目標の達成を、コード検査の成功から推測しない。

## Codex v5 の独立CLIレビューと最終補助処理

ローカルCLIのfeature一覧で `multi_agent` と `multi_agent_v2` が認識されることを確認し、v5では両方を明示的に無効化した。fixtureにもnative呼出しが利用できない構成であることを記載し、既存CLIと専用の別認証cacheを渡した。スキルのproduct bytesはv4から変えていない。この構成はnative経路の検証ではない。

実ログには、別 `CODEX_HOME` での `codex exec --ignore-user-config --ignore-rules --ephemeral --json -m gpt-6.1-sol -c model_reasoning_effort="medium" --disable multi_agent --disable multi_agent_v2 --sandbox read-only` の終了コード0がある。その後の実コマンドが、受信JSONLの `turn.completed` と最終 `agent_message` を読み、現在のsource/test hashとの一致をassertして、受信した `APPROVE` 本文を表示した。独立した最終照合でも、この呼出しと結果を確認できた。レビュー後にsource/testの変更はない。

レビュー用input作成で最初に `python` が見つからず失敗し、`python3` へ直した記録も残る。成功だけを抜き出して旧失敗を削除していない。レビューinputにはtasks.mdのメモも含まれたため、推奨する「作者メモを除く」プロンプト手順への完全準拠は未確認である。別文脈・読み取り専用CLIの実行元は確認できても、理想的なレビュー品質や全プロンプト規約の保証にはしない。

再実行ではbootstrapで作る `input-live-v4` に対し、次の公開flagを追加すると同じ機構になる（今回の物理固定コピーは `input-live-v5`）：

```sh
python3 tests/nextjs-continuation/live.py .omx/validation/ains-nextjs-replay --image ains-nextjs-rebuilt:20261108 --input-dir input-live-v4 --product codex --bundle candidate --scenario approved --native-review-disabled --run-id codex-cli-review-01
```

最終wrapperの失敗処理は、各認証・証拠検証・実行エラーを安全な固定コードで区別し、sanitized captureとmetadataを保存して非0終了する。予約されたresult/events/launchは排他的な一時ファイルからの置換で保存し、symlink先を上書きしない。cleanup失敗時はartifactを一切walk・sanitize・chmodせず、私有証拠をquarantineとして残し、停止が必要な正確なコンテナ名を記録する。これらは11件の偽CLI回帰で確認した。

v5実行は、そのrunに保存した当時の `launcher.py` bytesを使った。後から修正した失敗時の保護処理を、過去のlive実行で通ったことにはしていない。product入力は同一であり、最終wrapperの失敗分岐は別の回帰テストと独立ソースレビューで確認した。[cleanup点検記録](../.omx/plans/validation-cleanup.md)に分類と残る限界を記載した。
