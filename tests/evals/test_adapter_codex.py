"""codex adapter tests on saved JSONL samples; no model is called."""
from pathlib import Path
import unittest

from adapters import codex

FIX = Path(__file__).resolve().parent / 'fixtures' / 'codex'


class PromptRewriteTests(unittest.TestCase):
    def test_leading_slash_command(self):
        self.assertEqual(codex.to_codex_prompt('/ains-build docs/x を実装して'),
                         '$ains-build docs/x を実装して')

    def test_bare_ains_and_later_line_and_after_space(self):
        self.assertEqual(codex.to_codex_prompt('/ains を使う\nまず /ains-spec で\n'),
                         '$ains を使う\nまず $ains-spec で\n')

    def test_paths_are_not_rewritten(self):
        for text in ('docs/ains/human-review-rules', './ains-x', 'a/ains-build', 'https://x/ains-y'):
            self.assertEqual(codex.to_codex_prompt(text), text)

    def test_non_ains_slash_unchanged(self):
        self.assertEqual(codex.to_codex_prompt('/review と /ainsley'), '/review と $ainsley')

    def test_named_skills(self):
        self.assertEqual(codex.named_skills('$ains-build x $ains-build $ains-tdd'),
                         ['ains-build', 'ains-tdd'])
        self.assertEqual(codex.named_skills('docs/ains/x US$ains'), [])


class SummaryTests(unittest.TestCase):
    def test_invoked_sample(self):
        raw = (FIX / 'invoked.jsonl').read_text()
        self.assertEqual(codex.invoked_skills(raw), ['ains-build', 'ains-tdd'])
        s = codex.summarize_jsonl(raw)
        self.assertEqual(len(s['commands']), 2)
        self.assertEqual(s['edited_files'], [])
        self.assertIn('status: draft', s['final_response'])
        self.assertTrue(s['final_response'].startswith('tasks.md'))

    def test_not_invoked_sample(self):
        raw = (FIX / 'not_invoked.jsonl').read_text()
        self.assertEqual(codex.invoked_skills(raw), [])
        self.assertEqual(codex.summarize_jsonl(raw)['invoked_skills'], [])

    def test_skill_path_in_message_text_is_not_an_invocation(self):
        raw = '{"type":"item.completed","item":{"type":"agent_message","text":"see skills/ains-build/SKILL.md"}}\n'
        self.assertEqual(codex.invoked_skills(raw), [])

    def test_file_change_and_garbage_lines(self):
        raw = ('not json\n'
               '{"type":"item.completed","item":{"type":"file_change","changes":'
               '[{"path":"a.py","kind":"update"},{"path":"a.py","kind":"update"},{"path":"b.py"}]}}\n')
        self.assertEqual(codex.summarize_jsonl(raw)['edited_files'], ['a.py', 'b.py'])


if __name__ == '__main__':
    unittest.main()
