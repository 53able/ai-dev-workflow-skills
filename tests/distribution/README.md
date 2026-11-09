# 配布先に必要な16スキルが揃うか確認する

スキルの導入・更新方法を変更したときに使う開発用検査です。Claude Code 単独、Codex 単独、両製品への導入を、通常のリンク配置とコピー配置で確認します。製品のモデルは起動しません。

## 前提と実行

bash、git、uv（Python 3.11以降）、Node.js、npm/npx が必要です。固定した skills CLI 1.7.4 をキャッシュから使うか、ダウンロードできる環境で実行してください。リポジトリのルートで次を実行します。

```sh
bash tests/distribution/test-distribution.sh
```

`failed=0` と終了コード0を確認します。失敗した項目は出力に `FAIL` と理由が表示されます。メタデータだけを調べる場合とログを保存する場合は、次のオプションを使えます。

```sh
bash tests/distribution/test-distribution.sh --static-only
bash tests/distribution/test-distribution.sh --log-dir /absolute/path/to/new-log-directory
```

絶対パスでランナーを指定すれば、別の作業ディレクトリからも実行できます。検査は一時プロジェクトにのみ導入し、終了時に自身の一時領域を削除します。子プロセスの HOME・設定は分離し、既存の npm キャッシュを再利用します。グローバル導入は行いません。

## 何を検査するか

- 16スキルの名前、起動方針、実行時に必要なファイル
- インストール後のスクリプトの実行、雛形出力、実行権限
- スキル内・隣接スキルへの Markdown リンク
- 開発用の評価ケース・採点器・fixture が配布されないこと
- 空白を含むパスと、製品ごとの起動設定

期待する一覧は `intended-skills.json` にあります。明示起動の入口と4補助工程、エージェントが呼べる主要5工程、必要に応じて使う6規律を区別しています。発見したファイルから期待値を生成すると、意図しない削除や区分変更を見逃すため、この一覧は独立して維持します。起動可能という設定は、操作の許可や仕様・計画の承認を与えません。

メタデータの検査は `check_distribution.py` が定める範囲だけを解析します。先頭の front matter と Codex の `policy.allow_implicit_invocation` が対象です。未対応の書式や重複はエラーになり、一般的な YAML 全体の検証は行いません。

`--eval-inventory <original-eval-inventory.json>` を付けると、移動前に保存した非公開の一覧と、`tests/evals/<skill>/` のファイル集合・ハッシュ・モードも照合します。

## 関連するスクリプト検査

```sh
bash tests/route-review/test-route-review.sh
bash tests/scripts/test-status.sh
bash tests/scripts/test-new-change.sh
```

これらも使い捨て fixture と利用先の作業ディレクトリを使います。`STATUS_SCRIPT` と `NEW_CHANGE_SCRIPT` を指定すると、導入済みのスクリプトを検査できます。

配布検査の成功が証明するのは、配置と静的契約です。製品上での起動、独立レビュー、承認待ちなどの振る舞いは、[実製品の確認範囲](../../docs/compatibility.md)で別に確認してください。
