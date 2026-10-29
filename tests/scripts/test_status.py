"""Behavioral baseline; STATUS_SCRIPT can point at an installed script."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(os.environ.get('STATUS_SCRIPT', Path(__file__).resolve().parents[2] / 'skills/ains/scripts/status.sh')).resolve()

class StatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ains-status-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'changes'
        self.root.mkdir()

    def run_status(self, root=None):
        result = subprocess.run(['bash', str(SCRIPT), str(root or self.root)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return result.stdout.strip()

    def change(self, name='2026-10-20-example', spec='draft', plan=None, body=''):
        d = self.root / name
        d.mkdir()
        def doc(status):
            return '---\n' + (f'status: {status}\n' if status is not None else '') + '---\n'
        (d / 'spec.md').write_text(doc(spec) + body)
        if plan is not None:
            (d / 'tasks.md').write_text(doc(None if plan == 'MISSING' else plan) + body)
        return d

    def test_absent_and_empty_root(self):
        self.assertEqual(self.run_status(self.root / 'absent'), f'変更ディレクトリがない: {self.root}/absent')
        self.assertEqual(self.run_status(), f'spec.md のある変更がない: {self.root}')
        (self.root / 'not-a-change').mkdir()
        self.assertEqual(self.run_status(), f'spec.md のある変更がない: {self.root}')

    def test_spec_and_plan_states_remain_separate(self):
        for spec, plan in [('draft', 'approved'), ('approved', 'draft'), ('approved', 'approved')]:
            with self.subTest(spec=spec, plan=plan):
                d = self.change(name=f'{spec}-{plan}', spec=spec, plan=plan)
                self.assertIn(f'status={spec}  plan={plan}', self.run_status())
                for p in d.iterdir(): p.unlink()
                d.rmdir()

    def test_missing_and_unrecognized_states_never_become_approved(self):
        for spec, plan, want_spec, want_plan in [(None, 'MISSING', '?', 'draft'), ('unknown', 'broken', 'unknown', 'broken'), ('draft', 'draft', 'draft', 'draft')]:
            with self.subTest(spec=spec, plan=plan):
                d = self.change(spec=spec, plan=plan)
                out = self.run_status()
                self.assertIn(f'status={want_spec}  plan={want_plan}', out)
                self.assertNotIn('approved', out)
                for p in d.iterdir(): p.unlink()
                d.rmdir()

    def test_body_status_and_non_frontmatter_do_not_approve(self):
        d = self.change(spec=None, plan='MISSING')
        (d / 'spec.md').write_text('# Spec\nstatus: approved\n')
        (d / 'tasks.md').write_text('---\nstatus approved\n---\nstatus: approved\n')
        self.assertIn('status=?  plan=draft', self.run_status())

    def test_front_matter_needs_closing_line_and_ignores_cr(self):
        for name, text, want in [('noclose', '---\nstatus: approved\n# body\n', '?'),
                                 ('bodycr', '---\nstatus: approved\r\n---\n', 'approved'),
                                 ('crlf', '---\r\nstatus: approved\r\n---\r\n', 'approved'),
                                 ('trailws', '---\nstatus: approved  \n---\n', 'approved'),
                                 ('noclose-hr', '---\nstatus: approved\n# body\n\ntext\n\n---\nmore\n', '?'),
                                 ('nbsp', '---\nstatus: approved\u00a0\n---\n', 'approved\u00a0'),
                                 ('yaml-forms', '---\n# c\nid: x\ntags:\n  - a\nlist:\n- b\nstatus:approved\n\n---\n', 'approved')]:
            with self.subTest(name=name):
                d = self.change(spec=None)
                (d / 'spec.md').write_bytes(text.encode())
                (d / 'tasks.md').write_bytes(text.encode())
                plan = 'draft' if want == '?' else want
                self.assertEqual(self.run_status(), f'2026-10-20-example  status={want}  plan={plan}  未決=0  tasks=0/0')
                for p in d.iterdir(): p.unlink()
                d.rmdir()

    def test_counts_questions_and_fallback_spec_tasks(self):
        self.change(body='## 未決事項\n- question\n  - another\n\n## タスク\n- [x] T1: done\n- [X] T2: done\n- [ ] T3: open\n- [ ] T4:   \n- [ ] AC1: not a task\n')
        self.assertEqual(self.run_status(), '2026-10-20-example  status=draft  plan=-  未決=2  tasks=2/3')

    def test_tasks_file_overrides_spec_and_empty_tasks(self):
        d = self.change(body='- [x] T1: spec task\n', plan='approved')
        (d / 'tasks.md').write_text('---\nstatus: approved\n---\n- [ ] T1: \n')
        self.assertIn('tasks=0/0', self.run_status())
        (d / 'tasks.md').write_text('---\nstatus: approved\n---\n- [x] T1: done\n- [X] T2: done\n')
        self.assertIn('tasks=2/2', self.run_status())

    def test_newest_change_first(self):
        self.change('2026-01-01-old')
        self.change('2026-10-25-new')
        self.assertEqual([line.split('  ')[0] for line in self.run_status().splitlines()], ['2026-10-25-new', '2026-01-01-old'])

    def test_spaces_in_root_and_change(self):
        self.root = self.root / 'root with spaces'
        self.root.mkdir()
        self.change('2026-10-25-change with spaces', spec='approved', plan='draft')
        self.assertEqual(self.run_status(), '2026-10-25-change with spaces  status=approved  plan=draft  未決=0  tasks=0/0')

if __name__ == '__main__': unittest.main(verbosity=2)
