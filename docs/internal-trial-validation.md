# 社内・チーム試用の確認一覧

## 2026-10-28：合意記録への変更後の確認範囲

`ains-team-canvas` の翻訳質問テンプレートを配布対象から外し、利用者の判断・根拠・担当・反映先を記録する手順へ変更した。公式Canvasは参考リンクのみとし、質問集の取得・翻訳・出力は行わない。配布契約の静的検査は別途行うが、変更後のClaude Code/Codexでの実機確認は未実施。以下のCanvas成功例と32項目の集計は以前の版の履歴であり、現在版の成功へ読み替えない。人の確認も未了。

2026-10-28。**実行・成果確認は16スキル×2製品＝32項目が揃った。人による最終確認は32項目とも未了。**

完了条件は、各スキルが Claude Code と Codex でそれぞれ一度正常に働き、人がその結果を確認すること。既存の実機成功結果を再利用し、欠けていた機能を小さなローカルケースで補った。自動規律のスキルは、実際の作業中の振る舞いを確認した。

## 成果物を見る

各セルのリンクで実成果物または実行記録を開ける。「正常」には、その場面で必要な承認質問・draft保持・HUMAN_REQUIREDでの停止を含む。業務上の承認や公開を意味しない。

| スキル | Claude Code：正常動作の確認内容・成果 | Codex：正常動作の確認内容・成果 | 人の確認 |
|---|---|---|---|
| ains | 正常：[ 現状からsetupを推奨、次工程を起動せず停止 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/ultragoal/evidence/g004/claude/native-v1/runs/20261024T193814Z-a0dc2dba/chain-router/chain-router.json>) | 正常：[ 設定未整備を調べsetupを推奨 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/ultragoal/evidence/g004/codex/native-v46/runs-notification-workflow-router-source1f09-usage54-RELEASE-REQUIRED/turn-01.json>) | Claude未／Codex未 |
| ains-setup | 正常：[ 設定移行→内容確認→再実行 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/ultragoal/evidence/g004/claude/native-v1/runs/20261024T193814Z-a0dc2dba/setup-claude-only-ack-repeat/setup-claude-only-ack-repeat.json>) | 正常：[ CLAUDE-only設定の移行→内容確認→再実行 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/ultragoal/evidence/codex-claude-only-migration-repeat-audit/coverage.json>) | Claude未／Codex未 |
| ains-spec | 正常：[ 仕様draftと全体承認質問 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/continuations/resume-20261027-j56k2v96/claude-closure/runs/claude-copy-original-crossproduct/draft-after.md>) | 正常：[ 仕様draftを保存し承認確認、実装せず停止 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/continuations/resume-20261027-j56k2v96/codex-default-actual-independent-audit/actual-final-response.txt>) | Claude未／Codex未 |
| ains-tasks | 正常：[ 仕様に対応するタスク案を作成 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/ultragoal/evidence/g004/claude/native-v2/runs/20261024T205737Z-97ce1f7e/chain-tasks/chain-tasks.json>) | 正常：[ 案への全体承認質問→別入力の試験用承認。statusだけapproved ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/validation-fixtures/internal-trial-codex-r1/tasks/docs/changes/rounding/tasks.md>) | Claude未／Codex未 |
| ains-build | 正常：[ 承認済み範囲の実装・回帰試験 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/ultragoal/evidence/g004/claude/native-v1/runs/20261024T193814Z-a0dc2dba/default-build-original/default-build-original.json>) | 正常：[ 負数入力の回帰RED→関数修正→2テストGREEN ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/validation-fixtures/internal-trial-codex-r1/build/build.final.txt>) | Claude未／Codex未 |
| ains-review | 正常：[ 別セッションで仕様・差分・検査をレビュー ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/ultragoal/evidence/g004/claude/native-v3/runs/20261024T213927Z-6b935d15/chain-review/chain-review.json>) | 正常：[ 別コンテキストのレビューでAPPROVE、制限も明記 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/validation-fixtures/continuation-after-TDD-timeout-r1/author root/docs/review-results/notification-toggle.md>) | Claude未／Codex未 |
| ains-ship | 正常：[ ローカルPR資料を作成し人の判断で停止 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/ultragoal/evidence/g004/claude/native-v3/runs/20261024T213927Z-6b935d15/chain-ship/chain-ship.json>) | 正常：[ 21テスト成功・HUMAN_REQUIREDをローカルPR資料へ反映 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/validation-fixtures/continuation-after-TDD-timeout-r1/author root/docs/changes/2026-10-25-order-confirmation-email-toggle/pr.md>) | Claude未／Codex未 |
| ains-retro | 正常：[ 5問に回答し現行仕様へ保存失敗時の振る舞いを反映 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/validation-fixtures/internal-trial-claude-r1/retro/docs/ains/retro.md>) | 正常：[ 5問に回答し現行仕様へ数値・ゼロの振る舞いを反映 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/validation-fixtures/internal-trial-codex-r1/retro/docs/ains/retro.md>) | Claude未／Codex未 |
| ains-team-canvas | 正常：[ 8領域、現行の取り決め、空欄・担当・期限を整理 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/validation-fixtures/internal-trial-claude-r1/team-canvas/docs/ains/team-canvas.md>) | 正常：[ 8領域、7決定の反映先、課題の担当・期限。表配置を限定修正 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/validation-fixtures/internal-trial-codex-r1/team-canvas/docs/ains/team-canvas.md>) | Claude未／Codex未 |
| ains-harness | 正常：[ make checkを追加・実行、1テスト成功、段階導入のIssue下書き ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/validation-fixtures/internal-trial-claude-r1/harness/docs/ains/harness-issue.md>) | 正常：[ make checkを追加・実行、1テスト成功、Issue下書き ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/validation-fixtures/internal-trial-codex-r1/harness/docs/ains/harness-issue.md>) | Claude未／Codex未 |
| ains-tool-access | 正常：[ CLI/MCP・タスク・権限・認証・成否を具体化 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/validation-fixtures/internal-trial-claude-r1/tool-access/docs/ains/tool-access.md>) | 正常：[ CSV合計20を実測、接続・権限・承認範囲を整理 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/validation-fixtures/internal-trial-codex-r1/tool-access/docs/ains/tool-access.md>) | Claude未／Codex未 |
| ains-grilling | 正常：[ 個別の問い→回答→次の問い ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/ultragoal/evidence/g004/claude/native-v5/runs/20261024T224006Z-cc0d1d63-symlink/chain-build-continuation/chain-build-continuation.json>) | 正常：[ 操作範囲・影響・復旧を含む確認質問 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/continuations/resume-20261027-j56k2v96/remaining-evidence-r1/post-TDD-P5-actual-r1/observation.json>) | Claude未／Codex未 |
| ains-tdd | 正常：[ 失敗する試験→修正→成功 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/ultragoal/evidence/g004/claude/native-v1/runs/20261024T193814Z-a0dc2dba/automatic-tdd-symlink/automatic-tdd-symlink.json>) | 正常：[ 実行ログで新回帰exit2→関数修正→exit0/2tests ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/continuations/resume-20261027-j56k2v96/internal-trial-acceptance-r1/codex/build.stdout.jsonl>) | Claude未／Codex未 |
| ains-review-gate | 正常：[ 人確認対象でHUMAN_REQUIRED / exit10 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/ultragoal/evidence/g004/claude/REPORT-r2.md>) | 正常：[ 実スクリプトがHUMAN_REQUIRED / exit10、PR資料で停止 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/validation-fixtures/continuation-after-TDD-timeout-r1/author root/docs/changes/2026-10-25-order-confirmation-email-toggle/pr.md>) | Claude未／Codex未 |
| ains-release-safety | 正常：[ 実commit→revert→復元と保持データを確認 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/ultragoal/evidence/claude-r7-complete-acceptance-audit/coverage.json>) | 正常：[ 実commit→revert→復元、同じOFFデータで0→1→0 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/continuations/resume-20261027-j56k2v96/saved-P6-payload-replay-r1/REPORT.md>) | Claude未／Codex未 |
| ains-context-care | 正常：[ 誤参照rule.mdと実在rules.mdを突き止め最小修正先を特定 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/validation-fixtures/internal-trial-claude-r1/context-care/docs/context-check.md>) | 正常：[ 仕様に既存パターン・契約・部品・依存と根拠を記載 ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/validation-fixtures/continuation-after-TDD-timeout-r1/author root/docs/changes/2026-10-25-order-confirmation-email-toggle/spec.md>) | Claude未／Codex未 |

## 今回追加した実行

Claude Code 2.1.312 / claude-sonnet-5-5：context-care、retro、team-canvas、harness、tool-accessの5件が正常終了（各exit0、結果success）。Codex 0.164.0 / gpt-6.1-sol：retro、team-canvas、harness、tool-access、tasks、buildを8入力で確認し、すべて正常終了。tasksは質問と別入力の試験用承認、canvasは限定修正1回を含む。buildでは実際に回帰試験を失敗させ、関数を変更して2テストを成功させた。

初回Claude起動の引数区切り不備によるモデル実行前のexit1と、Codex canvas初回の表配置ミスは原本を保持した。修正後の正常結果を今回の一覧へ採用した。過去のタイムアウトや質問欠落も履歴として残している。

- [Claude実行結果・成果物ハッシュ](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/continuations/resume-20261027-j56k2v96/internal-trial-acceptance-r1/claude/ASSESSMENT.json>)
- [Codex実行結果・全成果物一覧](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/continuations/resume-20261027-j56k2v96/internal-trial-acceptance-r1/codex/summary.json>)
- [Codex計画への実際の確認質問](</Users/<user>/.t3/projects/ai-native-software-engineering/.omx/continuations/resume-20261027-j56k2v96/internal-trial-acceptance-r1/codex/tasks-draft-question.txt>)

## 結果の範囲

既存のClaude実行は主に2.1.310、Codexは記録ごとの0.163.0／0.164.0で行った。全32項目を今回同じ版・同じ環境で実行し直したものではない。現行で変更した仕様確認とレビュー引継ぎには、それぞれ変更後の結果を用いた。

合成ケースの役割・承認回答は試験入力であり、利用者本人の最終確認を代替しない。tool-accessは接続方法の設計とローカル処理を対象とし、GitHubへの実接続・認証は確認していない。harnessの1テストはコマンド整備の動作例である。実運用の効果・全環境互換性・配布先への動作保証は今回の確認範囲に含めない。

## 人の最終確認

上の16行の両製品の成果を開き、期待する用途で使える内容か確認する。差し戻す場合はスキル名・製品・気になった点を記録する。確認者・確認日・結果が記録されて初めて今回の完了条件を満たす。

- 確認者：未記入
- 確認日：未記入
- 結果：未確認

公開・push・外部PR・マージ・デプロイは実施していない。
