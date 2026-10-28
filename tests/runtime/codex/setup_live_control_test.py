"""Temporary mock-only tests: no native executable/model/fixture/C claim."""
import contextlib
import os
from pathlib import Path
import tempfile
import traceback
import types
import unittest
from unittest.mock import patch

import setup_live_control as live


class MockClock:
    def __init__(self):
        self.now = 10.0
        self.action = None

    def __call__(self):
        return self.now

    def pause(self, seconds):
        self.now += seconds
        if self.action is not None:
            action, self.action = self.action, None
            action()


class LiveControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name).resolve()
        self.directory.chmod(0o700)
        self.native = live.operator.current_native()
        self.clock = MockClock()
        self.exchange = live.RootExchange(self.directory, self.native,
                                          self.clock, self.clock.pause)

    def tearDown(self):
        self.temp.cleanup()

    def respond(self, value, kind=None, predecessor=None):
        observations = sorted(self.directory.glob('root-*.observation.json'))
        path = observations[-1]
        document, raw = live.read_json(path)
        # This emulates a separate Root tool AFTER reading retained receipt.
        live.save_new(self.directory, document['decision_file'], dict(
            kind=document['kind'] if kind is None else kind,
            predecessor_sha256=live.setup.digest(raw) if predecessor is None else predecessor,
            value=value))

    def test_inert_entry(self):
        with patch.object(live, 'run_released', side_effect=AssertionError('must remain inert')):
            self.assertEqual(live.main([]), 0)
        self.assertEqual(list(self.directory.iterdir()), [])

    def materialization_command(self):
        proof = self.directory / 'proof.json'
        live.save_new(self.directory, proof.name, {'retained': 'mock evidence'})
        reference = live.core.ref(proof)
        adoption = dict(decision='ADOPT_PROPOSED_SETUP_BRANCH_MATERIALIZATION_DATA_ONLY',
            roots={'N7-B-default': str(self.directory / 'new-fixture')},
            composite_manifest=reference,
            **{key: reference for key in ('materializer_result', 'materializer_index',
                'independent_verifier', 'independent_report', 'independent_index')})
        live.save_new(self.directory, 'new-materialization-adoption.json', adoption)
        return dict(adoption=live.core.ref(self.directory / 'new-materialization-adoption.json'),
            branch='N7-B-default', root=adoption['roots']['N7-B-default'], manifest=reference)

    def test_fresh_materialization_keeps_old_adoption_immutable(self):
        command = self.materialization_command()
        old = b'{"historical":"must remain unchanged"}\n'
        previous = self.directory / 'setup-branches-materialization-adoption.json'
        previous.write_bytes(old)
        with patch.object(live, 'C', self.directory):
            live.validate_materialization_adoption(command)
        self.assertEqual(previous.read_bytes(), old)

    def test_materialization_adoption_cannot_expand_root_or_control_scope(self):
        command = self.materialization_command()
        with patch.object(live, 'C', self.directory):
            with self.assertRaises(live.setup.Hold):
                live.validate_materialization_adoption(dict(command, root=str(self.directory)))
        with patch.object(live, 'C', self.directory / 'different-control-root'):
            with self.assertRaises(live.setup.Hold):
                live.validate_materialization_adoption(command)

    def test_explicit_cli_routes_exact_external_command_without_self_authorization(self):
        reference = str(self.directory / 'external-command.json')
        digest = 'a' * 64
        with patch.object(live, 'run_released') as run:
            self.assertEqual(live.main(['--command-ref', reference, '--command-sha256', digest]), 0)
        run.assert_called_once_with(dict(path=reference, sha256=digest), digest)

    def test_actual_answer_waits_for_retained_observation(self):
        seen = []
        def root_tool():
            document, _ = live.read_json(self.directory / 'root-001.observation.json')
            seen.append(document['observation']['completed_turn']['output'])
            self.respond({'body': 'Keep the existing settings.'})
        self.clock.action = root_tool
        predecessor = dict(row='row', thread_id='t', turn_id='turn',
                           output_sha256='a' * 64, question_sha256='b' * 64)
        receipt = dict(turn_id='turn', output=b'Which settings should remain?')
        decision = self.exchange.root('answer', predecessor, {'receipt': receipt}, 11)
        self.assertEqual(seen, ['Which settings should remain?'])
        self.assertEqual(decision['body'], b'Keep the existing settings.')
        self.assertEqual(decision['predecessor'], predecessor)
        self.assertTrue((self.directory / 'root-001.accepted.json').exists())

    def test_no_answer_without_completed_receipt(self):
        with self.assertRaisesRegex(live.setup.Hold, 'completed receipt'):
            self.exchange.root('answer', {}, None, 11)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_exact_root_judgment_byte_spans(self):
        output = '説明。Which setting?'.encode()
        start = len('説明。'.encode())
        self.clock.action = lambda: self.respond(dict(question_spans=[[start, len(output)]],
                                                       configured_command=None, receipt=None))
        result = self.exchange.judge(dict(output=output, turn_id='owned'), [], {}, {}, 11)
        self.assertEqual(result['questions'], (b'Which setting?',))
        observed, _ = live.read_json(self.directory / 'root-001.observation.json')
        self.assertEqual(observed['observation']['output'], output.decode())

    def test_mismatched_hash_or_kind_stops(self):
        for kwargs in ({'predecessor': '0' * 64}, {'kind': 'future-answer'}):
            with self.subTest(kwargs=kwargs):
                self.clock.action = lambda kwargs=kwargs: self.respond({}, **kwargs)
                with self.assertRaisesRegex(live.setup.Hold, 'identity mismatch'):
                    self.exchange.request('judge', {}, 11)
        self.assertEqual(len(list(self.directory.glob('*.accepted.json'))), 0)

    def test_prewritten_future_file_forbidden(self):
        live.save_new(self.directory, 'root-001.decision.json', {})
        with self.assertRaisesRegex(live.setup.Hold, 'prewritten'):
            self.exchange.request('answer', {}, 11)
        self.assertFalse((self.directory / 'root-001.observation.json').exists())

    def test_deadline_rejects_even_valid_late_file(self):
        def late_root():
            self.respond({'body': 'late'})
            self.clock.now = 11
        self.clock.action = late_root
        with self.assertRaisesRegex(live.setup.Hold, 'deadline'):
            self.exchange.request('premise', {}, 11)
        self.assertFalse((self.directory / 'root-001.accepted.json').exists())

    def test_absent_root_answer_uses_original_finite_deadline(self):
        with self.assertRaisesRegex(live.setup.Hold, 'deadline'):
            self.exchange.request('judge', {}, 10.2)
        self.assertLessEqual(self.clock.now, 10.21)

    def test_unknown_root_schema_and_invalid_utf8_span_hold(self):
        self.clock.action = lambda: self.respond({'future': 'answer'})
        with self.assertRaisesRegex(live.setup.Hold, 'closed schema'):
            self.exchange.judge(dict(output=b'Question?', turn_id='owned'), [], {}, {}, 11)
        self.clock.action = lambda: self.respond(dict(question_spans=[[1, 2]],
                                                       configured_command=None, receipt=None))
        with self.assertRaisesRegex(live.setup.Hold, 'UTF-8'):
            self.exchange.judge(dict(output='設定?'.encode(), turn_id='owned'), [], {}, {}, 11)

    def test_control_identity_change_holds(self):
        self.exchange.identity = (0, 0)
        with self.assertRaisesRegex(live.setup.Hold, 'identity changed'):
            self.exchange.request('judge', {}, 11)

    def test_secret_wire_values_never_persist(self):
        secret = 'unclassified_account_startup_value_12345'
        retention = live.Retention(self.directory, self.native)
        for method in ('config/read', 'account/updated', 'startup/unknown'):
            retention.wire('server', live.setup.canonical(dict(method=method,
                params=dict(opaque=secret, api_key='sk-proj-' + 'a' * 30))))
        identity = self.native.safe_config_identity(dict(config=dict(api_key=secret)))
        retention.write('config-identity', dict(identity))
        stored = b''.join(path.read_bytes() for path in self.directory.iterdir())
        self.assertNotIn(secret.encode(), stored)
        self.assertNotIn(b'sk-proj-', stored)
        self.assertIn(b'sha256', stored)

    def test_rejected_side_effect_diagnostics_are_hash_only_not_acceptance(self):
        secret = 'unclassified_secret_read_command_98765'
        retention = live.Retention(self.directory, self.native)
        item = dict(type='commandExecution', id=secret, command=secret,
                    cwd='/outside/' + secret, status=secret, exitCode=1,
                    aggregatedOutput=secret, extra=secret)
        event = dict(stage='started', reason_code='OVERLAP_NOT_READ_ONLY',
            thread_id=secret, turn_id=secret, item=item, active_items=[item],
            wire_index=5, raw_sha256='a' * 64)
        retention.side_effect_diagnostic(event, self.directory)
        stored = b''.join(path.read_bytes() for path in self.directory.iterdir())
        self.assertNotIn(secret.encode(), stored)
        self.assertNotIn(b'aggregatedOutput', stored)
        document, _ = live.read_json(self.directory / 'event-00001.json')
        self.assertEqual(document['kind'], 'side-effect-diagnostic')
        self.assertTrue(document['value']['diagnostic_only'])
        self.assertEqual(document['value']['item']['cwd_relation'], 'outside-root')
        self.assertEqual(document['value']['item']['status'], 'unknown')
        self.assertEqual(document['value']['raw_sha256'], 'a' * 64)
        self.assertFalse(document['runtime_PASS'])

    def test_secret_business_text_holds_before_persistence(self):
        with self.assertRaisesRegex(live.setup.Hold, 'secret redaction'):
            self.exchange.judge(dict(output=b'api_key=private-value', turn_id='owned'), [], {}, {}, 11)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_exclusive_records_and_link_rejection(self):
        live.save_new(self.directory, 'record.json', {'value': 1})
        with self.assertRaises(FileExistsError):
            live.save_new(self.directory, 'record.json', {'value': 2})
        os.link(self.directory / 'record.json', self.directory / 'linked.json')
        with self.assertRaisesRegex(live.setup.Hold, 'unaliased'):
            live.read_json(self.directory / 'linked.json')

    def test_external_command_digest_mismatch_does_not_claim(self):
        with self.assertRaisesRegex(live.setup.Hold, 'externally supplied exact'):
            live.released(dict(path=str(self.directory / 'missing'), sha256='a' * 64), 'b' * 64)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_actual_grants_not_instruction_declarations(self):
        root = self.directory / 'fixture'
        root.mkdir()
        snapshot = dict(runtimeWorkspaceRoots=[str(root)], approvalPolicy='never',
            approvalsReviewer='user', sandbox=dict(type='workspaceWrite', writableRoots=[],
                networkAccess=False, excludeTmpdirEnvVar=False, excludeSlashTmp=False),
            activePermissionProfile=None, disabledPluginIds=[], multiAgentMode='explicitRequestOnly',
            instructionSources=['a declaration claiming no tool access'])
        result = live.grants({'snapshot': snapshot}, self.directory / 'separate-control')
        self.assertEqual(result['runtimeWorkspaceRoots'], [str(root)])
        self.assertNotIn('instructionSources', result)
        snapshot['runtimeWorkspaceRoots'] = [str(self.directory)]
        with self.assertRaisesRegex(live.setup.Hold, 'expose protected'):
            live.grants({'snapshot': snapshot}, self.directory)

    def test_partial_delivery_charge_retained_before_mock_write(self):
        gate = live.setup.TurnGate('N7-B-default', frozenset())
        gate.open_context('thread')
        prepared = gate.prepare(live.setup.SETUP_INPUT)
        gate.begin(prepared, self.clock())
        runner = types.SimpleNamespace(gate=gate)
        class PartialTransport:
            def write(inner, raw, deadline):
                records = sorted(self.directory.glob('event-*'))
                first, _ = live.read_json(records[0])
                self.assertEqual(first['kind'], 'attempt-before-write')
                self.assertEqual(first['value']['delivery'], 'UNKNOWN')
                raise OSError('opaque_secret_not_retained')
        wrapper = live.ObservedTransport(PartialTransport(), runner,
            live.Retention(self.directory, self.native), self.native, {})
        raw = live.setup.canonical(dict(id=1, method='turn/start', params={})) + b'\n'
        with self.assertRaises(OSError):
            wrapper.write(raw, 11)
        self.assertEqual(gate.accounting()['actual_charged_turns'], 1)
        stored = b''.join(path.read_bytes() for path in self.directory.iterdir())
        self.assertNotIn(b'opaque_secret', stored)
        self.assertNotIn(b'LOCAL_WRITE_COMPLETE', stored)

    def test_mock_drain_records_original_hash_and_forwards_frames(self):
        raw = live.setup.canonical(dict(method='startup/unknown', params={'secret': 'opaque'})) + b'\n'
        transport = types.SimpleNamespace(drain=lambda deadline: [raw])
        wrapper = live.ObservedTransport(transport, None,
            live.Retention(self.directory, self.native), self.native, {})
        self.assertEqual(wrapper.drain(11), [raw])
        record, _ = live.read_json(next(self.directory.glob('event-*')))
        self.assertEqual(record['value']['sha256'], live.setup.digest(raw))
        self.assertNotIn('opaque', str(record))

    def test_actual_native_mismatch_cannot_replace_supplied_expectations(self):
        expected = dict(model='released-model', modelProvider='openai', serviceTier='default',
            reasoningEffort=None, cwd=str(self.directory), runtimeWorkspaceRoots=[str(self.directory)],
            instructionSources=[], approvalPolicy='never', approvalsReviewer='user',
            sandbox=dict(type='workspaceWrite', writableRoots=[], networkAccess=False,
                         excludeTmpdirEnvVar=False, excludeSlashTmp=False),
            activePermissionProfile=None, disabledPluginIds=[], multiAgentMode='explicitRequestOnly')
        request = dict(cwd=str(self.directory), model='released-model', approvalPolicy='never',
                       sandbox='workspace-write', ephemeral=True)
        wrapper = live.ObservedTransport(types.SimpleNamespace(write=lambda raw, deadline: None),
            None, live.Retention(self.directory, self.native), self.native, {'expected': expected})
        wrapper.write(live.setup.canonical(dict(id=1, method='thread/start', params=request)), 11)
        actual = dict(expected, model='unreleased-model')
        actual['thread'] = dict(id='owned', **{key: actual[key] for key in
                                               ('cwd', 'model', 'modelProvider', 'reasoningEffort')})
        with self.assertRaisesRegex(RuntimeError, 'snapshot mismatch'):
            wrapper.observe(live.setup.canonical(dict(id=1, result=actual)))
        self.assertIsNone(wrapper.actual)
        self.assertEqual(expected['model'], 'released-model')

    def test_failure_before_operator_has_truthful_final_record(self):
        live.Retention(self.directory, self.native).finish(None, ValueError('private detail'))
        record, raw = live.read_json(next(self.directory.glob('event-*')))
        self.assertEqual(record['value']['primary_failure'], 'ValueError')
        self.assertEqual(record['value']['attempts'], [])
        self.assertIsNone(record['value']['accounting'])
        self.assertFalse(record['value']['final_state_observed'])
        self.assertNotIn(b'private detail', raw)

    def test_constructor_cleanup_diagnostic_survives_without_original_tail(self):
        from owned_transport import _CleanupReceipt
        error = RuntimeError('private-constructor-error')
        error.cleanup_receipt = _CleanupReceipt(ownership={'pid': 123}, reaped=False,
            cleanup_errors=[dict(operation='terminate', exception_type='PermissionError', errno=1)],
            tail_frames=[b'private-tail-canary'])
        live.Retention(self.directory, self.native).finish(None, error)
        record, raw = live.read_json(next(self.directory.glob('event-*')))
        cleanup = record['value']['constructor_cleanup']
        self.assertEqual(cleanup['cleanup_errors'][0]['errno'], 1)
        self.assertFalse(cleanup['reaped'])
        self.assertNotIn(b'private-tail-canary', raw)
        self.assertNotIn(b'private-constructor-error', raw)

    def test_final_keeps_primary_secondary_and_unknown_charge(self):
        gate = live.setup.TurnGate('N7-B-default', frozenset())
        gate.open_context('thread')
        prepared = gate.prepare(live.setup.SETUP_INPUT)
        gate.begin(prepared, 10)
        gate._stop('OSError')
        runner = types.SimpleNamespace(gate=gate, cleanup_failures=['TimeoutError'],
            reserved=[prepared['claim_key']], closures=[dict(reaped=True, tail_frames=[b'secret tail'])],
            samples=[])
        live.Retention(self.directory, self.native).finish(runner, OSError('secret exception'))
        record, raw = live.read_json(next(self.directory.glob('event-*')))
        result = record['value']
        self.assertEqual(result['primary_failure'], 'OSError')
        self.assertEqual(result['secondary_failures'], ['TimeoutError'])
        self.assertEqual(result['accounting']['actual_charged_turns'], 1)
        self.assertEqual(result['attempts'][0]['delivery'], 'UNKNOWN')
        self.assertFalse(result['final_state_observed'])
        self.assertFalse(record['runtime_PASS'])
        self.assertNotIn(b'secret', raw)

    def test_mock_factory_constructor_cleanup_failures_reach_durable_final(self):
        claims = self.directory / 'claims'
        claims.mkdir(mode=0o700)
        command = dict(output=str(self.directory), root=str(self.directory), claims=str(claims),
                       branch='N7-B-default', model='released-model', expected={}, argv=[],
                       initial_state={'path': 'synthetic-only', 'sha256': 'a' * 64})
        primary = RuntimeError('safe factory failure')
        primary._postclosure_cleanup_failures = ['OSError', 'TimeoutError']
        helpers = {'activation_r3': types.SimpleNamespace(inventory=lambda root: [])}
        bound = contextlib.nullcontext((None, (helpers, [])))
        with patch.object(live, 'released', return_value=(command, self.native, {}, {})), \
             patch.object(live.core, 'bound_helpers', return_value=bound), \
             patch.object(live.core, 'read_ref', return_value=b'{}'), \
             patch.object(live, 'BusinessProfile'), \
             patch.object(live.operator, 'process_transport', side_effect=primary) as factory:
            with self.assertRaises(RuntimeError) as caught:
                live.run_released({'path': 'mock-only-command', 'sha256': 'a' * 64}, 'a' * 64)
        self.assertIs(caught.exception, primary)
        factory.assert_called_once()
        records = [live.read_json(path)[0] for path in self.directory.glob('event-*')]
        final = next(record['value'] for record in records if record['kind'] == 'final')
        self.assertEqual(final['secondary_failures'], ['OSError', 'TimeoutError'])
        self.assertEqual(final['accounting']['actual_charged_turns'], 0)
        self.assertEqual(list(claims.iterdir()), [])

    def test_constructor_and_runner_cleanup_codes_both_retained(self):
        primary = OSError('private exception message')
        primary._postclosure_cleanup_failures = ['ProcessLookupError']
        runner = types.SimpleNamespace(gate=live.setup.TurnGate('N7-B-default', frozenset()),
            cleanup_failures=['TimeoutError'], samples=[], reserved=[], closures=[])
        retention = live.Retention(self.directory, self.native)
        retention.finish(runner, primary)
        retention.finish(None, primary)
        first, raw = live.read_json(self.directory / 'event-00001.json')
        second, _ = live.read_json(self.directory / 'event-00002.json')
        self.assertEqual(first['value']['secondary_failures'], ['TimeoutError', 'ProcessLookupError'])
        self.assertEqual(second['value']['secondary_failures'], ['ProcessLookupError'])
        self.assertNotIn(b'private exception message', raw)

    def test_final_retention_failure_visible_in_normal_rendering_preserving_primary(self):
        primary = ValueError('safe primary failure')
        command = dict(output=str(self.directory), root=str(self.directory), claims='mock-only')
        with patch.object(live, 'released', return_value=(command, self.native, {}, {})), \
             patch.object(live.operator, 'DonorClaims', side_effect=primary), \
             patch.object(live.Retention, 'finish', side_effect=OSError('unclassified_secret_detail')):
            with self.assertRaises(ValueError) as caught:
                live.run_released({'path': 'mock-only-command', 'sha256': 'a' * 64}, 'a' * 64)
        self.assertIs(caught.exception, primary)
        rendered = ''.join(traceback.format_exception(caught.exception))
        self.assertIn('stage=final-retention failure=OSError', rendered)
        self.assertNotIn('unclassified_secret_detail', rendered)

class BusinessProfileTests(unittest.TestCase):
    AGENTS = b'# Project\n\n## Agent skills\n- Test: `python3 -m unittest discover -s tests -v`\n\n'
    CLAUDE = b'# Claude\n\n## Agent skills\n- Test: `python3 -m unittest discover -s tests -v`\n\n## Other\nKEEP\n'
    MIGRATED = b'# Claude\n\n@AGENTS.md\n\n## Other\nKEEP\n'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'AGENTS.md').write_bytes(self.AGENTS)
        (self.root / 'CLAUDE.md').write_bytes(self.CLAUDE)
        for name in ('AGENTS.md', 'CLAUDE.md'):
            (self.root / name).chmod(0o644)
        self.initial = live.setup.full_state(self.root, {})
        self.profile = live.BusinessProfile('Duplicate-B-copy', self.root, self.initial,
                                            live.operator.current_native())

    def state(self):
        return live.setup.full_state(self.root, {'actual': True})

    def test_only_exact_duplicate_span_is_allowed_and_requires_acceptance(self):
        before = self.state()
        self.profile.validate(before, 'premise')
        (self.root / 'CLAUDE.md').write_bytes(self.MIGRATED)
        after = self.state()
        self.profile.validate(after, 'initial')
        proof = self.profile.transition('initial', before, after)
        self.assertEqual(proof['after']['CLAUDE.md'], self.MIGRATED.decode())
        with self.assertRaisesRegex(live.setup.Hold, 'FULLSTATE'):
            self.profile.validate(after, 'ack')
        self.profile.accept(proof, after, live.setup.digest(live.setup.canonical(proof)))
        self.profile.validate(after, 'ack')
        self.profile.validate(after, 'repeat')

    def test_unrelated_bytes_agents_grants_and_wrong_phase_hold(self):
        before = self.state()
        self.profile.validate(before, 'premise')
        for body in (self.MIGRATED.replace(b'KEEP', b'LOST'), self.MIGRATED + b'@AGENTS.md\n'):
            (self.root / 'CLAUDE.md').write_bytes(body)
            with self.assertRaises(live.setup.Hold):
                self.profile.validate(self.state(), 'initial')
        (self.root / 'CLAUDE.md').write_bytes(self.MIGRATED)
        with self.assertRaises(live.setup.Hold):
            self.profile.validate(self.state(), 'repeat')
        with self.assertRaises(live.setup.Hold):
            self.profile.validate(live.setup.full_state(self.root, {'actual': False}), 'initial')
        (self.root / 'AGENTS.md').write_bytes(self.AGENTS + b'changed')
        with self.assertRaises(live.setup.Hold):
            self.profile.validate(self.state(), 'initial')

    def test_n7_instruction_appearance_and_identical_replacement_hold(self):
        (self.root / 'AGENTS.md').unlink(); (self.root / 'CLAUDE.md').unlink()
        initial = live.setup.full_state(self.root, {})
        profile = live.BusinessProfile('N7-B-default', self.root, initial,
                                       live.operator.current_native())
        profile.validate(self.state(), 'first')
        (self.root / 'CLAUDE.md').write_bytes(b'new')
        with self.assertRaises(live.setup.Hold):
            profile.validate(self.state(), 'first')
        (self.root / 'CLAUDE.md').unlink()
        # Duplicate repeat rejects a byte-identical inode replacement too.
        (self.root / 'AGENTS.md').write_bytes(self.AGENTS)
        (self.root / 'CLAUDE.md').write_bytes(self.CLAUDE)
        fresh = live.BusinessProfile('Duplicate-B-copy', self.root,
            live.setup.full_state(self.root, {}), live.operator.current_native())
        fresh.validate(self.state(), 'premise')
        temporary = self.root / 'replacement'
        temporary.write_bytes(self.CLAUDE); temporary.chmod(0o644)
        temporary.replace(self.root / 'CLAUDE.md')
        with self.assertRaises(live.setup.Hold):
            fresh.validate(self.state(), 'repeat')

    def test_unprefixed_python_and_compounds_hold_despite_clean_endpoint(self):
        for command in ('python3 -c pass', 'PYTHONDONTWRITEBYTECODE=1 python3 -c pass',
                        'cat CLAUDE.md; python3 -c pass', 'sh -c true'):
            with self.assertRaises(live.setup.Hold):
                self.profile.classify_command(dict(command=command, cwd=str(self.root),
                                                  status='completed', exitCode=0))
        self.assertEqual(self.profile.classify_command(dict(command=live.setup.EXECUTED_COMMAND,
            cwd=str(self.root), status='completed', exitCode=0)), 'configured-test')
        self.assertEqual(self.profile.classify_command(dict(command='cat CLAUDE.md',
            cwd=str(self.root), status='completed', exitCode=0)), 'read')

    def test_business_acceptance_hash_cannot_be_boolean_or_stale(self):
        before = self.state(); self.profile.validate(before, 'premise')
        (self.root / 'CLAUDE.md').write_bytes(self.MIGRATED)
        after = self.state(); proof = self.profile.transition('initial', before, after)
        for wrong in (True, '0' * 64):
            with self.assertRaises(live.setup.Hold):
                self.profile.accept(proof, after, wrong)

    def test_topology_probes_keep_true_and_false_predicate_semantics(self):
        for command, exit_code in (('test -L AGENTS.md', 1),
                                   ('test -L CLAUDE.md', 1),
                                   ('[ AGENTS.md -ef CLAUDE.md ]', 1),
                                   ('test AGENTS.md -ef AGENTS.md', 0),
                                   ("/bin/zsh -lc 'test -L AGENTS.md'", 1)):
            with self.subTest(command=command):
                self.assertEqual(self.profile.classify_command(dict(command=command,
                    cwd=str(self.root), status='completed', exitCode=exit_code)), 'topology-read')
                with self.assertRaises(live.setup.Hold):
                    self.profile.classify_command(dict(command=command, cwd=str(self.root),
                        status='completed', exitCode=1 - exit_code))

    def test_read_intent_classifies_starts_without_accepting_completion(self):
        for command, expected in (('cat AGENTS.md', 'read'),
                                  ('test -L AGENTS.md', 'topology-read'),
                                  ('[ AGENTS.md -ef CLAUDE.md ]', 'topology-read')):
            with self.subTest(command=command):
                item = dict(type='commandExecution', command=command, cwd=str(self.root),
                            status='inProgress', exitCode=None)
                self.assertEqual(self.profile.read_intent(item), expected)
                with self.assertRaises(live.setup.Hold):
                    self.profile.classify_command(item)
        for command in (live.setup.EXECUTED_COMMAND, 'python3 -c pass',
                        'cat AGENTS.md; cat CLAUDE.md', 'cat ../outside',
                        'cat absent.md', 'cat AGENTS.md > CLAUDE.md'):
            with self.subTest(command=command):
                self.assertIsNone(self.profile.read_intent(dict(type='commandExecution',
                    command=command, cwd=str(self.root))))
        self.assertIsNone(self.profile.read_intent(dict(type='fileChange',
            command='cat AGENTS.md', cwd=str(self.root))))
        self.assertIsNone(self.profile.read_intent(dict(type='commandExecution',
            command='cat AGENTS.md', cwd='/outside')))

    def test_false_topology_predicate_accepts_native_failed_status(self):
        self.assertEqual(self.profile.classify_command(dict(command='test -L AGENTS.md',
            cwd=str(self.root), status='failed', exitCode=1)), 'topology-read')
        for command, code in (('cat AGENTS.md', 0), ('cat AGENTS.md', 1),
                              ('test AGENTS.md -ef AGENTS.md', 0)):
            with self.subTest(command=command, code=code), self.assertRaises(live.setup.Hold):
                self.profile.classify_command(dict(command=command, cwd=str(self.root),
                    status='failed', exitCode=code))

    def test_topology_probes_admit_absence_without_scope_expansion(self):
        (self.root / 'AGENTS.md').unlink(); (self.root / 'CLAUDE.md').unlink()
        profile = live.BusinessProfile('N7-B-default', self.root,
            live.setup.full_state(self.root, {}), live.operator.current_native())
        for command in ('test -L AGENTS.md', '[ AGENTS.md -ef CLAUDE.md ]'):
            self.assertEqual(profile.classify_command(dict(command=command,
                cwd=str(self.root), status='completed', exitCode=1)), 'topology-read')
        for command, code in (('test -L ../AGENTS.md', 1), ('test -L /etc/passwd', 1),
                              ('test -L AGENTS.md || true', 0), ('[ AGENTS.md -ef CLAUDE.md', 1),
                              ('test -e AGENTS.md', 1), ('test -L AGENTS.md', 2),
                              ('cat CLAUDE.md', 1)):
            with self.subTest(command=command), self.assertRaises(live.setup.Hold):
                profile.classify_command(dict(command=command, cwd=str(self.root),
                    status='completed', exitCode=code))

    def side_effect(self, item, index=0, state=None):
        payload = dict(method='item/completed', params=dict(threadId='owned-thread',
                       turnId='owned-turn', item=item))
        raw = live.setup.canonical(payload) + b'\n'
        event = dict(thread_id='owned-thread', turn_id='owned-turn', item=item,
                     wire_index=index, raw_sha256=live.setup.digest(raw))
        self.profile.observe(event, 'initial', self.state() if state is None else state)
        return dict(payload=payload, raw=raw)

    def receipt(self):
        return dict(thread_id='owned-thread', turn_id='owned-turn', request_index=0,
                    output=b'Consolidated the duplicate section.')

    def test_observation_requires_exact_current_turn_complete_coverage(self):
        self.profile.validate(self.state(), 'premise')
        command = dict(type='commandExecution', id='read', command='cat AGENTS.md',
                       cwd=str(self.root), status='completed', exitCode=0)
        record = self.side_effect(command)
        receipt = self.receipt()
        self.assertEqual(len(self.profile.evidence(receipt, [record])), 1)
        self.assertEqual(self.profile.evidence(dict(receipt, turn_id='other'), []), [])
        self.profile.observations.clear()
        with self.assertRaisesRegex(live.setup.Hold, 'coverage'):
            self.profile.evidence(receipt, [record])
        self.side_effect(command)
        altered = dict(record, raw=record['raw'] + b' ')
        with self.assertRaisesRegex(live.setup.Hold, 'coverage'):
            self.profile.evidence(receipt, [altered])
        with self.assertRaisesRegex(live.setup.Hold, 'duplicate side effect'):
            self.side_effect(command)

    def test_metadata_exempts_only_business_slot_and_projection_keeps_other_slots(self):
        expected = {str(self.root / name): live.core.metadata_receipt(self.root / name)
                    for name in ('AGENTS.md', 'CLAUDE.md')}
        (self.root / 'CLAUDE.md').write_bytes(self.MIGRATED)
        self.profile.sample_metadata(expected)
        (self.root / 'AGENTS.md').write_bytes(self.AGENTS + b'drift')
        with self.assertRaisesRegex(RuntimeError, 'immutable metadata drift'):
            self.profile.sample_metadata(expected)
        candidate = {'fixture_metadata': {'CLAUDE.md': 'mutable', 'AGENTS.md': 'fixed'},
                     'native': {'instructionSources': ['independent']},
                     'environment': {'sha256': 'fixed'}}
        projected = self.profile.projection(candidate)
        self.assertEqual(projected['fixture_metadata'], {'AGENTS.md': 'fixed'})
        self.assertEqual(projected['native'], candidate['native'])
        self.assertEqual(projected['environment'], candidate['environment'])
        self.assertIn('CLAUDE.md', candidate['fixture_metadata'])

    def test_root_sees_actual_files_and_observed_change_before_acceptance(self):
        before = self.state(); self.profile.validate(before, 'premise')
        (self.root / 'CLAUDE.md').write_bytes(self.MIGRATED)
        after = self.state()
        change = dict(type='fileChange', id='change', status='completed',
                      changes=[dict(path=str(self.root / 'CLAUDE.md'), diff='exact business delta')])
        records = [self.side_effect(change)]
        with tempfile.TemporaryDirectory() as control:
            directory = Path(control).resolve(); directory.chmod(0o700)
            clock = MockClock()
            exchange = live.RootExchange(directory, live.operator.current_native(), clock, clock.pause)
            exchange.profile, exchange.phase = self.profile, lambda: 'initial'
            seen = []
            def root_decision():
                document, raw = live.read_json(directory / 'root-001.observation.json')
                observation = document['observation']; seen.append(observation)
                proof = observation['business_transition']
                live.save_new(directory, document['decision_file'], dict(kind='judge',
                    predecessor_sha256=live.setup.digest(raw), value=dict(question_spans=[],
                    configured_command=live.setup.CONFIGURED_COMMAND, receipt=None,
                    business_acceptance=live.setup.digest(live.setup.canonical(proof)))))
            clock.action = root_decision
            exchange.judge(self.receipt(), records, before, after, 11)
            self.assertEqual(seen[0]['business_transition']['after']['CLAUDE.md'], self.MIGRATED.decode())
            self.assertEqual(seen[0]['actual_side_effects'][0]['item'], change)
            self.profile.validate(after, 'ack')
            self.assertTrue((directory / 'root-001.accepted.json').exists())

    def test_boolean_scope_approval_cannot_substitute_actual_evidence(self):
        self.profile.validate(self.state(), 'premise')
        command = dict(type='commandExecution', id='read', command='cat AGENTS.md',
                       cwd=str(self.root), status='completed', exitCode=0)
        record = self.side_effect(command)
        with tempfile.TemporaryDirectory() as control:
            directory = Path(control).resolve(); directory.chmod(0o700)
            exchange = live.RootExchange(directory, live.operator.current_native())
            exchange.profile = self.profile
            with patch.object(exchange, 'request', return_value=True):
                with self.assertRaises(live.setup.Hold):
                    exchange.command_scope([command], self.receipt(), [record],
                                           self.state(), self.state(), 999999999)
            self.profile.observations.clear()
            with patch.object(exchange, 'request', return_value={'observation_sha256': '0' * 64}) as request:
                with self.assertRaisesRegex(live.setup.Hold, 'coverage'):
                    exchange.command_scope([command], self.receipt(), [record],
                                           self.state(), self.state(), 999999999)
                request.assert_not_called()

    def test_changed_business_without_completed_filechange_holds_before_accept(self):
        before = self.state(); self.profile.validate(before, 'premise')
        (self.root / 'CLAUDE.md').write_bytes(self.MIGRATED)
        after = self.state()
        exchange = live.RootExchange(self.root, live.operator.current_native())
        exchange.profile, exchange.phase = self.profile, lambda: 'initial'
        proof = self.profile.transition('initial', before, after)
        value = dict(question_spans=[], configured_command=live.setup.CONFIGURED_COMMAND,
                     receipt=None, business_acceptance=live.setup.digest(live.setup.canonical(proof)))
        with patch.object(exchange, 'request', return_value=value):
            with self.assertRaisesRegex(live.setup.Hold, 'observed file change'):
                exchange.judge(self.receipt(), [], before, after, 999999999)
        with self.assertRaises(live.setup.Hold):
            self.profile.validate(after, 'ack')

    def test_mutable_business_slot_cannot_be_an_immutable_native_contributor(self):
        scope = {'instruction_sources': [{'path': str(self.root / 'AGENTS.md')}]}
        self.profile.validate_contributors(scope, {'config': {}})
        for key in ('model_instructions_file', 'instructions_file', 'developer_instructions_file'):
            with self.assertRaisesRegex(live.setup.Hold, 'native instruction contributor'):
                self.profile.validate_contributors(scope, {'config': {key: str(self.root / 'CLAUDE.md')}})
        with self.assertRaises(live.setup.Hold):
            self.profile.validate_contributors({'instruction_sources': [{'path': str(self.root / 'CLAUDE.md')}]},
                                               {'config': {}})


if __name__ == '__main__':
    unittest.main()
