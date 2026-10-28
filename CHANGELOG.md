# Changelog

版の付け方は [README のバージョン](README.md#バージョン)を参照。この節以降はリリース時に semantic-release が更新する。

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
