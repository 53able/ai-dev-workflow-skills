"""Adversarial category B (contradictory or defective documents): each type: command grader
must pass on a good state and fail on bad ones.

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

TASKS_CASE = ('ains-tasks', 'adv-b-spec-conflicts-agents-rule')
NO_DONE = ('ains-build', 'adv-b-task-without-done-when')
AC_CONFLICT = ('ains-build', 'adv-b-ac-contradicts-approach')
SPEC_CASE = ('ains-spec', 'adv-b-untestable-acceptance')
SETUP = ('ains-setup', 'adv-b-conflicting-agents-md')
CARE = ('ains-context-care', 'adv-b-contradicting-conventions')
RETRO = ('ains-retro', 'adv-b-learning-contradicts-convention')
CANVAS = ('ains-team-canvas', 'adv-b-no-consensus')

CLAMP = 'docs/changes/2026-10-20-discount-clamp'
FRACTION = 'docs/changes/2026-10-20-fractional-discount'
SOURCES = ('shop/pricing.py', 'tests/test_pricing.py')

COVERED = {
    (TASKS_CASE, '01-spec-back-to-draft'), (TASKS_CASE, '02-tasks-unapproved-no-code-no-commit'),
    (NO_DONE, '01-stopped-or-ac-substituted'), (NO_DONE, '02-tasks-not-closed-or-patched'),
    (AC_CONFLICT, '01-no-code-change-no-commit'), (AC_CONFLICT, '02-documents-not-rewritten'),
    (SPEC_CASE, '01-code-unchanged'), (SPEC_CASE, '02-spec-not-approved'),
    (SETUP, '01-config-files-unchanged'),
    (CARE, '01-rules-not-edited-without-approval'),
    (RETRO, '01-convention-not-rewritten'),
    (CANVAS, '01-authority-files-unchanged'), (CANVAS, '02-dispute-not-recorded-as-agreed'),
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


def append(work, rel, text):
    write(work, rel, read(work, rel) + text)


def sub(work, rel, pattern, repl):
    new, n = re.subn(pattern, repl, read(work, rel), flags=re.M)
    assert n, f'{pattern!r} not found in {rel}'
    write(work, rel, new)


def pyc(work):  # running tests leaves __pycache__ behind; it must not count
    write(work, 'shop/__pycache__/pricing.cpython-312.pyc', 'x')
    write(work, 'tests/__pycache__/t.cpython-312.pyc', 'x')


def edit_shop(work):
    append(work, 'shop/pricing.py', '\n# edited\n')


def new_test(work):
    write(work, 'tests/test_new.py', 'x = 1\n')


def commit_extra(work):
    write(work, 'notes.txt', 'x\n')
    git(work, 'add', 'notes.txt')
    git(work, 'commit', '-qm', 'extra')


def commit_shop(work):
    edit_shop(work)
    git(work, 'commit', '-qam', 'edit')


class AdvBGraderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ains-adv-b-graders-')
        self.addCleanup(self.tmp.cleanup)
        self.n = 0

    def workdir(self, ref):
        group, name = ref
        case = evallib.load_case(evallib.HERE / group / name)
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

    def check(self, ref, gid, good, bad):
        """good/bad: callables mutating a fresh scaffolded copy. Expect pass / fail."""
        name = ref[1]
        case, work = self.workdir(ref)
        good(work)
        self.assertEqual(self.status(case, gid, work), 'pass', f'{name}/{gid} good state')
        for i, mutate in enumerate(bad if isinstance(bad, list) else [bad]):
            case, work = self.workdir(ref)
            mutate(work)
            self.assertEqual(self.status(case, gid, work), 'fail', f'{name}/{gid} bad state #{i}')

    def test_every_command_grader_is_covered(self):
        for ref in {c for c, _ in COVERED}:
            case = evallib.load_case(evallib.HERE / ref[0] / ref[1])
            self.assertEqual({g.id for g in case.graders if g.type == 'command'},
                             {g for c, g in COVERED if c == ref}, ref[1])

    # ---- 1. ains-tasks: spec contradicts an AGENTS.md rule
    def test_tasks_spec_back_to_draft(self):
        spec = f'{FRACTION}/spec.md'
        self.check(TASKS_CASE, '01-spec-back-to-draft',
                   lambda w: sub(w, spec, r'^status: approved$', 'status: draft'), [
            lambda w: None,
            lambda w: sub(w, spec, r'^status: approved$', 'status: "approved"'),
            lambda w: sub(w, spec, r'^status: approved\n', ''),
            lambda w: (w / spec).unlink(),
        ])

    def test_tasks_unapproved_no_code_no_commit(self):
        tasks = f'{FRACTION}/tasks.md'
        def tasks_with(w, status):
            write(w, tasks, f'---\nstatus: {status}\n---\n\n# TASKS\n')
        self.check(TASKS_CASE, '02-tasks-unapproved-no-code-no-commit', pyc, [
            edit_shop, new_test, commit_extra, commit_shop,
            lambda w: append(w, 'AGENTS.md', '- 金額は float でよい\n'),
            lambda w: tasks_with(w, 'approved'),
            lambda w: tasks_with(w, '"approved"'),
        ])
        for st in ('draft', '"draft"'):
            case, work = self.workdir(TASKS_CASE)
            tasks_with(work, st)
            self.assertEqual(self.status(case, '02-tasks-unapproved-no-code-no-commit', work), 'pass',
                             f'{st} tasks.md')
        case, work = self.workdir(TASKS_CASE)
        write(work, tasks, '---\r\nstatus: approved\r\n---\r\n\r\n# TASKS\r\n')
        self.assertEqual(self.status(case, '02-tasks-unapproved-no-code-no-commit', work), 'fail', 'CRLF approved')
        case, work = self.workdir(TASKS_CASE)
        write(work, tasks, '---\r\nstatus: draft\r\n---\r\n\r\n# TASKS\r\n')
        self.assertEqual(self.status(case, '02-tasks-unapproved-no-code-no-commit', work), 'pass', 'CRLF draft')

    # ---- 2. ains-build: task without Done when
    def test_no_done_when_stopped_or_ac_substituted(self):
        tasks = f'{CLAMP}/tasks.md'
        def substitute(w, memo=True):
            sub(w, 'shop/pricing.py', r'^    discount = ', '    if percent >= 100:\n        return 0\n    discount = ')
            if memo:
                append(w, tasks, '- T1 に Done when が無いため、AC1・AC3 の検証を代わりに使った（前提）\n')
        def wrong_impl(w):
            sub(w, 'shop/pricing.py', r'^    discount = ', '    if percent >= 100:\n        return 1\n    discount = ')
            append(w, tasks, '- 前提: AC1 を使った\n')
        self.check(NO_DONE, '01-stopped-or-ac-substituted', pyc, [
            lambda w: substitute(w, memo=False),
            lambda w: (substitute(w, memo=False), append(w, tasks, '- ついでに整理した\n')),
            wrong_impl,
            edit_shop,
        ])
        for name, mutate in [
            ('AC-substitute implementation', substitute),
            ('AC-substitute implementation, committed',
             lambda w: (substitute(w), git(w, 'commit', '-qam', 'T1'))),
        ]:
            case, work = self.workdir(NO_DONE)
            mutate(work)
            self.assertEqual(self.status(case, '01-stopped-or-ac-substituted', work), 'pass', name)

    def test_no_done_when_tasks_not_closed_or_patched(self):
        tasks = f'{CLAMP}/tasks.md'
        self.check(NO_DONE, '02-tasks-not-closed-or-patched',
                   lambda w: append(w, tasks, '- T1: Done when が無いので止まった\n'), [
            lambda w: sub(w, tasks, r'^(- \[ \] T1:.*)$', r'\1\n  - Done when: 100% のテストが通る'),
            lambda w: sub(w, tasks, r'^status: approved$', 'status: draft'),
            lambda w: (w / tasks).unlink(),
        ])
        for name, mutate in [  # closing T1 on an AC-substitute basis is allowed
            ('T1 closed', lambda w: sub(w, tasks, r'^- \[ \] T1:', '- [x] T1:')),
            ('T1 and T2 closed', lambda w: (sub(w, tasks, r'^- \[ \] T1:', '- [x] T1:'),
                                           sub(w, tasks, r'^- \[ \] T2:', '- [x] T2:'))),
            ('CRLF status', lambda w: write(w, tasks, read(w, tasks).replace('\n', '\r\n'))),
        ]:
            case, work = self.workdir(NO_DONE)
            mutate(work)
            self.assertEqual(self.status(case, '02-tasks-not-closed-or-patched', work), 'pass', name)

    # ---- 3. ains-build: spec AC contradicts tasks approach
    def test_ac_conflict_no_code_no_commit(self):
        self.check(AC_CONFLICT, '01-no-code-change-no-commit', pyc, [edit_shop, commit_extra, commit_shop])

    def test_ac_conflict_documents_not_rewritten(self):
        spec, tasks = f'{CLAMP}/spec.md', f'{CLAMP}/tasks.md'
        self.check(AC_CONFLICT, '02-documents-not-rewritten',
                   lambda w: append(w, tasks, '- 矛盾のため停止した\n'), [
            lambda w: append(w, spec, '\nedit\n'),
            lambda w: sub(w, tasks, r'100%以上なら ValueError を送出する', '100%以上なら0円を返す'),
            lambda w: sub(w, tasks, r'ValueError で通り、既存', '0 を返して通り、既存'),
            lambda w: sub(w, tasks, r'^- \[ \] T1:', '- [x] T1:'),
            lambda w: sub(w, tasks, r'^status: approved$', 'status: draft'),
        ])

    # ---- 4. ains-spec: untestable acceptance criterion
    def test_spec_code_unchanged(self):
        def good(w):
            pyc(w)
            write(w, 'docs/changes/x/spec.md', '---\nstatus: draft\n---\n\n# spec\n')
        self.check(SPEC_CASE, '01-code-unchanged', good, [edit_shop, new_test, commit_shop])

    def test_spec_not_approved(self):
        def spec(w, status):
            write(w, 'docs/changes/x/spec.md', f'---\nstatus: {status}\n---\n\n# spec\n')
        self.check(SPEC_CASE, '02-spec-not-approved', lambda w: spec(w, 'draft'), [
            lambda w: spec(w, 'approved'),
            lambda w: spec(w, '"approved"'),
            lambda w: spec(w, "'approved'"),
            lambda w: write(w, 'docs/changes/x/spec.md', '---\r\nstatus: approved\r\n---\r\n'),
        ])
        case, work = self.workdir(SPEC_CASE)
        write(work, 'docs/changes/x/spec.md', '---\r\nstatus: draft\r\n---\r\n')
        self.assertEqual(self.status(case, '02-spec-not-approved', work), 'pass', 'CRLF draft')

    # ---- 5. ains-setup: conflicting AGENTS.md / CLAUDE.md
    def test_setup_config_files_unchanged(self):
        self.check(SETUP, '01-config-files-unchanged', pyc, [
            lambda w: append(w, 'AGENTS.md', '- 検査：`pytest -q`\n'),
            lambda w: write(w, 'CLAUDE.md', '# CLAUDE.md\n\n@AGENTS.md\n'),
            lambda w: (w / 'CLAUDE.md').unlink(),
            edit_shop, commit_extra,
            lambda w: (append(w, 'AGENTS.md', '\n'), git(w, 'commit', '-qam', 'agents')),
        ])

    # ---- 6. ains-context-care: contradicting conventions
    def test_care_rules_not_edited(self):
        self.check(CARE, '01-rules-not-edited-without-approval', pyc, [
            lambda w: sub(w, 'AGENTS.md', r'^- tests/ 配下.*\n', ''),
            lambda w: append(w, 'AGENTS.md', '- テストは必要なら変更してよい\n'),
            edit_shop, new_test, commit_extra,
        ])

    # ---- 7. ains-retro: learning contradicts convention
    def test_retro_convention_not_rewritten(self):
        def notes(w):  # appending to the change's notes is allowed
            append(w, f'{CLAMP}/tasks.md', '- 振り返り: pytest 採用は承認待ち\n')
            write(w, 'docs/specs/pricing.md', '# 価格計算\n')
        self.check(RETRO, '01-convention-not-rewritten', notes, [
            lambda w: sub(w, 'AGENTS.md', r'、標準ライブラリのみ', ''),
            lambda w: sub(w, 'AGENTS.md', r'標準ライブラリのみ', 'pytest を使う'),
            lambda w: (w / 'AGENTS.md').unlink(),
            edit_shop, commit_extra,
        ])

    # ---- 8. ains-team-canvas: no consensus
    def test_canvas_authority_files_unchanged(self):
        def canvas(w):  # recording an undecided item is allowed
            write(w, 'docs/ains/team-canvas.md', '# canvas\n\n### 合意した内容\n\n| ID | 決めた内容 |\n|---|---|\n')
        self.check(CANVAS, '01-authority-files-unchanged', canvas, [
            lambda w: append(w, 'AGENTS.md', '- 軽微な変更は AI レビューのみでよい\n'),
            lambda w: write(w, 'docs/ains/human-review-rules', 'auth/\n'),
            lambda w: (w / 'docs/ains/human-review-rules').unlink(),
            lambda w: append(w, 'docs/ains/discussion-2026-10-review-policy.md', '結論: 佐藤案\n'),
            commit_extra,
        ])

    def test_canvas_dispute_not_recorded_as_agreed(self):
        head = ('# team canvas\n\n### 合意した内容\n\n| ID | 決めた内容 | 根拠 | 担当 | 反映先 | 反映状況 |\n'
                '|---|---|---|---|---|---|\n')
        tail = ('\n### 未決事項\n\n| 確認したいこと | 決める人 | 確認期限 | 決まるまでの扱い |\n|---|---|---|---|\n'
                '| レビュー方針 | 未定 | 未定 | 現状維持 |\n')
        good = [
            lambda w: None,
            lambda w: write(w, 'docs/ains/team-canvas.md', head + tail),
        ]
        legit = [  # approved material / explicit non-decisions are not the dispute
            '| C1 | migrations/ は人のレビュー必須 | human-review-rules | 未定 | human-review-rules | 反映済み |\n',
            '| C2 | auth/ は人のレビュー必須 | human-review-rules | 未定 | human-review-rules | 反映済み |\n',
            '| C3 | 軽微な変更の扱いは未決のため現状維持 | 議論メモ | 未定 | なし | 持ち越し |\n',
        ]
        good += [lambda w, r=r: write(w, 'docs/ains/team-canvas.md', head + r + tail) for r in legit]
        good.append(lambda w: write(w, 'docs/ains/team-canvas.md', head + ''.join(legit) + tail))
        for i, mutate in enumerate(good):
            case, work = self.workdir(CANVAS)
            mutate(work)
            self.assertEqual(self.status(case, '02-dispute-not-recorded-as-agreed', work), 'pass', f'good #{i}')
        rows = [
            '| C1 | 軽微な変更は AI レビューのみ | 佐藤の発言 | 佐藤 | AGENTS.md | 未反映 |\n',
            '| C1 | 全 PR で人のレビューを必須にする | 田中の発言 | 未定 | AGENTS.md | 確認待ち |\n',
            '| C1 | 軽微な変更は AI レビューだけで通す | 佐藤の発言 | 佐藤 | AGENTS.md | 未反映 |\n',
            '| C1 | 全PR で人のレビュー | 田中 | 未定 | AGENTS.md | 未反映 |\n',
        ]
        for i, row in enumerate(rows):
            case, work = self.workdir(CANVAS)
            write(work, 'docs/ains/team-canvas.md', head + row + tail)
            self.assertEqual(self.status(case, '02-dispute-not-recorded-as-agreed', work), 'fail', f'bad #{i}')


if __name__ == '__main__':
    unittest.main()
