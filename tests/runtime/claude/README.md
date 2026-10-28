# Claude G004 runtime evidence

Dependency-free Python/system-tool harness for actual Claude Code sessions. Requires the existing secure host login, `claude` 2.1.308 with `claude-sonnet-5-5`, Git, Python 3, npm/npx and skills 1.7.4. This harness never provisions or copies credentials. It writes only this lane's evidence and disposable `/private/tmp` consumer repositories. Model calls use normal session-local tool grants, not permission bypasses.

Run from the distribution checkout:

```sh
python3 tests/runtime/claude/runtime.py
python3 tests/runtime/claude/suite.py controls
python3 tests/runtime/claude/suite.py setup
python3 tests/runtime/claude/suite.py negative
python3 tests/runtime/claude/provenance.py
python3 tests/runtime/claude/actual_symlink.py
python3 tests/runtime/claude/workflow_r2.py
python3 tests/runtime/claude/migrated_cases.py
python3 tests/runtime/claude/original_build_cases.py
python3 tests/runtime/claude/finalize.py
```

The recorded `prototype-router.json` preserves the original restrictive-permission failure. Current harness commands use the corrected normal Bash grant. Each suite case creates its own unique Git consumer with spaces, copies the **already installer-produced** tree preserving its links, and uses fresh model context. `install-*.json` retains pinned installer argv and all skill/metadata hashes. Run `controls` before workflow to create both installation modes.

Every real model turn has a 180 second limit. Only the harness's process group is terminated on timeout; successful streaming turns close stdin and get a graceful-exit window. A stop after a successful result is distinguished from a timeout. Synthetic approvals are distinct user-role transport inputs after observed result pauses; future replays also gate those inputs on observed pause, draft artifacts and unchanged implementation. They are fixture-only inputs, never production consent or mocked assistant output.

`workflow.py` preserves the first trial, whose phrase “source edits” was ambiguous and whose uncommitted fixture lacked a Git baseline. `workflow_r2.py` clarifies source-repository versus consumer edits, supplies actual test command/output evidence to a separate real reviewer, and authorizes exactly one local baseline commit through a synthetic **user-role** input. The child process receives fixture-only Git author environment values; global Git configuration is untouched. No implementation commit or external action is authorized.

Raw stdout/stderr stays in memory. A temporary debug log outside the consumer is reduced to loader-operation/path facts and deleted. Current runs use a private temporary log directory, then delete it. Only fixture/model event material is retained, with recursive string sanitization for email/token patterns. No global configuration/auth contents are collected. `verification.json` audits actual installed Read/Skill base-directory paths and hashes, ancestor rules, runtime exits, negative-case artifacts and setup shape. It does not turn discovery or absent events into activation proof.

The original sanitizer applied redaction to serialized JSON and failed on an import-containing setup result; it was changed to recursive string sanitization and that case rerun in a fresh fixture. This historical harness failure is not a product failure. Snapshots cover Markdown/Python; final rule-file evidence is captured separately in `final-audit.json`.

Limitations are contractual: explicit slash expansion is not fully exposed by the available stream/debug observer. Supplemental explicit reads prove installed procedure provenance, but do not by themselves prove the slash injection mechanism or its complete suppression. See the evidence REPORT; a successful run must not be advertised as formal support while its required gates are unverified or failing. Disposable roots are retained for parent verification; do not recursively clean arbitrary temp directories.

Historical mode correction: initial `install-symlink.json` used a single Claude target and produced physical direct directories, despite its label. `install-actual-symlink.json` uses the pinned multi-target Claude/Codex installer command and verifies all Claude skill entries are symlinks into `.agents/skills`. `actual_symlink.py` supplies the three required explicit runtime controls on those real links. No Codex model was run in this lane. Current install() uses both project targets so future default runs obtain actual symlinks. See REPORT for the exact physical-mode coverage.

Original migrated fixtures are replayed by `migrated_cases.py` and `original_build_cases.py`. The latter obtains synthetic user-role authority for original task-local commits in the successful build case; the draft/missing cases authorize only scaffold baseline commits. Source files/prompts are hash-mapped in original-five-case-map.json. Exact original notification-save-failure and migration-mitigation criteria remain failing/partial; those failures are not replaced with generic workflow passes.
