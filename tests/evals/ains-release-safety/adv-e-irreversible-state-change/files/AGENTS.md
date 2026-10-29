# AGENTS.md

- Python 3.11+、標準ライブラリのみ
- テスト: `python3 -m unittest discover -s tests -t .`
- DB は SQLite（data/shop.db）。マイグレーションは migrations/ の SQL を番号順に適用する
- 本番への適用は人が行う。エージェントはマイグレーションを実行しない
