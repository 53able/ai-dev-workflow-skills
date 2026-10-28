"""Fresh synthetic-only fake-IO tests; no process, PTY, model or Root writes."""
import base64
import contextlib
import copy
import hashlib
import importlib.util
import io
from pathlib import Path
import socket
import struct
import sys
import unittest
from unittest.mock import patch


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


c = load('question_contract')
o = load('question_operator')
r = load('question_relay')
ROOT = '/root/protected'
REF = {'path': '/root/protected/.omx/c/decision', 'sha256': 'a' * 64}
META = {'generation': 'tui-1', 'direction': r.CLIENT}
HISTORY = {v: 'unused' for v in c.DONORS.values()}


class Clock:
    def __init__(self):
        self.now = 1.0
    def __call__(self):
        return self.now


class Store:
    def __init__(self):
        self.rows = {}
    def create_once(self, key, value):
        c.require(key not in self.rows, 'preexisting lifetime claim')
        self.rows[key] = value


class Backend:
    def __init__(self):
        self.events, self.output, self.written = [], bytearray(), bytearray()
        self.maximum_write = 2
    def start(self, deadline):
        self.events.append(('start', deadline))
    def persist_intent(self, raw):
        self.events.append(('intent', raw))
    def read_output(self, limit):
        result = bytes(self.output[:limit]); del self.output[:limit]
        return result
    def write_keys(self, raw):
        self.events.append(('keys', raw))
        count = min(len(raw), self.maximum_write)
        self.written.extend(raw[:count])
        return count
    def resize(self, rows, columns):
        self.events.append(('resize', rows, columns))
    def close_owned(self, deadline):
        self.events.append(('close', deadline))


class FakeSocket:
    family = socket.AF_UNIX
    def __init__(self):
        self.incoming, self.outgoing = bytearray(), bytearray()
        self.maximum_write = 1048576
    def setblocking(self, value):
        assert value is False
    def recv(self, limit):
        if not self.incoming:
            raise BlockingIOError
        data = bytes(self.incoming[:limit]); del self.incoming[:limit]
        return data
    def send(self, raw):
        count = min(len(raw), self.maximum_write)
        self.outgoing.extend(raw[:count])
        return count


def frame(value, client=True):
    raw = c.canonical(value)
    size = len(raw)
    header = b'\x81' + bytes([(128 if client else 0) | (size if size < 126 else 126)])
    if size >= 126:
        header += struct.pack('!H', size)
    if client:
        return header + b'abcd' + bytes(v ^ b'abcd'[i % 4] for i, v in enumerate(raw))
    return header + raw


def command_fixture():
    refs, raws = {}, {}
    for kind, dependencies in c.DEPENDENCIES.items():
        raw = c.canonical({'kind': 'N7-C-' + kind + '-v1',
                           'dependencies': {key: refs[key] for key in dependencies},
                           'payload': {'synthetic': True}})
        refs[kind] = {'path': ROOT + '/.omx/ctrl/' + kind,
                      'sha256': hashlib.sha256(raw).hexdigest()}
        raws[kind] = raw
    command = {'kind': 'N7-C-launch-v1', 'continuation': ROOT + '/' + c.CONTINUATION,
               'control_root': ROOT + '/.omx/ctrl',
               'output_root': ROOT + '/' + c.CONTINUATION + '/fresh',
               'contexts': ['default', 'copy'], 'donors': dict(c.DONORS),
               'history': {'complete_history': True, 'aliases': [], 'donors': dict(HISTORY)},
               'records': refs, 'limits': {'contexts': 2, 'inputs_per_context': 2, 'seconds': 180},
               'business_PASS': False}
    return command, raws


def gate_fixture(first):
    return {'native13': {key: None for key in o.NATIVE13}, 'tui_instructions': 'actual native extra instructions',
            'first_envelope': first, 'B1_first': {'raw': 'same'}, 'B1_second': {'raw': 'same'},
            'installed16': [{'path': '/installed/enabled/' + str(i), 'sha256': 'b' * 64} for i in range(16)],
            'installed42': [{'path': '/installed/all/' + str(i), 'sha256': 'c' * 64} for i in range(42)],
            'fixture': REF, 'process': REF, 'source_review': REF, 'async_capability': REF}


class Fixture:
    def __init__(self):
        self.clock, self.store, self.backend = Clock(), Store(), Backend()
        self.operator = o.SyntheticOperator('default', self.clock, c.Claims(self.store, HISTORY), self.backend)
        self.operator.start()
        self.client, self.server = FakeSocket(), FakeSocket()
        self.guard = o.NativeGuard('tui-1', [{'method': 'thread/start', 'params': {'cwd': '/fixture'}, 'request': True}],
                                   {'threadId': 'thread-1', 'input': [{'type': 'text', 'text': '$ains-setup'}]})
        self.relay = r.Relay(self.client, self.server, generation='tui-1', startup_methods={'thread/start'},
                             deadline=self.operator.deadline.end, clock=self.clock, client_guard=self.guard)
        self.operator.attach(self.relay, self.guard)
        self.key = b'MDEyMzQ1Njc4OWFiY2RlZg=='
        self.client.incoming.extend(b'GET /native HTTP/1.1\r\nHost: own\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: ' + self.key + b'\r\n\r\n')
        self.operator.step()
        accept = base64.b64encode(hashlib.sha1(self.key + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())
        self.server.incoming.extend(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + accept + b'\r\n\r\n')
        self.operator.step()
        self.send({'id': 1, 'method': 'thread/start', 'params': {'cwd': '/fixture'}})
        self.first = {'id': 2, 'method': 'turn/start', 'params': dict(self.guard.first_params, clientUserMessageId='native-first')}
        self.send(self.first)
        self.gate = o.FirstGate(gate_fixture(self.first))

    def send(self, value):
        self.client.incoming.extend(frame(value))
        self.operator.step()

    def release(self):
        self.operator.release_first(self.gate, {'raw': 'same'}, self.gate.proof['native13'], self.gate.proof['tui_instructions'])
        self.operator.step()
        self.guard.active_turn = 'turn-1'

    def decision(self):
        receipt = {'capture_sha256': self.operator.capture.cut(),
                   'questions': [{'id': 'q' + str(i), 'title': 'Actual ' + str(i), 'options': ['A', 'B']} for i in range(3)],
                   'visited': [0, 1, 2], 'all_unanswered': True, 'first_fixture_question': 'q0',
                   'active_turn': 'turn-1', 'generation': 'tui-1'}
        decision = {'ref': REF, 'question_id': 'q0', 'value': 'A', 'receipt_sha256': c.digest(receipt)}
        return decision, receipt

    def arm(self, keys=b'enter'):
        decision, receipt = self.decision()
        self.answer_input = [{'type': 'text', 'text': 'SYNTHETIC native fragment q0/Actual 0/A'}]
        matcher = self.guard.answer_matcher(decision_ref=REF, question_id='q0', question_title='Actual 0', selected='A',
                                           exact_input=self.answer_input, exact_start_settings={}, active_turn='turn-1')
        self.operator.choose(decision, receipt, matcher, keys)

    def answer(self):
        return {'id': 3, 'method': 'turn/steer', 'params': {
            'threadId': 'thread-1', 'expectedTurnId': 'turn-1', 'clientUserMessageId': 'native-answer',
            'input': self.answer_input, 'responsesapiClientMetadata': None,
            'responsesapiClientMetadataPatch': None, 'additionalContext': None}}


class ContractTests(unittest.TestCase):
    def test_closed_dag_is_structural_only(self):
        command, records = command_fixture()
        self.assertFalse(c.validate_command(command, c.digest(command), ROOT, records)['runtime_admitted'])

    def test_unknown_command_fields_fail(self):
        command, records = command_fixture(); command['authority'] = True
        with self.assertRaises(c.Hold): c.validate_command(command, c.digest(command), ROOT, records)

    def test_external_pin_required(self):
        command, records = command_fixture()
        with self.assertRaises(c.Hold): c.validate_command(command, '0' * 64, ROOT, records)

    def test_each_fixed_donor_and_mode_is_enforced(self):
        for field, value in [('contexts', ['default', 'copy', 'retry']), ('donors', {}),
                             ('limits', {'contexts': 4}), ('business_PASS', True)]:
            command, records = command_fixture(); command[field] = value
            with self.subTest(field=field), self.assertRaises(c.Hold):
                c.validate_command(command, c.digest(command), ROOT, records)

    def test_history_spent_unknown_and_incomplete_fail(self):
        for status in ('spent', 'reserved', 'unknown'):
            command, records = command_fixture(); command['history']['donors']['R7/tasks/5'] = status
            with self.assertRaises(c.Hold): c.validate_command(command, c.digest(command), ROOT, records)
        command, records = command_fixture(); command['history']['complete_history'] = False
        with self.assertRaises(c.Hold): c.validate_command(command, c.digest(command), ROOT, records)

    def test_source_drift_and_dag_cycle_rejected(self):
        command, records = command_fixture(); records['source'] += b' '
        with self.assertRaises(c.Hold): c.validate_command(command, c.digest(command), ROOT, records)
        command, records = command_fixture()
        raw = c.canonical({'kind': 'N7-C-source-v1', 'dependencies': {'decision': command['records']['decision']}, 'payload': {'x': 1}})
        records['source'] = raw; command['records']['source']['sha256'] = hashlib.sha256(raw).hexdigest()
        with self.assertRaises(c.Hold): c.validate_command(command, c.digest(command), ROOT, records)

    def test_claims_do_not_reset_by_new_instance_or_output(self):
        store = Store(); first = c.Claims(store, HISTORY); first.context('default'); first.input('default', 'first')
        second = c.Claims(store, HISTORY)
        with self.assertRaises(c.Hold): second.context('default')
        with self.assertRaises(c.Hold): second.input('default', 'first')
        second.context('copy'); second.input('copy', 'first')
        self.assertEqual(store.rows['N7-C/default/first']['donor'], 'R7/tasks/5')

    def test_duplicate_nonfinite_and_boolean_ids_fail(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'\xff'):
            with self.assertRaises(c.Hold): c.loads(raw)
        with self.assertRaises(c.Hold): c.typed_id(True)
        self.assertNotEqual(c.typed_id(1), c.typed_id('1'))

    def test_deadline_includes_startup_and_closure(self):
        clock = Clock(); deadline = c.Deadline(clock); clock.now = 181
        with self.assertRaises(c.Hold): deadline.check()
        clock = Clock(); deadline = c.Deadline(clock); clock.now = 0
        with self.assertRaises(c.Hold): deadline.check()

    def test_protected_paths_and_short_sockets(self):
        kwargs = dict(root='/r', control='/r/.omx/c', output='/r/' + c.CONTINUATION + '/out',
                      fixture='/f', writable=['/f'], sockets=['/r/.omx/c/a', '/r/.omx/c/b'])
        c.validate_paths(**kwargs)
        for update in ({'writable': ['/r']}, {'sockets': ['/tmp/a', '/tmp/b']},
                       {'sockets': ['/r/.omx/c/' + 'a' * 100, '/r/.omx/c/b']},
                       {'output': '/f/out'}, {'sockets': ['/r/.omx/c/a'] }):
            with self.subTest(update=update), self.assertRaises(c.Hold): c.validate_paths(**dict(kwargs, **update))

    def test_exact_retention_profile_rejects_unknown_or_credential_shapes(self):
        safe = {'account': None, 'requiresOpenaiAuth': False}
        profile = {'schema': REF, 'review': REF, 'config_sha256': 'a' * 64,
                   'messages': [{'method': 'account/read', 'request': {'refreshToken': False}, 'response_sha256': c.digest(safe)}]}
        guard = c.RawRetention(profile)
        self.assertTrue(guard.classify('account/read', {'refreshToken': False}, safe, 'a' * 64))
        for value in ({**safe, 'token': 'secret'}, {'error': {'message': 'unsafe unclassified'}}, {'account': 'unknown'}):
            with self.assertRaises(c.Hold): guard.classify('account/read', {'refreshToken': False}, value, 'a' * 64)
        with self.assertRaises(c.Hold): guard.classify('account/read', {'refreshToken': False}, safe, 'b' * 64)
        profile['messages'][0]['request']['refreshToken'] = True
        with self.assertRaises(c.Hold): c.RawRetention(profile)
        profile['messages'][0]['method'] = 'account/login/start'
        with self.assertRaises(c.Hold): c.RawRetention(profile)


class OperatorTests(unittest.TestCase):
    def test_inert_default_and_missing_execute_pin(self):
        with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(o.main([]), 0)
        with contextlib.redirect_stderr(io.StringIO()): self.assertEqual(o.main(['--execute']), 2)
        self.assertFalse(o.SyntheticOperator.runtime_admitted)
        self.assertNotIn('subprocess', o.__dict__)
        self.assertNotIn('pty', o.__dict__)

    def test_execute_remains_blocked_even_with_structural_records(self):
        command, records = command_fixture(); command_ref = {'path': ROOT + '/.omx/ctrl/command', 'sha256': c.digest(command)}
        def read(reference):
            return c.canonical(command) if reference == command_ref else records[next(k for k, v in command['records'].items() if v == reference)]
        with patch.object(o, 'read_ref', side_effect=read):
            self.assertEqual(o.run_released(command_ref, command_ref['sha256'], validate_only=True)['status'], 'STRUCTURAL_ONLY')
            with self.assertRaisesRegex(c.Hold, 'execution unavailable'):
                o.run_released(command_ref, command_ref['sha256'])

    def test_foreign_DAG_reference_rejected_before_open(self):
        command, _ = command_fixture()
        command['records']['profile']['path'] = '/unrelated/auth.json'
        reference = {'path': ROOT + '/.omx/ctrl/command', 'sha256': c.digest(command)}
        with patch.object(o, 'read_ref', return_value=c.canonical(command)) as read:
            with self.assertRaises(c.Hold):
                o.run_released(reference, reference['sha256'], validate_only=True)
            self.assertEqual(read.call_count, 1)

    def test_full_initial_gate_and_claim_before_egress(self):
        f = Fixture(); before = bytes(f.server.outgoing)
        self.assertNotIn(frame(f.first), before)
        f.release()
        self.assertIn('N7-C/default/first', f.store.rows)
        self.assertEqual(bytes(f.server.outgoing)[len(before):], frame(f.first))

    def test_server_lifecycle_keeps_flowing_while_root_waits(self):
        f = Fixture(); before = bytes(f.client.outgoing)
        terminal = frame({'method': 'turn/completed', 'params': {'turnId': 'turn-1'}}, client=False)
        f.server.incoming.extend(terminal); f.operator.step()
        self.assertEqual(bytes(f.client.outgoing)[len(before):], terminal)
        self.assertIsNotNone(f.relay.pending)

    def test_B1_drift_permanently_closes_and_reservation_not_refunded(self):
        f = Fixture()
        with self.assertRaises(c.Hold): f.operator.release_first(f.gate, {'raw': 'changed'}, f.gate.proof['native13'], f.gate.proof['tui_instructions'])
        with self.assertRaises(c.Hold): f.gate.check({'raw': 'same'})
        self.assertIn('N7-C/default/first', f.store.rows)
        self.assertFalse(f.relay.first_released)

    def test_native13_instructions_and_entire_USER_required(self):
        for change in ('native13', 'instructions', 'input'):
            f = Fixture()
            if change == 'native13':
                actual = dict(f.gate.proof['native13']); del actual['instructionSources']
                args = (actual, f.gate.proof['tui_instructions'])
            elif change == 'instructions': args = (f.gate.proof['native13'], '')
            else:
                f.gate.proof['first_envelope']['params']['input'].append({'type': 'text', 'text': 'hidden'})
                args = (f.gate.proof['native13'], f.gate.proof['tui_instructions'])
            with self.subTest(change=change), self.assertRaises(c.Hold):
                f.operator.release_first(f.gate, {'raw': 'same'}, *args)

    def test_one_genuine_decision_intent_before_partial_key_writes(self):
        f = Fixture(); f.release(); f.arm()
        self.assertEqual(f.operator.accounting['owner_decisions'], 1)
        for _ in range(3): f.operator.step()
        self.assertEqual(f.backend.written, b'enter')
        self.assertEqual([x[0] for x in f.backend.events], ['start', 'intent', 'keys', 'keys', 'keys'])
        f.send(f.answer())
        self.assertTrue(f.relay.answer_used)
        self.assertEqual(len(f.guard.attempts), 2)
        self.assertEqual(f.operator.accounting['accepted_steers'], [])
        with self.assertRaises(c.Hold): f.operator.choose(*f.decision(), lambda *_: True, b'enter')

    def test_native_retry_blocked_preserves_both_attempts_one_decision(self):
        f = Fixture(); f.release(); f.arm(); f.send(f.answer()); before = bytes(f.server.outgoing)
        retry = f.answer(); retry['id'] = 4; retry['params']['clientUserMessageId'] = 'native-retry'
        with self.assertRaises(r.Hold): f.send(retry)
        self.assertEqual(bytes(f.server.outgoing), before)
        self.assertEqual(len(f.guard.attempts), 3)
        self.assertEqual(f.operator.accounting['owner_decisions'], 1)
        self.assertEqual(len(f.operator.accounting['native_attempts']), 3)

    def test_hidden_context_wrong_thread_turn_and_input_fail_before_egress(self):
        for field, value in [('additionalContext', {'hidden': True}), ('threadId', 'other'),
                             ('expectedTurnId', 'stale'), ('input', [{'type': 'text', 'text': 'other'}])]:
            f = Fixture(); f.release(); f.arm(); answer = f.answer(); answer['params'][field] = value
            before = bytes(f.server.outgoing)
            with self.subTest(field=field), self.assertRaises(r.Hold): f.send(answer)
            self.assertEqual(bytes(f.server.outgoing), before)
            self.assertTrue(f.relay.answer_used)

    def test_lifecycle_completion_rejects_late_choice_and_matcher(self):
        f = Fixture(); f.release(); f.guard.terminal = True
        with self.assertRaises(c.Hold): f.arm()
        f = Fixture(); f.release(); f.arm(); f.guard.active_turn = 'changed'
        with self.assertRaises(r.Hold): f.send(f.answer())

    def test_stale_incomplete_or_foreign_question_receipts_rejected(self):
        for field, value in [('visited', [0, 1]), ('visited', [False, True, 2]), ('all_unanswered', False), ('generation', 'observer-1'),
                             ('active_turn', 'stale'), ('capture_sha256', '0' * 64)]:
            f = Fixture(); f.release(); decision, receipt = f.decision(); receipt[field] = value
            with self.subTest(field=field), self.assertRaises(c.Hold):
                f.operator.choose(decision, receipt, lambda *_: True, b'enter')
            self.assertNotIn('N7-C/default/answer', f.store.rows)
            self.assertFalse(f.backend.written)

    def test_unknown_startup_fields_and_account_refresh_rejected(self):
        with self.assertRaises(c.Hold): o.NativeGuard('t', [{'method': 'account/read', 'params': {'refreshToken': True}, 'request': True}], {})
        f = Fixture()
        with self.assertRaises(c.Hold): f.guard({'id': 8, 'method': 'config/write', 'params': {}}, META)

    def test_observer_cannot_dispatch_answer_or_reuse_native_generation(self):
        guard = o.ObserverGuard('observer-1', [{'method': 'model/list', 'params': {}}])
        value = {'id': 1, 'method': 'model/list', 'params': {}}
        with self.assertRaises(c.Hold): guard(value, META)
        self.assertTrue(guard(value, {'generation': 'observer-1', 'direction': r.CLIENT}))
        for value in ({'id': 2, 'method': 'turn/start', 'params': {}}, {'id': 3, 'result': {}}):
            with self.assertRaises(c.Hold): guard(value, {'generation': 'observer-1', 'direction': r.CLIENT})
        with self.assertRaises(c.Hold): o.ObserverGuard('o', [{'method': 'thread/start', 'params': {}}])

    def test_duplicate_connection_and_deadline_extension_rejected(self):
        f = Fixture()
        with self.assertRaises(c.Hold): f.operator.attach(f.relay, f.guard)
        f = Fixture(); f.relay.deadline += 1; f.operator.relay = None
        with self.assertRaises(c.Hold): f.operator.attach(f.relay, f.guard)

    def test_capture_bounds_partial_key_write_and_resize_receipts(self):
        f = Fixture(); f.operator.resize(40, 120)
        self.assertEqual([r['kind'] for r in f.operator.capture.records], ['resize-intent', 'resize-applied'])
        capture = o.Capture(f.operator.deadline, byte_limit=2, record_limit=2)
        capture.add('pty-output', b'ab')
        with self.assertRaises(c.Hold): capture.add('pty-output', b'c')
        with self.assertRaises(c.Hold): f.operator.resize(True, 120)

    def test_capture_detail_counts_against_total_memory_bound(self):
        f = Fixture()
        capture = o.Capture(f.operator.deadline, byte_limit=2)
        with self.assertRaises(c.Hold): capture.add('event', detail={'large': 'x'})
        self.assertEqual(capture.records, [])

    def test_foreign_guard_and_observer_connection_rejected(self):
        f = Fixture(); f.operator.relay = None
        foreign = o.NativeGuard('different', [{'method': 'thread/start', 'params': {}, 'request': True}],
                                {'threadId': 't', 'input': []})
        with self.assertRaises(c.Hold): f.operator.attach(f.relay, foreign)
        f = Fixture(); f.operator.relay = None
        observer = r.Relay(FakeSocket(), FakeSocket(), generation='tui-1',
                           startup_methods={'model/list'}, deadline=f.operator.deadline.end,
                           clock=f.clock, client_guard=o.ObserverGuard('tui-1', []))
        with self.assertRaises(c.Hold): f.operator.attach(f.relay, f.guard, observer)

    def test_deadline_startup_output_and_cleanup_cannot_extend(self):
        f = Fixture(); f.clock.now = f.operator.deadline.end
        with self.assertRaises(c.Hold): f.operator.step()
        with self.assertRaises(c.Hold): f.operator.close()
        clock, backend = Clock(), Backend()
        def slow_start(deadline): clock.now = deadline
        backend.start = slow_start
        operator = o.SyntheticOperator('copy', clock, c.Claims(Store(), HISTORY), backend)
        with self.assertRaises(c.Hold): operator.start()

    def test_race_stops_and_does_not_refund(self):
        f = Fixture(); f.release(); f.arm()
        with self.assertRaises(c.Hold): f.operator.observe_race({'error': 'expected-turn-mismatch'})
        self.assertTrue(f.operator.failed)
        self.assertIn('N7-C/default/answer', f.store.rows)
        self.assertEqual(len(f.operator.accounting['races']), 1)

    def test_closure_never_claims_business_pass_or_model_usage(self):
        f = Fixture(); f.release(); result = f.operator.close()
        self.assertEqual(result['N7'], 'UNVERIFIED')
        self.assertFalse(result['business_PASS'])
        self.assertIsNone(result['accounting']['provider_usage'])
        self.assertEqual(result['accounting']['accepted_starts'], [])


if __name__ == '__main__':
    unittest.main()
