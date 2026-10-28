"""Synthetic stdlib regressions; AST loading avoids collector import side effects."""
import ast
import hashlib
import json
import os
import pathlib
import re
import selectors
import shutil
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
FAKE = 'SYNTHETIC_ONLY_0123456789abcdef'
SECRET = 'Bearer ' + FAKE + '+/=='
BODY = '---\nname: ains-spec\n---\n# Specification\nAsk missing decisions before approving the draft.\n'


def definitions(relative):
    path = ROOT / 'tests/runtime' / relative
    tree = ast.parse(path.read_text(), filename=str(path))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    ns = dict(globals(), __file__=str(path), SOURCE=ROOT, MANUAL=[
        'ains', 'ains-spec', 'ains-build', 'ains-tasks'],
        SENSITIVE=re.compile(r'api.?key|access.?token|secret|password|authorization|cookie', re.I))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)
    return ns


class ManualLoads(unittest.TestCase):
    def setUp(self):
        classifier = definitions('claude/release_r3.py')['loads']
        self.sources = {'ains-spec/SKILL.md': BODY,
                        'ains-build/scripts/check.sh': '#!/bin/sh\n# Synthetic helper fixture\nexit 0\n'}
        # Source binding is part of the repaired API; old code receives the same
        # fixtures only through its original arguments for the pre-edit RED run.
        self.loads = lambda d, attempts=None: (classifier(d, attempts, self.sources)
            if 'sources' in classifier.__code__.co_varnames else classifier(d, attempts))

    def evidence(self, tool, content, error=False, **inputs):
        return {'events': [
            {'event': 'tool_use', 'id': 'synthetic', 'name': tool, 'input': inputs},
            {'event': 'tool_result', 'tool_use_id': 'synthetic',
             'is_error': error, 'content': content}]}

    def test_failed_read_is_attempt_not_load(self):
        d = self.evidence('Read', 'File does not exist.', True,
                          file_path='/fixture/.claude/skills/ains-spec/SKILL.md')
        self.assertEqual(self.loads(d), [])

    def test_full_body_read_remains_load_even_error(self):
        for error in (False, True):
            with self.subTest(error=error):
                self.assertEqual(len(self.loads(self.evidence('Read', BODY, error,
                    file_path='/fixture/.claude/skills/ains-spec/SKILL.md'))), 1)

    def test_partial_actual_grep_is_load(self):
        self.assertEqual(len(self.loads(self.evidence('Grep',
            '12:Ask missing decisions before approving the draft.',
            path='/fixture/.claude/skills/ains-spec', output_mode='content'))), 1)

    def test_failed_cat_is_attempt_not_load(self):
        self.assertEqual(self.loads(self.evidence('Bash',
            'cat: /fixture/.claude/skills/ains-spec/SKILL.md: Permission denied', True,
            command='cat /fixture/.claude/skills/ains-spec/SKILL.md')), [])

    def test_nonzero_aggregate_actual_body_remains_load(self):
        self.assertEqual(len(self.loads(self.evidence('Bash', BODY + '\nexit code 1', True,
            command='cat /fixture/.claude/skills/ains-spec/SKILL.md; false'))), 1)

    def test_successful_helper_execution(self):
        self.assertEqual(len(self.loads(self.evidence('Bash', '', False,
            command='bash /fixture/.claude/skills/ains-build/scripts/check.sh'))), 1)

    def test_successful_helper_summary_is_execution_evidence(self):
        self.assertEqual(len(self.loads(self.evidence('Bash', 'No errors found.', False,
            command='bash /fixture/.claude/skills/ains-build/scripts/check.sh'))), 1)

    def test_empty_cat_of_script_is_not_helper_execution(self):
        self.assertEqual(self.loads(self.evidence('Bash', '', False,
            command='cat /fixture/.claude/skills/ains-build/scripts/check.sh')), [])

    def test_attempts_are_retained_with_uncertainty(self):
        for content in ['Permission denied', 'EACCES opening file', '<tool_use_error>Read denied</tool_use_error>', 'Unknown failure']:
            attempts = []
            d = self.evidence('Read', content, True,
                              file_path='/fixture/.claude/skills/ains-spec/SKILL.md')
            self.assertEqual(self.loads(d, attempts), [])
            self.assertEqual(attempts[0]['tool_result'], d['events'][1])
            self.assertIn('attempt', attempts[0]['classification'])

    def test_indirect_partial_grep_and_structured_read_content(self):
        self.assertEqual(len(self.loads(self.evidence('Grep',
            '/fixture/.agents/skills/ains-spec/SKILL.md:12:Ask missing decisions before approving the draft.',
            path='/fixture', output_mode='content'))), 1)
        self.assertEqual(len(self.loads(self.evidence('Read',
            [{'type': 'text', 'text': BODY}], True,
            file_path='/fixture/.agents/skills/ains-spec/SKILL.md'))), 1)

    def test_failed_helper_and_path_only_match_are_not_loads(self):
        self.assertEqual(self.loads(self.evidence('Bash', 'Command failed', True,
            command='bash /fixture/.claude/skills/ains-build/scripts/check.sh')), [])
        self.assertEqual(self.loads(self.evidence('Grep',
            '/fixture/.agents/skills/ains-spec/SKILL.md',
            path='/fixture', output_mode='content')), [])

    def test_mixed_failed_read_and_unrelated_success_is_uncertain(self):
        attempts = []
        d = self.evidence('Bash',
            'cat: /fixture/.claude/skills/ains-spec/SKILL.md: No such file or directory\n'
            'ordinary fixture check complete\n', False,
            command='cat /fixture/.claude/skills/ains-spec/SKILL.md; printf "ordinary fixture check complete\\n"')
        self.assertEqual(self.loads(d, attempts), [])
        self.assertEqual(attempts[0]['tool_result'], d['events'][1])
        self.assertIn('UNVERIFIED', attempts[0]['classification'])

    def test_mixed_failed_helper_and_true_is_uncertain(self):
        attempts = []
        d = self.evidence('Bash',
            'bash: /fixture/.claude/skills/ains-build/scripts/check.sh: No such file or directory',
            False, command='bash /fixture/.claude/skills/ains-build/scripts/check.sh; true')
        self.assertEqual(self.loads(d, attempts), [])
        self.assertEqual(attempts[0]['tool_result'], d['events'][1])

    def test_silent_mixed_helper_status_is_not_attributable(self):
        self.assertEqual(self.loads(self.evidence('Bash', '', False,
            command='bash /fixture/.claude/skills/ains-build/scripts/check.sh; true')), [])

    def test_source_correlated_numbered_and_transformed_bodies(self):
        for content in ['Ask missing decisions before approving',
                        'Ask missing decisions before approving the draft.',
                        '12\tAsk missing decisions before approving the draft.',
                        '12→Ask   missing decisions before approving the draft.']:
            with self.subTest(content=content):
                self.assertEqual(len(self.loads(self.evidence('Bash', content, True,
                    command='nl -ba /fixture/.claude/skills/ains-spec/SKILL.md; false'))), 1)

    def test_unrelated_heading_or_numbered_output_is_not_source_content(self):
        for content in ['# Unrelated completed check', '12:ordinary fixture check complete']:
            self.assertEqual(self.loads(self.evidence('Bash', content, False,
                command='cat /fixture/.claude/skills/ains-spec/SKILL.md; printf unrelated')), [])

    def test_unsupported_helper_forms_retain_exact_uncertain_attempts(self):
        path = '/fixture/.claude/skills/ains-build/scripts/check.sh'
        self.sources['ains-build/scripts/check.sh'] = '#!/bin/sh\n# Synthetic helper fixture\nexit 1\n'
        commands = [interpreter + ' ' + option + ' ' + path
                    for interpreter in ['bash', 'sh', 'python', 'python3']
                    for option in ['--help', '--version', '-c', '-m', '-n', '--', '-lc', '-e', '--unknown']]
        commands += ['bash ' + path + sep + 'true' for sep in ['\n', '\r', '\r\n']]
        commands += [prefix + path for prefix in ['source ', '. ', 'exec ', 'command ',
                    'env bash ', 'timeout 1 bash ', '/unknown/bash ', 'bash --help=topic ', 'VALUE=']]
        commands += ['bash ' + path + suffix for suffix in ['; true', ' && true', ' | true',
                     ' > output.txt', ' $(true)', ' `true`', ' $VALUE', ' ${VALUE}', ' *.txt',
                     ' [ab]', ' {a,b}', ' ~', ' # comment', ' \\true', '\x0btrue']]
        for command in commands:
            with self.subTest(command=repr(command)):
                attempts = []
                d = self.evidence('Bash', 'GNU interpreter version/help output', False, command=command)
                before = json.dumps(d, sort_keys=True)
                self.assertEqual(self.loads(d, attempts), [])
                self.assertEqual(len(attempts), 1)
                self.assertEqual(attempts[0]['tool_use'], d['events'][0])
                self.assertEqual(attempts[0]['tool_result'], d['events'][1])
                self.assertIn('UNVERIFIED', attempts[0]['classification'])
                self.assertEqual(json.dumps(d, sort_keys=True), before)
        # Silent nonzero helper followed by true cannot borrow aggregate exit0.
        for sep in ['\n', '\r', '\r\n']:
            self.assertEqual(self.loads(self.evidence('Bash', '', False,
                command='bash ' + path + sep + 'true')), [])
        # The rejection must happen while CR/LF are still visible in raw text.
        helper = definitions('claude/release_r3.py')['successful_helper']
        with mock.patch.object(shlex, 'shlex', side_effect=AssertionError('newline reached tokenizer')):
            for sep in ['\n', '\r', '\r\n']:
                self.assertEqual(helper('bash ' + path + sep + 'true',
                    {'is_error': False}, self.sources), [])

    def test_supported_helper_forms_and_plain_helper_arguments(self):
        self.sources['ains-build/scripts/check.py'] = '#!/usr/bin/env python3\nprint("No errors found.")\n'
        for prefix in ['', 'bash ', 'sh ', 'python ', 'python3 ', '/bin/bash ', '/bin/sh ', '/usr/bin/python3 ']:
            path = '/fixture/.claude/skills/ains-build/scripts/check.' + ('py' if 'python' in prefix else 'sh')
            for suffix in ['', ' --help', ' --mode strict --verbose', ' "two words" file.txt']:
                with self.subTest(prefix=prefix, suffix=suffix):
                    self.assertEqual(len(self.loads(self.evidence('Bash', 'No errors found.', False,
                        command=prefix + path + suffix))), 1)

    def test_unsupported_helper_form_can_still_return_independent_source_content(self):
        path = '/fixture/.claude/skills/ains-build/scripts/check.sh'
        for command in ['bash --version ' + path, 'bash ' + path + '\ntrue']:
            for body in [self.sources['ains-build/scripts/check.sh'], '# Synthetic helper fixture']:
                result = self.loads(self.evidence('Bash', body, False, command=command))
                self.assertEqual(len(result), 1)
                self.assertIn('source-correlated', result[0]['classification'])

    def test_helper_target_requires_complete_decoded_resource_identity(self):
        suffixes = ['scripts/check.sh unrelated', 'scripts/check.sh ', 'scripts/check.sh  ',
                    'scripts/check.sh.extra', 'scripts/check.sh-other', 'scripts/check.sh_backup',
                    'scripts/check.sh/', 'scripts/./check.sh', 'scripts/sub/../check.sh',
                    'scripts//check.sh', 'scripts/nested/.agents/skills/ains-build/scripts/check.sh']
        for alias in ['.claude', '.agents']:
            for relative in suffixes:
                target = '/fixture root/' + alias + '/skills/ains-build/' + relative
                for prefix in ['', 'bash ']:
                    for quote in ['"', "'"]:
                        command = prefix + quote + target + quote
                        with self.subTest(command=command):
                            attempts = []
                            d = self.evidence('Bash', '', False, command=command)
                            self.assertEqual(self.loads(d, attempts), [])
                            self.assertEqual(len(attempts), 1)
                            self.assertEqual(attempts[0]['tool_use'], d['events'][0])
                            self.assertEqual(attempts[0]['tool_result'], d['events'][1])
                            self.assertIn('UNVERIFIED', attempts[0]['classification'])
        escaped = 'bash /fixture\\ root/.claude/skills/ains-build/scripts/check.sh'
        self.assertEqual(self.loads(self.evidence('Bash', '', False, command=escaped)), [])
        # Identity uncertainty cannot erase independently returned source content.
        d = self.evidence('Bash', self.sources['ains-build/scripts/check.sh'], False,
                          command='bash "/fixture/.claude/skills/ains-build/scripts/check.sh unrelated"')
        self.assertIn('source-correlated', self.loads(d)[0]['classification'])

    def test_exact_quoted_root_and_resource_spaces_remain_supported(self):
        for relative in ['scripts/check.sh', 'scripts/check tool.sh',
                         'scripts/check.sh unrelated', 'scripts/check.sh ']:
            self.sources = {'ains-build/' + relative: '#!/bin/sh\n# Exact synthetic helper resource\nexit 0\n'}
            for alias in ['.claude', '.agents']:
                for prefix in ['', 'bash ']:
                    for quote in ['"', "'"]:
                        target = '/fixture root with spaces/' + alias + '/skills/ains-build/' + relative
                        command = prefix + quote + target + quote + ' --mode strict'
                        with self.subTest(command=command):
                            self.assertEqual(len(self.loads(self.evidence('Bash', 'No errors found.',
                                False, command=command))), 1)


class CollectorSinks(unittest.TestCase):
    def test_targeted_cleaners_preserve_ordinary_text(self):
        for file, name in [('codex/runtime.py', 'clean'), ('claude/r3_runtime.py', 'sanitize')]:
            clean = definitions(file)[name]
            with self.subTest(file=file):
                for text in [SECRET, 'api_key="' + FAKE + '"', 'OPENAI_API_KEY=' + FAKE,
                             'sk-proj-' + FAKE]:
                    self.assertNotIn(FAKE, clean(text))
                self.assertEqual(clean('turn.failed count=2 sha256=abcd'), 'turn.failed count=2 sha256=abcd')

    def test_codex_active_sink_retains_events_reduces_diagnostics(self):
        ns = definitions('codex/activation_recheck.py')
        ns['clean'] = definitions('codex/runtime.py')['clean']
        stderr = ('auth error ' + SECRET).encode()
        stdout = (json.dumps({'type': 'turn.failed', 'text': SECRET,
                              'status': 'failed', 'api_key': FAKE}) + '\n' + SECRET).encode()
        fake = types.SimpleNamespace(returncode=1, communicate=lambda **kw: (stdout, stderr))
        ns.update(receipt=lambda *a: {}, snapshot=lambda *a: {})
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(subprocess, 'Popen', return_value=fake):
            ns['collect'](pathlib.Path(tmp), 'synthetic', 'fixture', pathlib.Path(tmp), [])
            result = json.loads((pathlib.Path(tmp) / 'synthetic.json').read_text())
        self.assertEqual(result['stderr_sha256'], hashlib.sha256(stderr).hexdigest())
        self.assertEqual(result['retained_json_event_count'], 1)
        self.assertEqual(result['event_types'], ['turn.failed'])
        self.assertEqual(result['exit'], 1)
        self.assertEqual(result['events'][0]['status'], 'failed')
        self.assertNotIn(FAKE, json.dumps(result))
        self.assertNotIn('stderr_lines', result)
        self.assertNotIn('stdout_non_json', result)
        self.assertEqual(result['stdout_non_json_count'], 1)

    def claude_run(self, code, timeout, debug_line=None):
        ns = definitions('claude/r3_runtime.py')
        saved = {}; children = []; original = subprocess.Popen
        def launch(*args, **kwargs):
            if debug_line is not None:
                argv = args[0]
                pathlib.Path(argv[argv.index('--debug-file') + 1]).write_text(debug_line)
            child = original([sys.executable, '-c', code], **kwargs)
            children.append(child)
            return child
        ns.update(save=lambda name, value: saved.update({name: value}),
                  contributors=lambda root: {}, snapshot=lambda root: {})
        start = time.monotonic()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(subprocess, 'Popen', side_effect=launch):
            try:
                result = ns['run']('synthetic', pathlib.Path(tmp), ['fixture'], timeout=timeout)
            finally:
                for child in children:
                    if child.poll() is None:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
                    for pipe in (child.stdin, child.stdout, child.stderr):
                        if pipe and not pipe.closed: pipe.close()
        self.assertTrue(all(child.poll() is not None for child in children))
        return result, saved, time.monotonic() - start

    def test_partial_line_deadline_and_cleanup(self):
        # Old readline waits 0.8s. Fixed collector must TERM well before then.
        result, _, elapsed = self.claude_run(
            "import os,time; os.write(1,b'partial-out'); os.write(2,b'partial-err'); time.sleep(.8)", .08)
        self.assertLess(elapsed, .6)
        self.assertTrue(result['timeout'])
        self.assertNotEqual(result['exit'], 0)
        self.assertEqual(result['stream_accounting']['stdout']['partial_lines'], 1)
        self.assertEqual(result['stream_accounting']['stderr']['partial_lines'], 1)
        self.assertEqual(result['stream_accounting']['stdout']['bytes'], len(b'partial-out'))

    def test_fragmented_utf8_and_final_partial_json_are_retained(self):
        event = {'type': 'assistant', 'message': {'role': 'assistant',
            'content': [{'type': 'text', 'text': '日本語'}]}}
        data = json.dumps(event, ensure_ascii=False).encode()
        split = data.index('日'.encode()) + 1
        code = ('import os,time; os.write(1,' + repr(data[:split]) +
                '); time.sleep(.01); os.write(1,' + repr(data[split:]) + ')')
        result, _, _ = self.claude_run(code, 1)
        self.assertEqual(result['events'][0]['text'], '日本語')
        self.assertEqual(result['stream_accounting']['stdout']['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(result['stream_accounting']['stdout']['partial_lines'], 1)
        self.assertFalse(result['final_drain_incomplete'])

    def test_events_after_result_in_same_read_are_retained(self):
        events = [{'type': 'result', 'result': 'done', 'is_error': False},
                  {'type': 'assistant', 'message': {'content': [
                      {'type': 'text', 'text': 'final event'}]}}]
        data = ('\n'.join(map(json.dumps, events)) + '\n').encode()
        result, _, _ = self.claude_run('import os; os.write(1,' + repr(data) + ')', 1)
        self.assertEqual(len(result['all_sanitized_stream_events']), 2)
        self.assertEqual(result['events'][0]['text'], 'final event')

    def test_timeout_final_drain_retains_termination_output(self):
        event = {'type': 'assistant', 'message': {'content': [
            {'type': 'text', 'text': 'termination evidence'}]}}
        data = json.dumps(event).encode()
        code = ('import os,time,signal; signal.signal(signal.SIGTERM, '
                'lambda *a: (os.write(2,' + repr(data) + '),exit(0))); '
                'os.write(1,b"ready"); time.sleep(.8)')
        result, _, elapsed = self.claude_run(code, .15)
        self.assertTrue(result['timeout'])
        self.assertLess(elapsed, .6)
        self.assertEqual(result['events'][0]['text'], 'termination evidence')
        self.assertEqual(result['stream_accounting']['stderr']['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(result['stream_accounting']['stderr']['partial_lines'], 1)

    def test_debug_diagnostics_keep_only_facts_and_hashes(self):
        line = '[DEBUG] Loading skills from: ains-spec ' + SECRET + ' api_key=' + FAKE
        result, saved, _ = self.claude_run('pass', 1, debug_line=line)
        self.assertNotIn(FAKE, json.dumps(saved))
        self.assertEqual(result['debug_facts'][0]['line_sha256'], hashlib.sha256(line.encode()).hexdigest())
        self.assertEqual(len(result['debug_loader_inventory']), 1)
        self.assertNotIn('loader_record', result['debug_facts'][0])

    def test_claude_duplicate_event_turn_and_checkpoint_sinks(self):
        events = [
            {'type': 'assistant', 'message': {'role': 'assistant', 'content': [
                {'type': 'text', 'text': SECRET},
                {'type': 'tool_use', 'name': 'Bash', 'id': 'fake', 'input': {'api_key': FAKE}}]}},
            {'type': 'user', 'message': {'role': 'user', 'content': [
                {'type': 'tool_result', 'tool_use_id': 'fake', 'is_error': True,
                 'content': SECRET}]}},
            {'type': 'result', 'result': SECRET, 'is_error': True, 'subtype': 'error'}]
        code = 'import os; os.write(1,' + repr(('\n'.join(map(json.dumps, events)) + '\n').encode()) + ')'
        result, saved, _ = self.claude_run(code, 1)
        self.assertNotIn(FAKE, json.dumps(saved))
        self.assertEqual(len(result['all_sanitized_stream_events']), 3)
        self.assertEqual(len(result['events']), 3)
        self.assertTrue(result['turns'][0]['is_error'])
        self.assertEqual(result['turns'][0]['subtype'], 'error')


if __name__ == '__main__':
    unittest.main()
