"""Independent approved workflow inventory; static contract, not model behavior proof."""
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[2]
CORE = {'ains-setup', 'ains-spec', 'ains-tasks', 'ains-build', 'ains-ship'}
EXPLICIT = {'ains', 'ains-harness', 'ains-retro', 'ains-team-canvas', 'ains-tool-access'}


class WorkflowInvocationTests(unittest.TestCase):
    def test_only_core_stages_migrate_to_agent_callable(self):
        contract = json.loads((ROOT / 'tests/distribution/intended-skills.json').read_text())
        self.assertEqual(set(contract['manual']), EXPLICIT)
        self.assertTrue(CORE <= set(contract['automatic']))
        for name in CORE | EXPLICIT:
            with self.subTest(skill=name):
                skill = ROOT / 'skills' / name
                frontmatter = (skill / 'SKILL.md').read_text().split('---', 2)[1]
                self.assertEqual('disable-model-invocation: true' in frontmatter, name in EXPLICIT)
                adapter = (skill / 'agents/openai.yaml').read_text()
                self.assertIn('allow_implicit_invocation: ' + ('false' if name in EXPLICIT else 'true'), adapter)


if __name__ == '__main__':
    unittest.main()
