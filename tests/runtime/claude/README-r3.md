# Claude r3 bounded terminal lane

Known FAIL; do not run more duplicate negative/positive sessions before an approved repair. Prior evidence is unchanged. Output: `.omx/ultragoal/evidence/g004/claude/release-r3/`; terminal report is sibling REPORT-r3.md.

Completed sequence:

```sh
python3 tests/runtime/claude/release_r3.py bootstrap
python3 tests/runtime/claude/release_r3.py negatives
# Stops after unnamed-spec-copy FAIL; no further negative/positive cases.
# Parent then authorized ONLY the two independent question sessions:
python3 tests/runtime/claude/release_r3_questions.py
python3 tests/runtime/claude/release_r3_audit.py
```

Question harness prints a checkpoint after saving the actual first result, then waits at most 120 seconds for its named JSON reply file. A JSON string becomes the next real USER transport input; an object with stop:true ends without another model turn. Inspect the actual question before authoring a fixture-only answer. Completed reply inputs/files are preserved. Do not reuse this completed output root to start another release or prepopulate a future replay with these old replies.

Model turns remain bounded at 180 seconds. Ordinary host auth/settings-source restrictions and session-local tool permissions are retained; no credentials/global configs copied or bypass flags used. Raw debug is outside consumers, reduced to loader facts, then deleted. All sanitized stdout JSON, controlled stdin and contributor snapshots are retained. No new fixture commit is created; the focused spec case materializes original fixture files without its commit scaffold.

Manual load audit includes direct Read, Bash full/partial/helper reads and content Grep through canonical .agents and logical .claude paths. Filename/count-only inventories and ordinary generic requested work are distinct from procedure content. STOP-FAIL preserves the initial detector output; final negative-results/failure-handoff include the earlier indirect Grep evidence and corrected stage-path classification. No source or prior harness file was modified for this lane.
