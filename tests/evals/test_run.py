"""Runner skeleton tests; no model is called."""
import contextlib
import io
from pathlib import Path
import shutil
import tempfile
import unittest

import evallib
import run

CASE_YAML = '''schema_version: "1.1"
name: sample
expected_outcome: |
  stops.
context:
  scaffold_script: place-files.sh
'''
PROMPT = '---\ntags: [x]\nmax_turns: 5\ntimeout_seconds: 60\nallowed_tools: [Read, Bash]\n---\n\ndo it\n'
GRADER = '---\ntype: llm\nfocus: trace\nweight: 1\n---\n\ncheck\n'
PLACE = '#!/usr/bin/env bash\nset -eu\necho hi > a.txt\ngit init -q -b main && git add -A && git -c user.name=e -c user.email=e@x commit -qm i\n'


class EvalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ains-evaltest-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.skills = self.root / 'skills'
        (self.skills / 's1').mkdir(parents=True)
        (self.skills / 's1' / 'SKILL.md').write_text('x')

    def make_case(self, yaml=CASE_YAML, prompt=PROMPT, graders=None, name='sample'):
        d = self.root / 'evals' / 'grp' / name
        shutil.rmtree(d, ignore_errors=True)
        (d / 'graders').mkdir(parents=True)
        (d / 'case.yaml').write_text(yaml)
        (d / 'prompt.md').write_text(prompt)
        (d / 'place-files.sh').write_text(PLACE)
        for n, text in (graders or {'01-a.md': GRADER}).items():
            (d / 'graders' / n).write_text(text)
        return d

    def assert_invalid(self, *needles, **kw):
        d = self.make_case(**kw)
        with self.assertRaises(evallib.EvalError) as cm:
            evallib.load_case(d)
        for n in needles:
            self.assertIn(n, str(cm.exception))

    def test_loads_valid_case(self):
        c = evallib.load_case(self.make_case())
        self.assertEqual((c.name, c.max_turns, c.timeout_seconds, c.tags), ('sample', 5, 60, ['x']))
        self.assertEqual(c.allowed_tools, ['Read', 'Bash'])
        self.assertEqual(c.prompt, 'do it\n')
        self.assertEqual(c.expected_outcome, 'stops.\n')
        self.assertEqual((c.graders[0].type, c.graders[0].weight, c.graders[0].run), ('llm', 1.0, None))

    def test_existing_cases_load(self):
        dirs = evallib.discover_cases()
        self.assertEqual(len(dirs), 11)
        for d in dirs:
            evallib.load_case(d)

    def test_invalid_case_yaml_names_file_and_reason(self):
        self.assert_invalid('case.yaml', 'unknown key', yaml=CASE_YAML + 'extra: 1\n')
        self.assert_invalid('case.yaml', 'schema_version', yaml=CASE_YAML.replace('"1.1"', '"1.0"'))
        self.assert_invalid('case.yaml', 'duplicate key', yaml=CASE_YAML + 'name: sample\n')
        self.assert_invalid('case.yaml', 'missing required key', yaml=CASE_YAML.replace('name: sample\n', ''))
        self.assert_invalid('case.yaml', 'does not match directory', yaml=CASE_YAML.replace('sample', 'other'))
        self.assert_invalid('case.yaml', 'unsupported', yaml=CASE_YAML.replace('name: sample', 'name: [a]'))

    def test_invalid_prompt_and_grader(self):
        self.assert_invalid('prompt.md', 'unknown key', prompt=PROMPT.replace('---\n\n', 'bogus: 1\n---\n\n'))
        self.assert_invalid('prompt.md', 'front matter', prompt='no front matter\n')
        self.assert_invalid('prompt.md', 'expected integer', prompt=PROMPT.replace('5', 'x'))
        g = lambda t: {'01-a.md': t}
        self.assert_invalid('01-a.md', 'type must be', graders=g(GRADER.replace('llm', 'human')))
        self.assert_invalid('01-a.md', 'requires run', graders=g(GRADER.replace('llm', 'command')))
        self.assert_invalid('01-a.md', 'duplicate key', graders=g(GRADER.replace('weight: 1', 'weight: 1\nweight: 2')))

    def test_command_grader_run_scalar_and_block(self):
        one = GRADER.replace('llm', 'command').replace('weight: 1', 'weight: 2\nrun: test -f a.txt')
        blk = GRADER.replace('llm', 'command').replace('weight: 1', 'run: |\n  set -e\n  test -f a.txt')
        c = evallib.load_case(self.make_case(graders={'01-a.md': one, '02-b.md': blk}))
        self.assertEqual((c.graders[0].run, c.graders[0].weight), ('test -f a.txt', 2.0))
        self.assertEqual(c.graders[1].run, 'set -e\ntest -f a.txt\n')

    def test_scaffold_places_skills_outside_git_diff(self):
        c = evallib.load_case(self.make_case())
        wd = self.root / 'wd'
        names = evallib.scaffold(c, wd, '.claude/skills/', self.skills)
        self.assertEqual(names, ['s1'])
        self.assertTrue((wd / '.claude/skills/s1/SKILL.md').is_file())
        import subprocess
        out = subprocess.run(['git', 'status', '--porcelain'], cwd=wd, text=True, capture_output=True).stdout
        self.assertEqual(out, '')

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = run.main(list(args), evals_dir=self.root / 'evals', workspace=self.root / 'ws')
        return code, out.getvalue(), err.getvalue()

    def test_cli_dry_run_both_products_and_unknown_case(self):
        self.make_case()
        code, out, err = self.cli('--dry-run', '--trials', '2')
        self.assertEqual(code, 0, err)
        self.assertEqual(out.count('[dry-run]'), 4)
        self.assertFalse((self.root / 'ws').exists())
        code, out, err = self.cli('--dry-run', '--product', 'codex', '--case', 'sample')
        self.assertEqual((code, out.count('[dry-run]')), (0, 1))
        code, _, err = self.cli('--dry-run', '--case', 'nope')
        self.assertEqual(code, 2)
        self.assertIn('unknown case', err)

    def test_cli_invalid_case_exits_nonzero_with_file(self):
        self.make_case(yaml=CASE_YAML + 'extra: 1\n')
        code, _, err = self.cli('--dry-run')
        self.assertEqual(code, 2)
        self.assertIn('case.yaml', err)
        self.assertIn('unknown key', err)

    def test_adapter_interface(self):
        for product in run.PRODUCTS:
            a = run.load_adapter(product)
            self.assertTrue(a.SKILL_DIR.endswith('/'))
            self.assertTrue(callable(a.run))
        self.assertEqual(set(evallib.empty_summary()), set(evallib.SUMMARY_KEYS))

    def test_run_one_error_trial_is_not_graded(self):
        case = evallib.load_case(self.make_case())

        class Boom:
            SKILL_DIR = '.claude/skills/'

            def run(self, case, workdir, out_dir):
                raise RuntimeError('cli missing')

        class NotInvoked(Boom):
            def run(self, case, workdir, out_dir):
                s = evallib.empty_summary()
                s['error'] = 'skill not invoked'
                return s
        for adapter, msg in ((Boom(), 'adapter raised RuntimeError'), (NotInvoked(), 'skill not invoked')):
            r = run.run_one(case, 'claude', 1, adapter, self.root / 'o' / msg[:5])
            self.assertEqual(r['graders'], [])
            self.assertIn(msg, r['summary']['error'])


if __name__ == '__main__':
    unittest.main()
