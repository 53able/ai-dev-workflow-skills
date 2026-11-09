"""New workflow boundary graders reject unauthorized implementation and false approvals."""
from pathlib import Path
import tempfile
import unittest

import evallib
import grading

CHANGE = 'docs/changes/2026-10-20-discount-clamp'
NAMES = ('workflow-continues-to-plan', 'workflow-standalone-stage',
         'workflow-legacy-manual-policy', 'workflow-draft-spec-stops', 'workflow-empty-tasks-stop-ship')


class WorkflowGraderTests(unittest.TestCase):
    def test_each_boundary_grader_accepts_expected_state_and_rejects_scope_escape(self):
        for name in NAMES:
            with self.subTest(case=name), tempfile.TemporaryDirectory(prefix='ains-workflow-') as temp:
                root = Path(temp)
                case = evallib.load_case(evallib.HERE / 'ains' / name)
                work = root / 'project'
                evallib.scaffold(case, work, '.agents/skills')
                task = work / CHANGE / 'tasks.md'
                plan_case = name in NAMES[:2]
                if plan_case:
                    task.write_text('---\nstatus: draft\n---\n\n# Plan\n')
                grader = next(g for g in case.graders if g.type == 'command')
                evidence = root / 'evidence'
                evidence.mkdir()
                self.assertEqual(grading.grade_command(grader, work, evidence)['status'], 'pass')
                pricing = work / 'shop/pricing.py'
                old = pricing.read_bytes()
                pricing.write_bytes(old + b'\n# unauthorized implementation\n')
                self.assertEqual(grading.grade_command(grader, work, evidence)['status'], 'fail')
                pricing.write_bytes(old)
                if plan_case:
                    task.write_text('---\nstatus: approved\n---\n')
                elif name == 'workflow-draft-spec-stops':
                    spec = work / CHANGE / 'spec.md'
                    spec.write_text(spec.read_text().replace('status: draft', 'status: approved'))
                else:
                    task.write_text('---\nstatus: draft\n---\n')
                self.assertEqual(grading.grade_command(grader, work, evidence)['status'], 'fail')


if __name__ == '__main__':
    unittest.main()
