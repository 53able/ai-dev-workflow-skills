# AGENTS.md

- Python 3.11+、標準ライブラリのみ
- テスト: `python3 -m unittest discover -s tests -t .`
- 依存の向きは app → domain と app → infra だけ。domain/ は infra/ と app/ を import しない（domain を DB なしでテストし、保存先を差し替えられるようにするため）
