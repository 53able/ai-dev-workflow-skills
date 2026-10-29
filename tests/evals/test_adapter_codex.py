"""codex adapter tests on saved JSONL samples; no model is called."""
import json
import os
import shutil
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
            self.assertEqual(env['GIT_CONFIG_GLOBAL'], os.devnull)
            self.assertEqual(env['GIT_CONFIG_NOSYSTEM'], '1')
            self.assertEqual((env['GIT_ALLOW_PROTOCOL'], env['GH_TOKEN']), ('file', 'ains-eval-invalid'))
            self.assertEqual(sorted(p.name for p in Path(tmp, '.codex').iterdir()), ['auth.json'])
            self.assertEqual(Path(tmp, '.codex', 'auth.json').resolve(), Path(real, 'auth.json').resolve())


FAKE = """#!/bin/sh
[ "$1" = --version ] && { echo 9.9.9; exit 0; }
printf '%s\\n%s\\n' "$HOME" "$CODEX_HOME" > "$FAKE_DIR/env"
[ -e "$CODEX_HOME/auth.json" ] && echo linked > "$FAKE_DIR/auth_seen"
[ -n "$FAKE_SLEEP" ] && sleep "$FAKE_SLEEP"
cat "$FAKE_DIR/stream"
echo boom >&2
exit "${FAKE_EXIT:-0}"
"""
READ_SKILL = {'type': 'item.completed', 'item': {'type': 'command_execution', 'exit_code': 0,
                                                 'command': "/bin/zsh -lc 'cat .agents/skills/ains-build/SKILL.md'"}}
OTHER = {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'no skill read'}}


class RunWithFakeCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='ains-fakecodex-')
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name).resolve()
        (self.dir / 'bin').mkdir()
        (self.dir / 'bin' / 'codex').write_text(FAKE)
        (self.dir / 'bin' / 'codex').chmod(0o755)
        self.work = self.dir / 'work'
        self.work.mkdir()
        self.real_home = self.dir / 'real-codex'
        self.real_home.mkdir()
        (self.real_home / 'auth.json').write_text('{"token": "x"}')
        self.case = object.__new__(evallib.Case)
        self.case.__dict__.update(prompt='/ains-build x\n', max_turns=3, timeout_seconds=30, allowed_tools=None)

    def run_fake(self, events, **env):
        (self.dir / 'stream').write_text(''.join(json.dumps(e) + '\n' for e in events))
        path = f'{self.dir / "bin"}{os.pathsep}{os.environ["PATH"]}'
        with mock.patch.dict(os.environ, {'PATH': path, 'FAKE_DIR': str(self.dir),
                                          'CODEX_HOME': str(self.real_home), **env}):
            return codex.run(self.case, self.work, self.dir / 'out')

    def test_skill_read_is_ok(self):
        s = self.run_fake([READ_SKILL, OTHER])
        self.assertIsNone(s['error'])
        self.assertEqual(s['invoked_skills'], ['ains-build'])
        self.assertEqual(s['cli_version'], '9.9.9')
        self.assertTrue((self.dir / 'out' / 'codex.jsonl').is_file())

    def test_skill_not_read_is_error(self):
        s = self.run_fake([OTHER])
        self.assertEqual(s['error'], 'skill not invoked: ains-build')

    def install(self, front='name: ains-build'):
        skill = self.work / '.agents/skills/ains-build/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text(f'---\n{front}\n---\nbody\n')

    def test_named_skill_in_working_copy_is_injected(self):
        self.install()
        s = self.run_fake([OTHER])
        self.assertIsNone(s['error'])
        self.assertEqual(s['invoked_skills'], ['ains-build'])
        self.assertEqual(s['injected_skills'], ['ains-build'])

    def test_read_skill_is_not_marked_injected(self):
        self.install()
        s = self.run_fake([READ_SKILL])
        self.assertEqual(s['invoked_skills'], ['ains-build'])
        self.assertEqual(s['injected_skills'], [])

    def test_skill_with_other_or_no_name_is_not_injected(self):
        for front in ['name: ains-other', 'description: x']:
            with self.subTest(front=front):
                shutil.rmtree(self.work / '.agents', ignore_errors=True)
                self.install(front)
                s = self.run_fake([OTHER])
                self.assertEqual(s['error'], 'skill not invoked: ains-build')

    def test_timeout_saves_transcript(self):
        self.case.timeout_seconds = 1
        s = self.run_fake([READ_SKILL], FAKE_SLEEP='20')
        self.assertEqual(s['error'], 'timeout after 1s')
        self.assertTrue((self.dir / 'out' / 'codex.jsonl').is_file())
        self.assertTrue((self.dir / 'out' / 'codex.stderr').is_file())

    def test_nonzero_exit_is_error(self):
        s = self.run_fake([READ_SKILL], FAKE_EXIT='3')
        self.assertTrue(s['error'].startswith('codex exited with 3'), s['error'])
        self.assertIn('boom', s['error'])

    def test_temp_home_removed_and_real_login_kept(self):
        self.run_fake([READ_SKILL])
        home, codex_home = (self.dir / 'env').read_text().splitlines()
        self.assertNotEqual(home, str(Path.home()))
        self.assertNotEqual(codex_home, str(self.real_home))
        self.assertEqual(codex_home, str(Path(home, '.codex')))
        self.assertTrue((self.dir / 'auth_seen').exists())   # login was reachable in the child
        self.assertFalse(Path(home).exists())
        self.assertEqual((self.real_home / 'auth.json').read_text(), '{"token": "x"}')


if __name__ == '__main__':
    unittest.main()
