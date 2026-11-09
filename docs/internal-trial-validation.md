# 試用結果：導入前に確認したい範囲

**現在は社内・チームでの試用段階です。** 2026-10-28 時点で16スキルを両製品で各1回動かした結果が揃いました。人による成果の最終確認は32項目とも未了です。初めて使う場合は[練習手順](getting-started.md)から始めてください。

## 現行版に当てはまるか

以下は過去の版の結果です。全32項目を同じ版・環境で実行し直したものではありません。

| 変更 | 確認状況 |
|---|---|
| 2026-10-28：ains-team-canvasを合意記録の手順へ変更 | 変更後の実製品確認は未実施。旧版の成功を現行版へ引き継がない |
| v0.5.0：主要5工程を承認後に続行する起動方針へ変更 | 旧版の32項目から現行版の全工程成功を推測しない |
| 2026-10-29：仕様確認とレビュー引継ぎの本文を修正（#12・#13） | 変更後は[自動評価](eval-after-2026-10-29.md)で確認。以下の実製品結果とは区別する |

ほかの版・環境を含む確認範囲は[互換性](compatibility.md)、作者の補足なしで使えるかの確認は[初見利用の記録用紙](first-use-check.md)を参照してください。

## 過去の版で確認できた動作

「正常動作」には、承認待ちでの停止や、人の確認が必要という判定も含みます。業務上の承認や公開の実行を示すものではありません。実成果物・生ログは非公開のローカル検証領域に保存されており、このリポジトリからは開けません。

| スキル | Claude Code：正常動作の確認内容・成果 | Codex：正常動作の確認内容・成果 | 人の確認 |
|---|---|---|---|
| ains | 現状からsetupを推奨、次工程を起動せず停止 | 設定未整備を調べsetupを推奨 | Claude未／Codex未 |
| ains-setup | 設定移行→内容確認→再実行 | CLAUDE-only設定の移行→内容確認→再実行 | Claude未／Codex未 |
| ains-spec | 仕様draftと全体承認質問 | 仕様draftを保存し承認確認、実装せず停止 | Claude未／Codex未 |
| ains-tasks | 仕様に対応するタスク案を作成 | 案への全体承認質問→別入力の試験用承認。statusだけapproved | Claude未／Codex未 |
| ains-build | 承認済み範囲の実装・回帰試験 | 負数入力の回帰RED→関数修正→2テストGREEN | Claude未／Codex未 |
| ains-review | 別セッションで仕様・差分・検査をレビュー | 別コンテキストのレビューでAPPROVE、制限も明記 | Claude未／Codex未 |
| ains-ship | ローカルPR資料を作成し人の判断で停止 | 21テスト成功・HUMAN_REQUIREDをローカルPR資料へ反映 | Claude未／Codex未 |
| ains-retro | 5問に回答し現行仕様へ保存失敗時の振る舞いを反映 | 5問に回答し現行仕様へ数値・ゼロの振る舞いを反映 | Claude未／Codex未 |
| ains-team-canvas | 8領域、現行の取り決め、空欄・担当・期限を整理 | 8領域、7決定の反映先、課題の担当・期限。表配置を限定修正 | Claude未／Codex未 |
| ains-harness | make checkを追加・実行、1テスト成功、段階導入のIssue下書き | make checkを追加・実行、1テスト成功、Issue下書き | Claude未／Codex未 |
| ains-tool-access | CLI/MCP・タスク・権限・認証・成否を具体化 | CSV合計20を実測、接続・権限・承認範囲を整理 | Claude未／Codex未 |
| ains-grilling | 個別の問い→回答→次の問い | 操作範囲・影響・復旧を含む確認質問 | Claude未／Codex未 |
| ains-tdd | 失敗する試験→修正→成功 | 実行ログで新回帰exit2→関数修正→exit0/2tests | Claude未／Codex未 |
| ains-review-gate | 人確認対象でHUMAN_REQUIRED / exit10 | 実スクリプトがHUMAN_REQUIRED / exit10、PR資料で停止 | Claude未／Codex未 |
| ains-release-safety | 実commit→revert→復元と保持データを確認 | 実commit→revert→復元、同じOFFデータで0→1→0 | Claude未／Codex未 |
| ains-context-care | 誤参照rule.mdと実在rules.mdを突き止め最小修正先を特定 | 仕様に既存パターン・契約・部品・依存と根拠を記載 | Claude未／Codex未 |

## 実行した製品と条件

既存のClaude Code実行は主に2.1.310、Codexは記録ごとの0.163.0／0.164.0です。仕様確認とレビュー引継ぎは、当時変更した版の結果を採用しています。

追加試用では次を確認しました。

- Claude Code 2.1.312 / claude-sonnet-5-5：context-care、retro、team-canvas、harness、tool-accessの5件が各exit 0で正常終了。
- Codex 0.164.0 / gpt-6.1-sol：retro、team-canvas、harness、tool-access、tasks、buildを8入力で確認し、すべて正常終了。tasksは質問と別入力の試験用承認、canvasは表配置の修正1回を含む。buildは回帰テストの失敗→関数修正→2テスト成功を実測。

初回Claude起動の引数不備によるモデル実行前のexit 1、Codex canvas初回の表配置ミス、過去のタイムアウトや承認質問の欠落は、失敗の記録として保持しています。

## この結果が保証しないこと

試験用の役割や承認回答は、利用者本人による成果の確認を代替しません。tool-accessは接続方針とローカル処理の確認で、GitHubへの実接続・認証は未確認です。harnessの1テストは検査コマンドを整える動作例です。

実運用での効果、全環境の互換性、導入先での動作は保証していません。公開・push・外部PR・マージ・デプロイは実施していません。

## 成果を確認する方へ

検証担当者から実成果物を受け取り、上表の各スキルが期待する用途に合うか確認してください。差戻しはスキル名・製品・気になった点を指定します。確認者・日付・結果を記録して、試用の最終確認とします。

- 確認者：未記入
- 確認日：未記入
- 結果：未確認
