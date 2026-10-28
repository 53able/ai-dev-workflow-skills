# Changelog

版の付け方は [README のバージョン](README.md#バージョン)を参照。この節以降はリリース時に semantic-release が更新する。

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
