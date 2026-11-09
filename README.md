<img src="assets/icon.svg" width="64" height="64" alt="">

# ains — AIと進める開発ワークフロー

**何を作り、何を変えず、何をもって完成とするかを決めてから、実装をAIに任せる。** Claude Code / Codex 向けの16スキルです。仕様、計画、テスト先行の実装、独立レビュー、出荷判断までを、変更ごとのファイルでつなぎます。

Gitとターミナルを扱える開発者向けです。AIを使った開発が初めてなら、[小さな変更を通して試す](docs/getting-started.md)から始めてください。

現在は社内・チームでの試用段階です。以前の版には16スキル×両製品の動作記録がありますが、その後の本文変更すべてを実製品で確認したものではありません。人による成果の最終確認と初見利用の確認も未了です。利用前に[確認済みの範囲と制限](docs/compatibility.md)を確認してください。

## 導入

利用先のプロジェクトへ**16スキルを一括導入**します。各工程は個別に使えますが、スキル同士が参照し合うため、一部だけの導入は動作保証の対象外です。

必要なもの：

- 導入・認証済みの Claude Code または Codex
- Node.js 22.20以降、npm/npx、Git、Bash
- 手元にチェックアウトした、このリポジトリ

以下は**ターミナル**で実行します。パスは手元の実際の絶対パスに置き換えてください。導入コマンドは検証に用いた `skills@1.7.4` に固定しています。

```bash
cd /absolute/path/to/consumer-project
npx --yes skills@1.7.4 add /absolute/path/to/ai-dev-workflow-skills --list
npx --yes skills@1.7.4 add /absolute/path/to/ai-dev-workflow-skills --skill '*' -a claude-code codex -y
npx --yes skills@1.7.4 list -a claude-code codex
```

使う製品が1つなら、`-a claude-code` または `-a codex` に絞れます。`--all` は全エージェントを対象にするため使いません。利用先にソースがない状態の `add .` は、このスキル群を指しません。

Claude Code は `.claude/skills/`、Codex は `.agents/skills/` を参照します。通常はリンク配置です。ソースの場所に依存しないコピー配置にする場合は、`add` に `--copy` を付けてください。

### 初回設定

利用先のディレクトリで製品を起動し、**会話欄**へ入力します。これ以降の `/ains` や `$ains` は、シェルのコマンドではありません。

| 製品 | 最初に入力するもの |
|---|---|
| Claude Code | `/ains-setup` |
| Codex | `$ains-setup` |

検査コマンド、変更記録の置き場所、人の確認が必要な変更、AIに任せる操作を決めます。既定で任せるのは編集とローカル検査です。設定は `AGENTS.md` の「Agent skills」節を正本とし、Claude Code は `CLAUDE.md` の `@AGENTS.md` から読みます。既存設定がある場合は、その値と無関係な記述を保持します。

**インストールと初回設定は別の作業です。** スキル一覧が見えても、プロジェクトの検査コマンドや権限が設定済みとは限りません。

## 使い方

迷ったら、会話欄で Claude Code は `/ains`、Codex は `$ains` を呼びます。コマンドだけなら、ファイルを変えず、現在の状態と次の工程を示します。

変更を進めたいときは、対象と終点を添えてください。以下は Codex の例です。Claude Code では先頭を `/ains` に置き換えます。

```text
$ains 注文履歴に日付フィルターを追加したいです。
仕様の作成から、実装・独立レビュー・ローカルの出荷資料まで進めてください。
コミット、push、PR作成、マージ、デプロイは依頼しません。
```

```text
初回設定 → 仕様 → 計画 → テスト先行の実装 → 検証・レビュー・出荷判断
ains-setup   ains-spec   ains-tasks   ains-build          ains-ship
```

人は仕様と計画を読んで承認します。一連の作業を依頼していれば、承認後は同じ依頼の範囲で次の工程へ進みます。工程ごとのコマンド再入力は不要です。仕様が変わった場合や、範囲を超える判断が必要になった場合は停止します。

小さな変更は仕様に方式とタスクをまとめ、計画ファイルを省きます。1行の修正やタイポには、全工程を使う必要はありません。

### 必要な工程だけ使う

以下は Claude Code の表記です。Codex は `/` を `$` に置き換えます。工程を単独で依頼した場合は、その工程までで終わります。

| したいこと | コマンド | 確認する成果 |
|---|---|---|
| 状態と次の工程を知る／一連の作業を依頼する | `/ains` | 対象の変更と次の工程 |
| プロジェクトの前提を揃える | `/ains-setup` | 検査・権限・人の確認の規則 |
| 要望を検証可能な仕様にする | `/ains-spec` | 受入条件と検証方法を持つ `spec.md` |
| 実装方法と順序を決める | `/ains-tasks` | 方針・範囲・完了条件を持つ `tasks.md` |
| 承認済みの計画を実装する | `/ains-build` | テスト結果と完了したタスク |
| 出荷できるか判断する資料を作る | `/ains-ship` | 受入検証・レビュー結果を含むPR本文 |
| 出荷後の学びを次へ反映する | `/ains-retro` | 現行仕様・規約・回帰テストなどへの反映 |
| チームの運用を決める | `/ains-team-canvas` | 合意・根拠・担当・反映先・未決事項 |
| CIや確認の仕組みを整える | `/ains-harness` | 次に導入する検査と段階導入の方法 |
| 外部ツールの接続を決める | `/ains-tool-access` | 接続方法・対象タスク・権限の範囲 |

`ains`、`retro`、`team-canvas`、`harness`、`tool-access` は明示依頼で使います。主要5工程はエージェントからも呼び出せます。振り返りやチーム運用の変更を自動で始めることはありません。

ほかの6スキルは作業中に必要に応じて使われます。質問の進め方（`ains-grilling`）、テスト先行実装（`ains-tdd`）、独立レビュー（`ains-review`）、人の確認の判定（`ains-review-gate`）、展開・切戻し（`ains-release-safety`）、文脈と引継ぎ（`ains-context-care`）です。詳しい手順は [skills/](skills/) にあります。

### 人が確認すること

- **仕様**：目的、受入条件、対象外が意図と合っているか。
- **計画**：方式、順序、任せる操作の範囲に同意できるか。
- **出荷**：差分、検証結果、未確認事項、展開と切戻しを確認し、マージ・展開を認めるか。

仕様や計画への承認だけで、コミット・push・PR作成・マージ・デプロイの許可が増えることはありません。各操作は、明示された権限の範囲で行います。独立レビューを実行・照合できなければ、未完了として引き継ぎます。

## 成果物と作業の再開

```text
docs/changes/<日付-slug>/
├── spec.md     目的・文脈・制約・受入条件・検証方法・対象外
├── tasks.md    方式・任せる範囲・停止条件・タスク・作業の記録
└── pr.md       PRを作らない場合の出荷資料
```

仕様と計画はそれぞれ `status: draft` または `status: approved` を持ちます。小さな変更では `spec.md` にタスクと作業の記録もまとめます。新しい会話では変更ディレクトリを指定して `/ains` または `$ains` を呼んでください。[再開とトラブルへの対処](docs/work-resumption.md)で、承認待ち・検査失敗・判定不能の場合を説明しています。

## 更新・削除

### ローカルソースから更新する

ソースを更新した後、利用先のディレクトリで「導入」の `add` を再実行します。コピー配置なら、再び `--copy` を付けます。リンク配置も、配置とメタデータの確認を兼ねて同じ手順を使ってください。

既存設定に「各工程は手動起動のみ」とある場合、再導入だけではその方針を変更しません。自動続行へ移る場合は、`ains-setup` に「承認後に主要工程を続行する方式へ起動方針を変更する」と明示してください。操作の権限は別に保持されます。

### バージョン

16スキルを1つの版として扱い、Gitタグ `vX.Y.Z` で固定します。[変更履歴](CHANGELOG.md)を確認し、使いたい公開タグを指定してください。下の `vX.Y.Z` は実在する公開タグに置き換えてください。選んだタグに含まれる文書に従います。旧版は現行版と起動方針が異なる場合があります。

```bash
npx --yes skills@1.7.4 add 53able/ai-dev-workflow-skills#vX.Y.Z --skill '*' -a claude-code codex -y
```

取得元のrefと内容のハッシュは、利用先の `skills-lock.json` に記録されます。このファイルもコミットしてください。タグ固定の場合、版を上げるには新しいタグで `add` し直します。refを省くと既定ブランチを追います。

CLI 1.7.4のプロジェクト更新構文は `npx --yes skills@1.7.4 update -p -y` です。他のスキルも対象になるため、絞る場合は `update <skill名...> -p -y` を使います。ローカルソースには再追加を使ってください。

### 削除する

利用先のディレクトリで実行します。ainsの16スキルだけを対象にします。

```bash
npx --yes skills@1.7.4 remove ains ains-setup ains-spec ains-tasks ains-build ains-ship ains-retro ains-team-canvas ains-harness ains-tool-access ains-grilling ains-tdd ains-review ains-review-gate ains-release-safety ains-context-care -a claude-code codex -y
npx --yes skills@1.7.4 list -a claude-code codex
```

`AGENTS.md` / `CLAUDE.md` の設定と作成済みの変更記録は、スキルの削除とは別に整理します。他のプロジェクト規則も含まれるため、ファイルごと削除しないでください。

## 詳しく読む

| 知りたいこと | 文書 |
|---|---|
| 小さな変更で導入から体験する | [はじめての利用](docs/getting-started.md) |
| 対応製品・検証済みの範囲・制限 | [互換性](docs/compatibility.md) |
| 中断・失敗から作業を再開する | [再開ガイド](docs/work-resumption.md) |
| 各工程の役割と設計方針 | [スキル群の設計](docs/skill-set-design.md) |
| 試用の実績と未確認事項 | [試用確認一覧](docs/internal-trial-validation.md) |
| 導入の分かりやすさを実際に確かめる | [初見利用の確認](docs/first-use-check.md) |
| 配布物を検査する | [配布検査](tests/distribution/README.md) |

開発用の評価ケースは `tests/evals/`、実製品の検証手順は `tests/runtime/` にあります。検査結果は実施した版と条件に限定され、配布検査だけで実製品の動作を保証するものではありません。

リリースは `release.config.cjs` と `.github/workflows/release.yml` の semantic-release で管理し、npmには公開しません。`fix:` はパッチ、`feat:` はマイナー、互換性を壊す変更は `BREAKING CHANGE:` とします。0.xの間は破壊的変更もマイナーを上げます。詳細は[設計文書](docs/skill-set-design.md)を参照してください。

## License

[MIT](LICENSE)
