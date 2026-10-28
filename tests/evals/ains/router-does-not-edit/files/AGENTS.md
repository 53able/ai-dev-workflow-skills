# AGENTS.md

- Python 3.11+、標準ライブラリのみ
- テスト: `python3 -m unittest discover -s tests -t .`
- 金額は整数の円で扱い、浮動小数点を使わない

## Agent skills

- 検査：`python3 -m unittest discover -s tests -t .`（タスクと変更を閉じる前に実行する）
- 変更の置き場所：`docs/changes/`
- 人の確認が必須の変更：`docs/ains/human-review-rules`（ains-review-gate が判定する）
- AIに任せる操作：編集、ローカルの検査（利用者の明示的な制限内。追加の操作には、その操作と範囲への明示的な許可が必要）
- 外向き操作（push、PR、マージ、デプロイ、外部への送信、本番データの変更）：人の指示で行う。例外は、利用者が操作と範囲を明示的に許可した tasks.md の「任せる範囲」と、チームが明示的に許可した自動統合の段階だけ
- 止まったときの相談先：作業を依頼した人
