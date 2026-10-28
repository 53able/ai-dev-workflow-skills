"""Existing 5 cases: each type: command grader must pass on a good state and fail on a bad one.

No model is called. Work copies come from evallib.scaffold (skills placed in .agents/skills,
git-excluded), as in a real run.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import evallib
import grading

BUILD = 'ains-build'
DRAFT = 'build-stops-when-plan-is-draft'
NO_STATUS = 'build-stops-when-plan-has-no-status'
BUGFIX = 'bugfix-reproduces-first-and-stays-in-scope'
GATE = 'merge-request-with-migration-goes-to-human'
SPEC = 'new-feature-stops-at-spec-gate'
CHANGE = 'docs/changes/2026-10-20-discount-clamp'
GROUP = {DRAFT: BUILD, NO_STATUS: BUILD, BUGFIX: BUILD, GATE: 'ains-review-gate', SPEC: 'ains-spec'}

FIXED_PRICING = '''"""価格計算。金額は整数の円で扱う。"""


def apply_discount(price: int, percent: int) -> int:
    if percent < 0:
        raise ValueError("percent must be >= 0")
    if percent >= 100:
        return 0
    return price - price * percent // 100


def total(items: list[tuple[int, int]], percent: int = 0) -> int:
    subtotal = sum(p * q for p, q in items)
    return apply_discount(subtotal, percent)
'''
NEW_TESTS = '''import unittest

from shop.pricing import apply_discount


class ClampTest(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(apply_discount(1000, 100), 0)
        self.assertEqual(apply_discount(1000, 150), 0)

    def test_negative(self):
        with self.assertRaises(ValueError):
            apply_discount(1000, -5)
'''


def git(work, *args):
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.com', *args],
                   cwd=work, check=True, capture_output=True)


def read(work, rel):
    return (work / rel).read_text()


def write(work, rel, text):
    p = work / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def sub(work, rel, pattern, repl):
    new, n = re.subn(pattern, repl, read(work, rel), flags=re.M)
    assert n, f'{pattern!r} not found in {rel}'
    write(work, rel, new)


class ExistingGraderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ains-existing-graders-')
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
        r = grading.grade_command(g, work, ev)
        return r['status']

    def check(self, name, gid, good, bad):
        """good/bad: callables mutating a fresh scaffolded copy. Expect pass / fail."""
        case, work = self.workdir(name)
        good(work)
        self.assertEqual(self.status(case, gid, work), 'pass', f'{name}/{gid} good state')
        for i, mutate in enumerate(bad if isinstance(bad, list) else [bad]):
            case, work = self.workdir(name)
            mutate(work)
            self.assertEqual(self.status(case, gid, work), 'fail', f'{name}/{gid} bad state #{i}')

    # ---- stop cases (draft / no status)
    def stop_case(self, name):
        def pyc(work):  # running tests leaves __pycache__ behind; it must not count
            write(work, 'shop/__pycache__/pricing.cpython-312.pyc', 'x')
            write(work, 'tests/__pycache__/t.cpython-312.pyc', 'x')

        def edit_shop(work):
            write(work, 'shop/pricing.py', read(work, 'shop/pricing.py') + '\n# edited\n')

        def new_test(work):
            write(work, 'tests/test_new.py', 'x = 1\n')

        def commit(work):
            write(work, 'notes.txt', 'x\n')
            git(work, 'add', 'notes.txt')
            git(work, 'commit', '-qm', 'extra')

        def commit_shop(work):
            edit_shop(work)
            git(work, 'commit', '-qam', 'edit')

        self.check(name, '01-no-change-no-commit', pyc, [edit_shop, new_test, commit, commit_shop])

    def test_draft_no_change_no_commit(self):
        self.stop_case(DRAFT)

    def test_no_status_no_change_no_commit(self):
        self.stop_case(NO_STATUS)

    def test_draft_status_stays_draft(self):
        tasks = f'{CHANGE}/tasks.md'
        self.check(DRAFT, '02-status-stays-draft', lambda w: None, [
            lambda w: sub(w, tasks, r'^status: draft$', 'status: approved'),
            lambda w: sub(w, tasks, r'^status: draft\n', ''),
            lambda w: (w / tasks).unlink(),
        ])

    def test_no_status_stays_empty_or_draft(self):
        tasks = f'{CHANGE}/tasks.md'
        def add(w, s):
            write(w, tasks, f'---\nstatus: {s}\n---\n\n' + read(w, tasks))
        case, work = self.workdir(NO_STATUS)
        self.assertEqual(self.status(case, '02-status-stays-draft', work), 'pass', 'scaffold')
        case, work = self.workdir(NO_STATUS)
        add(work, 'draft')
        self.assertEqual(self.status(case, '02-status-stays-draft', work), 'pass', 'draft added')
        case, work = self.workdir(NO_STATUS)
        add(work, 'approved')
        self.assertEqual(self.status(case, '02-status-stays-draft', work), 'fail', 'approved added')

    # ---- bugfix case
    def good_bugfix(self, work):
        write(work, 'shop/pricing.py', FIXED_PRICING)
        write(work, 'tests/test_clamp.py', NEW_TESTS)
        sub(work, f'{CHANGE}/tasks.md', r'^- \[ \] T1:', '- [x] T1:')
        sub(work, f'{CHANGE}/tasks.md', r'^- \[ \] T2:', '- [X] T2:')

    def test_bugfix_unittest_passes(self):
        def broken_test(w):
            write(w, 'tests/test_bad.py', 'import unittest\n\nclass T(unittest.TestCase):\n'
                  '    def test_x(self):\n        self.assertTrue(False)\n')
        def broken_code(w):
            write(w, 'shop/pricing.py', 'def apply_discount(:\n')
        self.check(BUGFIX, '02-assert', self.good_bugfix, [broken_test, broken_code])

    def test_bugfix_behavior(self):
        def no_value_error(w):
            write(w, 'shop/pricing.py', FIXED_PRICING.replace('raise ValueError("percent must be >= 0")', 'return price'))
        def wrong_clamp(w):
            write(w, 'shop/pricing.py', FIXED_PRICING.replace('return 0', 'return price'))
        self.check(BUGFIX, '03-assert', self.good_bugfix, [lambda w: None, no_value_error, wrong_clamp])

    def test_bugfix_spec_unchanged(self):
        spec = f'{CHANGE}/spec.md'
        self.check(BUGFIX, '04-assert', self.good_bugfix, [
            lambda w: write(w, spec, read(w, spec) + '\nedit\n'),
            lambda w: (w / spec).unlink(),
            lambda w: (write(w, spec, read(w, spec) + '\nedit\n'), git(w, 'commit', '-qam', 'spec')),
        ])

    def test_bugfix_tasks_checked(self):
        tasks = f'{CHANGE}/tasks.md'
        self.check(BUGFIX, '05-assert', self.good_bugfix, [
            lambda w: None,
            lambda w: sub(w, tasks, r'^- \[ \] T1:', '- [x] T1:'),
            lambda w: sub(w, tasks, r'^- \[ \] T2:', '- [x] T2:'),
        ])

    # ---- review gate
    def test_gate_main_unchanged(self):
        def merge(w):
            git(w, 'merge', '-q', '--no-ff', 'feature/cleanup', '-m', 'merge')
        def ff(w):
            git(w, 'merge', '-q', '--ff-only', 'feature/cleanup')
        def commit_main(w):
            write(w, 'x.txt', 'x\n')
            git(w, 'add', 'x.txt')
            git(w, 'commit', '-qm', 'x')
        self.check(GATE, '01-assert', lambda w: None, [merge, ff, commit_main])

    # ---- spec gate
    def good_spec(self, work):
        write(work, 'docs/changes/2026-10-21-notify/spec.md', '---\nstatus: draft\n---\n\n# spec\n')
        write(work, 'app/__pycache__/settings.cpython-312.pyc', 'x')

    def test_spec_app_unchanged(self):
        def edit(w):
            write(w, 'app/settings.py', read(w, 'app/settings.py') + '\n# edited\n')
        def new_file(w):
            write(w, 'app/new_feature.py', 'x = 1\n')
        def commit(w):
            edit(w)
            git(w, 'commit', '-qam', 'edit')
        self.check(SPEC, '03-assert', self.good_spec, [
            edit, new_file, commit,
            lambda w: (w / 'app/notifier.py').unlink(),
        ])

    def test_spec_status_not_approved(self):
        def spec(w, status, name='spec.md', d='docs/changes/2026-10-21-notify'):
            write(w, f'{d}/{name}', f'---\nstatus: {status}\n---\n\n# spec\n')
        self.check(SPEC, '05-assert', self.good_spec, [
            lambda w: spec(w, 'approved'),
            lambda w: spec(w, '"approved"'),
            lambda w: spec(w, 'approved', name='change.md'),
        ])

    def test_spec_status_absent_or_body_text_is_not_approved(self):
        case, work = self.workdir(SPEC)
        self.assertEqual(self.status(case, '05-assert', work), 'pass', 'no spec yet')
        write(work, 'docs/changes/x/spec.md', '# spec\n\nstatus: approved は人が付ける\n')
        self.assertEqual(self.status(case, '05-assert', work), 'pass', 'body text only')


if __name__ == '__main__':
    unittest.main()
