"""Recovery producer/dispatcher model-zero tests; no native process or claim."""
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import postclosure_recovery as core
import postclosure_recovery_operator as op
import postclosure_recovery_controller as controller


class Clock:
    def __init__(self, now=0):
        self.now = now
        self.sequence = 0

    def __call__(self):
        return self.now

    def ns(self):
        self.sequence += 1
        return self.sequence


class MockIO:
    def __init__(self, clock, frames):
        self.clock, self.frames = clock, list(frames)
        self.deadlines, self.writes = [], []

    def read(self, deadline):
        self.deadlines.append(deadline)
        if not self.frames or self.frames[0][0] >= deadline:
            self.clock.now = deadline
            raise TimeoutError('simulated transport deadline')
        at, frame = self.frames.pop(0)
        self.clock.now = at
        if isinstance(frame, BaseException):
            raise frame
        return (json.dumps(frame) + '\n').encode()

    def write(self, data, deadline):
        self.writes.append(json.loads(data))


def terminal(thread='thread-1', status='completed'):
    return {'method': 'turn/completed', 'params': {
        'threadId': thread, 'turn': {'id': 'turn-1', 'status': status}}}


class RecoveryWaitTests(unittest.TestCase):
    def rpc(self, frames=(), now=0, hard_deadline=178):
        clock = Clock(now)
        transport = MockIO(clock, frames)
        rpc = op.RecordingRPC(transport, hard_deadline, clock=clock, monotonic_ns=clock.ns)
        rpc.thread_id, rpc.turn_id, rpc.dispatched = 'thread-1', 'turn-1', True
        return rpc, transport, clock

    def test_silent_90_seconds_finishes_with_original_closing_reserve(self):
        rpc, transport, clock = self.rpc([(119.581, terminal())], now=29.581)
        op.await_terminal(rpc, 178, clock)
        self.assertEqual(transport.deadlines, [178])
        self.assertEqual(clock.now, 119.581)
        self.assertTrue(rpc.completed)
        self.assertFalse(rpc.failed)
        self.assertTrue(core.load_legacy().healthy_terminal(rpc.events, 'live'))

    def test_progress_never_extends_the_original_work_deadline(self):
        progress = {'method': 'turn/started', 'params': {
            'threadId': 'thread-1', 'turn': {'id': 'turn-1', 'status': 'inProgress'}}}
        rpc, transport, clock = self.rpc([(20, progress), (100, progress),
                                         (177, progress), (179, terminal())])
        with self.assertRaises(TimeoutError):
            op.await_terminal(rpc, 178, clock)
        self.assertEqual(transport.deadlines, [178] * 4)
        self.assertEqual(clock.now, 178)
        self.assertFalse(rpc.completed)

    def test_rpc_hard_deadline_clamps_a_later_caller_deadline(self):
        rpc, transport, clock = self.rpc([(150, terminal())], hard_deadline=120)
        with self.assertRaises(TimeoutError):
            op.await_terminal(rpc, 178, clock)
        self.assertEqual(transport.deadlines, [120])

    def test_transport_and_foreign_terminal_fail_without_second_input(self):
        for frame in (EOFError('simulated EOF'), terminal(thread='foreign'),
                      terminal(status='failed')):
            with self.subTest(frame=type(frame).__name__):
                rpc, transport, clock = self.rpc([(10, frame), (11, terminal())])
                with self.assertRaises((EOFError, core.Hold)):
                    op.await_terminal(rpc, 178, clock)
                with self.assertRaises(core.Hold):
                    rpc.send('turn/start', {'threadId': 'thread-1',
                                           'input': [{'type': 'text', 'text': 'forbidden retry'}]})
                self.assertEqual(len(transport.frames), 1)
                self.assertEqual(transport.writes, [])

    def test_expired_deadline_does_not_read_or_dispatch(self):
        rpc, transport, clock = self.rpc(now=178)
        with self.assertRaises(TimeoutError):
            op.await_terminal(rpc, 178, clock)
        self.assertEqual(transport.deadlines, [])
        self.assertEqual(transport.writes, [])


class RecoveryControllerTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {'PATH': '/fixture/bin',
                                               'CODEX_TOOL_CALL_ID': 'new-epoch-owner'}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.command = {'path': str(core.CONTROL_ROOT / 'MOCK-only.json'), 'sha256': '0' * 64}

    def request(self, ident, operation='execute', command=None):
        return {'id': ident, 'operation': operation,
                'command': self.command if command is None else command}

    def serve(self, requests, execute, lookup=None):
        source = io.BytesIO(b''.join((json.dumps(value) + '\n').encode() for value in requests))
        output = io.StringIO()
        code = controller.serve(source, output, execute=execute,
                                lookup=execute if lookup is None else lookup)
        return code, [json.loads(line) for line in output.getvalue().splitlines()]

    def test_failed_charged_business_result_stops_before_next_user(self):
        calls = []
        def execute(command, digest):
            calls.append((command, digest))
            return {'failure': {'primary': {'stage': 'turn-in-flight'}},
                    'accounting': {'attempted': 1, 'actual': 1, 'charged': 1}}
        code, output = self.serve([self.request('one'), self.request('two')], execute)
        self.assertEqual(code, 1)
        self.assertEqual(calls, [(self.command, self.command['sha256'])])
        self.assertEqual(output[-1]['state'], 'FAILED')
        self.assertEqual(output[-1]['accounting']['charged'], 1)
        self.assertIs(output[-1]['business_PASS'], False)

    def test_lookup_then_execute_keeps_exact_environment_and_current_identity(self):
        environments = []
        def lookup(command, digest):
            environments.append(dict(os.environ))
            self.assertEqual((command, digest), (self.command, self.command['sha256']))
            return {'USER': 0, 'native_facts': {'failure': None, 'invariant_candidate': None}}
        def execute(command, digest):
            environments.append(dict(os.environ))
            return {'failure': None, 'accounting': {'actual': 1, 'charged': 1}}
        code, output = self.serve([self.request('lookup', 'lookup'), self.request('execute'),
                                   {'id': 'stop', 'operation': 'stop'}], execute, lookup)
        self.assertEqual(code, 0)
        self.assertEqual(environments[0], environments[1])
        self.assertEqual(output[0]['environment_sha256'], core.canonical_hash(environments[0]))
        self.assertEqual(output[0]['controller_sha256'],
                         hashlib.sha256(Path(controller.__file__).read_bytes()).hexdigest())
        self.assertEqual([entry['state'] for entry in output],
                         ['READY', 'COMPLETED', 'COMPLETED', 'STOPPED'])

    def test_old_control_path_cannot_reach_recovery_producer(self):
        old = {'path': str(core.CONTROL_ROOT.parent / 'old-release.json'), 'sha256': '0' * 64}
        calls = []
        code, output = self.serve([self.request('old', command=old)],
                                  lambda *args: calls.append(args))
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])
        self.assertEqual(output[-1]['diagnostic']['chain'][0]['reason'],
                         'Root command outside current C')

    def test_environment_change_stops_before_following_operation(self):
        calls = []
        def execute(command, digest):
            calls.append(command)
            os.environ['CODEX_TOOL_CALL_ID'] = 'changed-owner'
            return {'failure': None, 'accounting': {'actual': 1, 'charged': 1}}
        code, output = self.serve([self.request('one'), self.request('two')], execute)
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(output[-1]['diagnostic']['chain'][0]['reason'], 'Root environment drift')

    def test_duplicate_id_or_exception_never_retries(self):
        calls = []
        def execute(command, digest):
            calls.append(command)
            return {'failure': None, 'accounting': {'actual': 1, 'charged': 1}}
        code, _ = self.serve([self.request('same'), self.request('same')], execute)
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 1)
        calls.clear()
        def fail(command, digest):
            calls.append(command)
            raise OSError('PRIVATE_CANARY')
        code, output = self.serve([self.request('one'), self.request('two')], fail)
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 1)
        self.assertNotIn('PRIVATE_CANARY', json.dumps(output))
        self.assertEqual(output[-1]['diagnostic']['chain'][0]['exception_type'], 'OSError')


class RecoverySourceTests(unittest.TestCase):
    def test_explicit_operator_delta_is_only_import_doc_and_absolute_wait(self):
        original = Path(op.__file__).with_name('postclosure_operator.py').read_text()
        expected = original.replace('"""One-context D2 operator.',
                                    '"""One-context D2 recovery operator.', 1)
        expected = expected.replace('import postclosure as core',
                                    'import postclosure_recovery as core\nfrom postclosure_deadline import await_terminal', 1)
        expected = expected.replace('            while not rpc.completed:\n                rpc.receive()',
                                    '            await_terminal(rpc, work_deadline, time.monotonic)', 1)
        self.assertEqual(Path(op.__file__).read_text(), expected)
        tree = ast.parse(expected)
        runner = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                      and node.name == 'run_released')
        self.assertEqual(sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                             and node.func.id == 'await_terminal' for node in ast.walk(runner)), 1)

    def test_current_modules_use_new_core_and_natural_source_identity(self):
        self.assertIs(op.core, core)
        self.assertIs(controller.core, core)
        self.assertIs(controller.operator, op)
        self.assertEqual(controller.SOURCE, Path(controller.__file__).resolve().parents[3])
        self.assertEqual(core.SOURCE, controller.SOURCE)
        self.assertEqual(Path(op.__file__).name, 'postclosure_recovery_operator.py')
        self.assertEqual(Path(controller.__file__).name, 'postclosure_recovery_controller.py')

    def test_all_original_eleven_source_pins_unchanged(self):
        source_set = json.loads((core.CONTROL_ROOT.parent /
            'postclosure-controller-preparation-r2/source-set-DATA.json').read_text())
        self.assertEqual(len(source_set['files']), 11)
        for expected in source_set['files']:
            with self.subTest(path=expected['path']):
                path = Path(expected['path'])
                info = path.stat()
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected['sha256'])
                self.assertEqual(info.st_size, expected['size'])
                self.assertEqual(oct(info.st_mode & 0o777), expected['mode'])
                self.assertEqual(info.st_nlink, expected['nlink'])

    def test_no_argument_cli_is_inert(self):
        with patch.object(op, 'run_released') as execute, patch.object(op, 'produce_lookup') as lookup:
            with patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(op.main([]), 0)
            execute.assert_not_called()
            lookup.assert_not_called()


if __name__ == '__main__':
    unittest.main()
