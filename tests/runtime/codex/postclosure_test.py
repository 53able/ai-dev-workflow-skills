#!/usr/bin/env python3
"""Model-free successor regression tests using fresh real inventories/mock IO."""
import contextlib
import copy
import importlib.util
import io
import json
import marshal
import os
from pathlib import Path
import shutil
import shlex
import struct
import sys
import tomllib
import tempfile
import time
import unittest
from unittest import mock

import postclosure as c
import postclosure_operator as op


class MockTransport:
    pid = 123

    def __init__(self, responses=(), write_error=None):
        self.responses = list(responses)
        self.writes = []
        self.write_error = write_error

    def write(self, data, deadline):
        self.writes.append(data)
        if self.write_error:
            raise self.write_error

    def read(self, deadline):
        if not self.responses:
            raise EOFError('mock EOF')
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value if type(value) is bytes else (json.dumps(value) + '\n').encode()

    def drain(self, deadline):
        values, self.responses = self.responses, []
        return [(json.dumps(x) + '\n').encode() for x in values]


class MockNativeTransport(MockTransport):
    def __init__(self, config, catalog, thread, on_turn=None, on_close=None):
        super().__init__()
        self.config, self.catalog, self.thread = config, catalog, thread
        self.on_turn, self.on_close = on_turn, on_close

    def write(self, data, deadline):
        self.writes.append(data)
        request = json.loads(data)
        if 'id' not in request:
            return
        method = request['method']
        results = {'initialize': {}, 'config/read': self.config, 'skills/list': self.catalog,
                   'thread/start': self.thread, 'turn/start': {'turn': {'id': 'MOCK-turn'}}}
        self.responses.append({'id': request['id'], 'result': results[method]})
        if method == 'turn/start':
            if self.on_turn:
                self.on_turn()
            thread_id = self.thread['thread']['id']
            self.responses.extend([
                {'method': 'turn/started', 'params': {'threadId': thread_id, 'turn': {'id': 'MOCK-turn', 'status': 'inProgress'}}},
                {'method': 'item/started', 'params': {'threadId': thread_id, 'turnId': 'MOCK-turn',
                 'item': {'type': 'agentMessage', 'id': 'MOCK-final', 'phase': 'final_answer', 'text': ''}}},
                {'method': 'item/completed', 'params': {'threadId': thread_id, 'turnId': 'MOCK-turn',
                 'item': {'type': 'agentMessage', 'id': 'MOCK-final', 'phase': 'final_answer', 'text': 'MOCK fixture approved'}}},
                {'method': 'turn/completed', 'params': {'threadId': thread_id,
                 'turn': {'id': 'MOCK-turn', 'status': 'completed'}}},
            ])

    def close(self):
        if self.on_close:
            self.on_close()
        return {'reaped': True, 'returncode': -15, 'stderr_sha256': c.digest(b''), 'stderr_bytes': 0,
                'partial_stdout_bytes': 0, 'tail_frames': [], 'watchdog_fired': False, 'watchdog_error': None}


class TempCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='postclosure-own-')
        self.root = Path(self.temporary.name).resolve()

    def tearDown(self):
        self.temporary.cleanup()

    def save(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return c.ref(path)

    def text(self, name, value='proof'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        return c.ref(path)

    def plan(self, row='D2-tail/spec-approval'):
        placeholder = self.text('placeholder')
        return {'schema': 'postclosure-row-plan-v1', 'branch_id': 'fresh-D2',
                'row_id': row, 'donor_slot': c.ROWS[row], 'scope': placeholder, 'predecessor': placeholder,
                'predecessor_review': placeholder, 'contract': placeholder, 'input': placeholder, 'source_set': placeholder,
                'admission': placeholder, 'output': str(self.root / 'out'),
                'claim': str(c.claim_path('fresh-D2', row, self.root)), 'limits': dict(c.LIMITS), 'feasibility': None}


class RecordTests(TempCase):
    def test_duplicate_json_and_nonfinite_rejected(self):
        for raw in ('{"x":1,"x":2}', '{"a":{"x":1,"x":2}}', '{"a":NaN}', '{'):
            with self.subTest(raw=raw), self.assertRaises(c.Hold):
                c.decode(raw)

    def test_closed_schema_and_literal_limits(self):
        plan = self.plan()
        self.assertEqual(c.validate_record(plan), plan)
        for mutation in ({'extra': 1}, {'limits': {'contexts': True, 'USER': 1, 'seconds': 180}},
                         {'row_id': 'N7-B/default/first'}, {'donor_slot': 'BUILD4'}):
            with self.subTest(mutation=mutation), self.assertRaises(c.Hold):
                c.validate_record(dict(plan, **mutation))

    def test_exact_reference_hash_mode_and_size(self):
        path = self.root / 'source.py'
        path.write_text('x = 1\n')
        reference = c.ref(path, executable=True)
        self.assertEqual(c.read_ref(reference, executable=True), b'x = 1\n')
        for key, value in (('size', True), ('mode', '0o777'), ('sha256', '0' * 64)):
            with self.subTest(key=key), self.assertRaises(c.Hold):
                c.read_ref(dict(reference, **{key: value}), executable=True)
        path.write_text('x = 2\n')
        with self.assertRaises(c.Hold):
            c.read_ref(reference, executable=True)

    def test_path_normalization_symlink_hardlink(self):
        original = self.root / 'a'
        original.write_text('one')
        link = self.root / 'link'
        link.symlink_to(original)
        for path in (str(link), str(self.root) + '/./a', str(self.root) + '/../a'):
            with self.subTest(path=path), self.assertRaises(c.Hold):
                c.ref(path)
        os.link(original, self.root / 'hard')
        with self.assertRaises(c.Hold):
            c.ref(original)

    def test_current_legacy_import_and_helpers_are_exact(self):
        legacy = c.load_legacy()
        self.assertEqual(legacy.SOURCE, c.SOURCE)
        self.assertEqual(c.ref(c.HERE / 'native_delta.py')['sha256'], c.LEGACY_SHA)
        with c.bound_helpers(self.root / 'sink') as (_, (helpers, receipts)):
            self.assertEqual(helpers['runtime'].OUT, self.root / 'sink')
            self.assertEqual(len(receipts), 4)
            self.assertTrue(all(not item['function_bodies_changed'] for item in receipts))

    def test_safe_config_identity_provenance_and_no_secret_retention(self):
        legacy = c.load_legacy()
        identity = legacy.safe_config_identity({'api_key': 'private-canary', 'unknown': 1})
        retained = legacy.finite_receipt({'config': identity})
        self.assertNotIn('private-canary', json.dumps(retained))
        self.assertEqual(retained['config']['sha256'], identity['sha256'])
        identity['sha256'] = '0' * 64
        with self.assertRaises(RuntimeError):
            legacy.finite_receipt({'config': identity})

    def test_identity_survives_separate_load_calls_and_operator_save(self):
        first = c.load_legacy()
        identity = first.safe_config_identity({'instructionSources': ['/fixture/AGENTS.md'],
                                               'instructions': 'private model context', 'api_key': 'private-canary'})
        second = c.load_legacy()
        self.assertIs(first, second)
        expected = dict(identity)
        path = self.root / 'safe.json'
        op._save(path, {'config': identity})
        retained = json.loads(path.read_text())['config']
        self.assertEqual(retained, expected)
        self.assertEqual(retained['fields'], expected['fields'])
        self.assertNotIn('private-canary', path.read_text())

    def test_legacy_exact_47_and_order(self):
        prefix = {'schema': 'postclosure-legacy-prefix-v1', 'refs': [], 'prefix_sha256': '0' * 64,
                  'audit': self.text('audit'), 'expected_actual': 74, 'expected_held': 32, 'whole': 106, 'reserve': 1}
        with self.assertRaisesRegex(c.Hold, 'legacy47'):
            c.validate_legacy(prefix)
        prefix['refs'] = [{'path': str(self.root / str(i)), 'sha256': '0' * 64} for i in range(47)]
        with self.assertRaisesRegex(c.Hold, 'prefix order'):
            c.validate_legacy(prefix)

    def test_inert_main_and_data_not_authority(self):
        with mock.patch.object(op, 'ProcessTransport', side_effect=AssertionError('launch')), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(op.main([]), 0)
        for data in ({'approved': True}, {'schema': 'postclosure-root-review-v1'}):
            reference = self.save('fake.json', data)
            with self.assertRaises(c.Hold):
                c.validate_graph(reference, reference['sha256'])
        reference = self.save('wrong-hash.json', {'approved': True})
        with self.assertRaisesRegex(c.Hold, 'caller exact command'):
            c.validate_graph(reference, 'f' * 64)

    def test_claim_stable_across_release_and_failure(self):
        row = next(iter(c.ROWS))
        path = c.acquire_claim('branch', row, self.root, {'sha256': 'a' * 64})
        self.assertEqual(path, c.claim_path('branch', row, self.root))
        with self.assertRaises(FileExistsError):
            c.acquire_claim('branch', row, self.root, {'sha256': 'b' * 64})
        self.assertTrue(path.exists())

    def test_real_inventory_includes_empty_git_and_cache(self):
        (self.root / '.git').mkdir()
        (self.root / 'empty').mkdir()
        (self.root / '__pycache__').mkdir()
        (self.root / '__pycache__/old.pyc').write_bytes(b'old')
        state = c.inventory(self.root)
        self.assertEqual(state['empty']['kind'], 'directory')
        self.assertIn('.git', state)
        self.assertEqual(state['__pycache__/old.pyc']['sha256'], c.digest(b'old'))
        (self.root / 'escape').symlink_to(self.root.parent)
        with self.assertRaises(RuntimeError):
            c.inventory(self.root)


class PolicyTests(TempCase):
    def test_project_override_uses_native_single_key_and_toml_rhs(self):
        for name in ('D2 author root', 'D2.author root', 'D2 "quoted" 日本'):
            root = str(self.root / name)
            override = c.argv_for('/opt/homebrew/bin/codex', root)[-1]
            self.assertEqual(override.split('=', 1)[0], 'projects')
            self.assertEqual(tomllib.loads(override), {'projects': {root: {'trust_level': 'trusted'}}})
            self.assertIn('agents.enabled=false', c.argv_for('/opt/homebrew/bin/codex', root))
    def policy_data(self):
        root = str(self.root)
        scope = {'root': root, 'realroot': root}
        session = c.session_for(root)
        placeholder = self.text('policy-placeholder')
        policy = {'schema': 'postclosure-process-policy-v1', 'row_plan': placeholder, 'scope': placeholder,
                  'argv': [], 'session': session, 'session_sha256': c.canonical_hash(session),
                  'metadata_paths': {'p': {}}, 'native_expectation': placeholder, 'official_sources': [], 'turn_permission': None}
        metadata = {'name': {'type': 'sessionFlags'}, 'version': 'sha256:' + c.canonical_hash(session)}
        data = {'config': copy.deepcopy(session), 'layers': [
            {**metadata, 'config': copy.deepcopy(session), 'disabledReason': None},
            {'name': {'type': 'user', 'file': '/unchanged/user.toml'}, 'version': 'sha256:' + c.canonical_hash({}),
             'config': {}, 'disabledReason': None}],
            'origins': {'projects.' + root + '.trust_level': metadata, 'agents.enabled': metadata}}
        return scope, policy, data

    def test_actual_origin_layers_and_null_are_preserved(self):
        scope, policy, data = self.policy_data()
        first = c.policy_projection(data, policy, scope)
        data['config']['skills'] = None
        second = c.policy_projection(data, policy, scope)
        self.assertNotEqual(first, second)
        data['config']['skills'] = {'include_instructions': None}
        third = c.policy_projection(data, policy, scope)
        self.assertNotEqual(second, third)

    def test_effective_disabled_mcp_retains_inherited_fields_in_identity(self):
        scope, policy, data = self.policy_data()
        original = c.policy_projection(data, policy, scope)
        inherited = {'args': ['fixture-argument'], 'cwd': '/fixture/unchanged',
                     'env': {'FIXTURE_ONLY': 'nonsecret'}, 'env_vars': ['FIXTURE_ONLY'],
                     'environment_id': 'fixture', 'startup_timeout_sec': 15.0,
                     'tool_timeout_sec': None}
        for name in c.MCP:
            data['config']['mcp_servers'][name].update(copy.deepcopy(inherited))
        observed = c.policy_projection(data, policy, scope)
        self.assertNotEqual(original, observed)
        for name in c.MCP:
            for field, value in (('enabled', True), ('enabled', 0), ('command', '/fixture/other')):
                altered = copy.deepcopy(data)
                altered['config']['mcp_servers'][name][field] = value
                with self.subTest(name=name, field=field, value=value), self.assertRaises(c.Hold):
                    c.policy_projection(altered, policy, scope)

    def test_policy_negative_origins_layers_mcp_flags_and_persistent_trust(self):
        scope, policy, base = self.policy_data()
        mutations = []
        item = copy.deepcopy(base); item['origins'] = {}; mutations.append(item)
        item = copy.deepcopy(base); item['layers'].reverse(); mutations.append(item)
        item = copy.deepcopy(base); item['layers'][0]['version'] = 'sha256:' + '0' * 64; mutations.append(item)
        item = copy.deepcopy(base); item['config']['features']['hooks'] = 0; mutations.append(item)
        item = copy.deepcopy(base); item['config']['mcp_servers']['other'] = {}; mutations.append(item)
        item = copy.deepcopy(base); item['config']['skills'] = {'include_instructions': False}; mutations.append(item)
        item = copy.deepcopy(base)
        raw = {'projects': {scope['root']: {'trust_level': 'trusted'}}}
        item['layers'][1].update(config=raw, version='sha256:' + c.canonical_hash(raw)); mutations.append(item)
        for index, item in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises((c.Hold, RuntimeError)):
                c.policy_projection(item, policy, scope)

    def test_bundle_pairs_raw_not_just_redacted_and_baseline_never_resets(self):
        scope, policy, first = self.policy_data()
        second = copy.deepcopy(first)
        first['config']['api_key'] = 'canary-a'
        second['config']['api_key'] = 'canary-b'
        kwargs = dict(before={}, after={}, metadata_before=policy['metadata_paths'],
                      metadata_after=policy['metadata_paths'], policy=policy, scope=scope,
                      catalog_validator=lambda *_: {'enabled_unique_targets': 16, 'load_errors': 0})
        with self.assertRaisesRegex(c.Hold, 'raw config'):
            c.validate_bundle(first, {}, second, **kwargs)
        valid = c.validate_bundle(first, {}, first, **kwargs)
        baseline = c.Baselines(valid, valid)
        with self.assertRaises(c.Hold):
            baseline.check(dict(valid, state_sha256='a' * 64))
        with self.assertRaises(c.Hold):
            baseline.check(valid)
        kwargs['after'] = {'drift': 1}
        with self.assertRaises(c.Hold):
            c.validate_bundle(first, {}, first, **kwargs)


class RPCTests(unittest.TestCase):
    def rpc(self, responses=(), write_error=None):
        return op.RecordingRPC(MockTransport(responses, write_error), time.monotonic() + 180)

    def started(self, responses=()):
        rpc = self.rpc(responses)
        rpc.thread_id = 'thread-1'
        return rpc

    def test_original_bytes_hash_and_config_safe_identity(self):
        raw = b'{ "id": 1, "result": {"config": {"api_key": "private-canary"}} }\n'
        rpc = self.rpc([raw])
        actual = rpc.call('config/read', {'includeLayers': True, 'cwd': '/tmp'})
        self.assertEqual(actual['config']['api_key'], 'private-canary')
        self.assertNotIn('private-canary', json.dumps(rpc.wire))
        self.assertEqual(rpc.wire[-1]['bytes_sha256'], c.digest(raw))
        self.assertEqual(rpc.wire[-1]['bytes_length'], len(raw))

    def test_one_user_one_thread_no_resume_fork_or_server_answer(self):
        rpc = self.started([{'id': 1, 'result': {'turn': {'id': 'turn-1'}}}])
        params = {'threadId': 'thread-1', 'input': [{'type': 'text', 'text': 'real decision'}]}
        rpc.call('turn/start', params)
        for method, args in [('turn/start', params), ('thread/resume', {}), ('thread/fork', {}), ('answer', {})]:
            with self.subTest(method=method), self.assertRaises(c.Hold):
                rpc.send(method, args)
        charge = c.validate_wire(rpc.wire, 'thread-1', 'turn-1')
        self.assertEqual(charge, {'actual': 1, 'attempted': 1, 'charged': 1, 'status': 'ACTUAL', 'accepted': 1})

    def test_zero_and_partial_write_unknown_do_not_refund(self):
        self.assertEqual(c.validate_wire([], None, None)['status'], 'ZERO')
        rpc = self.started()
        rpc.transport.write_error = BrokenPipeError('partial mock write')
        with self.assertRaises(BrokenPipeError):
            rpc.send('turn/start', {'threadId': 'thread-1', 'input': [{'type': 'text', 'text': 'one'}]})
        self.assertEqual(c.validate_wire(rpc.wire, 'thread-1', None),
                         {'actual': None, 'attempted': 1, 'charged': 1, 'status': 'UNKNOWN', 'accepted': 0})

    def test_server_rejected_dispatch_is_charged_actual_failure(self):
        rpc = self.started([{'id': 1, 'error': {'code': -1, 'message': 'rejected'}}])
        with self.assertRaises(c.Hold):
            rpc.call('turn/start', {'threadId': 'thread-1', 'input': [{'type': 'text', 'text': 'one'}]})
        self.assertEqual(c.validate_wire(rpc.wire, 'thread-1', None),
                         {'actual': 1, 'attempted': 1, 'charged': 1, 'status': 'ACTUAL', 'accepted': 0})

    def test_malformed_turn_results_are_typed_holds_and_replay_unknown(self):
        for result in (1, [], {'turn': 1}, {'turn': []}, {'turn': None}):
            rpc = self.started([{'id': 1, 'result': result}])
            with self.subTest(result=result), self.assertRaises(c.Hold):
                rpc.call('turn/start', {'threadId': 'thread-1', 'input': [{'type': 'text', 'text': 'one'}]})
            self.assertEqual(len(rpc.wire), 3)
            with self.assertRaises(c.Hold):
                c.validate_wire(rpc.wire, 'thread-1', None)

    def test_predispatch_eof_is_explicit_failure(self):
        rpc = self.rpc()
        with self.assertRaises(EOFError):
            rpc.call('config/read', {})
        self.assertTrue(rpc.failed)
        self.assertEqual(rpc.wire[-1]['direction'], 'transport_error')
        self.assertEqual(c.validate_wire(rpc.wire, None, None)['status'], 'ZERO')

    def test_foreign_ids_server_request_and_late_errors(self):
        bad = [
            {'id': 45, 'result': {}},
            {'id': 1, 'method': 'item/commandExecution/requestApproval', 'params': {}},
            {'method': 'item/started', 'params': {'threadId': 'other'}},
            {'method': 'item/started', 'params': {'turnId': 'other'}},
            {'method': 'error', 'params': {'error': 'late'}},
            {'method': 'turn/completed', 'params': {'turn': {'id': 'other', 'status': 'completed'}}},
        ]
        for event in bad:
            with self.subTest(event=event):
                rpc = self.started([event])
                rpc.turn_id = 'turn-1'
                with self.assertRaises(c.Hold):
                    rpc.receive()
                self.assertTrue(rpc.failed)

    def test_terminal_and_late_drain_failure(self):
        rpc = self.started([{'id': 1, 'result': {'turn': {'id': 'turn-1'}}},
                            {'method': 'turn/completed', 'params': {'threadId': 'thread-1',
                             'turn': {'id': 'turn-1', 'status': 'completed'}}}])
        rpc.call('turn/start', {'threadId': 'thread-1', 'input': [{'type': 'text', 'text': 'one'}]})
        rpc.receive()
        self.assertTrue(rpc.completed)
        rpc.transport.responses = [{'method': 'error', 'params': {'error': 'late'}}]
        with self.assertRaises(c.Hold):
            rpc.drain()

    def test_absolute_deadline_and_wire_clock(self):
        rpc = op.RecordingRPC(MockTransport(), 5, clock=lambda: 6)
        with self.assertRaisesRegex(c.Hold, 'absolute'):
            rpc.send('initialize', {})
        rpc = op.RecordingRPC(MockTransport(), time.monotonic() + 30, monotonic_ns=lambda: 1)
        rpc.send('initialized', notification=True)
        with self.assertRaisesRegex(c.Hold, 'nonmonotonic'):
            rpc.send('initialized', notification=True)

    def test_terminal_requires_exact_ids_and_rejects_late_items_and_nested_agents(self):
        for params in ({'turn': {'status': 'completed'}},
                       {'threadId': 'thread-1', 'turn': {'id': 'other', 'status': 'completed'}},
                       {'threadId': 'other', 'turn': {'id': 'turn-1', 'status': 'completed'}}):
            rpc = self.started([{'method': 'turn/completed', 'params': params}])
            rpc.dispatched, rpc.turn_id = True, 'turn-1'
            with self.subTest(params=params), self.assertRaises(c.Hold):
                rpc.receive()
        for kind in ('commandExecution', 'collabAgentSpawnToolCall'):
            event = {'method': 'item/started', 'params': {'threadId': 'thread-1', 'turnId': 'turn-1',
                     'item': {'type': kind, 'id': 'late', 'command': 'touch late', 'cwd': '/tmp'}}}
            rpc = self.started([event]); rpc.turn_id = 'turn-1'; rpc.completed = True
            with self.subTest(kind=kind), self.assertRaises(c.Hold):
                rpc.receive()
        event = {'method': 'item/started', 'params': {'item': {'type': 'collabAgentSpawnToolCall', 'id': 'child'}}}
        rpc = self.started([event])
        with self.assertRaises(c.Hold):
            rpc.receive()
        with self.assertRaises(c.Hold):
            c.validate_wire(rpc.wire, 'thread-1', None)

    def test_first_safe_failure_survives_cleanup_reconcile_and_deadline(self):
        raw = {'failure': None}
        op.record_failure(raw, EOFError('private-canary'), 'initialize')
        for error, stage in ((OSError('private-canary'), 'owned-process-close'),
                             (c.Hold('private-canary'), 'wire-reconciliation'),
                             (TimeoutError('private-canary'), 'absolute-context-deadline')):
            op.record_failure(raw, error, stage)
        self.assertEqual(raw['failure']['primary']['stage'], 'initialize')
        self.assertEqual(len(raw['failure']['secondary']), 3)
        self.assertNotIn('private-canary', json.dumps(raw))

    def test_owned_watchdog_kills_exact_group_independently_of_RPC_or_CPU(self):
        process = mock.Mock(pid=9312)
        timer = mock.Mock()
        with mock.patch.object(op.subprocess, 'Popen', return_value=process), \
             mock.patch.object(op.os, 'set_blocking'), \
             mock.patch.object(op.threading, 'Timer', return_value=timer) as timer_class, \
             mock.patch.object(op.os, 'killpg') as kill:
            transport = op.ProcessTransport(['/never-executed'], '/tmp', {}, time.monotonic() + 1)
            callback = timer_class.call_args.args[1]
            callback()  # deterministically simulate deadline during a CPU validator
            self.assertTrue(transport.watchdog_fired)
            kill.assert_called_once_with(9312, op.signal.SIGKILL)
            timer.start.assert_called_once()
            transport.stderr.close()


    def test_constructor_failure_reaps_owned_group_and_preserves_first_cause(self):
        for stage in ('timer', 'blocking'):
            process = mock.Mock(pid=9312)
            timer = mock.Mock()
            primary = OSError('private-constructor-canary')
            if stage == 'timer': timer.start.side_effect = primary
            with self.subTest(stage=stage), mock.patch.object(op.subprocess, 'Popen', return_value=process), \
                 mock.patch.object(op.os, 'set_blocking', side_effect=primary if stage == 'blocking' else None), \
                 mock.patch.object(op.threading, 'Timer', return_value=timer), mock.patch.object(op.os, 'killpg') as kill:
                with self.assertRaises(OSError) as failure:
                    op.ProcessTransport(['/never-executed'], '/tmp', {}, time.monotonic() + 1)
                self.assertIs(failure.exception, primary)
                kill.assert_called_once_with(9312, op.signal.SIGKILL)
                process.wait.assert_called_once_with(timeout=2)
                process.stdin.close.assert_called_once(); process.stdout.close.assert_called_once()
                timer.cancel.assert_called_once()

    def test_item_ownership_required_before_callback_and_in_replay(self):
        for missing in ('threadId', 'turnId', 'both', 'id'):
            rpc = self.started(); rpc.turn_id = 'turn-1'; rpc.dispatched = True
            callback = mock.Mock(); rpc.on_event = callback
            params = {'threadId': 'thread-1', 'turnId': 'turn-1',
                      'item': {'type': 'commandExecution', 'id': 'cmd', 'command': 'pwd', 'cwd': '/tmp'}}
            if missing == 'both': params.pop('threadId'); params.pop('turnId')
            elif missing == 'id': params['item'].pop('id')
            else: params.pop(missing)
            with self.subTest(missing=missing), self.assertRaises(c.Hold):
                rpc.receive(raw=(json.dumps({'method': 'item/started', 'params': params}) + '\n').encode())
            callback.assert_not_called(); self.assertEqual(rpc.active_items, {})
            with self.assertRaises(c.Hold): c.validate_wire(rpc.wire, 'thread-1', 'turn-1')

    def test_early_owned_turn_started_must_match_later_acknowledgement(self):
        for acknowledged in ('turn-1', 'other'):
            rpc = self.started([
                {'method': 'turn/started', 'params': {'threadId': 'thread-1', 'turn': {'id': 'turn-1', 'status': 'inProgress'}}},
                {'id': 1, 'result': {'turn': {'id': acknowledged}}}])
            if acknowledged == 'other':
                with self.assertRaises(c.Hold): rpc.call('turn/start', {'threadId': 'thread-1', 'input': [{'type': 'text', 'text': 'one'}]})
            else:
                rpc.call('turn/start', {'threadId': 'thread-1', 'input': [{'type': 'text', 'text': 'one'}]})
                self.assertEqual(c.validate_wire(rpc.wire, 'thread-1', 'turn-1')['accepted'], 1)


OBLIGATIONS = {
    'D2-tail/spec-approval': 'actual_question separate_spec_decision spec_content_identical spec_approved',
    'D2-tail/tasks-initial': 'approved_spec_consumed all_AC_linked new_tasks plan_question no_implementation',
    'D2-tail/plan-approval': 'actual_plan_question separate_plan_decision tasks_content_identical tasks_approved',
    'D2-tail/TDD-build': 'actual_tasks_feasibility red_before_production configured_checks_green AC9_concurrency owner_review_stop',
    'D2-tail/content-to-operation-question': 'actual_content_decision operation_question targets_effects_recovery no_implementation',
    'D2-tail/Git-AC9': 'separate_exact_git_grant commit_revert_restore same_persistent_OFF baseline_MAIN_unchanged feature_docs_unchanged actual_AC11',
    'D2-tail/unavailable-review': 'complete_current_packet actual_supported_route_unavailable independent_review_incomplete no_root_packet_fill',
    'D2-tail/independent-review': 'separate_context_no_author_conversation installed_F1_body_consumed installed_template_consumed current_all_layers completed_review',
    'D2-tail/local-ship': 'current_checks AC_evidence installed_HUMAN_REQUIRED_10 local_pr_complete owner_rollback no_external_action',
    'D2-tail/scope-invalidation': 'actual_scope_change both_approvals_draft no_implementation',
}


class TransitionTests(TempCase):
    def transition(self, row, authored, before, after):
        evidence = {}
        roles = {'spec': None, 'tasks': None, 'application': [], 'tests': [], 'callers': [],
                 'progress': [], 'packet': [], 'review': None, 'local_pr': None, 'off': None}
        slot = {'D2-tail/spec-approval': 'spec', 'D2-tail/tasks-initial': 'tasks',
                'D2-tail/plan-approval': 'tasks', 'D2-tail/TDD-build': 'application',
                'D2-tail/content-to-operation-question': 'progress',
                'D2-tail/unavailable-review': 'packet', 'D2-tail/independent-review': 'review',
                'D2-tail/local-ship': 'local_pr', 'D2-tail/scope-invalidation': 'spec'}.get(row)
        if slot and authored:
            roles[slot] = authored if type(roles[slot]) is list else authored[0]
        if row == 'D2-tail/scope-invalidation' and len(authored) == 2:
            roles['tasks'] = authored[1]
        contract = {'schema': 'postclosure-contract-v1', 'row_id': row, 'roles': roles, 'authored': authored,
                    'derived': [], 'immutable_paths': ['AGENTS.md'],
                    'expected_before': c.canonical_hash(before), 'expected_after': None,
                    'obligations': OBLIGATIONS[row].split(), 'evidence': evidence,
                    'git_profile': None, 'cache_profile': None, 'capability_profile': None, 'tasks_progress': None}
        plan = self.plan(row)
        plan['contract'] = self.save('contract.json', contract)
        return plan, contract, evidence

    def test_each_row_structural_contract_and_unsupported_profiles_hold(self):
        for row in c.ROWS:
            with self.subTest(row=row):
                before = {'AGENTS.md': {'kind': 'file', 'mode': '0o644', 'identity': [1, 1], 'sha256': 'a' * 64}}
                after = dict(before)
                path = 'docs/ains/spec.md' if row != 'D2-tail/tasks-initial' else 'docs/ains/tasks.md'
                after[path] = {'kind': 'file', 'mode': '0o644', 'identity': [1, 2], 'link_text': None, 'sha256': 'b' * 64}
                authored = [path]
                if row == 'D2-tail/scope-invalidation':
                    authored += ['docs/ains/tasks.md']
                    after['docs/ains/tasks.md'] = {'kind': 'file', 'mode': '0o644', 'identity': [1, 3], 'link_text': None, 'sha256': 'c' * 64}
                contents_before = {}
                contents_after = {}
                if row in ('D2-tail/spec-approval', 'D2-tail/plan-approval', 'D2-tail/scope-invalidation'):
                    for name in authored:
                        old = b'---\nstatus: draft\n---\nBusiness\n'
                        new = b'---\nstatus: approved\n---\nBusiness\n'
                        if row == 'D2-tail/scope-invalidation':
                            old, new = new, old
                        contents_before[name], contents_after[name] = old, new
                        before[name] = {'kind': 'file', 'mode': '0o644', 'identity': [1, 5 + len(contents_before)], 'sha256': c.digest(old)}
                        after[name] = dict(before[name], sha256=c.digest(new))
                plan, _, evidence = self.transition(row, authored, before, after)
                if row in ('D2-tail/Git-AC9', 'D2-tail/unavailable-review'):
                    with self.assertRaises(c.Hold):
                        c.validate_transition(plan, before, after, evidence)
                else:
                    result = c.validate_transition(plan, before, after, evidence,
                                                   contents_before=contents_before, contents_after=contents_after)
                    self.assertIs(result['business_PASS'], False)
                bad = dict(after, **{'AGENTS.md': {'kind': 'file', 'mode': '0o644', 'identity': [1, 1], 'sha256': 'c' * 64}})
                with self.assertRaises(c.Hold):
                    c.validate_transition(plan, before, bad, evidence)

    def test_boolean_obligations_and_future_postimage_are_not_proof(self):
        row = 'D2-tail/spec-approval'
        plan, contract, evidence = self.transition(row, ['spec.md'], {}, {})
        bad = {key: True for key in OBLIGATIONS[row].split()}
        contract['evidence'] = bad
        contract['expected_after'] = c.canonical_hash({})
        plan['contract'] = self.save('contract.json', contract)
        with self.assertRaisesRegex(c.Hold, 'not proof'):
            c.validate_transition(plan, {}, {}, bad, adjudicating=True)
        contract['evidence'] = evidence
        contract['expected_after'] = c.canonical_hash({})
        plan['contract'] = self.save('contract.json', contract)
        with self.assertRaisesRegex(c.Hold, 'preload'):
            c.validate_transition(plan, {}, {}, evidence)
        # A content-preserving status change still needs trusted byte captures;
        # independent evidence cannot fill missing actual artifact observations.
        with self.assertRaises(c.Hold):
            c.validate_transition(plan, {}, {}, evidence, adjudicating=True)

    def test_alias_metadata_overlap_and_negative_cache(self):
        row = 'D2-tail/TDD-build'
        state = {'app.py': {'kind': 'file', 'mode': '0o644', 'identity': [1, 1], 'link_text': None}}
        plan, contract, evidence = self.transition(row, ['app.py'], {}, state)
        for authored, derived, immutable in [(['AGENTS.md'], [], []),
                                              (['app.py'], ['app.py'], []),
                                              (['app.py'], [], ['app.py']),
                                              (['app.py'], ['__pycache__/app.cpython-314.pyc'], [])]:
            contract.update(authored=authored, derived=derived, immutable_paths=immutable)
            plan['contract'] = self.save('contract.json', contract)
            with self.assertRaises(c.Hold):
                c.validate_transition(plan, {}, state, evidence)
        contract.update(authored=['app.py'], derived=[], immutable_paths=[])
        plan['contract'] = self.save('contract.json', contract)
        alias = {'app.py': {'kind': 'symlink', 'link_text': 'elsewhere'}}
        with self.assertRaises(c.Hold):
            c.validate_transition(plan, {}, alias, evidence)


class SuccessorLinkageTests(TempCase):
    def setUp(self):
        super().setUp()
        (self.root / 'owned-project').mkdir()
        self.project = self.root / 'owned-project'
        (self.project / 'spec.md').write_text('---\nstatus: approved\n---\nOWN SYNTHETIC FIXTURE\n')
        self.state = c.inventory(self.project)
        placeholder = self.text('control-proof')
        event = {'method': 'item/completed', 'params': {'threadId': 'fixture-thread', 'turnId': 'fixture-turn',
                 'item': {'type': 'agentMessage', 'id': 'fixture-final', 'phase': 'final_answer',
                          'text': 'OWN fixture final, not a future real approval'}}}
        wire = [{'index': 0, 'monotonic_ns': 1, 'direction': 'response', 'payload': event,
                 'bytes_sha256': c.digest(json.dumps(event).encode()), 'bytes_length': len(json.dumps(event).encode())}]
        raw = {'schema': 'postclosure-context-v1', 'branch_id': 'OWN-synthetic', 'row_id': 'D2-tail/spec-approval',
               'donor_slot': c.ROWS['D2-tail/spec-approval'], 'common': placeholder, 'release': placeholder,
               'prior_history_sha256': c.LEGACY_PREFIX_SHA, 'root': str(self.project), 'realroot': str(self.project),
               'process_id': 7, 'thread_id': 'fixture-thread', 'turn_id': 'fixture-turn', 'wire': wire,
               'samples': [], 'input_delivery': {}, 'state_before': self.state, 'state_after': self.state,
               'close': {'reaped': True, 'partial_stdout_bytes': 0}, 'failure': None,
               'accounting': {'actual': 0, 'accepted': 0, 'status': 'ZERO'}, 'business_PASS': False}
        self.context = self.save('OWN-mock-context.json', raw)
        self.result_value = {'schema': 'postclosure-independent-result-v1', 'context': self.context,
                             'review': placeholder, 'adjudication': placeholder,
                             'decision': 'ACCEPT_EXACT_D2_ROW', 'business_PASS': True}
        self.result = self.save('OWN-mock-result.json', self.result_value)
        self.question_value = {'schema': 'postclosure-question-v1', 'context': self.context,
                               'wire_index': 0, 'item_sha256': c.canonical_hash(event['params']['item']),
                               'text': event['params']['item']['text']}
        self.question = self.save('OWN-mock-question.json', self.question_value)
        self.predecessor = {'schema': 'postclosure-predecessor-v1', 'context': self.context,
                            'independent_result': self.result, 'state': self.save('OWN-state.json', self.state),
                            'question': self.question}

    def test_last_accepted_result_context_poststate_and_actual_final_are_bound(self):
        raw = c.validate_successor_predecessor(self.predecessor, [self.result], {'root': str(self.project)}, self.state, {})
        self.assertEqual(raw['state_after'], self.state)
        cases = [dict(self.predecessor, context=self.text('unrelated-context')),
                 dict(self.predecessor, independent_result=self.text('unrelated-result'))]
        for predecessor in cases:
            with self.assertRaises(c.Hold):
                c.validate_successor_predecessor(predecessor, [self.result], {'root': str(self.project)}, self.state, {})
        with self.assertRaises(c.Hold):
            c.validate_successor_predecessor(self.predecessor, [self.result], {'root': str(self.project)}, {}, {})
        forged = self.save('forged-question.json', dict(self.question_value, text='fabricated future question'))
        with self.assertRaises(c.Hold):
            c.validate_successor_predecessor(dict(self.predecessor, question=forged), [self.result],
                                             {'root': str(self.project)}, self.state, {})
        failed = self.save('failed-result.json', dict(self.result_value, business_PASS=False))
        with self.assertRaises(c.Hold):
            c.validate_successor_predecessor(dict(self.predecessor, independent_result=failed), [failed],
                                             {'root': str(self.project)}, self.state, {})


class CacheTests(TempCase):
    def profile(self):
        # Resolve the invoked interpreter: executable identity is explicit.
        return {'executable': c.ref(Path(sys.executable).resolve(), executable=True),
                'version': '3.14.6', 'cache_tag': 'cpython-314',
                'magic': '2b0e0d0a', 'marshal_version': 5}

    def candidate(self, source=b'x = 1\n', flags=0, filename=None):
        source_path = str(self.root / 'app.py')
        header = importlib.util.MAGIC_NUMBER + struct.pack('<I', flags)
        header += struct.pack('<II', 1, len(source)) if flags == 0 else importlib.util.source_hash(source)
        return header + marshal.dumps(compile(source, filename or source_path, 'exec',
                                             flags=0, dont_inherit=True, optimize=0), marshal.version)

    def verify(self, candidate, source=b'x = 1\n', **overrides):
        source_path = str(self.root / 'app.py')
        kwargs = dict(source_path=source_path,
                      cache_path=importlib.util.cache_from_source(source_path, optimization=''),
                      mtime_ns=1_000_000_000, source_size=len(source),
                      interpreter=self.profile(), expected_interpreter=self.profile())
        kwargs.update(overrides)
        return c.validate_cache(candidate, source, **kwargs)

    def test_timestamp_hash_and_unchecked_hash_full_attribution(self):
        for flags in (0, 1, 3):
            with self.subTest(flags=flags):
                self.assertEqual(self.verify(self.candidate(flags=flags))['flags'], flags)

    def test_wrong_source_tag_filename_trailing_and_flags_rejected(self):
        valid = self.candidate()
        cases = [(valid, {'source': b'x = 2\n'}),
                 (valid, {'cache_path': str(self.root / '__pycache__/app.cpython-313.pyc')}),
                 (self.candidate(filename='/foreign/app.py'), {}),
                 (valid + b'trailing', {}),
                 (valid[:4] + struct.pack('<I', 2) + valid[8:], {}),
                 (b'wrong' + valid[5:], {}),
                 (valid, {'mtime_ns': 2_000_000_000})]
        for candidate, kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(c.Hold):
                self.verify(candidate, **kwargs)


class CapabilityTests(TempCase):
    def test_disabled_mcp_capability_accepts_only_disabled_inherited_entries(self):
        profile = {'schema': 'postclosure-capability-profile-v1', 'route': 'model-native-independent-agent',
                   'process_only': True, 'agents_enabled': False, 'multi_agent_v2': False,
                   'dynamic_tools': [], 'client_review_rpc': False, 'external_review_cli': False,
                   'wording': 'independent-agent review unavailable in this declared P7 route',
                   'official_sources': [self.text('registry-source')]}
        cfg = {'config': c.session_for(str(self.root), True)}
        for name in c.MCP:
            cfg['config']['mcp_servers'][name].update(args=['fixture'], tool_timeout_sec=None)
        c.validate_capability(profile, cfg, supplied_dynamic_tools=[], authorized_methods=op.RecordingRPC.METHODS)
        for name in c.MCP:
            for field, value in (('enabled', True), ('enabled', 0), ('command', '/fixture/other')):
                altered = copy.deepcopy(cfg)
                altered['config']['mcp_servers'][name][field] = value
                with self.subTest(name=name, field=field, value=value), self.assertRaises(c.Hold):
                    c.validate_capability(profile, altered, supplied_dynamic_tools=[], authorized_methods=op.RecordingRPC.METHODS)

    def test_declared_negative_requires_actual_two_boolean_predicate(self):
        profile = {'schema': 'postclosure-capability-profile-v1', 'route': 'model-native-independent-agent',
                   'process_only': True, 'agents_enabled': False, 'multi_agent_v2': False,
                   'dynamic_tools': [], 'client_review_rpc': False, 'external_review_cli': False,
                   'wording': 'independent-agent review unavailable in this declared P7 route',
                   'official_sources': [self.text('registry-source')]}
        cfg = {'config': dict(c.session_for(str(self.root), True))}
        proof = c.validate_capability(profile, cfg, supplied_dynamic_tools=[], authorized_methods=op.RecordingRPC.METHODS)
        self.assertIs(proof['business_PASS'], False)
        for agents in (None, {}, {'enabled': True}, {'enabled': 0}):
            altered = copy.deepcopy(cfg)
            altered['config']['agents'] = agents
            with self.subTest(agents=agents), self.assertRaises(c.Hold):
                c.validate_capability(profile, altered, supplied_dynamic_tools=[], authorized_methods=op.RecordingRPC.METHODS)
        for methods, dynamic in (({'review/start'}, []), (op.RecordingRPC.METHODS, ['reviewer'])):
            with self.assertRaises(c.Hold):
                c.validate_capability(profile, cfg, supplied_dynamic_tools=dynamic, authorized_methods=methods)


class PacketTests(TempCase):
    def packet(self):
        events = []
        resources = []
        for index, name in enumerate(('review-body.md', 'review-template.md')):
            reference = self.text(name, 'complete ' + name + '\n')
            command = 'cat -- ' + shlex.quote(reference['path'])
            events.append({'method': 'item/completed', 'params': {'item': {'id': 'read-' + str(index),
                           'type': 'commandExecution', 'command': command, 'cwd': str(self.root),
                           'status': 'completed', 'exitCode': 0, 'aggregatedOutput': c.read_ref(reference).decode()}}})
            resources.append({'resource': reference, 'command': command, 'event_index': index})
        before, after = self.text('baseline.py', 'old'), self.text('implementation.py', 'new')
        layers = {'commit': {'app/a.py': {'before': before, 'after': after}},
                  'index': {}, 'worktree': {'spec.md': {'before': self.text('old-spec', 'old spec'),
                                                       'after': self.text('new-spec', 'new spec')}},
                  'untracked': {'tasks.md': {'before': None, 'after': self.text('new-tasks', 'tasks')}}}
        target = c.canonical_hash(layers)
        events.append({'method': 'item/completed', 'params': {'item': {'id': 'check', 'type': 'commandExecution',
                       'command': 'python3 -m unittest discover -v', 'cwd': str(self.root),
                       'status': 'completed', 'exitCode': 0}}})
        packet = {'schema': 'postclosure-review-packet-v1', 'scope': {'root': str(self.root)},
                  'capture': 'actual-current-capture', 'base': '1' * 40, 'head': '2' * 40, 'merge_base': '1' * 40,
                  **layers, 'target': ['app/a.py', 'spec.md', 'tasks.md'], 'callers': [],
                  'spec': self.text('approved-spec'), 'tasks': self.text('approved-tasks'), 'origins': {},
                  'checks': [{'command': 'python3 -m unittest discover -v', 'cwd': str(self.root),
                              'target_sha256': target, 'event_index': 2}], 'resources': resources}
        kwargs = {'expected_scope': packet['scope'], 'expected_capture': packet['capture'],
                  'target_paths': packet['target'], 'implementation_paths': ['app/a.py'],
                  'expected_resources': resources, 'events': events}
        return packet, kwargs

    def test_all_layers_and_complete_successful_resource_consumption(self):
        packet, kwargs = self.packet()
        self.assertIs(c.validate_review_packet(packet, **kwargs)['business_PASS'], False)
        for alteration in ('staged-only', 'missing-untracked', 'unrelated', 'stale-check', 'failed-read', 'substring-read'):
            altered, options = copy.deepcopy(packet), copy.deepcopy(kwargs)
            if alteration == 'staged-only':
                altered['index'], altered['commit'] = altered['commit'], {}
            elif alteration == 'missing-untracked':
                altered['untracked'] = {}
            elif alteration == 'unrelated':
                altered['commit']['unrelated.py'] = next(iter(altered['commit'].values()))
            elif alteration == 'stale-check':
                altered['checks'][0]['target_sha256'] = '0' * 64
            elif alteration == 'failed-read':
                options['events'][0]['params']['item']['exitCode'] = 1
            else:
                options['events'][0]['params']['item']['aggregatedOutput'] += 'extra output'
            with self.subTest(alteration=alteration), self.assertRaises(c.Hold):
                c.validate_review_packet(altered, **options)


@unittest.skipUnless(os.environ.get('POSTCLOSURE_GIT_PROOF'), 'optional Root-owned observed Git fixture not supplied')
class ObservedGitTests(TempCase):
    """Replay actual Root-collected bytes, never invoke Git or alter its proof."""
    def setUp(self):
        super().setUp()
        proof_root = Path(os.environ['POSTCLOSURE_GIT_PROOF']).resolve()
        self.result = json.loads((proof_root / 'result.json').read_text())
        self.before, self.before_bytes = self.capture(proof_root / 'before-inventory.json')
        self.after, self.after_bytes = self.capture(proof_root / 'after-inventory.json')
        raw_events = json.loads((proof_root / 'events.json').read_text())[self.result['journey_event_start']:]
        self.events = [{'method': 'item/completed', 'params': {'item': {'id': str(index), 'type': 'commandExecution',
                        'command': shlex.join(value['argv']), 'cwd': value['cwd'], 'status': 'completed',
                        'exitCode': value['returncode'], 'aggregatedOutput': value['stdout']}}}
                       for index, value in enumerate(raw_events)]
        executable = Path(shutil.which('git')).resolve()
        overrides = raw_events[0]['argv'][2:-4:2]
        self.profile = {'schema': 'postclosure-git-profile-v1', 'branch': 'refs/heads/fixture',
                        'main_ref': 'refs/heads/main', 'off_path': self.result['off_path'], 'object_format': 'sha1',
                        'off_initial': 'preserve', 'off_data': c.ref(Path(self.before[self.result['off_path']]['bytes_ref']['path'])) if 'bytes_ref' in self.before[self.result['off_path']] else c.ref(proof_root / 'before' / self.result['off_path']),
                        'off_mode': self.after[self.result['off_path']]['mode'], 'verification_commands': [], 'command_prefix': [], 'env_executable': None,
                        'command_cwd': self.result['repo'], 'executable': c.ref(executable, executable=True),
                        'invoked_path': 'git', 'version': '2.54.0', 'auto_merge': 'restore-tree',
                        'official_sources': [c.ref(Path('/tmp/postclosure-p6-git-research-20261027.md').resolve())],
                        'overrides': overrides, 'environment_proof': c.ref(proof_root / 'result.json')}
        self.roles = {'application': ['app/a.py'], 'tests': ['tests/test_a.py'], 'off': 'off.json'}

    @staticmethod
    def capture(path):
        original = json.loads(path.read_text())
        data = {name: c.read_ref(value['bytes_ref']) for name, value in original.items() if 'bytes_ref' in value}
        state = {name: {key: value for key, value in item.items() if key in ('kind', 'mode', 'identity', 'sha256')}
                 for name, item in original.items()}
        return state, data

    def validate(self, **kwargs):
        values = dict(profile=self.profile, before=self.before, after=self.after,
                      before_bytes=self.before_bytes, after_bytes=self.after_bytes,
                      events=self.events, roles=self.roles)
        values.update(kwargs)
        return c.validate_git_rollback(**values)

    def test_actual_observed_commit_revert_restore_object_index_reflog_profile(self):
        proof = self.validate()
        self.assertEqual(proof['commit'], self.result['commit'])
        self.assertEqual(proof['revert'], self.result['revert'])
        self.assertEqual(proof['restore'], self.result['restore'])

    def test_object_ref_index_off_and_override_tampering_fail(self):
        cases = []
        changed = dict(self.after_bytes); changed['off.json'] += b'changed'; cases.append({'after_bytes': changed})
        changed = dict(self.after_bytes); changed['.git/AUTO_MERGE'] = b'0' * 40 + b'\n'; cases.append({'after_bytes': changed})
        changed = dict(self.after_bytes); changed['.git/index'] = changed['.git/index'][:-1] + b'x'; cases.append({'after_bytes': changed})
        changed = dict(self.after_bytes); changed['.git/refs/heads/main'] = b'0' * 40 + b'\n'; cases.append({'after_bytes': changed})
        changed = copy.deepcopy(self.events); changed[0]['params']['item']['command'] = 'git add -- app/a.py tests/test_a.py'; cases.append({'events': changed})
        changed = dict(self.after_bytes)
        object_path = '.git/objects/' + self.result['commit'][:2] + '/' + self.result['commit'][2:]
        changed[object_path] += b'junk'; cases.append({'after_bytes': changed})
        for index, kwargs in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(c.Hold):
                self.validate(**kwargs)


    def test_new_OFF_requires_every_actual_stage_and_exact_isolated_environment(self):
        before = dict(self.before); before.pop('off.json')
        before_bytes = dict(self.before_bytes); before_bytes.pop('off.json')
        profile = dict(self.profile, off_initial='create', command_prefix=list(c.GIT_ENV_PREFIX),
                       env_executable=c.ref(Path('/usr/bin/env'), executable=True),
                       invoked_path=self.profile['executable']['path'])
        events = copy.deepcopy(self.events)
        for event in events:
            item = event['params']['item']; argv = shlex.split(item['command'])
            item['command'] = shlex.join(['/bin/zsh', '-lc', shlex.join(c.GIT_ENV_PREFIX + [profile['invoked_path']] + argv[1:])])
        stages = [index for index, event in enumerate(events) if c.git_command_kind(profile, event['params']['item']['command']) in ('add', 'commit', 'revert')]
        samples = [{'event_index': index, 'command': events[index]['params']['item']['command'], 'path': 'off.json',
            'capture': profile['off_data'], 'identity': self.after['off.json']['identity'], 'mode': profile['off_mode'],
            'relation': 'actual post-command observation; no pre-execution timing claim'} for index in stages]
        self.validate(profile=profile, before=before, before_bytes=before_bytes, events=events, off_samples=samples)
        for mutation in ('missing-stage', 'different-identity', 'different-bytes', 'missing-env'):
            bad_samples = copy.deepcopy(samples); bad_events = copy.deepcopy(events)
            if mutation == 'missing-stage': bad_samples.pop()
            elif mutation == 'different-identity': bad_samples[1]['identity'] = [0, 1]
            elif mutation == 'different-bytes': bad_samples[1]['capture'] = self.text('wrong-off', 'wrong')
            else: bad_events[0]['params']['item']['command'] = self.events[0]['params']['item']['command']
            with self.subTest(mutation=mutation), self.assertRaises(c.Hold):
                self.validate(profile=profile, before=before, before_bytes=before_bytes, events=bad_events, off_samples=bad_samples)


@unittest.skipUnless(os.environ.get('POSTCLOSURE_BOOTSTRAP_DATA'), 'read-only adopted D2 bootstrap data not supplied')
class CompleteGraphTests(TempCase):
    """Complete process-free source graph. Native lookup is explicitly MOCK IO.

    Real source, legacy47, adoptions, 151-entry relocation and executable bytes
    are read. Only this test's temporary controls/output descriptions are made.
    """
    def setUp(self):
        super().setUp()
        preparation = Path(os.environ['POSTCLOSURE_BOOTSTRAP_DATA']).resolve()
        upstream = json.loads((preparation / 'PREPARATION.json').read_text())['records']
        self.upstream = upstream
        material = c.read_record(upstream['materialization'], 'materialization')
        predecessor = c.read_record(upstream['predecessor'], 'predecessor')
        self.state = c.decode(c.read_ref(predecessor['state']))
        author = Path(material['relocation']['destination_root'])
        self.author = author
        legacy = c.load_legacy()
        source_files = [c.HERE / name for name in ('postclosure.py', 'postclosure_operator.py',
                         'postclosure_test.py', 'postclosure_f1_test.py', 'native_delta.py')]
        source_files += [c.HERE / (name + '.py') for name in c.HELPERS]
        self.accessory = self.root / 'fixture-accessory.py'
        self.accessory.write_text('# never executed; a pinned fixture accessory\n')
        source_files.append(self.accessory)
        officials = [c.ref(c.SOURCE / path) for path in legacy.STARTUP_LOOKUP_SOURCES]
        self.sources = self.save('source-set.json', {'schema': 'postclosure-source-set-v1',
                            'files': [c.ref(path, executable=True) for path in source_files], 'official_sources': officials})
        self.impl = self.save('implementation-review.json', {'schema': 'postclosure-implementation-review-v1',
                             'source_set': self.sources, 'findings': [], 'decision': 'APPROVE_EXACT_SOURCE'})
        raw = c.decode(c.read_ref(predecessor['context']))
        old_release = c.decode(c.read_ref(raw['release']))
        native = c.decode(c.read_ref(old_release['native_premises']))
        old_root = native['forward_thread_expectation']['cwd']
        def relocate(value):
            if type(value) is str:
                return value.replace(old_root, str(author))
            if type(value) is list:
                return [relocate(item) for item in value]
            if type(value) is dict:
                return {key: relocate(item) for key, item in value.items()}
            return value
        native['forward_thread_expectation'] = relocate(native['forward_thread_expectation'])
        native['forward_trust_root'] = str(author)
        self.native = self.save('native-MOCK-premises.json', native)
        self.native_data = native
        invoked = Path('/opt/homebrew/bin/codex')
        self.choice = self.save('process-choice.json', {'schema': 'postclosure-process-choice-v1',
            'scope_id': 'source-fixture-author', 'root': str(author), 'realroot': str(author), 'topology': 'author-git',
            'executable': c.ref(invoked.resolve(), executable=True), 'invoked_path': str(invoked),
            'invoked_link_text': os.readlink(invoked), 'invoked_mode': oct(invoked.lstat().st_mode & 0o777),
            'argv': c.argv_for(str(invoked), str(author)), 'environment': legacy.environment_facts(dict(os.environ)),
            'native_binding': self.native, 'decision': 'SELECT_EXACT_PROCESS_ONLY_SCOPE'})
        self.scope = self.save('scope.json', {'schema': 'postclosure-scope-v1', 'scope_id': 'source-fixture-author',
            'root': str(author), 'realroot': str(author), 'topology': 'author-git', 'materialization': upstream['materialization'],
            'instruction_sources': [c.ref(Path(path).resolve()) for path in native['forward_thread_expectation']['instructionSources']],
            'install': [], 'process_choice': self.choice})
        prefix = c.read_record(upstream['prefix'], 'legacy-prefix')
        funding = c.read_record(upstream['funding'], 'funding-adoption')
        selection = c.decode(c.read_ref(funding['selection']))
        metadata = c.required_metadata(c.read_record(self.scope))
        session = c.session_for(str(author))
        origin = {'name': {'type': 'sessionFlags'}, 'version': 'sha256:' + c.canonical_hash(session)}
        config = {'config': copy.deepcopy(session), 'layers': [dict(origin, config=copy.deepcopy(session), disabledReason=None),
                  {'name': {'type': 'user', 'file': str(Path.home() / '.codex/config.toml')}, 'version': 'sha256:' + c.canonical_hash({}),
                   'config': {}, 'disabledReason': None}],
                  'origins': {'projects.' + str(author) + '.trust_level': origin, 'agents.enabled': origin}}
        installed = [{'name': name, 'path': str(author / '.agents/skills' / name / 'SKILL.md'),
                      'realpath': str(author / '.agents/skills' / name / 'SKILL.md')} for name in sorted(legacy.MANUAL | legacy.AUTO)]
        catalog = {'data': [{'cwd': str(author), 'skills': [dict(name=item['name'], path=item['path'], enabled=True)
                            for item in installed], 'errors': []}], 'errors': []}
        request = {'cwd': str(author), 'model': native['forward_thread_expectation']['model'],
                   'approvalPolicy': 'never', 'sandbox': 'workspace-write', 'ephemeral': True}
        actual = dict(native['forward_thread_expectation'])
        actual['thread'] = {'id': 'MOCK-lookup-thread', **{key: actual[key] for key in ('cwd', 'model', 'modelProvider', 'reasoningEffort')}}
        anchor = c.invariant_projection(c.read_record(self.scope), material['composite_manifest'], config, catalog,
            legacy.reconcile_thread(actual, request, native['forward_thread_expectation']), dict(os.environ), metadata)
        self.anchor = self.save('invariant-anchor-MOCK.json', anchor)
        self.admission = self.save('admission.json', {'schema': 'postclosure-D2-admission-v1',
            'branch_id': funding['branch_id'], 'funding_selection': funding['selection'], 'funding_adoption': upstream['funding'],
            'legacy_prefix': upstream['prefix'], 'composite_manifest': material['composite_manifest'],
            'materialization': upstream['materialization'], 'scopes': [self.scope], 'rows': c.ROWS, 'source_review': self.impl, 'invariant_anchor': self.anchor})
        spec = 'docs/changes/2026-10-25-order-confirmation-email-toggle/spec.md'
        contract = {'schema': 'postclosure-contract-v1', 'row_id': 'D2-tail/spec-approval',
            'roles': {'spec': spec, 'tasks': None, 'application': [], 'tests': [], 'callers': [], 'progress': [],
                      'packet': [], 'review': None, 'local_pr': None, 'off': None},
            'authored': [spec], 'derived': [], 'immutable_paths': ['AGENTS.md'],
            'expected_before': c.canonical_hash(self.state), 'expected_after': None,
            'obligations': OBLIGATIONS['D2-tail/spec-approval'].split(), 'evidence': {},
            'git_profile': None, 'cache_profile': None, 'capability_profile': None, 'tasks_progress': None}
        self.contract = self.save('contract.json', contract)
        plan = self.plan()
        plan.update(branch_id=funding['branch_id'], scope=self.scope, predecessor=upstream['predecessor'],
                    predecessor_review=material['relocation']['actual_adoption'], contract=self.contract,
                    input=upstream['decision'], source_set=self.sources, admission=self.admission,
                    claim=str(c.claim_path(funding['branch_id'], plan['row_id'], c.CLAIM_ROOT)))
        self.row_plan = self.save('row-plan.json', plan)
        marker = self.text('metadata-marker')
        policy = c.process_policy(self.scope, self.row_plan, {**metadata, marker['path']: marker}, self.native, officials)
        self.policy = self.save('policy.json', policy)
        config_facts = legacy.config_facts(config, lambda value: {})
        catalog_proof = legacy.validate_catalog(catalog, installed, config_facts, 'live')
        identity = legacy.safe_config_identity(config)
        frame = {'config': identity, 'catalog': catalog, 'catalog_proof': catalog_proof,
                 'state_sha256': c.canonical_hash(self.state), 'metadata_sha256': c.canonical_hash(policy['metadata_paths']), 'invariant_sha256': c.canonical_hash(anchor)}
        transport = MockTransport()
        rpc = op.RecordingRPC(transport, time.monotonic() + 180)
        def call(method, params, result):
            transport.responses.append({'id': rpc.sequence + 1, 'result': result})
            return rpc.call(method, params)
        call('initialize', {}, {})
        rpc.send('initialized', notification=True)
        def bundle():
            call('config/read', {'includeLayers': True, 'cwd': str(author)}, config)
            call('skills/list', {'cwds': [str(author)], 'forceReload': True}, catalog)
            call('config/read', {'includeLayers': True, 'cwd': str(author)}, config)
        bundle(); call('thread/start', request, actual); bundle(); bundle()
        lookup = {'schema': 'postclosure-lookup-v1', 'policy': self.policy, 'wire': rpc.wire,
                  'state_before': self.state, 'state_after': self.state, 'USER': 0,
                  'native_facts': {'configuration_identity': identity, 'config_facts': config_facts,
                    'native13': legacy.reconcile_thread(actual, request, native['forward_thread_expectation']),
                    'catalog_proof': catalog_proof, 'capability': None, 'supplied_dynamic_tools': [],
                    'bundles': [frame, frame, frame], 'process_id': 123, 'close': {'reaped': True,
                    'partial_stdout_bytes': 0, 'watchdog_fired': False, 'watchdog_error': None},
                    'failure': None, 'source_set': self.sources, 'native_binding': self.native, 'invariant_candidate': self.anchor}}
        self.lookup = self.save('lookup-MOCK.json', c.load_legacy().finite_receipt(lookup))
        self.mock_config, self.mock_catalog, self.mock_thread = config, catalog, actual
        self.common = self.save('common.json', {'schema': 'postclosure-common-v1', 'row_plan': self.row_plan,
            'policy': self.policy, 'lookup': self.lookup, 'native_binding': self.native, 'source_set': self.sources,
            'product_manifest': material['composite_manifest'], 'predecessor_state_sha256': c.canonical_hash(self.state),
            'history_sha256': prefix['prefix_sha256'], 'input_sha256': c.canonical_hash(c.read_record(upstream['decision']))})
        context_review = self.save('context-review.json', {'schema': 'postclosure-source-context-review-v1',
            'common': self.common, 'implementation_review': self.impl, 'findings': [], 'decision': 'APPROVE_EXACT_CONTEXT'})
        self.review = self.save('root-review.json', {'schema': 'postclosure-root-review-v1',
            'common': self.common, 'source_context_review': context_review, 'admission': self.admission,
            'row_plan': self.row_plan, 'policy': self.policy, 'lookup': self.lookup,
            'release_id': 'SOURCE-TEST-NOT-ACTUAL-RUNTIME', 'decision': 'RELEASE_EXACT_ONE_D2_CONTEXT'})
        self.release = self.save('release.json', {'schema': 'postclosure-release-v1', 'root_review': self.review,
            'common': self.common, 'release_id': 'SOURCE-TEST-NOT-ACTUAL-RUNTIME'})
        self.command_value = {'schema': 'postclosure-command-v1', 'release': self.release, 'row_plan': self.row_plan,
            'native_binding': self.native, 'source_set': self.sources, 'operator': c.ref(c.HERE / 'postclosure_operator.py', executable=True),
            'output': plan['output'], 'claim': plan['claim'], 'history': []}
        self.command = self.save('command.json', self.command_value)

    def test_complete_positive_P1_graph_and_source_or_command_drift(self):
        graph = c.validate_graph(self.command, self.command['sha256'])
        self.assertEqual(graph['state'], self.state)
        self.assertFalse(Path(graph['plan']['claim']).exists())
        self.assertFalse(Path(graph['plan']['output']).exists())
        wrong = self.save('wrong-command.json', dict(self.command_value, output=str(self.root / 'unreviewed-output')))
        with self.assertRaisesRegex(c.Hold, 'command/release'):
            c.validate_graph(wrong, wrong['sha256'])
        self.accessory.write_text('# changed own fixture accessory\n')
        with self.assertRaisesRegex(c.Hold, 'reference byte drift'):
            c.validate_graph(self.command, self.command['sha256'])

    def test_marker_only_metadata_full_graph_is_rejected(self):
        policy=dict(c.read_record(self.policy),metadata_paths={str(self.root/'marker'):self.text('marker')})
        policy_ref=self.save('omitted-metadata-policy.json',policy)
        common=dict(c.read_record(self.common),policy=policy_ref)
        common_ref=self.save('omitted-metadata-common.json',common)
        old_review=c.read_record(self.review)
        context_review=dict(c.read_record(old_review['source_context_review']),common=common_ref)
        context_ref=self.save('omitted-metadata-context-review.json',context_review)
        review_ref=self.save('omitted-metadata-root-review.json',dict(old_review,common=common_ref,policy=policy_ref,source_context_review=context_ref))
        release_ref=self.save('omitted-metadata-release.json',dict(c.read_record(self.release),common=common_ref,root_review=review_ref))
        command=self.save('omitted-metadata-command.json',dict(self.command_value,release=release_ref))
        with self.assertRaisesRegex(c.Hold,'mandatory config/auth/instruction metadata closure missing'):
            c.validate_graph(command,command['sha256'])

    def test_anchor_observation_mode_has_no_business_admission_and_emits_actual_candidate(self):
        policy=c.read_record(self.policy)
        output=str(self.root/'anchor-observation-output')
        observation=self.save('observation-plan.json',{'schema':'postclosure-observation-plan-v1',
            'scope':self.scope,'source_set':self.sources,'native_binding':self.native,
            'product_manifest':c.read_record(self.common)['product_manifest'],'metadata_paths':policy['metadata_paths'],'output':output})
        policy_ref=self.save('observation-policy.json',dict(policy,row_plan=observation,turn_permission=None))
        review=self.save('observation-review.json',{'schema':'postclosure-lookup-review-v1','policy':policy_ref,
            'scope':self.scope,'source_set':self.sources,'native_binding':self.native,'implementation_review':self.impl,
            'decision':'RELEASE_EXACT_ZERO_USER_ANCHOR_OBSERVATION_ONLY'})
        value={'schema':'postclosure-lookup-command-v1','mode':'anchor-observation','review':review,'policy':policy_ref,
            'scope':self.scope,'source_set':self.sources,'native_binding':self.native,
            'operator':c.ref(c.HERE/'postclosure_operator.py',executable=True),'output':output}
        command=self.save('observation-command.json',value)
        graph=c.validate_lookup_command(command,command['sha256'])
        self.assertIsNone(graph['anchor'])
        self.assertNotIn('admission',c.read_record(observation));self.assertNotIn('contract',c.read_record(observation))
        transport=MockNativeTransport(self.mock_config,self.mock_catalog,self.mock_thread)
        with self.mocked_mdm_helpers(),mock.patch.object(op,'enforce_control_scope'):
            raw=op.produce_lookup(command,command['sha256'],transport_factory=lambda *args:transport)
        self.assertIsNone(raw['native_facts']['failure'],raw['native_facts']['failure'])
        self.assertEqual(raw['USER'],0)
        self.assertEqual(c.read_record(raw['native_facts']['invariant_candidate']),c.read_record(self.anchor))
        self.assertNotIn('turn/start',[json.loads(item)['method'] for item in transport.writes])
        wrong=self.save('wrong-observation-mode.json',dict(value,mode='business'))
        with self.assertRaises(c.Hold):c.validate_lookup_command(wrong,wrong['sha256'])

    def test_lifetime_anchor_normalizes_only_actual_reviewer_prefix_and_preserves_immutable_roles(self):
        scope=c.read_record(self.scope); original=c.read_record(self.anchor)
        reviewer=self.root/'reviewer-anchor';reviewer.mkdir()
        for name,item in original['fixture_metadata'].items():
            if item.get('exists',True):
                path=reviewer/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes((self.author/name).read_bytes());path.chmod(int(item['mode'],8))
        old=str(self.author)
        def move(value):
            if type(value)is str:return str(reviewer)+value[len(old):] if value==old or value.startswith(old+'/') else value
            if type(value)is list:return [move(item)for item in value]
            if type(value)is dict:return {move(key):move(item)for key,item in value.items()}
            return value
        scope=dict(scope,root=str(reviewer),realroot=str(reviewer),topology='reviewer-no-git',
            instruction_sources=[c.ref(Path(move(pin['path']))) for pin in scope['instruction_sources']])
        config=move(self.mock_config);catalog=move(self.mock_catalog)
        native=move(c.read_record(self.lookup)['native_facts']['native13']);native['thread_id']='distinct-P8-context'
        candidate=c.invariant_projection(scope,original['product_manifest'],config,catalog,native,dict(os.environ),c.required_metadata(scope))
        self.assertEqual(candidate,original)
        for field in ('model','reasoningEffort','modelProvider','approvalPolicy'):
            changed=copy.deepcopy(candidate);changed['native']['snapshot'][field]='drift'
            with self.subTest(field=field),self.assertRaises(c.Hold):c.validate_anchor(self.anchor,changed)
        changed=copy.deepcopy(candidate);changed['product_manifest']['sha256']='0'*64
        with self.assertRaises(c.Hold):c.validate_anchor(self.anchor,changed)
        (reviewer/'AGENTS.md').write_bytes(b'changed instructions')
        changed=c.invariant_projection(scope,original['product_manifest'],config,catalog,native,dict(os.environ),c.required_metadata(scope))
        with self.assertRaises(c.Hold):c.validate_anchor(self.anchor,changed)

    def test_configured_instruction_contributors_require_pinned_anchor_membership(self):
        scope = c.read_record(self.scope)
        original = c.read_record(self.anchor)
        contributor = self.root / 'external-instructions.md'
        contributor.write_text('original instruction bytes\n')
        contributor.chmod(0o644)
        native = c.read_record(self.lookup)['native_facts']['native13']
        for key in ('model_instructions_file', 'instructions_file', 'developer_instructions_file'):
            with self.subTest(key=key):
                config = copy.deepcopy(self.mock_config)
                config['config'][key] = str(contributor)
                config['layers'][-1]['config'][key] = str(contributor)
                metadata = dict(c.required_metadata(scope), **{str(contributor): c.metadata_receipt(contributor)})
                with self.assertRaisesRegex(c.Hold, 'configured instruction contributor outside pinned closure'):
                    c.invariant_projection(scope, original['product_manifest'], config,
                        self.mock_catalog, native, dict(os.environ), metadata)
                pinned_scope = dict(scope, instruction_sources=scope['instruction_sources'] + [c.ref(contributor)])
                first = c.invariant_projection(pinned_scope, original['product_manifest'], config,
                    self.mock_catalog, native, dict(os.environ), c.required_metadata(pinned_scope))
                self.assertEqual(first['external_metadata'][str(contributor)], c.metadata_receipt(contributor))
                contributor.write_text('changed instruction bytes\n')
                changed_scope = dict(pinned_scope, instruction_sources=scope['instruction_sources'] + [c.ref(contributor)])
                second = c.invariant_projection(changed_scope, original['product_manifest'], config,
                    self.mock_catalog, native, dict(os.environ), c.required_metadata(changed_scope))
                self.assertNotEqual(first, second)
                contributor.write_text('original instruction bytes\n')

    def test_initial_materialization_wrong_predecessor_or_exception_rejected(self):
        material = c.read_record(self.upstream['materialization'])
        scope = c.read_record(self.scope)
        predecessor = c.read_record(self.upstream['predecessor'])
        prefix = c.read_record(self.upstream['prefix'])
        spec = c.read_record(self.contract)['roles']['spec']
        for altered in (dict(material, predecessor=self.text('unrelated-raw')),
                        dict(material, relocation=dict(material['relocation'], exceptions=['app/notifier.py']))):
            with self.assertRaises(c.Hold):
                c.validate_initial_materialization(altered, scope, predecessor, prefix, spec)

    @contextlib.contextmanager
    def mocked_mdm_helpers(self):
        actual_helpers = c.bound_helpers
        @contextlib.contextmanager
        def helpers(sink):
            with actual_helpers(sink) as value:
                with mock.patch.object(value[1][0]['activation_r3'], 'mdm_forced', return_value={'fixture_managed': False}):
                    yield value
        with mock.patch.object(c, 'bound_helpers', helpers):
            yield

    def test_zero_USER_producer_positive_roundtrip_and_no_turn_dispatch(self):
        review = self.save('lookup-review.json', {'schema': 'postclosure-lookup-review-v1',
            'policy': self.policy, 'scope': self.scope, 'source_set': self.sources,
            'native_binding': self.native, 'implementation_review': self.impl,
            'decision': 'RELEASE_EXACT_ZERO_USER_LOOKUP_ONLY'})
        value = {'schema': 'postclosure-lookup-command-v1', 'review': review, 'mode': 'business',
            'policy': self.policy, 'scope': self.scope, 'source_set': self.sources, 'native_binding': self.native,
            'operator': c.ref(c.HERE / 'postclosure_operator.py', executable=True), 'output': str(self.root / 'zero-output')}
        command = self.save('lookup-command.json', value)
        transport = MockNativeTransport(self.mock_config, self.mock_catalog, self.mock_thread)
        before = c.inventory(self.author)
        with self.mocked_mdm_helpers(), mock.patch.object(op, 'enforce_control_scope'):
            raw = op.produce_lookup(command, command['sha256'], transport_factory=lambda *args: transport)
        self.assertIsNone(raw['native_facts']['failure'], raw['native_facts']['failure'])
        self.assertEqual(raw['USER'], 0)
        self.assertEqual(raw['state_before'], raw['state_after'])
        self.assertEqual(c.inventory(self.author), before)
        methods = [json.loads(data)['method'] for data in transport.writes]
        self.assertEqual(methods, list(c.LOOKUP_METHODS))
        self.assertNotIn('turn/start', methods)
        persisted = c.read_record(c.ref(self.root / 'zero-output/lookup.json'), 'lookup')
        c.validate_lookup(persisted, self.policy, self.sources, self.native)
        for field, changed in (('USER', 1), ('state_after', {})):
            with self.subTest(field=field), self.assertRaises(c.Hold):
                c.validate_lookup(dict(persisted, **{field: changed}), self.policy, self.sources, self.native)

    def run_mock_P1(self, shutdown_mutation=False, malformed=False):
        # Runtime engine fixture owns its entire copied root; the actual adopted
        # author root and all Root controls remain read-only.
        clone = self.root / 'owned author clone'
        shutil.copytree(self.author, clone, symlinks=True)
        old_root = str(self.author)
        def relocate(value):
            if type(value) is str:
                return value.replace(old_root, str(clone))
            if type(value) is list:
                return [relocate(item) for item in value]
            if type(value) is dict:
                return {key: relocate(item) for key, item in value.items()}
            return value
        native = relocate(self.native_data)
        native_ref = self.save('engine-native.json', native)
        state = c.inventory(clone)
        contract = c.read_record(self.contract)
        contract['expected_before'] = c.canonical_hash(state)
        plan = c.read_record(self.row_plan)
        plan['claim'] = str(c.claim_path(plan['branch_id'], plan['row_id'], self.root))
        plan['contract'] = self.save('engine-contract.json', contract)
        scope = dict(c.read_record(self.scope), root=str(clone), realroot=str(clone))
        scope['instruction_sources'] = [c.ref(Path(relocate(pin['path']))) for pin in scope['instruction_sources']]
        policy = c.read_record(self.policy)
        policy.update(session=c.session_for(str(clone)), session_sha256=c.canonical_hash(c.session_for(str(clone))), metadata_paths=c.required_metadata(scope))
        config, catalog, thread = relocate(self.mock_config), relocate(self.mock_catalog), relocate(self.mock_thread)
        # Replace the project key too; ordinary string relocation above only
        # transforms values, while native config maps use absolute path keys.
        config['config']['projects'] = {str(clone): {'trust_level': 'trusted'}}
        config['layers'][0]['config']['projects'] = {str(clone): {'trust_level': 'trusted'}}
        version = 'sha256:' + c.canonical_hash(config['layers'][0]['config'])
        config['layers'][0]['version'] = version
        origin = {'name': {'type': 'sessionFlags'}, 'version': version}
        config['origins'] = {'projects.' + str(clone) + '.trust_level': origin, 'agents.enabled': origin}
        graph = {'plan': plan, 'scope': scope, 'policy': policy, 'choice': c.read_record(self.choice),
                 'state': state, 'contract': contract, 'decision': c.read_record(self.upstream['decision']),
                 'command': self.command_value, 'root_review': {'common': self.common},
                 'common': dict(c.read_record(self.common), native_binding=native_ref), 'graph_pins': {}, 'anchor': self.anchor}
        engine_lookup = c.read_record(self.lookup)
        engine_lookup['native_facts']['configuration_identity'] = c.load_legacy().safe_config_identity(config)
        engine_lookup['native_facts']['native13'] = relocate(engine_lookup['native_facts']['native13'])
        engine_lookup['native_facts']['native_binding'] = native_ref
        graph['common']['lookup'] = self.save('engine-lookup.json', engine_lookup)
        spec = clone / contract['roles']['spec']
        def approve():
            spec.write_bytes(spec.read_bytes().replace(b'status: draft', b'status: approved', 1))
        late = clone / 'late-shutdown-write'
        scope_ref = self.save('engine-scope.json', scope)
        plan['scope'] = scope_ref
        plan_ref = self.save('engine-plan.json', plan)
        policy.update(scope=scope_ref, row_plan=plan_ref)
        policy_ref = self.save('engine-policy.json', policy)
        zero_transport = MockNativeTransport(config, catalog, thread)
        zero_rpc = op.RecordingRPC(zero_transport, time.monotonic() + 180)
        for frame in c.read_record(self.lookup)['wire']:
            if frame['direction'] == 'request':
                request_value = relocate(frame['payload'])
                if request_value['method'] == 'initialized': zero_rpc.send('initialized', notification=True)
                else: zero_rpc.call(request_value['method'], request_value.get('params'))
        engine_lookup.update(policy=policy_ref, wire=zero_rpc.wire, state_before=state, state_after=state)
        identity = c.load_legacy().safe_config_identity(config)
        engine_lookup['native_facts']['config_facts'] = c.load_legacy().config_facts(config, lambda value: {})
        installed = [{'name':name,'path':str(clone/'.agents/skills'/name/'SKILL.md'),'realpath':str(clone/'.agents/skills'/name/'SKILL.md')}
                     for name in sorted(c.load_legacy().MANUAL | c.load_legacy().AUTO)]
        proof=c.load_legacy().validate_catalog(catalog,installed,engine_lookup['native_facts']['config_facts'],'live')
        engine_lookup['native_facts']['catalog_proof']=proof
        engine_lookup['native_facts']['bundles'] = [dict(frame, config=identity, catalog=catalog,catalog_proof=proof,
            state_sha256=c.canonical_hash(state)) for frame in engine_lookup['native_facts']['bundles']]
        graph['common']['lookup'] = self.save('engine-lookup-final.json', engine_lookup)
        plan_ref = self.save('engine-plan.json', plan)
        common = dict(graph['common'], row_plan=plan_ref, policy=policy_ref,
                      predecessor_state_sha256=c.canonical_hash(state))
        common_ref = self.save('engine-common.json', common)
        review = dict(c.read_record(self.review), common=common_ref, row_plan=plan_ref, policy=policy_ref)
        review_ref = self.save('engine-review.json', review)
        release_ref = self.save('engine-release.json', dict(c.read_record(self.release), root_review=review_ref, common=common_ref))
        graph.update(common=common, root_review=review, command=dict(self.command_value, release=release_ref))
        transport = MockNativeTransport(config, catalog, thread, on_turn=approve,
            on_close=(lambda: late.write_text('late process mutation')) if shutdown_mutation else None)
        if malformed:
            original_write = transport.write
            def malformed_write(data, deadline):
                original_write(data, deadline)
                if json.loads(data).get('method') == 'turn/start':
                    transport.responses = [{'id': json.loads(data)['id'], 'result': 1}]
            transport.write = malformed_write
        before_actual = c.inventory(self.author)
        with mock.patch.object(c, 'validate_graph', return_value=graph), self.mocked_mdm_helpers(), \
             mock.patch.object(op, 'enforce_control_scope'):
            raw = op.run_released(self.command, self.command['sha256'], transport_factory=lambda *args: transport)
        self.assertEqual(c.inventory(self.author), before_actual)
        return raw, graph, clone

    def test_shutdown_mutation_is_captured_after_close_and_claim_retained(self):
        raw, graph, clone = self.run_mock_P1(shutdown_mutation=True)
        plan = graph['plan']
        self.assertEqual(raw['failure']['primary']['stage'], 'post-close-final-state-or-metadata', raw['failure'])
        self.assertIn('late-shutdown-write', raw['state_after'])
        self.assertEqual(raw['state_after'], c.inventory(clone))
        self.assertIs(raw['business_PASS'], False)
        self.assertTrue(Path(plan['claim']).exists())
        self.assertTrue((Path(plan['output']) / 'context.json').is_file())
        self.assertEqual(raw['accounting']['actual'], 1)


    def test_malformed_actual_turn_response_still_persists_claim_and_raw(self):
        raw, graph, clone = self.run_mock_P1(malformed=True)
        self.assertIsNotNone(raw['failure'])
        self.assertEqual(raw['accounting']['status'], 'UNKNOWN')
        self.assertTrue(Path(graph['plan']['claim']).is_file())
        self.assertEqual(c.read_record(c.ref(Path(graph['plan']['output']) / 'context.json')), raw)

    def test_complete_P1_adjudication_and_accepted_history_from_actual_bootstrap(self):
        raw, graph, clone = self.run_mock_P1()
        self.assertIsNone(raw['failure'], raw['failure'])
        plan = graph['plan']
        context = c.ref(Path(plan['output']) / 'context.json')
        capture = next(x['capture'] for x in raw['samples'] if x.get('phase') == 'review-target-capture')
        request = graph['decision']['request'].encode()
        input_slice = {'kind': 'input', 'context': context, 'start': 0, 'end': len(request), 'sha256': c.digest(request)}
        predecessor = c.read_record(plan['predecessor'])
        question = c.read_record(predecessor['question'])
        old = c.decode(c.read_ref(predecessor['context']))
        old_wire = c.decode(c.read_ref(old['wire']))
        item = old_wire[question['wire_index']]['payload']['params']['item']
        question_slice = {'kind': 'wire', 'context': predecessor['context'], 'wire_index': question['wire_index'],
            'item_sha256': c.canonical_hash(item), 'field': 'text', 'start': 0,
            'end': len(item['text'].encode()), 'sha256': c.digest(item['text'].encode())}
        spec = graph['contract']['roles']['spec']; data = (clone / spec).read_bytes()
        artifact_slice = {'kind': 'artifact', 'capture': capture, 'path': spec,
            'start': 0, 'end': len(data), 'sha256': c.digest(data)}
        observations = {key: {'sources': [artifact_slice], 'judgment': 'Independent synthetic source-test judgment'}
                        for key in graph['contract']['obligations']}
        observations['actual_question']['sources'] = [question_slice]
        observations['separate_spec_decision']['sources'] = [input_slice]
        poststate = self.save('engine-poststate.json', raw['state_after'])
        adjudication = self.save('engine-adjudication.json', {'schema': 'postclosure-adjudication-v1',
            'context': context, 'row_contract': plan['contract'], 'poststate': poststate,
            'observations': observations, 'packet': None, 'capture': capture, 'projection': None})
        result_value = {'schema': 'postclosure-independent-result-v1', 'context': context,
            'review': self.text('engine-independent-review.txt'), 'adjudication': adjudication,
            'business_PASS': True, 'decision': 'ACCEPT_EXACT_D2_ROW'}
        result = self.save('engine-result.json', result_value)
        c.validate_adjudication(result_value, raw, plan, [])
        with mock.patch.object(c, 'CLAIM_ROOT', self.root):
            history = c.validate_history(c.LEGACY_PREFIX_SHA, [result], c.BRANCH_ID, self.sources)
        self.assertEqual(history['actual'], 75)
        self.assertFalse(history['blocked'])
        observations['separate_spec_decision']['sources'] = [artifact_slice]
        forged = self.save('forged-adjudication.json', dict(c.read_record(adjudication), observations=observations))
        with self.assertRaises(c.Hold):
            c.validate_adjudication(dict(result_value, adjudication=forged), raw, plan, [])


class MetadataAndZeroPolicyTests(TempCase):
    def test_absence_appearance_and_hash_only_auth_metadata(self):
        path=self.root/'auth.json'
        absent=c.metadata_receipt(path)
        self.assertFalse(absent['exists'])
        path.write_text('PRIVATE-CANARY-AUTH-BODY')
        observed=c.metadata_receipt(path)
        self.assertTrue(observed['exists']);self.assertNotIn('PRIVATE-CANARY',json.dumps(observed))
        self.assertEqual(observed['sha256'],c.digest(path.read_bytes()))
        with self.assertRaises(c.Hold):c.sample_metadata({str(path):absent})
        alias=self.root/'alias';alias.symlink_to(path)
        with self.assertRaises(c.Hold):c.metadata_receipt(alias)

    def test_P6_zero_policy_can_differ_only_by_unapplied_turn_permission(self):
        plan=self.plan('D2-tail/Git-AC9');plan_ref=self.save('P6-plan.json',plan)
        placeholder=self.text('native-proof')
        policy={'schema':'postclosure-process-policy-v1','row_plan':plan_ref,'scope':placeholder,'argv':['exact'],
            'session':{},'session_sha256':c.canonical_hash({}),'metadata_paths':{},'native_expectation':placeholder,
            'official_sources':[],'turn_permission':placeholder}
        business=self.save('P6-business-policy.json',policy)
        zero=self.save('P6-zero-policy.json',dict(policy,turn_permission=None))
        self.assertIsNone(c.lookup_policy_relation(zero,business)['turn_permission'])
        changed=self.save('P6-zero-drift.json',dict(policy,turn_permission=None,argv=['drift']))
        with self.assertRaises(c.Hold):c.lookup_policy_relation(changed,business)
        other_plan=self.save('P1-plan.json',self.plan())
        other=self.save('P1-policy.json',dict(policy,row_plan=other_plan))
        with self.assertRaises(c.Hold):c.lookup_policy_relation(zero,other)


class ProjectionConsumptionRegressionTests(unittest.TestCase):
    def test_matching_inline_bytes_cannot_rescue_missing_projected_file_reads(self):
        import postclosure_f1_test as f1
        case=f1.F1Case('test_p8_exact_no_git_projection_delivery_consumption_and_report')
        case.setUp()
        self.addCleanup(case.doCleanups)
        current, adjudication, source_result=case.reviewer()
        projection=c.read_record(adjudication['projection'])
        inline='\n'.join(c.read_ref(item['source']).decode('utf-8') for item in projection['files'])
        current['plan']['input']=case.record('decision',request=inline)
        # A valid filesystem delivery plus matching USER substrings cannot
        # replace successful complete actual model consumption.
        for frame in current['raw']['wire']:
            item=frame['payload'].get('params',{}).get('item',{})
            if item.get('type')=='commandExecution':item['command']='echo filenames only'
        with self.assertRaises(c.Hold):
            c.validate_review_projection(adjudication['projection'],source_result,c.read_record(source_result),case.packet,
                case.author,current,case.contexts,case.captures)


class LocalShipObjectiveTests(TempCase):
    def setUp(self):
        super().setUp()
        root = self.root / 'fixture'; root.mkdir(); self.fixture = root
        helper = '.agents/skills/ains-review-gate/scripts/route-review.sh'
        helper_bytes = (c.SOURCE / 'skills/ains-review-gate/scripts/route-review.sh').read_bytes()
        (root / 'local_pr.md').write_text('Actual MODEL local PR artifact')
        helper_path = root / helper; helper_path.parent.mkdir(parents=True); helper_path.write_bytes(helper_bytes); helper_path.chmod(0o755)
        self.contract = {'schema': 'postclosure-contract-v1', **{key: None for key in c.SCHEMAS['contract'].split()}}
        self.contract.update(row_id='D2-tail/local-ship', expected_before='0'*64, roles={'local_pr': 'local_pr.md'}, authored=['local_pr.md'])
        common = {'schema': 'postclosure-common-v1', **{key:self.text('ref-'+key) for key in c.SCHEMAS['common'].split()}}
        common.update(predecessor_state_sha256='0'*64,history_sha256='0'*64,input_sha256='0'*64,
            product_manifest=c.ref(c.CONTROL_ROOT / 'composite-source/manifest.json'))
        command = '/bin/zsh -lc ' + shlex.quote(helper + ' docs/ains/human-review-rules main')
        item = {'id':'H','type':'commandExecution','command':command,'cwd':str(root),'status':'completed','exitCode':10,'aggregatedOutput':'HUMAN_REQUIRED: actual installed helper result\n'}
        final = {'type':'agentMessage','id':'final','phase':'final_answer','text':'Actual local PR artifact at local_pr.md'}
        raw = {'root':str(root),'common':self.save('common.json',common),'thread_id':'t','turn_id':'u','state_before':{},'wire':[
            {'direction':'response','payload':{'method':'item/completed','params':{'threadId':'t','turnId':'u','item':item}}},
            {'direction':'response','payload':{'method':'item/completed','params':{'threadId':'t','turnId':'u','item':final}}}]}
        self.reference=self.text('context-ref'); self.capture=self.text('capture-ref')
        self.entry={'reference':self.reference,'raw':raw,'plan':{'row_id':'D2-tail/local-ship','contract':self.save('contract.json',self.contract)},
            'capture_ref':self.capture,'state':c.inventory(root),'content':{helper:helper_bytes,'local_pr.md':(root/'local_pr.md').read_bytes()}}
        output=item['aggregatedOutput'].encode()
        self.hslice={'kind':'wire','context':self.reference,'wire_index':0,'item_sha256':c.canonical_hash(item),
            'field':'aggregatedOutput','start':0,'end':len(output),'sha256':c.digest(output)}
        data=self.entry['content']['local_pr.md']
        self.prslice={'kind':'artifact','capture':self.capture,'path':'local_pr.md','start':0,'end':len(data),'sha256':c.digest(data)}
        self.adjudication={'observations':{'installed_HUMAN_REQUIRED_10':{'sources':[self.hslice]},'local_pr_complete':{'sources':[self.prslice]}}}

    def validate(self, entry=None, adjudication=None):
        entry=entry or self.entry
        return c.validate_local_ship_adjudication(adjudication or self.adjudication,entry,
            {c.canonical_hash(self.reference):entry},{c.canonical_hash(self.capture):entry})

    def test_actual_current_helper_and_captured_model_PR_are_required(self):
        self.assertTrue(self.validate())
        for mutation in ('missing-command','cwd','wrong-helper','wrong-exit','boolean-exit','truncated','unrelated-H-source','missing-PR','unrelated-PR-source','no-model-provenance','helper-bytes'):
            entry=copy.deepcopy(self.entry); adjudication=copy.deepcopy(self.adjudication)
            item=entry['raw']['wire'][0]['payload']['params']['item']
            if mutation=='missing-command':entry['raw']['wire']=entry['raw']['wire'][1:]
            elif mutation=='cwd':item['cwd']=str(self.root)
            elif mutation=='wrong-helper':item['command']='echo HUMAN_REQUIRED'
            elif mutation=='wrong-exit':item['exitCode']=0
            elif mutation=='boolean-exit':item['exitCode']=True
            elif mutation=='truncated':item['outputTruncated']=True
            elif mutation=='unrelated-H-source':adjudication['observations']['installed_HUMAN_REQUIRED_10']['sources']=[self.prslice]
            elif mutation=='missing-PR':entry['content'].pop('local_pr.md')
            elif mutation=='unrelated-PR-source':adjudication['observations']['local_pr_complete']['sources']=[self.hslice]
            elif mutation=='no-model-provenance':entry['raw']['wire'][1]['payload']['params']['item']['text']='No path supplied'
            else:entry['content']['.agents/skills/ains-review-gate/scripts/route-review.sh']+=b'tamper'
            with self.subTest(mutation=mutation),self.assertRaises(c.Hold):self.validate(entry,adjudication)


class ReviewReturnTests(TempCase):
    def test_actual_reviewer_report_returns_to_unchanged_author_root_only(self):
        author_root = self.root / 'author'; author_root.mkdir()
        (author_root / 'app.py').write_text('actual source')
        author_state = c.inventory(author_root)
        report = 'review.md'; report_bytes = b'Actual completed independent reviewer verdict'
        (author_root / report).write_bytes(report_bytes)
        source = self.text('actual-reviewer-verdict.txt', report_bytes.decode())
        source_capture = self.text('reviewer-capture-ref.txt')
        p7_context = self.text('p7-context-ref.txt')
        p8_context = self.text('p8-context-ref.txt')
        p7 = self.save('p7-result.json', {'schema': 'postclosure-independent-result-v1', 'context': p7_context,
            'review': source, 'adjudication': source, 'business_PASS': True, 'decision': 'ACCEPT_EXACT_D2_ROW'})
        p8 = self.save('p8-result.json', {'schema': 'postclosure-independent-result-v1', 'context': p8_context,
            'review': source, 'adjudication': source, 'business_PASS': True, 'decision': 'ACCEPT_EXACT_D2_ROW'})
        p9_contract = {'schema': 'postclosure-contract-v1', **{key: None for key in c.SCHEMAS['contract'].split()}}
        p9_contract['row_id'] = 'D2-tail/local-ship'
        p9_contract['expected_before'] = c.canonical_hash(author_state)
        p9_contract['roles'] = {'review': report}
        p8_contract = dict(p9_contract, roles={'review': None})
        reviewer = {'plan': {'row_id': 'D2-tail/independent-review', 'contract': self.save('p8-contract.json', p8_contract)},
            'capture_ref': source_capture, 'content': {}, 'state': {},
            'raw': {'state_before': {}, 'wire': [{'direction': 'response', 'payload': {'method': 'item/completed',
             'params': {'item': {'type': 'agentMessage', 'phase': 'final_answer', 'text': report_bytes.decode()}}}}]}}
        author = {'plan': {'row_id': 'D2-tail/unavailable-review'}, 'state': author_state, 'raw': {'root': str(author_root)}}
        state = c.inventory(author_root)
        scope = {'root': str(author_root), 'realroot': str(author_root)}
        plan = {'contract': self.save('p9-contract.json', p9_contract)}
        bridge = {'schema': 'postclosure-review-return-v1', 'source_result': p8, 'source_capture': source_capture,
            'destination_root': str(author_root), 'destination_state': self.save('destination-state.json', state),
            'report': report, 'source': source}
        contexts = {c.canonical_hash(p7_context): author}
        def validate(value=bridge, actual=state):
            return c.validate_review_return(self.save('return.json', value), [p7, p8], c.read_record(p8), reviewer, scope, actual, plan, contexts)
        self.assertTrue(validate())
        for change in ('fabricated-report', 'unrelated-app-change', 'wrong-mode', 'different-root'):
            value = copy.deepcopy(bridge); altered = copy.deepcopy(state)
            if change == 'fabricated-report': value['source'] = self.text('fabricated.txt', 'Root invented verdict')
            elif change == 'unrelated-app-change': altered['app.py']['sha256'] = '0' * 64
            elif change == 'wrong-mode': altered[report]['mode'] = '0o755'
            else: value['destination_root'] = str(self.root)
            value['destination_state'] = self.save('altered-state.json', altered)
            with self.subTest(change=change), self.assertRaises(c.Hold): validate(value, altered)


if __name__ == '__main__':
    unittest.main()
