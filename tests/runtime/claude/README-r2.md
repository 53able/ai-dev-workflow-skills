# Claude source-repair-r2 runtime lane

Closed bounded followup. Do not run additional models against the known incompatibility until an approved repair. r1 evidence and REPORT.md are preserved.

Completed commands:

```sh
python3 tests/runtime/claude/release_r2_cases.py bootstrap
python3 tests/runtime/claude/release_r2_cases.py cases
python3 tests/runtime/claude/release_r2_cases.py controls
python3 tests/runtime/claude/release_r2_workflow.py
python3 tests/runtime/claude/release_r2_audit.py
```

The first four commands launch actual models/installations; the last is read-only deterministic evidence auditing. Output is isolated in `.omx/ultragoal/evidence/g004/claude/release-r2/`. `REPORT-r2.md` sits beside the preserved r1 report. Replaying bootstrap intentionally creates a new installation; do not overwrite this completed evidence when resuming a future release—select a new output root first.

`r2_runtime.py` adds controlled USER stdin, all sanitized stdout JSON events, per-input contributor state, full Skill body/path observations and loader-debug facts to the dependency-free r1 approach. Normal host auth is retained; credentials/global config are never copied. Each model turn is limited to 180 seconds; only own process groups can be terminated. Source is read-only input. Actual AC9 commits/reverts/restoration are separately authorized only by a distinct synthetic USER input inside a disposable consumer. No production consent is inferred.

The approved r1 spec/tasks are explicitly carried into a fresh r2 consumer for the AC9 continuation, with the former characterization substitute rejected. Independent review runs in a fresh real CLI context with frozen baseline diff, actual acceptance evidence and code/tests. It is not an author roleplay or a source-repair approval.

Strict load-policy counterexamples exist in unnamed spec (Read and Bash cat) and unnamed build (Bash cat), despite no native manual Skill invocation. Complete silent slash/effective-input observation remains unverified. See REPORT-r2 and exact fail-event records. No extra dependency or generic testing framework is introduced.
