"""claude adapter tests: summarize() on saved stream-json; no model is called."""
from pathlib import Path
import unittest

from adapters import claude

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'claude'


def lines(name):
    return (FIXTURES / name).read_text().splitlines()


class SummarizeTests(unittest.TestCase):
    def test_real_run_stopping_on_draft(self):
        s = claude.summarize(lines('stops-on-draft.jsonl'), Path('/tmp/work'),
                             '/ains-build docs/changes/x を実装して。')
        self.assertIn('status: draft', s['final_response'])
        self.assertEqual(len(s['commands']), 1)
        self.assertTrue(s['commands'][0].startswith('git status'))
        self.assertEqual(s['edited_files'], [])
        self.assertEqual(s['invoked_skills'], ['ains-build'])
        self.assertEqual(s['model'], 'claude-sonnet-5-5')
        self.assertIsNone(s['error'])

    def test_slash_prefix_ignored_when_not_a_skill(self):
        s = claude.summarize(lines('stops-on-draft.jsonl'), Path('/tmp/work'), '/unknown x')
        self.assertEqual(s['invoked_skills'], [])

    def test_tool_uses_and_max_turns(self):
        s = claude.summarize(lines('tools-max-turns.jsonl'), Path('/tmp/work'))
        self.assertEqual(s['invoked_skills'], ['ains-tdd'])
        self.assertEqual(s['commands'], ['pytest -q'])
        self.assertEqual(s['edited_files'], ['shop/pricing.py', 'tests/test_new.py', 'n.ipynb'])
        self.assertIn('error_max_turns', s['error'])

    def test_path_outside_workdir_kept_and_empty_input(self):
        s = claude.summarize(lines('tools-max-turns.jsonl'), Path('/elsewhere'))
        self.assertEqual(s['edited_files'][0], '/tmp/work/shop/pricing.py')
        e = claude.summarize([])
        self.assertEqual((e['final_response'], e['commands'], e['error']), ('', [], None))


if __name__ == '__main__':
    unittest.main()
