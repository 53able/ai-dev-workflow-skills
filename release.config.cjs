// Skills are distributed by git tag (README「バージョン」), so there is no npm publish step.
module.exports = {
  branches: ['main'],
  tagFormat: 'v${version}',
  plugins: [
    // README: during 0.x a breaking change bumps the minor. Remove this rule when moving to 1.0.0.
    ['@semantic-release/commit-analyzer', { releaseRules: [{ breaking: true, release: 'minor' }] }],
    '@semantic-release/release-notes-generator',
    ['@semantic-release/changelog', {
      changelogTitle: '# Changelog\n\n版の付け方は [README のバージョン](README.md#バージョン)を参照。この節以降はリリース時に semantic-release が更新する。',
    }],
    ['@semantic-release/git', {
      assets: ['CHANGELOG.md'],
      message: 'chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}',
    }],
    '@semantic-release/github',
  ],
};
