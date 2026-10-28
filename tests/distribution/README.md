# Distribution regression tests

Run from any cwd using absolute runner paths, or from the repository root:

```sh
bash tests/route-review/test-route-review.sh
bash tests/scripts/test-status.sh
bash tests/scripts/test-new-change.sh
bash tests/distribution/test-distribution.sh
```

Requires bash, Python 3 stdlib, git, Node/npm/npx and access to the pinned skills CLI 1.7.4 package (cached or downloadable). No repository dependency is added. The distribution runner installs only into fresh temporary projects, tests Claude Code alone, Codex alone and both together, each in symlink and `--copy` mode, and removes its own temp roots. Child HOME/config settings are isolated; the existing npm package cache is reused. It never invokes either product's model runtime or installs globally.

`--static-only` skips the CLI matrix. `--log-dir <directory>` retains CLI output and exit codes. `--eval-inventory <original-eval-inventory.json>` additionally verifies the exact migrated file set, hashes and modes under `tests/evals/<skill>/`. The original eval inventory records the pre-move files and is retained privately.

`intended-skills.json` is the independently specified design inventory: ten manual stage roles, six automatic disciplines and required runtime resources. A deliberate architecture change must update this reviewed contract; deriving expectations solely from discovered files would miss accidental deletion or reclassification.

Metadata checks parse only the owned subset documented in `check_distribution.py`: first-line frontmatter and the exact Codex `policy.allow_implicit_invocation` block. Unsupported or duplicate policy syntax fails with an explicit error. Parser fixtures prove that body text, comments and another section's similarly named property cannot satisfy the control. This is not a general YAML parser.

The shell-script suites use disposable fixtures and unrelated consumer cwd. `STATUS_SCRIPT` and `NEW_CHANGE_SCRIPT` can point to installed scripts. The distribution matrix directly executes installed new-change and status scripts, compares template output, checks runtime/sibling Markdown links and executable bits, and rejects shipped development fixtures. Mechanical checks do not establish actual runtime support, independent review or activation provenance.

Regression assertions cover paths with spaces, exact manual-stage adapters and fixture exclusion. Keep these checks intact.
