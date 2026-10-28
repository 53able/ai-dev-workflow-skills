"""codex adapter tests on saved JSONL samples; no model is called."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import evallib
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

    def test_only_working_copy_skill_md_counts(self):
        def cmd(c):
            return json.dumps({'type': 'item.completed', 'item': {'type': 'command_execution', 'command': c}}) + '\n'
        raw = ''.join(cmd(c) for c in (
            "/bin/zsh -lc 'cat /Users/u/.codex/skills/ains-a/SKILL.md'",
            "/bin/zsh -lc 'cat /elsewhere/.agents/skills/ains-b/SKILL.md'",
            "/bin/zsh -lc 'cat skills/ains-c/SKILL.md'",
            "/bin/zsh -lc 'cat ./.agents/skills/ains-d/SKILL.md'",
            "/bin/zsh -lc \"sed -n 1,80p /w/.agents/skills/ains-e/SKILL.md\"",
            "/bin/zsh -lc 'cd .agents/skills/ains-f && cat SKILL.md'",
            "/bin/zsh -lc 'cd /elsewhere/.agents/skills/ains-g; cat SKILL.md'",
        ))
        self.assertEqual(codex.invoked_skills(raw, Path('/w')), ['ains-d', 'ains-e', 'ains-f'])
        self.assertEqual(codex.invoked_skills(raw), ['ains-d', 'ains-f'])

    def test_timeline(self):
        raw = ('{"type":"item.completed","item":{"type":"command_execution","command":"pytest -q",'
               '"aggregated_output":"' + 'E' * 3000 + '","exit_code":1}}\n'
               '{"type":"item.completed","item":{"type":"file_change","changes":[{"path":"a.py"}]}}\n')
        t = codex.summarize_jsonl(raw)['timeline']
        self.assertEqual([(e['type'], e.get('name')) for e in t],
                         [('tool_use', 'shell'), ('tool_result', None), ('tool_use', 'file_change')])
        self.assertTrue(t[1]['is_error'])
        self.assertLess(len(t[1]['output']), evallib.TIMELINE_CHARS + 50)
        self.assertEqual(t[2]['input'], 'a.py')
        ok = codex.summarize_jsonl((FIX / 'invoked.jsonl').read_text())['timeline']
        self.assertEqual(sum(e['type'] == 'tool_result' for e in ok), 2)
        self.assertFalse(any(e.get('is_error') for e in ok))


class IsolatedEnvTests(unittest.TestCase):
    def test_home_and_codex_home_point_at_empty_dir_with_login_link(self):
        with tempfile.TemporaryDirectory() as real, tempfile.TemporaryDirectory() as tmp:
            Path(real, 'auth.json').write_text('{}')
            Path(real, 'AGENTS.md').write_text('user instructions')
            with mock.patch.dict(os.environ, {'CODEX_HOME': real}):
                env = codex.isolated_env(Path(tmp))
            self.assertEqual(env['HOME'], tmp)
            self.assertEqual(env['CODEX_HOME'], str(Path(tmp, '.codex')))
            self.assertEqual(sorted(p.name for p in Path(tmp, '.codex').iterdir()), ['auth.json'])
            self.assertEqual(Path(tmp, '.codex', 'auth.json').resolve(), Path(real, 'auth.json').resolve())


if __name__ == '__main__':
    unittest.main()
