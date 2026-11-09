# Next.jsの固定ソースで工程の続行を検証する


仕様承認後の続行、状態確認、未承認での停止、単独の実装工程を確かめる開発用の実験です。通常の導入は[利用ガイド](../../docs/getting-started.md)、実測結果は[検証レポート](../../outputs/apple-container-validation-ains-nextjs.md)を参照してください。

モデルやコンテナを起動せず、補助処理の単体検査だけを実行する場合は、リポジトリのルートで次を実行します。Python 3が必要です。

```sh
python3 -m unittest discover -s tests/nextjs-continuation -p 'test_*.py' -v
```

`OK` と終了コード0を確認してください。以下の実験再現は Apple Container、固定入力、製品認証が必要で、モデル使用料・実行時間を伴います。既存の出力先を使い回さず、新しいワークスペースで実行します。

These fixtures test ains continuation on the selected Next.js commit. The
apostrophe-matching fault is deliberately seeded into existing framework source;
it is **not** an upstream defect report. The focused Jest regression imports
that source directly. Existing compiled `next/dist` output cannot satisfy it.

`container_case.py` is a Python-standard-library coordinator. Its generated Jest
test follows the consumer's existing TypeScript/Jest conventions; no new JS
harness runtime or project dependency is introduced.

Prepare public inputs under a fresh ignored validation directory: copy a frozen
baseline skills tree, the pinned `packages/next/src/shared/lib/htmlescape.ts` and
source-provenance JSON, then run `prepare.py <workspace>`. The source-provenance
file records repository, commit and SHA-256 of selected source/config files.

Validate and dry-run with the installed Apple Container validation skill's
`validate-manifest.py` and `run-matrix.py`. Run the three-case smoke before the
four-case fixture matrix. The seeded-fault case intentionally has a falsification
oracle: `SEEDED_ACCEPTED`; healthy behavior yields `oracle-fail` for that case.
The manifest claim is only about fixture discrimination, not agent usability.

Live CLI runs require an additional frozen candidate skills copy, authenticated
subscription-only preflight and actual observed edits/test events. Do not copy
credentials into public input trees, manifests, Git or evidence. Codex's private
writable auth cache must be excluded from provenance/hashing and used serially;
never resume it. Claude requires `CLAUDE_CODE_OAUTH_TOKEN`, never an API key.
Unavailable authentication or independent review remains an explicit gap.

## Exact reproduction

From this repository root on the recorded Apple Container host, use a **new**
workspace/run-id each time. The bootstrap refuses an existing directory, fetches
Next.js commit `ec8ddcd7a52fb7b3508fa1cf467abc85dea3a0b8`, derives source hashes from
Git objects, extracts baseline skills from commit
`3b2525c1f96609962dadf7e41dae3afea47faf97`, and copies the current candidate.
No provenance JSON needs to be handwritten. `git clone` is filtered/no-checkout;
`--image-source` additionally fetches all blobs for the large image rebuild.

この再現手順には、別途導入した `apple-container-validation` スキルが必要です。本リポジトリには同梱していません。下の変数を手元の実際の導入先へ置き換え、2つのスクリプトが存在することを確認してから実行してください。`.omx/validation/ains-nextjs-replay` は、この手順で新しく生成する出力先です。

```sh
APPLE_CONTAINER_SKILL_DIR=/absolute/path/to/apple-container-validation
test -f "$APPLE_CONTAINER_SKILL_DIR/scripts/validate-manifest.py" && test -f "$APPLE_CONTAINER_SKILL_DIR/scripts/run-matrix.py"
python3 tests/nextjs-continuation/bootstrap.py .omx/validation/ains-nextjs-replay --image-source
container build --cpus 4 --memory 8G --progress plain \
  -t ains-nextjs-rebuilt:20261108 \
  -f .omx/validation/ains-nextjs-replay/image-rebuild/Containerfile \
  .omx/validation/ains-nextjs-replay/image-rebuild
python3 tests/nextjs-continuation/prepare.py .omx/validation/ains-nextjs-replay --image ains-nextjs-rebuilt:20261108
python3 "$APPLE_CONTAINER_SKILL_DIR/scripts/validate-manifest.py" .omx/validation/ains-nextjs-replay/manifest.json
python3 "$APPLE_CONTAINER_SKILL_DIR/scripts/run-matrix.py" .omx/validation/ains-nextjs-replay/smoke.json --run-id smoke-replay-01 --dry-run --concurrency 1
python3 "$APPLE_CONTAINER_SKILL_DIR/scripts/run-matrix.py" .omx/validation/ains-nextjs-replay/smoke.json --run-id smoke-replay-02 --concurrency 1
python3 "$APPLE_CONTAINER_SKILL_DIR/scripts/run-matrix.py" .omx/validation/ains-nextjs-replay/manifest.json --run-id matrix-replay-01 --concurrency 1
```

Existing recorded runs used already-unpacked image `nextjs-document-baseline:20261108`,
digest `2a42265da56df0907a2c8f6930b8139efee1507b6e8d08650a7eaa7684b9c90d`.
The rebuild recipe was derived from its recorded build history; a fresh rebuild
has **not** been executed by this change. Base tags/apt repositories can change;
record its new digest and do not claim identical historical bytes.

After a successful smoke, live probes use the fresh frozen `input-live-v4`.
Run Codex cases serially. `--scenario` accepts `approved`, `status`, `draft`, and
`standalone`. Use `--bundle baseline` for comparison and `candidate` for the new
contract. All model calls have a 240-second bound, zero retries, and postchecks.

```sh
python3 tests/nextjs-continuation/live.py .omx/validation/ains-nextjs-replay --image ains-nextjs-rebuilt:20261108 --input-dir input-live-v4 --product codex --bundle candidate --scenario approved --run-id codex-candidate-01
python3 tests/nextjs-continuation/live.py .omx/validation/ains-nextjs-replay --image ains-nextjs-rebuilt:20261108 --input-dir input-live-v4 --product claude --bundle candidate --scenario approved --run-id claude-candidate-01
python3 -m unittest discover -s tests/nextjs-continuation -p 'test_*.py' -v
```

Codex uses an existing ChatGPT `auth.json`, copied only to a private run-specific
cache and deleted after that launch; it is excluded from hashes and artifacts.
Claude requires the secret environment variable `CLAUDE_CODE_OAUTH_TOKEN` already
set through a trusted secret channel. It installs exact CLI `2.1.319` once per
container into `/tmp` with the token removed from the npm process environment;
this is a **runtime install**, not an image-pinned CLI. No API key is passed.
Never put a token value in these commands. A successful CLI exit or final claim
is not a workflow PASS: inspect command/test/tool events, hashes and copied files.

The custom live launcher records its own source/hash, public input hashes,
resolved image digest, exact CLI argv, sanitized events, postcheck and source
inventory. `node_modules` and `.git` internals are excluded from the inventory;
HEAD/status/diff names are recorded separately. It does not inherit all standard
runner publication/resume guarantees. Do not resume live runs. Transformed/split
secrets are not universally detected; interruption before sanitation can leave
raw data in the private evidence directory. Review artifacts before sharing.
