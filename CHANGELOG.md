# Changelog

版の付け方は [README のバージョン](README.md#バージョン)を参照。この節以降はリリース時に semantic-release が更新する。

## [0.3.4](https://github.com/53able/ai-dev-workflow-skills/compare/v0.3.3...v0.3.4) (2026-10-29)


### Bug Fixes

* Codex が $<名前> で注入したスキルを起動とみなし、[#25](https://github.com/53able/ai-dev-workflow-skills/issues/25) の計測を記録する ([3e6d004](https://github.com/53able/ai-dev-workflow-skills/commit/3e6d004ba28b8732ea3879876a6cd54775bd96ca))
* route-review.sh の一時ディレクトリを TMPDIR の下に作る ([0e922d2](https://github.com/53able/ai-dev-workflow-skills/commit/0e922d22a0b7baccb264c28efdeb75a55b084278))
* スキル本文の残る指摘を一般形に直し、grader 02 の要件の優先を明記する ([dd56de8](https://github.com/53able/ai-dev-workflow-skills/commit/dd56de8306654b4d3c62b1920611421824339076)), closes [#25](https://github.com/53able/ai-dev-workflow-skills/issues/25) [#25](https://github.com/53able/ai-dev-workflow-skills/issues/25)
* レビュー指摘の文言を整理する（重複、長文、参照の形、古い引用） ([72c5c45](https://github.com/53able/ai-dev-workflow-skills/commit/72c5c456f360541d7a4049a9e07c807198927735)), closes [#25](https://github.com/53able/ai-dev-workflow-skills/issues/25)
* レビュー指摘を反映する（作業ツリー内の TMPDIR、承認文の定義、ship の許可の規則） ([667af10](https://github.com/53able/ai-dev-workflow-skills/commit/667af101a77852cacf93dbb5f6e2ae88c8ca2cb3)), closes [#25](https://github.com/53able/ai-dev-workflow-skills/issues/25)
* 推定で起動とみなした Codex のスキルを分けて記録し、計測の記録の誤りを直す ([1de7e93](https://github.com/53able/ai-dev-workflow-skills/commit/1de7e93f6569b8344fc8a745fa28d7fe1d54b9ea)), closes [#25](https://github.com/53able/ai-dev-workflow-skills/issues/25)

## [0.3.3](https://github.com/53able/ai-dev-workflow-skills/compare/v0.3.2...v0.3.3) (2026-10-29)


### Bug Fixes

* new-change.sh で長すぎる slug と複数の slug を usage エラーにする ([f2af10e](https://github.com/53able/ai-dev-workflow-skills/commit/f2af10e42de5f0be15c0222656d96be6238f0c14)), closes [#27](https://github.com/53able/ai-dev-workflow-skills/issues/27)
* status.sh が閉じの --- の無い front matter を承認済みと表示しないようにする ([dd64fb0](https://github.com/53able/ai-dev-workflow-skills/commit/dd64fb07489f8d6bbc6a8b7c8c134a97c5468da0)), closes [#26](https://github.com/53able/ai-dev-workflow-skills/issues/26)

## [0.3.2](https://github.com/53able/ai-dev-workflow-skills/compare/v0.3.1...v0.3.2) (2026-10-29)


### Bug Fixes

* eval の被験実行と採点がホストや実アカウントに届かないよう隔離する ([b584598](https://github.com/53able/ai-dev-workflow-skills/commit/b58459855a77fc9db68f9e5c3085c74adf6a728d)), closes [#28](https://github.com/53able/ai-dev-workflow-skills/issues/28)

## [0.3.1](https://github.com/53able/ai-dev-workflow-skills/compare/v0.3.0...v0.3.1) (2026-10-29)


### Bug Fixes

* 3回目のレビューで残した本文と grader 02 の指摘を直す ([02ca123](https://github.com/53able/ai-dev-workflow-skills/commit/02ca123bd9c53cda6af0c22f61cde0cfc7fafead))
* ains-tasks で承認を求める手順は依頼文で省けないと明記する ([4eaaa80](https://github.com/53able/ai-dev-workflow-skills/commit/4eaaa807570229e6acbece0e72fdb1920764fa63))
* eval で未達だったケースの原因に合わせてスキル本文を直す ([9bfdc5c](https://github.com/53able/ai-dev-workflow-skills/commit/9bfdc5ccc62fde1216f7b359030025844d701b92))
* レビュー指摘を反映し、ains-build の spec.md の規定を受入条件に絞り、承認とレビューの記録を引用に限る ([0ac7f86](https://github.com/53able/ai-dev-workflow-skills/commit/0ac7f86a4abf49e818111253054e5d18e122a958))
* 残る未達ケースの原因に合わせて ains-build、ains-tasks、ains-review を直す ([168751d](https://github.com/53able/ai-dev-workflow-skills/commit/168751d7590c56139ab1880c44ac72ec5931fde3))


### Reverts

* ains-review の記録を引用に限る規定を 9bfdc5c の文に戻す ([1b7d952](https://github.com/53able/ai-dev-workflow-skills/commit/1b7d9526ae4fd0de49a3cb99d009489c47c6af84))

# [0.3.0](https://github.com/53able/ai-dev-workflow-skills/compare/v0.2.0...v0.3.0) (2026-10-28)


### Bug Fixes

* ains-build で spec.md と tasks.md の status を別々に確かめる ([58aabe6](https://github.com/53able/ai-dev-workflow-skills/commit/58aabe6807362da0e79df8aecccff829c72e3eb1))
* ains-build の承認確認を箇条に分け、status 欄の無い tasks.md で止まる条件を目立たせる ([80e3833](https://github.com/53able/ai-dev-workflow-skills/commit/80e3833eba2906b28223610a87588a6f81699931))
* eval の並列実行で Ctrl+C が実行中の試行と採点を止めるようにする ([703a074](https://github.com/53able/ai-dev-workflow-skills/commit/703a0741e06673015d173cf16401c4bbccdbf6f6))
* ゲート判定と質問の上限に関わるスキル本文の欠陥を直す ([#12](https://github.com/53able/ai-dev-workflow-skills/issues/12), [#13](https://github.com/53able/ai-dev-workflow-skills/issues/13)) ([2163f12](https://github.com/53able/ai-dev-workflow-skills/commit/2163f129ee193facc35f39992cc1c01aef246ede)), closes [#11](https://github.com/53able/ai-dev-workflow-skills/issues/11)
* レビュー指摘を反映し、依頼文の言い回しに頼らない一般形にする ([da8a4e4](https://github.com/53able/ai-dev-workflow-skills/commit/da8a4e4943b9fd0a8178281222671c12f873862a))


### Features

* eval 実行系に試行を並列で回す --jobs を追加 ([904e245](https://github.com/53able/ai-dev-workflow-skills/commit/904e2455539d44a963766e7c9ff2c11cf1f0b79a))

# [0.2.0](https://github.com/53able/ai-dev-workflow-skills/compare/v0.1.0...v0.2.0) (2026-10-28)


### Bug Fixes

* Codex の被験実行を空の HOME/CODEX_HOME で隔離する ([c00f34e](https://github.com/53able/ai-dev-workflow-skills/commit/c00f34e7c56016638c1ae49fd48ce282286a6eca))
* eval 実行系のレビュー指摘を修正 ([f52632e](https://github.com/53able/ai-dev-workflow-skills/commit/f52632e50531a5aedfee27e261326c4345a39dde))
* PR [#16](https://github.com/53able/ai-dev-workflow-skills/issues/16) のレビュー指摘を修正 ([8354307](https://github.com/53able/ai-dev-workflow-skills/commit/835430707df5d94db0b6513fa31edceddb1232a1))
* uv.lock から利用者設定由来の exclude-newer を外す ([c9417f5](https://github.com/53able/ai-dev-workflow-skills/commit/c9417f5baa32566768e6b28e58b30e39c0ca1acc)), closes [#3](https://github.com/53able/ai-dev-workflow-skills/issues/3)


### Features

* eval の Claude Code / Codex adapter と採点・集計を追加 ([e109970](https://github.com/53able/ai-dev-workflow-skills/commit/e109970be65aa1ec662aa51814d0439b62415b0a)), closes [#5](https://github.com/53able/ai-dev-workflow-skills/issues/5) [#6](https://github.com/53able/ai-dev-workflow-skills/issues/6) [#7](https://github.com/53able/ai-dev-workflow-skills/issues/7)
* eval 実行系の骨格（解析、scaffold、--dry-run）を追加 ([0dec36a](https://github.com/53able/ai-dev-workflow-skills/commit/0dec36ad3b2259ed08e3a5b3144d6c0a3d2b83b3)), closes [#4](https://github.com/53able/ai-dev-workflow-skills/issues/4)

## 0.1.0

- 最初の版。16スキル（利用者が呼ぶ10、エージェントが使う6）を Claude Code / Codex 向けに skills CLI 1.7.4 で配布する。
