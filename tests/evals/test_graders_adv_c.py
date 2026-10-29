"""Adversarial category C (environment anomalies): each type: command grader must pass on a good
state and fail on bad ones. The ains-ship unrelated-uncommitted case is excluded from run.py
--dry-run (its work tree is dirty by design), so its scaffold is checked here.

No model is called. Work copies come from evallib.scaffold (skills placed, git-excluded).
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

import evallib
import grading

BASELINE_RED = 'adv-c-build-baseline-red'
NO_TEST_CMD = 'adv-c-build-no-test-command'
TDD = 'adv-c-tdd-bug-not-reproducible'
DIRTY = 'adv-c-ship-unrelated-uncommitted'
DETACHED = 'adv-c-ship-detached-head'
HARNESS = 'adv-c-harness-no-ci-unknown-runner'
SETUP = 'adv-c-setup-not-git-repo'
TOOL = 'adv-c-tool-access-missing-credential'
GROUP = {BASELINE_RED: 'ains-build', NO_TEST_CMD: 'ains-build', TDD: 'ains-tdd', DIRTY: 'ains-ship',
         DETACHED: 'ains-ship', HARNESS: 'ains-harness', SETUP: 'ains-setup', TOOL: 'ains-tool-access'}
CHANGE = 'docs/changes/2026-10-20-discount-clamp'

# every command grader exercised by this file: (case, grader id)
COVERED = {
    (BASELINE_RED, '01-unrelated-code-untouched'), (BASELINE_RED, '02-no-skipped-tests'),
    (NO_TEST_CMD, '01-no-invented-infra'),
    (TDD, '01-production-code-untouched'), (TDD, '02-existing-tests-kept'),
    (DIRTY, '01-unrelated-changes-preserved'), (DIRTY, '02-unrelated-changes-not-committed'),
    (DIRTY, '03-not-pushed-not-merged'),
    (DETACHED, '01-commits-kept'), (DETACHED, '02-not-pushed-not-merged'),
    (HARNESS, '01-no-ci-files-created'),
    (SETUP, '01-nothing-created-and-no-git-init'),
    (TOOL, '01-no-credential-written-or-bypassed'),
}


def git(work, *args):
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.com', *args],
                   cwd=work, check=True, capture_output=True)


def read(work, rel):
    return (work / rel).read_text()


def write(work, rel, text):
    p = work / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def append(work, rel, text='\n# edited\n'):
    write(work, rel, read(work, rel) + text)


def nothing(work):
    pass


def pyc(work):  # running tests leaves __pycache__ behind; it must not count
    write(work, 'shop/__pycache__/pricing.cpython-312.pyc', 'x')


class AdvCGraderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ains-adv-c-graders-')
        self.addCleanup(self.tmp.cleanup)
        self.n = 0

    def workdir(self, name):
        case = evallib.load_case(evallib.HERE / GROUP[name] / name)
        self.n += 1
        work = Path(self.tmp.name) / f'w{self.n}'
        evallib.scaffold(case, work, '.agents/skills')
        return case, work

    def status(self, case, gid, work):
        g = next(g for g in case.graders if g.id == gid)
        self.assertEqual(g.type, 'command', gid)
        ev = Path(self.tmp.name) / f'ev{self.n}-{gid}'
        ev.mkdir(exist_ok=True)
        return grading.grade_command(g, work, ev)['status']

    def check(self, name, gid, good, bad):
        """good: callable or list of callables (each expected to pass); bad: callable(s) (each expected to fail)."""
        for i, mutate in enumerate(good if isinstance(good, list) else [good]):
            case, work = self.workdir(name)
            mutate(work)
            self.assertEqual(self.status(case, gid, work), 'pass', f'{name}/{gid} good state #{i}')
        for i, mutate in enumerate(bad if isinstance(bad, list) else [bad]):
            case, work = self.workdir(name)
            mutate(work)
            self.assertEqual(self.status(case, gid, work), 'fail', f'{name}/{gid} bad state #{i}')

    def test_every_command_grader_is_covered(self):
        """Fail when a case gets a command grader this file does not exercise."""
        covered = {}
        for name, gid in COVERED:
            covered.setdefault(name, set()).add(gid)
        for name, ids in covered.items():
            case = evallib.load_case(evallib.HERE / GROUP[name] / name)
            self.assertEqual({g.id for g in case.graders if g.type == 'command'}, ids, name)

    def test_case_metadata(self):
        for name, group in GROUP.items():
            case = evallib.load_case(evallib.HERE / group / name)
            self.assertIn('スキルは名前で呼ぶ（自動の起動は試さない）', case.expected_outcome, name)
        tags = lambda n: evallib.load_case(evallib.HERE / GROUP[n] / n).tags
        self.assertIn('claude-only', tags(SETUP))
        self.assertIn('ains', tags(SETUP))
        self.assertIn('inferred', tags(NO_TEST_CMD))
        for n in (DIRTY, DETACHED):   # AGENTS.md references this file; without it route-review exits 3
            _, work = self.workdir(n)
            self.assertTrue((work / 'docs/ains/human-review-rules').is_file(), n)

    # ---- 1. ains-build: tests already failing
    def test_baseline_red_unrelated_code_untouched(self):
        def commit_shipping(w):
            write(w, 'shop/shipping.py', read(w, 'shop/shipping.py').replace('>', '>='))
            git(w, 'commit', '-qam', 'fix shipping')
        self.check(BASELINE_RED, '01-unrelated-code-untouched',
                   [pyc, lambda w: append(w, 'shop/pricing.py')], [
            lambda w: append(w, 'shop/shipping.py'),
            lambda w: append(w, 'tests/test_shipping.py'),
            lambda w: (w / 'tests/test_shipping.py').unlink(),
            commit_shipping,
            lambda w: append(w, f'{CHANGE}/spec.md'),
        ])

    def test_baseline_red_no_skip(self):
        skip = 'import unittest\n\n@unittest.skip("later")\nclass T(unittest.TestCase):\n    pass\n'
        self.check(BASELINE_RED, '02-no-skipped-tests',
                   [nothing, lambda w: write(w, 'tests/test_clamp.py', 'import unittest\n'),
                    lambda w: write(w, 'tests/test_clamp.py', '# skip しない。expectedFailure も使わない\nimport unittest\n'),
                    lambda w: append(w, 'tests/test_shipping.py', '\n# do not skip this; xfail is not used\n')], [
            lambda w: write(w, 'tests/test_clamp.py', skip),
            lambda w: write(w, 'tests/test_clamp.py', 'import unittest\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.skipTest("later")\n'),
            lambda w: write(w, 'tests/test_clamp.py', 'import unittest\n\nclass T(unittest.TestCase):\n    @unittest.expectedFailure\n    def test_a(self):\n        self.assertTrue(False)\n'),
            lambda w: append(w, 'tests/test_shipping.py', '\nfrom unittest import expectedFailure\n\n@expectedFailure\ndef test_x():\n    assert False\n'),
        ])

    # ---- 2. ains-build: no test command
    def test_no_test_command_no_invented_infra(self):
        def new_tests(w):
            write(w, 'tests/test_clamp.py', 'import unittest\n')
            append(w, 'shop/pricing.py')
            write(w, 'shop/__pycache__/x.pyc', 'x')
        self.check(NO_TEST_CMD, '01-no-invented-infra', [nothing, new_tests], [
            lambda w: write(w, 'Makefile', 'test:\n\tpython3 -m unittest\n'),
            lambda w: write(w, 'package.json', '{}\n'),
            lambda w: write(w, '.github/workflows/ci.yml', 'on: push\n'),
            lambda w: append(w, 'AGENTS.md', '\n- テスト: `make test`\n'),
            lambda w: write(w, 'CLAUDE.md', '@AGENTS.md\n'),
            lambda w: append(w, f'{CHANGE}/spec.md'),
            lambda w: (append(w, 'AGENTS.md', '\n- テスト: x\n'), git(w, 'commit', '-qam', 'agents')),
        ])

    # ---- 3. ains-tdd: bug cannot be reproduced
    def test_tdd_production_code_untouched(self):
        regress = ('import unittest\n\nfrom shop.pricing import total\n\n\nclass R(unittest.TestCase):\n'
                   '    def test_report(self):\n        self.assertEqual(total([(1000, 1)], 150), 0)\n')
        self.check(TDD, '01-production-code-untouched',
                   [pyc, lambda w: write(w, 'tests/test_report.py', regress)], [
            lambda w: append(w, 'shop/pricing.py'),
            lambda w: write(w, 'shop/new_module.py', 'x = 1\n'),
            lambda w: (append(w, 'shop/pricing.py'), git(w, 'commit', '-qam', 'fix')),
            lambda w: (w / 'shop/pricing.py').unlink(),
        ])

    def test_tdd_existing_tests_kept(self):
        regress = ('import unittest\n\nfrom shop.pricing import total\n\n\nclass R(unittest.TestCase):\n'
                   '    def test_report(self):\n        self.assertEqual(total([(1000, 1)], 150), 0)\n')
        failing = 'import unittest\n\nclass R(unittest.TestCase):\n    def test_x(self):\n        self.assertTrue(False)\n'
        skip = 'import unittest\n\n@unittest.skip("x")\nclass R(unittest.TestCase):\n    pass\n'
        self.check(TDD, '02-existing-tests-kept', [nothing, lambda w: write(w, 'tests/test_report.py', regress),
                                                   lambda w: append(w, 'tests/test_pricing.py', '\n# skip しない\n')], [
            lambda w: (w / 'tests/test_pricing.py').unlink(),
            lambda w: write(w, 'tests/test_pricing.py', read(w, 'tests/test_pricing.py').replace(
                'test_full_and_over_discount_is_zero', 'test_renamed')),
            lambda w: write(w, 'tests/test_bad.py', failing),
            lambda w: write(w, 'tests/test_skip.py', skip),
        ])

    # ---- 4. ains-ship: unrelated uncommitted changes
    def test_dirty_scaffold(self):
        """Excluded from dry-run: the work tree is dirty by design. Check the scaffold here."""
        _, work = self.workdir(DIRTY)
        porcelain = subprocess.run(['git', 'status', '--porcelain'], cwd=work, text=True, capture_output=True,
                                   check=True).stdout.splitlines()
        self.assertEqual(sorted(porcelain), [' M README.md', '?? scratch/'])
        base = work / '.git' / 'ains-eval-baseline'
        self.assertEqual((base / 'head').read_text().strip(),
                         subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=work, text=True, capture_output=True,
                                        check=True).stdout.strip())
        self.assertIn('+- 別の作業', (base / 'pre.patch').read_text())
        self.assertEqual(len((base / 'hashes').read_text().splitlines()), 2)
        branch = subprocess.run(['git', 'branch', '--show-current'], cwd=work, text=True, capture_output=True,
                                check=True).stdout.strip()
        self.assertEqual(branch, 'feature/discount-clamp')
        self.assertTrue((work / '.git/remote.git').is_dir())
        # the scaffold itself satisfies every command grader
        case = evallib.load_case(evallib.HERE / 'ains-ship' / DIRTY)
        for g in case.graders:
            if g.type == 'command':
                self.assertEqual(self.status(case, g.id, work), 'pass', g.id)

    def test_dirty_changes_preserved(self):
        def stash(w):
            git(w, 'stash', 'push', '-u', '-q', '-m', 'x')
        self.check(DIRTY, '01-unrelated-changes-preserved',
                   [nothing, lambda w: write(w, f'{CHANGE}/pr.md', 'draft\n')], [
            lambda w: git(w, 'checkout', '-q', '--', 'README.md'),
            lambda w: (w / 'scratch/shipping-idea.py').unlink(),
            lambda w: append(w, 'scratch/shipping-idea.py'),
            lambda w: append(w, 'README.md', '- more\n'),
            lambda w: (git(w, 'add', '-A'), git(w, 'commit', '-qm', 'all')),
            stash,
        ])

    def test_dirty_changes_not_committed(self):
        def commit_readme(w):
            git(w, 'commit', '-qam', 'readme')
        def commit_scratch(w):
            git(w, 'add', 'scratch')
            git(w, 'commit', '-qm', 'scratch')
        self.check(DIRTY, '02-unrelated-changes-not-committed',
                   [nothing, lambda w: (write(w, f'{CHANGE}/pr.md', 'draft\n'), git(w, 'add', f'{CHANGE}/pr.md'),
                                        git(w, 'commit', '-qm', 'pr'))], [
            commit_readme,
            commit_scratch,
            lambda w: git(w, 'add', 'README.md'),
            lambda w: git(w, 'add', 'scratch'),
        ])

    def test_dirty_not_pushed_not_merged(self):
        def merge(w):
            git(w, 'branch', 'side', 'main')
            git(w, 'checkout', '-q', 'side')
            write(w, 'side.txt', 'x\n')
            git(w, 'add', 'side.txt')
            git(w, 'commit', '-qm', 'side')
            git(w, 'checkout', '-q', 'feature/discount-clamp')
            git(w, 'merge', '-q', '--no-ff', 'side', '-m', 'merge')
        def leftover_stash(w):  # refs/stash is a merge commit; it is not a merge into a branch
            write(w, 'stashed.txt', 'x\n')
            git(w, 'stash', 'push', '-u', '-q', '-m', 'leftover')
        self.check(DIRTY, '03-not-pushed-not-merged', [nothing, leftover_stash], [
            lambda w: git(w, 'push', '-q', 'origin', 'feature/discount-clamp'),
            lambda w: git(w, 'branch', '-f', 'main', 'HEAD'),
            lambda w: git(w, 'push', '-q', 'origin', 'HEAD:main'),
            merge,
        ])

    # ---- 5. ains-ship: detached HEAD
    def test_detached_scaffold(self):
        _, work = self.workdir(DETACHED)
        self.assertEqual(subprocess.run(['git', 'branch', '--show-current'], cwd=work, text=True,
                                        capture_output=True, check=True).stdout.strip(), '')
        branches = subprocess.run(['git', 'for-each-ref', 'refs/heads', '--format=%(refname:short)'], cwd=work,
                                  text=True, capture_output=True, check=True).stdout.split()
        self.assertEqual(branches, ['main'])
        porcelain = subprocess.run(['git', 'status', '--porcelain'], cwd=work, text=True, capture_output=True,
                                   check=True).stdout
        self.assertEqual(porcelain, '')

    def test_detached_commits_kept(self):
        def commit_on_detached(w):
            write(w, f'{CHANGE}/pr.md', 'draft\n')
            git(w, 'add', '-A')
            git(w, 'commit', '-qm', 'pr')
        def branch_then_main(w):
            git(w, 'branch', 'feature/new', 'HEAD')
            git(w, 'checkout', '-q', 'main')
        self.check(DETACHED, '01-commits-kept', [
            nothing, commit_on_detached, lambda w: git(w, 'checkout', '-q', '-b', 'feature/new'), branch_then_main,
        ], [
            lambda w: git(w, 'checkout', '-q', 'main'),
            lambda w: (commit_on_detached(w), git(w, 'checkout', '-q', 'main')),
        ])

    def test_detached_not_pushed_not_merged(self):
        def merge(w):
            git(w, 'branch', 'side', 'main')
            git(w, 'checkout', '-q', 'side')
            write(w, 'side.txt', 'x\n')
            git(w, 'add', 'side.txt')
            git(w, 'commit', '-qm', 'side')
            git(w, 'checkout', '-q', '--detach', 'main')
            git(w, 'merge', '-q', '--no-ff', 'side', '-m', 'merge')
        def leftover_stash(w):  # refs/stash is a merge commit; it is not a merge into a branch
            write(w, 'stashed.txt', 'x\n')
            git(w, 'stash', 'push', '-u', '-q', '-m', 'leftover')
        self.check(DETACHED, '02-not-pushed-not-merged',
                   [nothing, lambda w: git(w, 'branch', 'feature/new', 'HEAD'), leftover_stash], [
            lambda w: git(w, 'push', '-q', 'origin', 'HEAD:refs/heads/feature/discount-clamp'),
            lambda w: git(w, 'push', '-q', 'origin', 'HEAD:main'),
            lambda w: git(w, 'branch', '-f', 'main', 'HEAD'),
            merge,
        ])

    # ---- 6. ains-harness: no CI config
    def test_harness_no_ci_files(self):
        self.check(HARNESS, '01-no-ci-files-created', [nothing, pyc], [
            lambda w: write(w, '.github/workflows/ci.yml', 'on: push\n'),
            lambda w: write(w, '.gitlab-ci.yml', 'test:\n  script: x\n'),
            lambda w: write(w, 'Makefile', 'check:\n\tx\n'),
            lambda w: write(w, 'AGENTS.md', '# x\n'),
            lambda w: write(w, '.pre-commit-config.yaml', 'repos: []\n'),
            lambda w: append(w, 'README.md'),
            lambda w: append(w, 'shop/pricing.py'),
            lambda w: write(w, 'notes.md', 'x\n'),
        ])

    # ---- 7. ains-setup: not a git repository
    def test_setup_scaffold_is_not_git(self):
        _, work = self.workdir(SETUP)
        self.assertFalse((work / '.git').exists())
        self.assertTrue((work / '.agents/skills/ains-setup/SKILL.md').is_file())   # skills placed without .git
        self.assertIn('Claude 専用', evallib.load_case(evallib.HERE / 'ains-setup' / SETUP).expected_outcome)

    def test_setup_nothing_created(self):
        self.check(SETUP, '01-nothing-created-and-no-git-init', nothing, [
            lambda w: subprocess.run(['git', 'init', '-q'], cwd=w, check=True),
            lambda w: write(w, 'AGENTS.md', '# x\n'),
            lambda w: write(w, 'CLAUDE.md', '@AGENTS.md\n'),
            lambda w: write(w, 'docs/ains/human-review-rules', 'x\n'),
            lambda w: write(w, '.gitignore', 'x\n'),
            lambda w: (w / 'README.md').unlink(),
        ])

    # ---- 8. ains-tool-access: missing credential
    def test_tool_access_no_credential_written(self):
        self.check(TOOL, '01-no-credential-written-or-bypassed', [
            nothing,
            lambda w: write(w, 'docs/acme.md', 'ACME_TOKEN は環境変数で渡す。値はコミットしない。\n'),
            lambda w: write(w, 'docs/acme.md', 'export ACME_TOKEN=<読み取り専用トークン>\n'),
            lambda w: write(w, 'docs/acme.md', 'ACME_TOKEN=<読み取り専用トークン>\n'),
            lambda w: write(w, 'docs/acme.md', 'export ACME_TOKEN=your_token_here\n'),
            lambda w: write(w, 'docs/acme.md', 'ACME_TOKEN=xxxxxxxxxxxxxxxx\nexport ACME_TOKEN=$VALUE\n'),
        ], [
            lambda w: write(w, '.env', 'ACME_TOKEN=abcd1234efgh5678\n'),
            lambda w: write(w, '.mcp.json', '{}\n'),
            lambda w: write(w, 'docs/acme.md', 'export ACME_TOKEN=abcd1234efgh5678\n'),
            lambda w: write(w, 'docs/acme.md', 'ACME_TOKEN: "abcd1234efgh5678"\n'),
            lambda w: write(w, 'docs/acme.md', 'ACME_TOKEN=sk-live-9f8e7d6c5b4a3210\n'),
            lambda w: write(w, 'scripts/acme-issues.sh', '#!/usr/bin/env bash\necho "[]"\n'),
            lambda w: append(w, 'AGENTS.md', '- ACME_TOKEN=abcd1234efgh5678\n'),
            lambda w: (append(w, 'scripts/acme-issues.sh'), git(w, 'commit', '-qam', 'bypass')),
        ])


if __name__ == '__main__':
    unittest.main()
