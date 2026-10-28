"""Mock-only execution tests: owned temp files, fake clock/transport, no native child."""
import ast
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import remaining_evidence_operator as op


class Clock:
    def __init__(self):
        self.now, self.sequence = 10.0, 0

    def __call__(self):
        return self.now

    def ns(self):
        self.sequence += 1
        return int(self.now * 1000000000) + self.sequence


class FakeTransport:
    """Original JSON bytes supplied to the real frozen RecordingRPC."""
    pid = 1234

    def __init__(self, clock, terminal_delay=0, action=None, turn_error=None, close_error=False):
        self.clock, self.delay, self.action = clock, terminal_delay, action
        self.turn_error, self.close_error = turn_error, close_error
        self.queue, self.requests, self.deadlines = [], [], []
        self.closed = 0

    def write(self, raw, deadline):
        request = json.loads(raw)
        self.requests.append(request)
        if 'id' not in request:
            return
        method = request['method']
        result = {'thread': {'id': 'owned-thread'}} if method == 'thread/start' else {}
        if method == 'config/read':
            result = {'config': {}, 'layers': [], 'origins': {}}
        if method == 'turn/start':
            if self.turn_error is not None:
                raise self.turn_error
            result = {'turn': {'id': 'owned-turn', 'status': 'inProgress'}}
        self.queue.append((0, {'id': request['id'], 'result': result}, None))
        if method == 'turn/start':
            self.queue.append((0, {'method': 'turn/started', 'params': {
                'threadId': 'owned-thread', 'turn': {'id': 'owned-turn', 'status': 'inProgress'}}}, None))
            self.queue.append((self.delay, {'method': 'turn/completed', 'params': {
                'threadId': 'owned-thread', 'turn': {'id': 'owned-turn', 'status': 'completed'}}}, self.action))

    def read(self, deadline):
        self.deadlines.append(deadline)
        if not self.queue:
            raise EOFError('mock EOF')
        delay, value, action = self.queue.pop(0)
        if self.clock.now + delay >= deadline:
            self.clock.now = deadline
            raise TimeoutError('mock deadline')
        self.clock.now += delay + 0.001
        if action is not None:
            action()
        return (json.dumps(value) + '\n').encode()

    def drain(self, deadline):
        return []

    def close(self):
        self.closed += 1
        return dict(reaped=True, returncode=1 if self.close_error else 0,
                    cleanup_finished=True, group_state='absent', cleanup_errors=[],
                    termination_attempted=False,
                    cleanup_started_monotonic=self.clock(), cleanup_finished_monotonic=self.clock(),
                    cleanup_deadline=self.clock() + 2,
                    stderr_complete=True, stdout_complete=True,
                    stderr_sha256=op.core.digest(b''), stderr_bytes=0,
                    partial_stdout_bytes=0, tail_frames=[], watchdog_fired=False,
                    watchdog_error=None)


class MockSession:
    """Replace native semantics only; real RPC lifecycle/counts/capture/transition run."""
    def __init__(self, graph, rpc, environment, helpers, raw):
        self.graph, self.rpc, self.raw, self.environment = graph, rpc, raw, environment
        self.native = None
        self.candidate = dict(schema='postclosure-invariant-anchor-v1', product_manifest=graph['manifest'],
            environment={'facts': op.core.load_legacy().environment_facts(environment),
                         'sha256': op.contract.environment_identity(environment)['full_sha256']})

    def bundle(self, phase):
        first = self.rpc.call('config/read', {'includeLayers': True, 'cwd': self.graph['scope']['root']})
        self.rpc.call('skills/list', {'cwds': [self.graph['scope']['root']], 'forceReload': True})
        self.rpc.call('config/read', {'includeLayers': True, 'cwd': self.graph['scope']['root']})
        frame = dict(config=op.core.load_legacy().safe_config_identity(first), metadata_sha256='a' * 64,
                     state_sha256=op.core.canonical_hash(op.core.inventory(Path(self.graph['scope']['root']))))
        self.raw['samples'].append(dict(phase=phase, frame=frame))
        return frame, first

    def start_thread(self, config):
        self.rpc.call('thread/start', dict(cwd=self.graph['scope']['root'], model='mock-model',
                      approvalPolicy='never', sandbox='workspace-write', ephemeral=True))
        self.native = dict(thread_id=self.rpc.thread_id, snapshot={
            'runtimeWorkspaceRoots': [self.graph['scope']['root']],
            'sandbox': {'type': 'workspaceWrite', 'writableRoots': [], 'networkAccess': False},
            'activePermissionProfile': None})
        op.check_grants(self.native, self.graph['scope']['root'])

    def metadata(self):
        return {}

    def check_environment(self):
        return None


class OperatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()
        self.root = self.directory / 'author root'; self.root.mkdir()
        self.control = self.directory / 'controls'; self.control.mkdir(mode=0o700)
        self.clock = Clock()
        (self.root / 'spec.md').write_bytes(b'---\nstatus: approved\n---\nAC1\n')
        (self.root / 'tasks.md').write_bytes(b'---\nstatus: draft\n---\n- [ ] T1 AC1\n')
        self.serial = 0
        self.graph = self.make_graph()
        self.claim = self.control / 'claim.json'

    def put(self, value):
        self.serial += 1
        path = self.control / ('data-%03d.json' % self.serial)
        path.write_text(json.dumps(value))
        return op.core.ref(path)

    def test_saved_zero_roundtrip_preserves_hashes_without_environment_literals(self):
        secret = 'private-environment-value-must-not-persist-42571'
        with patch.dict(os.environ, {'AINS_TEST_PRIVATE_VALUE': secret}):
            self.graph['expected_environment'] = op.contract.environment_identity(dict(os.environ))
            baseline, _ = self.execute(FakeTransport(self.clock), observe=True)
            expected = copy.deepcopy(self.graph['expected_environment'])
        stored = json.loads((self.control / 'out/baseline.json').read_text())
        self.assertEqual(stored['environment'], baseline['environment'])
        self.assertEqual(stored['invariant']['environment'], baseline['invariant']['environment'])
        op.contract.validate_current_environment(stored['environment'], expected)
        self.assertNotIn(secret.encode(), b''.join(p.read_bytes() for p in
            (self.control / 'out').rglob('*') if p.is_file()))

    def test_environment_literal_cannot_enter_the_typed_receipt_exception(self):
        baseline, _ = self.execute(FakeTransport(self.clock), observe=True)
        baseline['environment']['raw_environment'] = {'private': 'must never persist'}
        path = self.control / 'forbidden-receipt.json'
        with self.assertRaises(op.core.Hold):
            op.save_record(path, baseline)
        self.assertFalse(path.exists())

    def make_graph(self):
        pin = self.put({'mock': True})
        scope = dict(schema='postclosure-scope-v1', scope_id='owned-mock-root', root=str(self.root),
            realroot=str(self.root), topology='author-git', materialization=pin,
            instruction_sources=[], install=[], process_choice=pin)
        scope_ref = self.put(scope)
        state = op.core.inventory(self.root)
        roles = dict(spec='spec.md', tasks='tasks.md', application=[], tests=[], callers=[],
                     progress=[], packet=[], review=None, local_pr=None, off=None)
        contract = dict(schema='postclosure-contract-v1', row_id='D2-tail/plan-approval', roles=roles,
            authored=['tasks.md'], derived=[], immutable_paths=['spec.md'],
            expected_before=op.core.canonical_hash(state), expected_after=None,
            obligations=['actual_plan_question', 'separate_plan_decision', 'tasks_content_identical', 'tasks_approved'],
            evidence={}, git_profile=None, cache_profile=None, capability_profile=None, tasks_progress=None)
        plan = dict(schema='postclosure-row-plan-v1', branch_id='remaining-mock', row_id='D2-tail/plan-approval',
            donor_slot='R7/spec/6', scope=scope_ref, predecessor=pin, predecessor_review=pin,
            contract=self.put(contract), input=pin, source_set=pin, admission=pin,
            output=str(self.control / 'out'), claim=str(self.control / 'claim.json'),
            limits=op.core.LIMITS, feasibility=None)
        configuration = op.core.load_legacy().safe_config_identity({'config': {}, 'layers': [], 'origins': {}})
        baseline = dict(wire=[{'direction': 'request', 'payload': {'id': 1, 'method': 'config/read'}},
            {'direction': 'response', 'payload': {'id': 1, 'result': configuration}}], invariant={})
        return dict(command_ref=pin, command={}, campaign=pin, baseline_ref=pin, baseline=baseline,
            scope_ref=scope_ref, scope=scope, policy={'argv': ['mock-only-native']}, native={},
            manifest=pin, source_set=pin, plan=plan, contract=contract,
            decision={'request': 'Approve only this draft status.'}, input='Approve only this draft status.',
            output=str(self.control / 'out'), graph_pins={}, state=state,
            expected_environment=op.contract.environment_identity(dict(os.environ)), turn_overlay=None,
            release={'stage': 'D2-tail/plan-approval', 'donor': 'R7/spec/6'})

    def approve(self):
        path = self.root / 'tasks.md'
        path.write_bytes(path.read_bytes().replace(b'status: draft', b'status: approved', 1))

    def acquire(self, graph):
        with self.claim.open('x') as stream:
            stream.write('retained mock-only donor claim')
        return self.claim

    def execute(self, transport, observe=False, session=MockSession, factory_error=None):
        graph = copy.deepcopy(self.graph)
        if observe:
            graph.update(plan=None, contract=None, baseline=None, baseline_ref=None)
        method = 'validate_observation_command' if observe else 'validate_release'
        factory_calls = []
        def factory(argv, root, environment, deadline):
            factory_calls.append((argv, root, dict(environment), deadline))
            if factory_error is not None:
                raise factory_error
            return transport
        with patch.object(op.contract, method, return_value=graph), \
             patch.object(op.contract, 'acquire_donor_claim', side_effect=self.acquire), \
             patch.object(op.core, 'bound_helpers', return_value=contextlib.nullcontext((None, ({}, {})))), \
             patch.object(op, 'Session', session):
            result = (op.observe if observe else op.run_stage)(graph['command_ref'], graph['command_ref']['sha256'],
                transport_factory=factory, clock=self.clock, monotonic_ns=self.clock.ns)
        return result, factory_calls

    def test_no_arguments_are_inert(self):
        with patch.object(op, 'observe') as observe, patch.object(op, 'run_stage') as run, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(op.main([]), 0)
        observe.assert_not_called(); run.assert_not_called()

    def test_cli_failure_reports_nonzero_without_wire_or_success_claim(self):
        result = dict(failure={'primary': {'exception_type': 'TimeoutError'}},
                      accounting={'actual': 1, 'charged': 1}, wire='must not be printed')
        output = io.StringIO()
        with patch.object(op, 'run_stage', return_value=result) as run, contextlib.redirect_stdout(output):
            code = op.main(['--run-stage', '--command', '/mock-command.json',
                            '--command-sha256', 'a' * 64])
        self.assertEqual(code, 1)
        run.assert_called_once_with(dict(path='/mock-command.json', sha256='a' * 64), 'a' * 64)
        report = json.loads(output.getvalue())
        self.assertEqual(report['status'], 'FAILED')
        self.assertIs(report['business_PASS'], False)
        self.assertNotIn('wire', report)

    def test_current_bundle_cannot_reset_its_actual_invariant(self):
        graph = copy.deepcopy(self.graph)
        graph['baseline'] = None
        graph['policy']['metadata_paths'] = {}
        raw, native = {'samples': []}, Mock()
        helper = Mock(); helper.inventory.return_value = []; helper.mdm_forced.return_value = {}
        rpc = Mock(); rpc.wire = []; rpc.call.return_value = {'config': {}}
        environment = dict(os.environ)
        candidate = dict(schema='mock-actual-invariant', native={'same': True},
                         environment={'facts': {}, 'sha256': op.contract.environment_identity(environment)['full_sha256']})
        changed = copy.deepcopy(candidate); changed['native'] = {'same': False}
        with patch.object(op.core, 'load_legacy', return_value=native), \
             patch.object(op.core, 'validate_bundle', return_value={'config': {}}), \
             patch.object(op.core, 'invariant_projection', side_effect=[candidate, changed]):
            session = op.Session(graph, rpc, environment,
                {'activation_r3': helper, 'activation_closure_probe': Mock()}, raw)
            session.native = {'thread_id': 'owned-thread'}
            session.bundle('post-start-1')
            with self.assertRaisesRegex(op.core.Hold, 'invariant reset'):
                session.bundle('post-start-2')
        self.assertEqual(len(raw['samples']), 1)
        self.assertFalse(any(call.args[0] == 'turn/start' for call in rpc.call.call_args_list))

    def test_actual_single_input_long_silence_capture_and_status_only_transition(self):
        transport = FakeTransport(self.clock, terminal_delay=90, action=self.approve)
        raw, calls = self.execute(transport)
        self.assertIsNone(raw['failure'])
        self.assertEqual(raw['accounting'], dict(actual=1, attempted=1, charged=1, status='ACTUAL', accepted=1))
        self.assertEqual(transport.closed, 1)
        self.assertEqual(len([r for r in transport.requests if r['method'] == 'turn/start']), 1)
        self.assertTrue(self.claim.exists())
        self.assertIs(raw['business_PASS'], False)
        self.assertEqual(calls[0][2], dict(os.environ))
        self.assertEqual(calls[0][3], 188)
        self.assertTrue(Path(raw['capture']['path']).is_file())
        retained = op.core.decode(op.core.read_ref(raw['capture']))
        self.assertEqual(set(retained['files']), {'spec.md', 'tasks.md'})
        self.assertEqual([s['phase'] for s in raw['samples'] if s['phase'].startswith('artifact-byte')],
                         ['artifact-byte-captures-before', 'artifact-byte-captures-after'])

    def test_zero_observation_has_no_claim_or_user_and_retains_actual_baseline(self):
        transport = FakeTransport(self.clock)
        baseline, _ = self.execute(transport, observe=True)
        self.assertEqual(baseline['schema'], 'remaining-baseline-v1')
        self.assertEqual(baseline['accounting']['actual'], 0)
        self.assertFalse(self.claim.exists())
        self.assertFalse(any(request['method'] == 'turn/start' for request in transport.requests))
        self.assertEqual([r['method'] for r in transport.requests], list(op.core.LOOKUP_METHODS))
        op.contract.validate_record(baseline, 'baseline')
        raw = json.loads((self.control / 'out/observation.json').read_text())
        op.contract.validate_record(raw, 'observation')

    def test_absolute_timeout_retains_claim_and_failure_without_retry(self):
        transport = FakeTransport(self.clock, terminal_delay=190)
        raw, _ = self.execute(transport)
        self.assertIsNotNone(raw['failure'])
        self.assertEqual(raw['failure']['primary']['exception_type'], 'TimeoutError')
        self.assertTrue(self.claim.exists())
        self.assertEqual(transport.closed, 1)
        self.assertEqual(sum(r['method'] == 'turn/start' for r in transport.requests), 1)
        self.assertTrue(Path(raw['capture']['path']).is_file())

    def test_partial_write_is_unknown_not_refunded(self):
        transport = FakeTransport(self.clock, turn_error=OSError('mock partial write'))
        raw, _ = self.execute(transport)
        self.assertIsNotNone(raw['failure'])
        self.assertTrue(self.claim.exists())
        self.assertIsNone(raw['accounting']['actual'])
        self.assertEqual(raw['accounting']['attempted'], 1)
        self.assertEqual(raw['accounting']['status'], 'UNKNOWN')

    def test_unauthorized_file_change_is_retained_as_integrity_failure(self):
        def modify():
            self.approve(); (self.root / 'outside-contract.txt').write_text('mock unauthorized mutation')
        raw, _ = self.execute(FakeTransport(self.clock, action=modify))
        self.assertIsNotNone(raw['failure'])
        self.assertEqual(raw['failure']['primary']['stage'], 'transition')
        self.assertIn('outside-contract.txt', raw['state_after'])
        capture = op.core.decode(op.core.read_ref(raw['capture']))
        self.assertIn('outside-contract.txt', capture['files'])

    def test_close_failure_retains_actual_diagnostics(self):
        raw, _ = self.execute(FakeTransport(self.clock, action=self.approve, close_error=True))
        self.assertEqual(raw['close']['returncode'], 1)
        self.assertIsNotNone(raw['failure'])
        self.assertEqual(raw['failure']['primary']['stage'], 'owned-close')

    def test_reaped_zero_exit_cannot_hide_denied_cleanup_and_is_saved(self):
        class DeniedTransport(FakeTransport):
            def close(inner):
                receipt = super().close()
                receipt['cleanup_errors'] = [dict(operation='terminate',
                    exception_type='PermissionError', errno=1)]
                return receipt
        raw, _ = self.execute(DeniedTransport(self.clock, action=self.approve))
        self.assertEqual(raw['failure']['primary']['stage'], 'owned-close')
        saved = json.loads((self.control / 'out/observation.json').read_text())
        self.assertEqual(saved['close']['cleanup_errors'], raw['close']['cleanup_errors'])
        self.assertTrue(saved['close']['reaped'])
        self.assertIsNotNone(saved['failure'])

    def test_constructor_failure_keeps_owned_cleanup_diagnostic_without_tail(self):
        from owned_transport import _CleanupReceipt
        error = RuntimeError('private-constructor-error')
        error.cleanup_receipt = _CleanupReceipt(ownership={'pid': 123}, reaped=False,
            cleanup_errors=[dict(operation='terminate', exception_type='PermissionError', errno=1)],
            tail_frames=[b'private-tail-canary'])
        raw, _ = self.execute(None, factory_error=error)
        saved = (self.control / 'out/observation.json').read_text()
        self.assertEqual(raw['close']['cleanup_errors'][0]['errno'], 1)
        self.assertIsNotNone(raw['failure'])
        self.assertNotIn('private-tail-canary', saved)
        self.assertNotIn('private-constructor-error', saved)

    def test_foreign_native_grants_and_controls_are_rejected(self):
        native = dict(snapshot=dict(runtimeWorkspaceRoots=[str(self.root)],
            sandbox=dict(type='workspaceWrite', writableRoots=[], networkAccess=False),
            activePermissionProfile=None))
        op.check_grants(native, self.root)
        for key, value in (('runtimeWorkspaceRoots', [str(self.directory)]),
                           ('sandbox', dict(type='workspaceWrite', writableRoots=[str(self.control)], networkAccess=False))):
            changed = copy.deepcopy(native); changed['snapshot'][key] = value
            with self.assertRaises(op.core.Hold):
                op.check_grants(changed, self.root)

    def test_entry_uses_external_digest_and_never_old_graph_history(self):
        with patch.object(op.contract, 'validate_release', side_effect=op.core.Hold('mock rejection')) as validate:
            with self.assertRaises(op.core.Hold):
                op.run_stage(self.graph['command_ref'], 'b' * 64,
                             transport_factory=lambda *args: self.fail('must not launch'))
        validate.assert_called_once_with(self.graph['command_ref'], 'b' * 64)
        tree = ast.parse(Path(op.__file__).read_text())
        forbidden = {'validate_graph', 'validate_history', 'validate_adjudication', 'validate_f1_adjudication',
                     'run_released', 'produce_lookup'}
        self.assertFalse({n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and
                          isinstance(n.func, ast.Attribute)} & forbidden)

    def test_environment_and_prestate_drift_stop_before_claim_or_launch(self):
        self.graph['expected_environment'] = op.contract.environment_identity(dict(os.environ, OTHER='different'))
        with self.assertRaises(op.core.Hold):
            self.execute(FakeTransport(self.clock))
        self.assertFalse(self.claim.exists())
        self.assertFalse((self.control / 'out').exists())
        self.graph['expected_environment'] = op.contract.environment_identity(dict(os.environ))
        (self.root / 'tasks.md').write_bytes(b'foreign changed state')
        with self.assertRaises(op.core.Hold):
            self.execute(FakeTransport(self.clock))
        self.assertFalse(self.claim.exists())

    def test_current_context_environment_cannot_change_even_its_nonce(self):
        environment = dict(os.environ)
        native = Mock()
        helper = Mock()
        helper.inventory.return_value = []
        with patch.object(op.core, 'load_legacy', return_value=native):
            session = op.Session(self.graph, Mock(), environment,
                                 {'activation_r3': helper}, {'samples': []})
        with patch.dict(os.environ, {'CODEX_TOOL_CALL_ID': 'changed-inside-same-context'}):
            with self.assertRaises(op.core.Hold):
                session.check_environment()
        session.environment['CODEX_TOOL_CALL_ID'] = 'changed-child-map'
        with self.assertRaises(op.core.Hold):
            session.check_environment()

    def test_invariant_ignores_only_full_hash_after_environment_comparator(self):
        expected = dict(schema='mock-invariant', native={'roots': ['same']},
                        environment={'facts': {'interpreter': 'same'}, 'sha256': 'a' * 64})
        actual = copy.deepcopy(expected); actual['environment']['sha256'] = 'b' * 64
        op.same_invariant(actual, expected)
        for changed in (dict(actual, native={'roots': ['outside']}),
                        dict(actual, environment={'facts': {'interpreter': 'changed'}, 'sha256': 'b' * 64})):
            with self.assertRaises(op.core.Hold):
                op.same_invariant(changed, expected)

    def test_cache_and_off_hooks_retain_actual_bytes_and_thread_guard_proofs(self):
        command = 'python3 -m unittest discover -v'
        cache_ref, git_ref = self.put({'mock': 'cache'}), self.put({'mock': 'git'})
        graph = copy.deepcopy(self.graph)
        graph['contract'].update(cache_profile=cache_ref, git_profile=git_ref)
        graph['contract']['roles']['off'] = 'off.json'
        cache = {'row_id': 'D2-tail/Git-AC9'}
        git = {'off_path': 'off.json', 'verification_commands': []}
        profiles = {cache_ref['path']: cache, git_ref['path']: git}
        rpc = types.SimpleNamespace(command_items={})
        version = dict(source='tasks.md', bytes=(self.root / 'tasks.md').read_bytes(),
                       mtime_ns=1, size=(self.root / 'tasks.md').stat().st_size,
                       event_index=7, relation='mock post-command source')
        with patch.object(op.core, 'read_record', side_effect=lambda pin, kind: profiles[pin['path']]):
            capture = op.ProfileCapture(graph, rpc, self.control, dict(os.environ))
        (self.root / 'off.json').write_bytes(b'{"enabled":false}\n')
        event = dict(method='item/completed', params={'item': dict(type='commandExecution',
            id='observed', command=command, cwd=str(self.root), status='completed', exitCode=0)})
        with patch.object(op.core, 'allowed_cache_commands', return_value=[command]), \
             patch.object(op.core, 'capture_cache_versions', return_value=[version]), \
             patch.object(op.core, 'git_command_kind', return_value=None):
            capture.observe(event, 7)
        self.assertEqual(capture.versions, [version])
        retained = capture.samples[0]['versions'][0]['capture']
        self.assertEqual(op.core.read_ref(retained), version['bytes'])
        self.assertEqual(capture.off_samples[0]['event_index'], 7)
        self.assertEqual(op.core.read_ref(capture.off_samples[0]['capture']), b'{"enabled":false}\n')
        cache_proof, git_proof = object(), object()
        after = op.core.inventory(self.root)
        with patch.object(op.cache_payload, 'validate_derived_caches_replay', return_value=cache_proof) as cache_guard, \
             patch.object(op.core, 'validate_git_rollback', return_value=git_proof) as git_guard, \
             patch.object(op.packet_replay, 'validate_transition', return_value=True) as transition:
            capture.validate_transition(after, {}, {}, [event], None)
        self.assertIs(transition.call_args.kwargs['cache_proof'], cache_proof)
        self.assertIs(transition.call_args.kwargs['git_proof'], git_proof)
        self.assertIs(git_guard.call_args.args[-2], cache_proof)
        self.assertEqual(cache_guard.call_args.args[3], [version])

    def test_failed_cache_proof_blocks_transition(self):
        graph = copy.deepcopy(self.graph)
        graph['contract']['cache_profile'] = self.put({'mock': True})
        with patch.object(op.core, 'read_record', return_value={'row_id': 'D2-tail/TDD-build'}):
            capture = op.ProfileCapture(graph, types.SimpleNamespace(command_items={}),
                                        self.control, dict(os.environ))
        with patch.object(op.cache_payload, 'validate_derived_caches_replay', side_effect=op.core.Hold('mock invalid cache')), \
             patch.object(op.packet_replay, 'validate_transition') as transition:
            with self.assertRaises(op.core.Hold):
                capture.validate_transition(self.graph['state'], {}, {}, [], None)
        transition.assert_not_called()

    def test_runtime_profile_accepts_actual_loader_caches_from_saved_p6(self):
        import remaining_evidence_replay as replay
        c, f = op.contract, op.core
        raw = c.read_record(dict(path=str(c.CONTROL_ROOT / 'post-TDD-P6-actual-r1/observation.json'),
                                 sha256=replay.OBSERVATION_SHA), 'observation')
        command = c.read_record(raw['command'], 'command')
        release = c.read_record(command['release'], 'stage-release')
        plan = f.read_record(release['plan'], 'row-plan')
        contract = f.read_record(plan['contract'], 'contract')
        previous = c.read_record(c.read_record(release['predecessor'], 'assessment')['observation'], 'observation')
        previous_capture = f.read_record(previous['capture'], 'review-capture')
        final_capture = f.read_record(raw['capture'], 'review-capture')
        before_bytes = {name: f.read_ref(pin) for name, pin in previous_capture['files'].items()}
        after_bytes = {name: f.read_ref(pin) for name, pin in final_capture['files'].items()}
        capture = op.ProfileCapture.__new__(op.ProfileCapture)
        capture.graph = dict(state=raw['state_before'], plan=plan, contract=contract)
        capture.cache = f.read_record(contract['cache_profile'], 'cache-profile')
        capture.git = f.read_record(contract['git_profile'], 'git-profile')
        capture.root = Path(raw['root'])
        capture.environment, capture.before_bytes = capture.cache['environment'], before_bytes
        capture.versions, capture.off_samples = [], []
        for sample in raw['samples']:
            if sample['phase'] == 'post-command-source-equivalence':
                capture.versions += [{**{k: v for k, v in item.items() if k != 'capture'},
                    'bytes': f.read_ref(item['capture'])} for item in sample['versions']]
            if sample['phase'] == 'P6-off-observation':
                capture.off_samples.append(sample['observation'])
        events = [item['payload'] for item in raw['wire'] if item['direction'] == 'response'
                  and 'id' not in item['payload']]
        names = [contract['roles']['spec'], contract['roles']['tasks']]
        with patch.object(capture, 'git_bytes', return_value=after_bytes), \
             patch.object(op.cache_payload, 'file_bytes', side_effect=lambda path:
                          (after_bytes[str(path.relative_to(capture.root))], None)), \
             patch.object(f, 'validate_derived_caches', side_effect=AssertionError('old false-negative verifier')):
            proof = capture.validate_transition(raw['state_after'],
                {name: before_bytes[name] for name in names},
                {name: after_bytes[name] for name in names}, events, None)
        self.assertEqual(proof['state_after_sha256'], f.canonical_hash(raw['state_after']))

    def test_runtime_profile_preserves_private_off_packet_copy_from_actual_p7(self):
        c, f = op.contract, op.core
        raw = c.read_record(f.ref(c.CONTROL_ROOT / 'post-TDD-P7-actual-r1/observation.json'), 'observation')
        release = c.read_record(c.read_record(raw['command'], 'command')['release'], 'stage-release')
        plan = f.read_record(release['plan'], 'row-plan')
        contract = f.read_record(plan['contract'], 'contract')
        final = f.read_record(raw['capture'], 'review-capture')
        content = {name: f.read_ref(pin) for name, pin in final['files'].items()}
        capture = op.ProfileCapture.__new__(op.ProfileCapture)
        capture.graph = dict(state=raw['state_before'], plan=plan, contract=contract)
        capture.root, capture.cache, capture.git = Path(raw['root']), None, None
        capability = f.decode(f.read_ref(f.ref(c.CONTINUATION / 'P7-capability-witness-r1/RESULT.json')))['capability']
        artifacts = {name: content[name] for name in (contract['roles']['spec'], contract['roles']['tasks'])}
        with self.assertRaisesRegex(f.Hold, 'authored artifact mode/kind'):
            f.validate_transition(plan, raw['state_before'], raw['state_after'], {},
                contents_before=artifacts, contents_after=artifacts, capability_proof=capability)
        original_read = Path.read_bytes
        def captured_read(path):
            return content[str(path.relative_to(capture.root))] if path.is_relative_to(capture.root) else original_read(path)
        with patch.object(Path, 'read_bytes', captured_read):
            result = capture.validate_transition(raw['state_after'], artifacts, artifacts, [], capability)
        self.assertEqual(result['state_after_sha256'], f.canonical_hash(raw['state_after']))
        self.assertIsNotNone(raw['failure'])

    def test_capability_proof_uses_actual_config_and_frozen_methods(self):
        graph = copy.deepcopy(self.graph)
        graph['contract']['capability_profile'] = self.put({'mock': True})
        profile, configuration, proof = {'mock': 'profile'}, {'config': 'actual-sample'}, object()
        with patch.object(op.core, 'read_record', return_value=profile):
            capture = op.ProfileCapture(graph, types.SimpleNamespace(command_items={}),
                                        self.control, dict(os.environ))
        with patch.object(op.core, 'validate_capability', return_value=proof) as guard:
            self.assertIs(capture.capability_proof(configuration), proof)
        guard.assert_called_once_with(profile, configuration, supplied_dynamic_tools=[],
                                      authorized_methods=op.RecordingRPC.METHODS)


if __name__ == '__main__':
    unittest.main()
