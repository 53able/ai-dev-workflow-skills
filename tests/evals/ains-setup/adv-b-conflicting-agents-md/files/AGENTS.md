# AGENTS.md

- Python 3.11+、標準ライブラリのみ
- 金額は整数の円で扱い、浮動小数点を使わない

## Agent skills

- 検査：`python3 -m unittest discover -s tests -t .`（タスクと変更を閉じる前に実行する）
- 変更の置き場所：`docs/changes/`
- AIに任せる操作：編集、ローカルの検査
- 外向き操作（push、PR、マージ、デプロイ、外部への送信、本番データの変更）：人の指示で行う
