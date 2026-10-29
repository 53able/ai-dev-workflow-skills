"""claude adapter tests: summarize() on saved stream-json, run() with a fake `claude`; no model is called."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import evallib
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
        self.assertTrue(s['error'].startswith('max_turns'))

    def test_path_outside_workdir_kept_and_empty_input(self):
        s = claude.summarize(lines('tools-max-turns.jsonl'), Path('/elsewhere'))
        self.assertEqual(s['edited_files'][0], '/tmp/work/shop/pricing.py')
        e = claude.summarize([])
        self.assertEqual((e['final_response'], e['commands'], e['error']), ('', [], None))


    def test_timeline(self):
        s = claude.summarize(lines('stops-on-draft.jsonl'), Path('/tmp/work'), '/ains-build x')
        self.assertEqual([e['type'] for e in s['timeline']], ['tool_use', 'tool_result'])
        self.assertEqual(s['timeline'][0]['name'], 'Bash')
        self.assertIn('git status', s['timeline'][0]['input'])
        self.assertEqual(s['timeline'][1], {'type': 'tool_result', 'output': '(trimmed)', 'is_error': False})
        long = json.dumps({'type': 'user', 'message': {'content': [
            {'type': 'tool_result', 'content': [{'type': 'text', 'text': 'F' * 5000}], 'is_error': True}]}})
        entry = claude.summarize([long])['timeline'][0]
        self.assertTrue(entry['is_error'])
        self.assertLess(len(entry['output']), evallib.TIMELINE_CHARS + 50)

    def test_named_skill_missing_from_init_is_not_invoked(self):
        s = claude.summarize(lines('stops-on-draft.jsonl'), Path('/tmp/work'), '/ains-review x')
        self.assertEqual(s['error'], 'skill not invoked: ains-review')
        self.assertEqual(s['invoked_skills'], [])

    def test_check_init(self):
        init = {'cwd': '/tmp/work', 'additional_directories': [], 'tools': ['Read', 'Skill']}
        self.assertIsNone(claude.check_init(init, Path('/tmp/work'), ['Read', 'Skill', 'Bash']))
        self.assertIsNone(claude.check_init(init, Path('/tmp/work'), None))
        bad = [({**init, 'tools': ['Read', 'Agent']}, 'Agent'), ({**init, 'cwd': '/home/x'}, 'cwd'),
               ({**init, 'additional_directories': ['/home']}, 'additional'), ({}, 'no init')]
        for ev, needle in bad:
            err = claude.check_init(ev, Path('/tmp/work'), ['Read', 'Skill'])
            self.assertTrue(err.startswith('unexpected context'), err)
            self.assertIn(needle, err)


FAKE = """#!/bin/sh
[ "$1" = --version ] && { echo 9.9.9; exit 0; }
printf '%s\\n' "$@" > "$FAKE_DIR/args"
cat > /dev/null
[ -n "$FAKE_SLEEP" ] && sleep "$FAKE_SLEEP"
sed "s#@CWD@#$PWD#" "$FAKE_DIR/stream"
exit "${FAKE_EXIT:-0}"
"""


class RunWithFakeCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='ains-fakeclaude-')
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name).resolve()
        (self.dir / 'bin').mkdir()
        (self.dir / 'bin' / 'claude').write_text(FAKE)
        (self.dir / 'bin' / 'claude').chmod(0o755)
        self.work = self.dir / 'work'
        self.work.mkdir()
        self.case = object.__new__(evallib.Case)
        self.case.__dict__.update(prompt='/ains-build x\n', max_turns=3, timeout_seconds=30,
                                  allowed_tools=['Read', 'Skill', 'Bash'])

    def run_fake(self, events, **env):
        (self.dir / 'stream').write_text(''.join(json.dumps(e) + '\n' for e in events))
        path = f'{self.dir / "bin"}{os.pathsep}{os.environ["PATH"]}'
        with mock.patch.dict(os.environ, {'PATH': path, 'FAKE_DIR': str(self.dir), **env}):
            return claude.run(self.case, self.work, self.dir / 'out')

    def init(self, **kw):
        return {'type': 'system', 'subtype': 'init', 'cwd': '@CWD@', 'model': 'm', 'skills': ['ains-build'],
                'additional_directories': [], 'tools': ['Read', 'Skill', 'Bash'], **kw}

    def test_tools_limit_and_init_saved(self):
        s = self.run_fake([self.init(), {'type': 'result', 'subtype': 'success', 'result': 'done'}])
        self.assertIsNone(s['error'])
        args = (self.dir / 'args').read_text().splitlines()
        self.assertEqual(args[args.index('--tools') + 1], 'Read,Skill,Bash')
        self.assertEqual(json.loads((self.dir / 'out' / 'init.json').read_text())['cwd'], str(self.work))
        self.assertEqual(s['cli_version'], '9.9.9')

    def test_git_config_isolated_in_env(self):
        (self.dir / 'bin' / 'claude').write_text(FAKE.replace('cat > /dev/null', 'cat > /dev/null\n'
            'echo "$GIT_CONFIG_GLOBAL $GIT_CONFIG_NOSYSTEM" > "$FAKE_DIR/gitenv"'))
        self.run_fake([self.init(), {'type': 'result', 'subtype': 'success', 'result': 'done'}])
        self.assertEqual((self.dir / 'gitenv').read_text().split(), [os.devnull, '1'])

    def test_subject_isolation(self):
        (self.dir / 'bin' / 'claude').write_text(FAKE.replace('cat > /dev/null', 'cat > /dev/null\n'
            'echo "$GIT_ALLOW_PROTOCOL|$GH_TOKEN|${SSH_AUTH_SOCK-unset}" > "$FAKE_DIR/subj"'))
        self.run_fake([self.init(), {'type': 'result', 'subtype': 'success', 'result': 'done'}], SSH_AUTH_SOCK='/x')
        self.assertEqual((self.dir / 'subj').read_text().strip(), 'file|ains-eval-invalid|unset')
        args = (self.dir / 'args').read_text().splitlines()
        settings = json.loads(args[args.index('--settings') + 1])
        self.assertTrue(settings['sandbox']['enabled'])
        self.assertTrue(settings['sandbox']['failIfUnavailable'])
        self.assertFalse(settings['sandbox']['allowUnsandboxedCommands'])
        self.assertEqual(settings['sandbox']['network']['allowedDomains'], [])
        self.assertIn('~/', settings['sandbox']['filesystem']['denyRead'])
        self.assertIn('Read(~/**)', settings['permissions']['deny'])
        self.assertEqual(sorted(p.name for p in self.work.iterdir()), [])   # nothing written into the copy

    def test_agent_tool_provided_is_error(self):
        s = self.run_fake([self.init(tools=['Read', 'Skill', 'Bash', 'Agent']),
                           {'type': 'result', 'subtype': 'success', 'result': 'done'}])
        self.assertIn('Agent', s['error'])

    def test_max_turns_kept_over_exit_code(self):
        s = self.run_fake([self.init(), {'type': 'result', 'subtype': 'error_max_turns', 'result': ''}],
                          FAKE_EXIT='1')
        self.assertTrue(s['error'].startswith('max_turns'), s['error'])
        s = self.run_fake([self.init()], FAKE_EXIT='2')
        self.assertTrue(s['error'].startswith('claude exited with code 2'), s['error'])

    def test_timeout_saves_transcript(self):
        self.case.timeout_seconds = 1
        s = self.run_fake([self.init()], FAKE_SLEEP='20')
        self.assertTrue(s['error'].startswith('timeout after 1s'), s['error'])
        self.assertTrue((self.dir / 'out' / 'transcript.jsonl').is_file())

    def test_kill_group_tolerates_finished_process(self):
        p = subprocess.Popen(['true'], start_new_session=True)
        p.wait()
        evallib.kill_group(p)


if __name__ == '__main__':
    unittest.main()
