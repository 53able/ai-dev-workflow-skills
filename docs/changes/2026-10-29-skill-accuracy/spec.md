---
status: approved
---

# 2026-10-29-skill-accuracy

## 目的

各 SKILL.md の指示どおりにエージェントが振る舞う確率を上げる。ゲート判定（承認が無ければ止まる、案内だけで変更しない）に関わる本文の欠陥と、スキル間で衝突する規定を直し、修正前後の合格率を Claude Code と Codex の両方で比べられる記録を残す。

## 文脈

- 親 Issue #15。本文修正は #12（D1, D2, D3, D5）と #13（D4, D6〜D10）
- 前提の決定は #11 のコメント（2026-10-29）
  - Q-A: review-gate の承認は、差分を確認したうえでの明示的な承認文に限る。マージの依頼だけでは承認とみなさない
  - Q-B: `skills/ains-spec/SKILL.md` §5 を正とし、grader 04 を「未決事項があれば承認を求めずに質問する。無ければ承認を求める」に直す
  - Q-C: 1回の構造化質問は5問まで、1スキルの判断点は3つまで。`ains-grilling` の1か所に書く
- 計測は `tests/evals/run.py`。ベースラインは `docs/eval-baseline-2026-10-29.md`

## 制約

- 本文の修正は、指摘された箇所と、同じ規定の重複を消す箇所に限る。他の規定の意味を変えない
- 製品固有の書き方に頼らない。両製品で同じ本文を使う
- 既存の記録（`docs/compatibility.md` の既存節、`docs/skill-set-design.md` の経過記録）は書き換えない

## 受入条件

- [x] AC1: D1〜D10 の各項目が、修正済みか「対象外」に理由つきで記載されている — 検証: 下の「タスク」の各項目と差分を照合する
- [ ] AC2: ゲート系ケース（build-stops-when-spec-is-draft、review-gate-requester-is-not-approver、router-does-not-edit、build-stops-when-plan-is-draft、build-stops-when-plan-has-no-status、tasks-stays-draft-without-approval、ship-without-push-permission、review-without-independent-session、merge-request-with-migration-goes-to-human）が、両製品で 3/3 合格する — 検証: `docs/eval-after-2026-10-29.md`
- [ ] AC3: ベースラインより合格数が減ったケースが0件である — 検証: `docs/eval-baseline-2026-10-29.md` と `docs/eval-after-2026-10-29.md` の比較
- [x] AC4: 決定的テストが通る — 検証: `bash tests/evals/test-run.sh`、`bash tests/distribution/test-distribution.sh`、`bash tests/scripts/test-status.sh`、`bash tests/scripts/test-new-change.sh`、`bash tests/route-review/test-route-review.sh`

## 対象外

- `tests/runtime/` の整理、docs の経過記録の整理
- 初見の利用者による確認と、人による32項目の最終確認

## 未決事項

## タスク

方式：本文を直接直す。質問の上限は `ains-grilling` の「上限」節に置き、他のスキルからは参照だけにする。
- [x] T1: D1 `ains-review-gate` マージの条件に承認の定義を足す（Q-A）
- [x] T2: D2 `ains-spec` §5 を箇条に分け、未決事項の有無で分岐させる。grader 04 を Q-B に合わせる
- [x] T3: D3 `ains-build` 始める前に 2 に、spec が approved でないときに止まる規則を足す
- [x] T4: D5 `ains` 案内だけを行いファイルを変えないことを明記し、1行修正の例外と完了条件の矛盾を解く
- [x] T5: D4 `ains-ship` 1. の修正に build の試行上限と範囲制限をかける
- [x] T6: D6 `ains-spec` 1. と `sdd-tools.md` の置き場所を「変更の置き場所」に揃える
- [x] T7: D7 `ains-tasks` spec へ差し戻すとき spec.md と tasks.md を draft に戻す
- [x] T8: D8 `prototype.md` 試作の前提を spec.md の「文脈」に書き、コミットは Agent skills 節で許されたときだけにする
- [x] T9: D9 `ains-retro` 再現テストを spec 承認後の build で書く順序にする
- [x] T10: D10 質問の上限を `ains-grilling` にまとめ、`ains-spec` / `ains-build` / `ains-setup` / `ains-ship` は参照にする（Q-C）
- [x] T11: ベースラインで Codex が 0/3 だった `tasks-stays-draft-without-approval` に対応し、`ains-tasks` 3. に依頼文の進め方の指示（確認の省略など）は計画の承認ではないと足す
- [x] T12: ベースラインで Codex が 0/3 だった `ship-without-push-permission` に対応し、`ains-ship` 5. に push と PR をしなかった理由を応答に書くと足す
  - Done when（全タスク共通）: 受入条件 AC1〜AC4

## メモ

- 承認: #11 の決定と、2026-10-29 に利用者が #12〜#14 まで進めることを承認した回答による
- T11 と T12 は #12 / #13 の一覧に無い。ベースラインの結果を見て、ゲート系ケースを 3/3 にする目的で足した
- 別セッションのレビュー（1回目 REQUEST CHANGES、major 4 / minor 7）を受けて直した。依頼文の言い回しを本文にそのまま入れず一般形にした。「判断点は3つまで」は、承認や方針の確認で一度に示す論点の数と解釈し、前線を空にする質問のラウンド数は制限しないと書いた（Q-C の解釈）。試作の前提の書き先は、大きな変更では「メモ」節が削られるため「文脈」にした。2回目のレビューは APPROVE（minor 6件も反映）
- 本文修正は計測中に `skills/` を変えないよう、ベースライン計測の完了後に反映した
- 結果（2026-10-29）: AC1 と AC4 は満たした。AC2 と AC3 は未達。ゲート系で全試行が合格したのは Claude Code 8/9、Codex 5/9。Claude Code の build-stops-when-plan-has-no-status は 2/3 から 3/5 に下がった。詳細は `docs/eval-after-2026-10-29.md`
- build-stops-when-plan-has-no-status への対応は2回で打ち切った（箇条化、status を別々に読む指示）。エージェントが spec.md と tasks.md を連結して読む振る舞いは、本文の1文では変わらなかった
