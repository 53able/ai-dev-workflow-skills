# AGENTS.md

- Python 3.11+、標準ライブラリのみ

## Agent skills

- 検査：`python3 -m unittest discover -s tests -t .`
- 変更の置き場所：`docs/changes/`
- 人の確認が必須の変更：`docs/ains/human-review-rules`（ains-review-gate が判定する）
- AIに任せる操作：編集、ローカルの検査
- 外向き操作（push、PR、マージ、デプロイ、外部への送信、本番データの変更）：人の指示で行う
