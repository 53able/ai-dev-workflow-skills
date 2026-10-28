# Bounded Codex runtime evidence

Python standard library and installed `codex`, `git`, `npx` only. Uses secure existing host auth; never copies auth/config, changes global settings, or writes outside the assigned harness/evidence and its own temporary consumers. Model calls use actual installed skills and have 180-second process/turn bounds. Reviewers are separate real sessions. Synthetic fixture decisions are separate USER inputs.

The historical source-bound inventory includes the former Canvas question asset. That asset was removed from the current product; these frozen drivers are not a validator for the redesigned agreement-recording skill. Keep historical pins unchanged.

Historical workflow recipe (preserved for the original installed-source runs). These fixed-name commands are not a fresh validation of the current source. From repository root, preserve existing evidence before any separately authorized replay:

```sh
python3 tests/runtime/codex/runtime.py init
python3 tests/runtime/codex/runtime.py controls
python3 tests/runtime/codex/cases.py
python3 tests/runtime/codex/setup_matrix.py
python3 tests/runtime/codex/setup_resume.py
python3 tests/runtime/codex/workflow.py
python3 tests/runtime/codex/router_check.py
python3 tests/runtime/codex/ship_repair.py
python3 tests/runtime/codex/audit.py
python3 tests/runtime/codex/verify_evidence.py
```

`init` installs skills@1.7.4 in two new consumer projects with spaces; it does not reuse source ancestors. Later scripts use that exact run-state root. `setup_matrix` contains the valid final setup fixtures. `cases` retains the original broad preliminary probes. `ship_repair` is separately authorized by the parent USER to make exactly one local fixture baseline commit with synthetic identity before the runtime agent's work. Its agent still cannot commit or do external operations. Do not invoke that script without such fixture-baseline authorization.

CLI controls use literal dollar syntax in argv arrays. App-server multi-turn cases use live ephemeral threads and actual subsequent user messages. All raw subprocess stderr/auth output stays in memory; evidence retains selected sanitized events. Body/path read provenance is checked against source hashes. The harness does not claim a complete injection observer and never converts absent reads into suppression PASS.

Historical report and gate artifacts are `REPORT.md`, `audit.json`, and `verification.json` in the privately retained run evidence. The disposable consumers are retained for inspection at the path in `run-state.json`. No new project dependency or generic testing framework is introduced.

Historical handoff: r1 results are frozen in `REPORT-r1.md`, `r1-summary.json`, and `verification-r1.json`. The exact original-case result is 4 PASS / 1 FAIL; migration final-response requirements failed despite correct HUMAN_REQUIRED/no-merge. Announced source-r2 repairs are expected version changes. Do not rerun the old fixed-name scripts or overwrite r1 evidence during that repair.

At that historical handoff, `activation_recheck.py` was prepared only. It requires an explicit `--run --freeze-id <parent-announced-id>` and writes a new versioned evidence directory. No activation rerun had happened at that point; this is not the current execution status. Its source-bound effective contributor/required-skill closure remains for parent review; structural launch snapshots are not labeled effective runtime state. It closes stdin and retains all sanitized JSON event/item types.

## Current observer evidence

The final independently audited matrix completed **ten actual controls and all 165 emitted events**, five each using installer default and `--copy`, on Codex 0.163.0 with requested model `gpt-6.1-sol` and skills 1.7.4. Six positives bind installed full spec/build/TDD bodies; both TDD positives show actual red/green. Four unnamed spec/approved-build negatives consume no manual procedure, partial content, resource or helper. Independent inspection plus finite source-bound input/configuration/native-route reasoning establishes **PASS for this configured local activation matrix**.

This is the later completed matrix, not the historical single-positive attempt. Raw structural equality remains `stable:false`; exact projected equality is `stable:true`, excluding only the ignored user-file content digest and exact User-layer version. Relevant source/path/profile/root, MCP union/disabled settings and management premises remain checked. The catalog sidecar is UNVERIFIED as a per-run effective catalog and unused in the proof. Historical failures, the stopped single-positive attempt and earlier UNVERIFIED controls remain unchanged.

Privately retained `REPORT-r2.md` maps completed behavior. The initial `REPORT-r3.md` handoff describes early config/preflight stops; later `attempt-4` manifests and ten default/copy result names map the completed controls. The final independent activation audit gives their terminal verdict and source bounds. Preserve these records separately: the early handoff is not the current count. Later collector fixes do not change historical helper bytes; this audit does not certify generic automated continuation predicates.

Completed behavior checks cover migration mitigations, save-I/O draft criteria, authority-preserving setup, approved workflow, scoped red/green, seven independent-review tests, local ship and scope invalidation. **The original spec interaction still failed one-question pacing**, despite setup's successful one-question pauses. This observer matrix does not rerun questions or whole-workflow cases for the new boundary policy. No new question/full-workflow PASS follows.

Scope is fresh ordinary localhost execution under the **recorded constrained configuration**, retaining authentication and home skill discovery while disabling relevant hooks/plugins/MCP/contributors. It is not unrestricted normal-host, remote-executor, other-version/OS or universal suppression support. “Default” names an installer option, not an additional physical Codex symlink layout. Claude's current direct-read/helper FAIL, incomplete slash/effective-input observation and unrun positive/setup matrices keep combined formal support blocked. See [current compatibility findings](../../../docs/compatibility.md). No additional model replay is required to establish this finite audit result. Detailed evidence remains private; do not overwrite or publish raw transcripts.
