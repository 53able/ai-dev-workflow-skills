"""Grading tests; the LLM is always a stub, no model is called."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import evallib
import grading
from evallib import Grader


def make_grader(id, type, run=None, body='rubric'):
    return Grader(id=id, path=Path(id), type=type, focus='trace', weight=1.0, run=run, body=body)


class GradingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ains-gradetest-')
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.work = root / 'project'
        self.work.mkdir()
        git = ['git', '-c', 'user.name=e', '-c', 'user.email=e@x']
        subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=self.work, check=True)
        (self.work / 'a.txt').write_text('hi\n')
        subprocess.run(['git', 'add', '-A'], cwd=self.work, check=True)
        subprocess.run([*git, 'commit', '-qm', 'init'], cwd=self.work, check=True)
        (self.work / 'new.txt').write_text('untracked-marker\n')
        self.out = root / 'out'

    def case(self, graders):
        c = object.__new__(evallib.Case)
        c.__dict__.update(name='c', expected_outcome='stops', prompt='REQUEST-MARK', graders=graders)
        return c

    def grade(self, graders, llm, summary=None):
        return grading.grade(self.case(graders), self.work, summary or evallib.empty_summary(), self.out, llm=llm)

    def test_dispatch_order_and_command(self):
        calls = []
        graders = [make_grader('03-llm', 'llm'), make_grader('02-fail', 'command', run='exit 3'),
                   make_grader('01-ok', 'command', run='test -f new.txt && echo out && echo err >&2')]

        def llm(prompt):
            calls.append(prompt)
            return '{"pass": true, "reason": "fine"}'
        res = self.grade(graders, llm)
        self.assertEqual([r['grader'] for r in res], ['01-ok', '02-fail', '03-llm'])
        self.assertEqual([r['status'] for r in res], ['pass', 'fail', 'pass'])
        self.assertEqual(len(calls), 1)
        self.assertEqual((self.out / 'graders' / '01-ok.stdout').read_text(), 'out\n')
        self.assertEqual((self.out / 'graders' / '01-ok.stderr').read_text(), 'err\n')
        self.assertEqual(json.loads((self.out / 'grades.json').read_text())['status'], 'fail')

    def test_llm_prompt_contents_and_saved(self):
        s = evallib.empty_summary()
        s['final_response'] = 'FINAL-MARK'
        s['prompt_sent'] = 'SECRET-PROMPT'
        s['timeline'] = [{'type': 'tool_result', 'output': 'FAILED-BEFORE-FIX', 'is_error': True}]
        seen = []
        self.grade([make_grader('01', 'llm', body='RUBRIC-MARK')], lambda p: seen.append(p) or '{"pass":false,"reason":"r"}', s)
        p = seen[0]
        for needle in ('RUBRIC-MARK', 'stops', 'FINAL-MARK', 'untracked-marker', 'init', 'REQUEST-MARK',
                       'FAILED-BEFORE-FIX'):
            self.assertIn(needle, p)
        self.assertNotIn('SECRET-PROMPT', p)
        self.assertEqual((self.out / 'graders' / '01.prompt.md').read_text(), p)
        self.assertIn('"pass":false', (self.out / 'graders' / '01.raw.txt').read_text())

    def test_command_timeout_is_error(self):
        old = grading.COMMAND_TIMEOUT
        grading.COMMAND_TIMEOUT = 1
        self.addCleanup(setattr, grading, 'COMMAND_TIMEOUT', old)
        res = self.grade([make_grader('01', 'command', run='sleep 5')], None)
        self.assertEqual(res[0]['status'], 'error')

    def test_llm_accept_and_reject(self):
        ok = ['{"pass": true, "reason": "r"}', '  {"pass": false, "reason": ""}\n',
              '```json\n{"pass": true, "reason": "r"}\n```']
        for raw in ok:
            self.assertIsInstance(grading.parse_verdict(raw)[0], bool, raw)
        bad = ['', 'pass', 'Sure! {"pass": true, "reason": "r"}', '{"pass": true}',
               '{"pass": true, "reason": "r", "extra": 1}', '{"pass": "true", "reason": "r"}',
               '{"pass": 1, "reason": "r"}', '{"pass": true, "reason": 5}', '[true]', 'null']
        for raw in bad:
            res = self.grade([make_grader('01', 'llm')], lambda p, raw=raw: raw)
            self.assertEqual(res[0]['status'], 'error', raw)
            self.assertIn('invalid grader output', res[0]['reason'])

    def test_llm_exception_is_error(self):
        def boom(prompt):
            raise RuntimeError('down')
        res = self.grade([make_grader('01', 'llm')], boom)
        self.assertEqual(res[0]['status'], 'error')

    def test_trial_status(self):
        st = lambda *s: grading.trial_status([{'status': x} for x in s])
        self.assertEqual(st('pass', 'pass'), 'pass')
        self.assertEqual(st('pass', 'fail'), 'fail')
        self.assertEqual(st('fail', 'error'), 'error')

    def test_write_summary(self):
        def summ(error=None, ignored=()):
            s = evallib.empty_summary()
            s.update(cli_version='1.2.3', model='m-x', error=error, ignored_options=list(ignored))
            return s
        g = lambda *st: [{'grader': f'g{i}', 'type': 'command', 'status': x, 'reason': 'timeout after 120s'}
                         for i, x in enumerate(st)]
        results = [
            {'product': 'claude', 'case': 'c1', 'trial': 1, 'graders': g('pass', 'pass'), 'summary': summ()},
            {'product': 'claude', 'case': 'c1', 'trial': 2, 'graders': g('pass', 'fail'), 'summary': summ()},
            {'product': 'claude', 'case': 'c1', 'trial': 3, 'graders': g('pass', 'error'), 'summary': summ()},
            {'product': 'codex', 'case': 'c1', 'trial': 1, 'graders': [], 'summary': summ('skill not invoked', ['--max-turns'])},
            {'product': 'codex', 'case': 'c1', 'trial': 2, 'graders': [], 'summary': summ('skill not invoked: ains-x', ['--max-turns'])},
        ]
        results[1]['summary']['commands'] = ['ls', "/bin/zsh -lc 'git -c user.name=x commit -qm wip'"]
        run_dir = Path(self.tmp.name) / 'run-1'
        grading.write_summary(run_dir, results, now=datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc))
        text = (run_dir / 'summary.md').read_text()
        for needle in ('| claude | c1 | 1/3 | 1 | 1 | 3 |', '| codex | c1 | 0/2 | 0 | 2 | 2 |',
                       '| codex | skill not invoked | 2 |', '| claude | grader timeout | 1 |', '1.2.3', 'm-x',
                       '--max-turns', '2026-01-02T03:04:05+00:00', grading.GRADER_MODEL, 'run-1',
                       '| claude | 1.2.3 | m-x | none | 1 |', "- claude/c1/2: `/bin/zsh -lc 'git -c user.name=x commit"):
            self.assertIn(needle, text)

    def test_error_category(self):
        cases = {
            'timeout after 900s': 'timeout', 'claude exited with code 1: boom': 'exit',
            'codex exited with 2: x': 'exit', 'max_turns: result error_max_turns: ': 'max_turns',
            'skill not invoked: ains-build': 'skill not invoked', 'invalid grader output: not JSON': 'invalid grader output',
            'llm call failed: down': 'llm call failed', 'adapter raised RuntimeError: x': 'adapter exception',
            'runner raised EvalError: x': 'runner exception', 'cannot start claude: x': 'start failed',
            'unexpected context: tools outside allowed_tools: Agent': 'unexpected context', 'result error_x: y': 'other',
        }
        for msg, cat in cases.items():
            self.assertEqual(grading.error_category(msg), cat, msg)

    def test_git_write_attempts(self):
        cmds = ['git commit -m x', "/bin/zsh -lc 'git -c a=b push origin x'", 'git -C sub merge main',
                'git status', 'git log --oneline', 'echo commit', 'cat .git/COMMIT_EDITMSG']
        self.assertEqual(grading.git_write_attempts(cmds), cmds[:3])

    def test_git_write_attempts_boundaries(self):
        no = ['git merge-base main HEAD', 'git merge-tree a b c', 'git commit-graph verify', 'git push --dry-run origin x',
              'git push -n origin x', 'git commit-tree HEAD^{tree}']
        yes = ['git -c k=v commit -m x', 'git merge --no-ff x', 'git push origin x', 'git commit', 'git merge',
               'git push --dry-run origin x && git commit -m wip', 'git commit -am wip; git push -n origin x',
               'git add -A && git commit -m "push -n support"', 'git commit -m "allow push --dry-run"']
        self.assertEqual(grading.git_write_attempts(no), [])
        self.assertEqual(grading.git_write_attempts(yes), yes)

    def test_write_summary_by_grader(self):
        s = evallib.empty_summary()
        g = lambda a, b: [{'grader': 'g1', 'status': a, 'reason': ''}, {'grader': 'g2', 'status': b, 'reason': ''}]
        err = evallib.empty_summary()
        err['error'] = 'timeout after 1s'
        results = [
            {'product': 'claude', 'case': 'c1', 'trial': 1, 'graders': g('pass', 'fail'), 'summary': s},
            {'product': 'claude', 'case': 'c1', 'trial': 2, 'graders': g('pass', 'error'), 'summary': s},
            {'product': 'claude', 'case': 'c1', 'trial': 3, 'graders': [], 'summary': err},
        ]
        run_dir = Path(self.tmp.name) / 'run-g'
        grading.write_summary(run_dir, results)
        text = (run_dir / 'summary.md').read_text()
        self.assertIn('| claude | c1 | g1 | 2 | 0 | 0 |', text)
        self.assertIn('| claude | c1 | g2 | 0 | 1 | 1 |', text)

    def test_llm_then_command_does_not_touch_index(self):
        # A pyc left untracked in a committed directory must not fail a later command grader.
        git = ['git', '-c', 'user.name=e', '-c', 'user.email=e@x']
        (self.work / 'app').mkdir()
        (self.work / 'app' / 'm.py').write_text('x = 1\n')
        subprocess.run(['git', 'add', '-A'], cwd=self.work, check=True)
        subprocess.run([*git, 'commit', '-q', '--amend', '--no-edit'], cwd=self.work, check=True)
        (self.work / 'app' / '__pycache__').mkdir()
        (self.work / 'app' / '__pycache__' / 'm.cpython-312.pyc').write_bytes(b'\x00PYC-MARK\x00')
        (self.work / 'blob.bin').write_bytes(b'\x00BIN-MARK\x00')
        before = subprocess.run(['git', 'ls-files', '--stage'], cwd=self.work, text=True, capture_output=True).stdout
        seen = []
        run = 'git diff --quiet $(git rev-list --max-parents=0 HEAD) -- app'
        res = self.grade([make_grader('01-llm', 'llm'), make_grader('02-cmd', 'command', run=run)],
                         lambda p: seen.append(p) or '{"pass": true, "reason": "r"}')
        self.assertEqual([r['status'] for r in res], ['pass', 'pass'])
        after = subprocess.run(['git', 'ls-files', '--stage'], cwd=self.work, text=True, capture_output=True).stdout
        self.assertEqual(before, after)
        self.assertIn('Binary files /dev/null and b/blob.bin differ', seen[0])   # untracked, shown as binary
        self.assertNotIn('PYC-MARK', seen[0])
        self.assertNotIn('__pycache__', seen[0])
        self.assertNotIn('BIN-MARK', seen[0])

    def test_command_grader_ignores_user_git_config(self):
        cfg = Path(self.tmp.name) / 'gitconfig'
        cfg.write_text('[eval]\n\tmarker = user\n')
        with mock.patch.dict(os.environ, {'GIT_CONFIG_GLOBAL': str(cfg)}):
            res = self.grade([make_grader('01', 'command', run='! git config eval.marker')], None)
        self.assertEqual(res[0]['status'], 'pass')


if __name__ == '__main__':
    unittest.main()
