<img src="assets/icon.svg" width="64" height="64" alt="">

# AI-Native 開発ワークフロー スキル群

AIを使った開発が初めてなら、[小さな変更を通して試す](docs/getting-started.md)から始める。Git・ターミナルと製品の導入・認証ができる開発者向け。

現在は社内・チームでの試用段階。以前の版では16スキルを両製品で各1回動かした結果が揃った。`ains-team-canvas` はその後に合意記録の手順へ変更し、変更後の実製品確認は未実施である。人による成果の最終確認と、初見の利用者が作者の補足なしで進められるかの確認は未了。[現在の確認範囲](docs/compatibility.md)と[初見利用の記録用紙](docs/first-use-check.md)を参照。

目的・制約・受入条件を先に決め、その範囲の実装と修正をAIに任せる Claude Code / Codex 向けエージェントスキル。人は仕様、計画、差分、展開を判断する。

## 使い方

入口は Claude Code の `/ains`、Codex の `$ains`。今の状況を見て、次に使うスキルを示す。以下の流れと表は Claude Code の表記で、Codex では先頭の `/` を `$` に置き換える。

```
/ains-setup → /ains-spec → /ains-tasks → /ains-build → /ains-ship → /ains-retro
（初回のみ）   質問して仕様   方針とタスク   テスト先行で実装  検証・PR・展開   学びを戻す
```

小さな変更は `/ains-spec` の中にタスクも書き、`/ains-tasks` を省く。1行の修正は流れに乗せない。

## スキル

### 利用者が呼ぶ

| スキル | 成果 |
|---|---|
| `/ains` | 次に使うスキル |
| `/ains-setup` | AGENTS.md の Agent skills 節（CLAUDE.md からも読み込む）と、人の確認の規則 |
| `/ains-spec` | `status: approved` の spec.md |
| `/ains-tasks` | `status: approved` の tasks.md（Done when 付き） |
| `/ains-build` | タスク単位のテスト先行実装 |
| `/ains-ship` | 埋まった PR 本文と、人によるマージ・展開の判断 |
| `/ains-retro` | 規約・現行仕様・回帰テスト・レビュー規則への反映 |
| `/ains-team-canvas` | 合意した運用・担当・反映先と未決事項の記録 |
| `/ains-harness` | CI と自動化の次の一手 |
| `/ains-tool-access` | 外部ツールの接続方針と権限 |

利用者が呼ぶ段階は、Claude Code の `disable-model-invocation: true` と Codex の `agents/openai.yaml` の `policy.allow_implicit_invocation: false` で明示起動にする。これは起動の制御であり、操作権限や仕様・計画への承認を与える設定ではない。Codex での文脈節約量は保証しない。

### エージェントが必要に応じて使う

| スキル | 規律 |
|---|---|
| `ains-grilling` | 質問で認識を揃える（推奨案つき、事実はAI・決定は人） |
| `ains-tdd` | 赤→緑→整理、再現から始めるバグ修正 |
| `ains-review` | 別セッションの敵対的レビューと指摘の選別 |
| `ains-review-gate` | パスと差分の規則で人の確認の要否を判定、マージ条件 |
| `ains-release-safety` | フラグ、段階公開、戻らない状態変更 |
| `ains-context-care` | 規約無視の診断、引継ぎ、ルールの整理 |

## 変更ごとの成果物

```
docs/changes/<日付-slug>/
├── spec.md    目的・文脈・制約・受入条件・対象外・観測された契約・未決事項（status: draft | approved）
│              小さな変更ではタスクとメモもここに書く
└── tasks.md   方針・任せる範囲・停止条件・タスク（Done when）・メモ（status: draft | approved）
```

人の承認を記録するのは spec.md と tasks.md の `status`。マージと展開の判断は `/ains-ship` が1回の質問で求める。検証結果は PR 本文にまとめ、PR を作らないときは本文の下書きを `pr.md` に置く。

## スクリプト

| スクリプト | 用途 |
|---|---|
| `ains/scripts/status.sh [<dir>]` | 変更ごとの spec と計画の状態、未決事項、タスクの進捗 |
| `ains-spec/scripts/new-change.sh <slug>` | 変更ディレクトリと spec.md の雛形 |
| `ains-review-gate/scripts/route-review.sh <rules> [base]` | 人の確認の要否判定（10 = 必須、0 = 規則外、3 = 判定不能） |

## 導入

全スキルのプロジェクト単位の一括導入を利用契約とする。段階ごとに使い分けられるが、個別スキルだけの導入は動作保証の対象外。対象は Claude Code / Codex で、他エージェントと macOS 以外の OS は未検証。両製品の正式な実行時サポート確認はまだ完了していない。[検証状況と互換性](docs/compatibility.md)を参照。

前提は Node.js 22.20 以降と npm/npx、git、bash、および利用する製品のインストールと認証。[skills 公式 README](https://github.com/vercel-labs/skills#install-a-skill)の Node 要件に従う。初期の配布確認環境は skills 1.7.4、Node 24.13.1、npm 11.8.0、git 2.54.0、bash 5.2.26、Claude Code 2.1.308、Codex 0.163.0、macOS 26.7。これらは検証対象の版であり、全バージョンの保証ではない。最新の追加試用は Claude Code 2.1.312 / Codex 0.164.0 で行った。各結果の版と範囲は[試用確認一覧](docs/internal-trial-validation.md)に記載する。

このリポジトリは [MIT License](LICENSE) で提供する。以下ではローカルのチェックアウトから導入する。

```bash
# ソースのリポジトリを cwd にした場合：このリポジトリ自身へ導入
npx --yes skills@1.7.4 add . --list
npx --yes skills@1.7.4 add . --skill '*' -a claude-code codex -y
```

別のプロジェクトで使う場合は、**利用先を cwd** にし、ソースを絶対パスで指定する。`.` は常に現在のディレクトリを指す。

```bash
cd /absolute/path/to/consumer-project
npx --yes skills@1.7.4 add /absolute/path/to/ai-native-software-engineering --list
npx --yes skills@1.7.4 add /absolute/path/to/ai-native-software-engineering --skill '*' -a claude-code codex -y
npx --yes skills@1.7.4 list -a claude-code codex
```

`--all` は全エージェントも対象にするため使わない。通常配置はリンクを使い、コピー配置は同じ add に `--copy` を付ける。実際の参照先は Claude Code が `.claude/skills/`、Codex が `.agents/skills/`。導入後、利用先で Claude Code は `/ains-setup`、Codex は `$ains-setup` を実行する。インストールとプロジェクトのワークフロー設定は別の作業である。

設定の正本は `AGENTS.md` の Agent skills 節とし、Claude Code は `CLAUDE.md` の `@AGENTS.md` import で読む。既存の CLAUDE.md だけにある設定はその節を移し、無関係な文章を保持する。重複は統合し、値が食い違う場合は選択を確認してから移す。同一実体・シンボリックリンクは重複書き込みや自己 import を避ける。詳細と未検証の移行ケースは[互換性文書](docs/compatibility.md)を参照。

### 更新・削除

利用先の cwd で実行する。ローカルソースの内容を更新したら、上の絶対パスによる全スキル add を再実行する（コピー配置なら再び `--copy`）。リンク配置でもメタデータや配置の再確認に同じ手順を使う。CLI 1.7.4 の両配置方式で、一時ソースの変更が再追加後の利用先に反映されることを確認した。リモート更新の検出でローカル変更が反映されるとは保証しない。

CLI 1.7.4 の help で確認したプロジェクト更新の構文は `npx --yes skills@1.7.4 update -p -y`。これは利用先の他のスキルも対象にするため、必要なら `update <skill名...> -p -y` で絞る。ローカルソースには上記の再追加を使う。新版の CLI を使う場合は help、配布検査、製品の実行を再確認してから版を変える。

ains だけを両製品から削除する場合：

```bash
npx --yes skills@1.7.4 remove ains ains-setup ains-spec ains-tasks ains-build ains-ship ains-retro ains-team-canvas ains-harness ains-tool-access ains-grilling ains-tdd ains-review ains-review-gate ains-release-safety ains-context-care -a claude-code codex -y
```

この名前指定削除は両配置方式で検証し、無関係なスキルが残ることを確認した。削除後は `list -a claude-code codex` で確認する。設定した AGENTS.md / CLAUDE.md や変更成果物の整理は、スキルの削除とは別に判断する。

### バージョン

skills CLI はスキルの版番号を持たず、取得元の git ref と内容のハッシュを利用先の `skills-lock.json` に記録する。このため版は git タグ `vX.Y.Z` で表し、16スキルを1つの版として扱う。スキルごとの版は持たない（一括導入が利用契約のため）。変更内容は [CHANGELOG.md](CHANGELOG.md) に書く。

[Semantic Versioning](https://semver.org/lang/ja/) に従い、次の変更はメジャーを上げる。試用段階の 0.x ではマイナーを上げる。

- スキルの削除・改名、利用者が呼ぶか自動かの区分の変更
- spec.md / tasks.md の書式や `status` の値など、利用先に残る成果物の互換を壊す変更
- `scripts/` の引数・終了コードの変更

リモートから版を固定して導入する。利用先を cwd にし、`#` の後にタグを付ける。

```bash
npx --yes skills@1.7.4 add 53able/ai-dev-workflow-skills#v0.1.0 --skill '*' -a claude-code codex -y
```

指定した ref は `skills-lock.json` の `ref` に記録される。`skills-lock.json` は利用先でコミットする。`update` は記録した ref と照合するため、タグを固定した場合は版が上がらない。版を上げるときは新しいタグで上の add を再実行する。16スキルの `ref` と内容が新しいタグのものに置き換わる。ref を省くと既定ブランチを追い、`update` で最新の内容になる。

CLI 1.7.4 で、このリポジトリに一時的に置いたタグとブランチを使い、リンク・コピー両配置で上記を確認した。ブランチを指定した場合は、ブランチが進むと `update` が変更を取り込む。

リリース手順：

1. `CHANGELOG.md` の `Unreleased` を版番号と日付に置き換える。
2. 配布検査 `bash tests/distribution/test-distribution.sh` を通す。
3. main で `git tag -a vX.Y.Z -m vX.Y.Z` を作り、`git push origin vX.Y.Z` で公開する。

## 設計

方針は [docs/skill-set-design.md](docs/skill-set-design.md)。

## 検証

開発用の比較ケースは `tests/evals/ains-spec/`、`tests/evals/ains-build/`、`tests/evals/ains-review-gate/` に置く。元の5ケース・76ファイルを内容とモードを保持して移動し、配布スキルから分離した。結果は `ains-workspace/`（git 管理外）に出力する。

スキル内の `assets/`、`scripts/`、参照 Markdown、`agents/` の製品設定は実行時の配布対象。開発用 eval、grader、fixture は導入しない。[配布検査の実行方法](tests/distribution/README.md)と[製品別の証拠](docs/compatibility.md)を参照。静的検査の成功だけで製品上の動作確認完了とはしない。

## License

[MIT](LICENSE)
