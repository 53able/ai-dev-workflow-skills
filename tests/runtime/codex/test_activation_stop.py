"""Synthetic stop/continuation checks; no collector imports or runtime launch."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shlex
import types
import tempfile
from unittest import mock
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
STAGES = ['ains', 'ains-setup', 'ains-spec', 'ains-tasks', 'ains-build',
          'ains-ship', 'ains-retro', 'ains-team-canvas', 'ains-harness', 'ains-tool-access']


def collector_definitions():
    path = ROOT / 'tests/runtime/codex/activation_r3.py'
    tree = ast.parse(path.read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) or
             (isinstance(n, ast.Assign) and all(isinstance(t, ast.Name) and t.id in
              ['CANONICAL', 'PROJECTION_VERSION', 'PINNED_CODEX_SOURCE', 'PROJECTION_REASON']
              for t in n.targets))]
    ns = dict(globals(), __file__=str(path))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)
    # Before the repair, execute the original predicates extracted from main.
    # This reproduces behavior rather than failing merely on a missing new API.
    if 'continuation_ready' not in ns:
        gate = next(n for n in ast.walk(tree) if isinstance(n, ast.If) and
                    "record['exit'] != 0" in ast.unparse(n.test))
        expr = compile(ast.Expression(gate.test), str(path), 'eval')
        ns['continuation_ready'] = lambda record, expr=expr: not eval(expr, {}, {'record': record})
    if 'manual_access' not in ns:
        check = next(n for n in ast.walk(tree) if isinstance(n, ast.If) and
                     isinstance(n.test, ast.Call) and isinstance(n.test.func, ast.Name) and
                     n.test.func.id == 'any' and 'body' in ast.unparse(n.test))
        expr = compile(ast.Expression(check.test), str(path), 'eval')
        ns['manual_access'] = lambda record, sources: {
            'loads': [record] if eval(expr, {'record': record,
                       'body': sources['ains-spec/SKILL.md']}) else [], 'attempts': []}
    return ns


def paired(command, output='', exit_code=0, status='completed'):
    return [
        {'type': 'item.started', 'item': {'id': 'synthetic', 'type': 'command_execution',
                                        'command': command, 'status': 'in_progress'}},
        {'type': 'item.completed', 'item': {'id': 'synthetic', 'type': 'command_execution',
            'command': command, 'aggregated_output': output, 'exit_code': exit_code, 'status': status}}]


class ActivationStopTests(unittest.TestCase):
    def setUp(self):
        self.ns = collector_definitions()
        self.sources = {stage + '/SKILL.md':
            '---\nname: ' + stage + '\n---\n# Synthetic ' + stage + '\n'
            'Ask missing decisions for the synthetic ' + stage + ' draft.\n'
            for stage in STAGES}
        self.sources['ains-ship/scripts/check.sh'] = '#!/bin/sh\n# Synthetic shipping helper\nexit 0\n'
        self.sources['ains-retro/references/notes.md'] = 'Preserve the synthetic retrospective learning record.\n'

    def record(self, events):
        return {'exit': 0, 'timeout': False,
                'structural_closure': {'projected_stable': True}, 'events': events}

    def classify(self, command, output='', exit_code=0, status='completed'):
        record = self.record(paired(command, output, exit_code, status))
        before = copy.deepcopy((record, self.sources))
        result = self.ns['manual_access'](record, self.sources)
        self.assertEqual((record, self.sources), before)
        return result

    def test_missing_success_terminal_blocks(self):
        self.assertFalse(self.ns['continuation_ready'](self.record([{'type': 'turn.started'}])))

    def test_timeout_exit_zero_blocks(self):
        record = self.record([{'type': 'turn.completed'}]); record['timeout'] = True
        self.assertFalse(self.ns['continuation_ready'](record))

    def test_failed_or_error_terminal_exit_zero_blocks(self):
        for typ in ['turn.failed', 'error', 'turn.cancelled']:
            with self.subTest(typ=typ):
                record = self.record([{'type': 'turn.completed'}, {'type': typ}])
                self.assertFalse(self.ns['continuation_ready'](record))
        for detail in [{'status': 'failed'}, {'status': 'in_progress'}, {'error': {'message': 'synthetic failure'}}]:
            self.assertFalse(self.ns['continuation_ready'](self.record([
                {'type': 'turn.completed', **detail}])))

    def test_completed_healthy_turn_allows_red_green_commands(self):
        events = paired('python3 -m unittest', 'FAILED (failures=1)', 1)
        events += paired('python3 -m unittest', 'OK', 0) + [{'type': 'turn.completed'}]
        self.assertTrue(self.ns['continuation_ready'](self.record(events)))

    def test_exit_or_projection_failure_blocks(self):
        record = self.record([{'type': 'turn.completed'}])
        record['exit'] = 1
        self.assertFalse(self.ns['continuation_ready'](record))
        record['exit'] = 0; record['structural_closure']['projected_stable'] = False
        self.assertFalse(self.ns['continuation_ready'](record))

    def test_partial_numbered_other_stages_and_both_aliases_stop(self):
        for stage in STAGES:
            line = 'Ask missing decisions for the synthetic ' + stage + ' draft.'
            for alias in ['.agents', '.claude']:
                path = '/fixture/' + alias + '/skills/' + stage + '/SKILL.md'
                for output in [line, line[:32], '12\t' + line, path + ':12:' + line,
                               line.replace(' ', '  ')]:
                    with self.subTest(stage=stage, alias=alias, output=output):
                        self.assertEqual(len(self.classify('sed -n 12p ' + path, output)['loads']), 1)

    def test_full_body_nonzero_aggregate_stops(self):
        output = self.sources['ains-spec/SKILL.md'] + '\nother command failed'
        self.assertEqual(len(self.classify('cat /fixture/.agents/skills/ains-spec/SKILL.md; false',
                                          output, 1)['loads']), 1)

    def test_other_manual_resource_and_successful_helper_stop(self):
        self.assertEqual(len(self.classify('cat /fixture/.agents/skills/ains-retro/references/notes.md',
            self.sources['ains-retro/references/notes.md'])['loads']), 1)
        self.assertEqual(len(self.classify('bash /fixture/.claude/skills/ains-ship/scripts/check.sh')['loads']), 1)

    def test_failed_and_path_only_attempts_are_retained(self):
        for command, output, code in [
            ('cat /fixture/.agents/skills/ains-spec/SKILL.md', 'Permission denied', 1),
            ('grep -l draft /fixture/.agents/skills/ains-spec/SKILL.md',
             '/fixture/.agents/skills/ains-spec/SKILL.md', 0),
            ('bash /fixture/.claude/skills/ains-ship/scripts/check.sh; true',
             'bash: /fixture/.claude/skills/ains-ship/scripts/check.sh: No such file', 0),
            ('cat /fixture/.agents/skills/ains-spec/SKILL.md; printf ordinary',
             'cat: No such file\nordinary fixture check complete', 0)]:
            with self.subTest(command=command):
                result = self.classify(command, output, code)
                self.assertEqual(result['loads'], [])
                self.assertEqual(len(result['attempts']), 1)
                self.assertIn('UNVERIFIED', result['attempts'][0]['classification'])

    def test_completed_then_unfinished_turn_is_blocked(self):
        self.assertFalse(self.ns['continuation_ready'](self.record([
            {'type': 'turn.completed'}, {'type': 'turn.started'}])))

    def test_import_safe_shared_classifier_and_installed_resource_corpus(self):
        with mock.patch('subprocess.Popen', side_effect=AssertionError('No runtime launch')):
            classifier = self.ns['manual_classifier']()
            with tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                for alias in ['.claude', '.agents']:
                    stage = 'ains-spec' if alias == '.claude' else 'ains-retro'
                    base = root / alias / 'skills' / stage
                    (base / 'references').mkdir(parents=True)
                    (base / 'references/notes.md').write_text(self.sources['ains-spec/SKILL.md'])
                    (base / 'agents').mkdir()
                    (base / 'agents/openai.yaml').write_text('discovery metadata only')
                result = classifier.installed_manual_sources(root)
        self.assertEqual(set(result), {'ains-spec/references/notes.md', 'ains-retro/references/notes.md'})

    def test_nonmanual_automatic_stage_does_not_inherit_manual_classification(self):
        output = self.sources['ains-spec/SKILL.md']
        result = self.classify('cat /fixture/.agents/skills/ains-tdd/SKILL.md', output)
        self.assertEqual(result['loads'], [])

    def test_unsupported_helper_forms_are_uncertain_through_codex_adapter(self):
        path = '/fixture/.claude/skills/ains-ship/scripts/check.sh'
        self.sources['ains-ship/scripts/check.sh'] = '#!/bin/sh\n# Synthetic shipping helper\nexit 1\n'
        commands = ['bash ' + option + ' ' + path for option in
                    ['--help', '--version', '-c', '-m', '-n', '--', '-lc', '-e', '--unknown']]
        commands += ['bash ' + path + sep + 'true' for sep in ['\n', '\r', '\r\n']]
        commands += [prefix + path for prefix in ['source ', 'exec ', 'command ',
                     'env bash ', 'timeout 1 bash ', '/unknown/bash ', 'VALUE=']]
        commands += ['bash ' + path + suffix for suffix in [' && true', ' $(true)', ' $VALUE',
                     ' *.txt', ' {a,b}', ' # comment', ' \\true']]
        for command in commands:
            with self.subTest(command=repr(command)):
                result = self.classify(command)
                self.assertEqual(result['loads'], [])
                self.assertEqual(len(result['attempts']), 1)
                attempt = result['attempts'][0]
                self.assertIn('UNVERIFIED', attempt['classification'])
                self.assertEqual(attempt['paired_events']['command_result'], paired(command)[1])

    def test_supported_helper_arguments_and_independent_content_through_codex(self):
        path = '/fixture/.agents/skills/ains-ship/scripts/check.sh'
        self.sources['ains-ship/scripts/check.py'] = '#!/usr/bin/env python3\nprint("No errors found.")\n'
        for prefix in ['', 'bash ', 'sh ', 'python3 ']:
            target = path.replace('.sh', '.py') if prefix == 'python3 ' else path
            self.assertEqual(len(self.classify(prefix + target + ' --mode strict', 'No errors found.')['loads']), 1)
        for command in ['bash --version ' + path, 'bash ' + path + '\ntrue']:
            result = self.classify(command, self.sources['ains-ship/scripts/check.sh'], 1)
            self.assertEqual(len(result['loads']), 1)
            self.assertIn('source-correlated', result['loads'][0]['classification'])

    def test_exact_helper_target_identity_through_codex(self):
        for alias in ['.claude', '.agents']:
            for suffix in ['scripts/check.sh unrelated', 'scripts/check.sh ', 'scripts/check.sh.extra',
                           'scripts/check.sh_other', 'scripts/check.sh/', 'scripts/./check.sh',
                           'scripts/sub/../check.sh', 'scripts//check.sh',
                           'scripts/nested/.claude/skills/ains-ship/scripts/check.sh']:
                path = '/fixture root/' + alias + '/skills/ains-ship/' + suffix
                for prefix in ['', 'bash ']:
                    for quote in ['"', "'"]:
                        command = prefix + quote + path + quote
                        with self.subTest(command=command):
                            result = self.classify(command)
                            self.assertEqual(result['loads'], [])
                            self.assertEqual(len(result['attempts']), 1)
                            self.assertEqual(result['attempts'][0]['paired_events']['command_result'], paired(command)[1])
                            self.assertIn('UNVERIFIED', result['attempts'][0]['classification'])
        escaped = 'bash /fixture\\ root/.agents/skills/ains-ship/scripts/check.sh'
        self.assertEqual(self.classify(escaped)['loads'], [])
        command = 'bash "/fixture/.agents/skills/ains-ship/scripts/check.sh unrelated"'
        result = self.classify(command, self.sources['ains-ship/scripts/check.sh'], 1)
        self.assertIn('source-correlated', result['loads'][0]['classification'])

    def test_exact_registered_spaced_helper_identity_through_codex(self):
        for relative in ['scripts/check.sh', 'scripts/check tool.sh',
                         'scripts/check.sh unrelated', 'scripts/check.sh ']:
            self.sources = {'ains-ship/' + relative: '#!/bin/sh\n# Exact synthetic shipping helper\nexit 0\n'}
            for alias in ['.claude', '.agents']:
                for prefix in ['', 'bash ']:
                    for quote in ['"', "'"]:
                        path = '/fixture root with spaces/' + alias + '/skills/ains-ship/' + relative
                        command = prefix + quote + path + quote + ' --mode strict'
                        with self.subTest(command=command):
                            self.assertEqual(len(self.classify(command, 'No errors found.')['loads']), 1)

    def test_started_only_or_unpaired_completion_cannot_prove_helper_execution(self):
        events = paired('bash /fixture/.claude/skills/ains-ship/scripts/check.sh')
        self.assertEqual(self.ns['manual_access'](self.record(events[:1]), self.sources)['loads'], [])
        incomplete = copy.deepcopy(events[-1]); incomplete['item'].pop('command')
        self.assertEqual(self.ns['manual_access'](self.record([incomplete]), self.sources)['loads'], [])


if __name__ == '__main__':
    unittest.main()
