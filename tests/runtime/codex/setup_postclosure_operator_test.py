"""Synthetic mock transport only: no native process/model or real fixture writes."""
import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import setup_postclosure as s
import setup_postclosure_operator as o


def state(cache=False):
    records = [dict(path='.', kind='directory', mode=493, dev=1, ino=2, nlink=2),
               dict(path='settings', kind='file', mode=420, dev=1, ino=3,
                    nlink=1, size=1, sha256=s.digest(b'x'))]
    if cache:
        records.append(dict(path='__pycache__/x.pyc', kind='file', size=1,
                            sha256=s.digest(b'x'), dev=1, ino=4, nlink=1, mode=384))
    return dict(records=records, grants={'synthetic-only': True})


def command_receipt():
    return dict(command=s.EXECUTED_COMMAND, status='completed', exit_code=0,
                earlier_import_cache_writes=False, other_cache_writes=False)


class Clock:
    def __init__(self):
        self.now = 1
    def __call__(self):
        return self.now


class Transport:
    def __init__(self, spec, context, owner):
        self.spec, self.context, self.owner = spec, context, owner
        self.queue, self.writes = [], []
        self.turn = 0
        self.closed = False
        self.drain_extra = []

    def frame(self, obj):
        self.queue.append(s.canonical(obj) + b'\n')

    def event(self, method, **params):
        self.frame(dict(method=method, params=params))

    def write(self, raw, deadline):
        self.writes.append((raw, deadline))
        obj = s.decode(raw)
        method = obj['method']
        if method == 'initialized':
            return
        result = {}
        if method == 'thread/start':
            result = copy.deepcopy(self.spec['expected'])
            result['thread'] = dict(id='thread-' + str(self.context),
                **{k: result[k] for k in ('cwd', 'model', 'modelProvider', 'reasoningEffort')})
        if method == 'config/read':
            result = dict(config={}, layers=['synthetic'])
        if method == 'skills/list':
            result = dict(data=['synthetic'])
        if method == 'turn/start':
            self.turn += 1
            if self.owner.partial:
                raise OSError('synthetic partial delivery after prefix')
            turn_id = 'turn-%s-%s' % (self.context, self.turn)
            result = dict(turn=dict(id=turn_id))
        self.frame(dict(id=obj['id'], result=result))
        if method != 'turn/start':
            return
        if self.owner.expire:
            self.owner.clock.now = deadline
        thread = 'thread-' + str(self.context)
        self.event('turn/started', threadId=thread, turn=dict(id=turn_id))
        output, question, needs_command = self.owner.turn_plan(self.context, self.turn)
        if needs_command:
            item = dict(id='command-' + turn_id, type='commandExecution',
                        command=s.EXECUTED_COMMAND, cwd=self.spec['root'])
            self.event('item/started', threadId=thread, turnId=turn_id, item=item)
            self.event('item/completed', threadId=thread, turnId=turn_id,
                       item=dict(item, status='completed', exitCode=0))
        item = dict(id='message-' + turn_id, type='agentMessage', phase='final_answer')
        self.event('item/started', threadId=thread, turnId=turn_id, item=item)
        self.event('item/completed', threadId=thread,
                   turnId='foreign' if self.owner.foreign else turn_id,
                   item=dict(item, text=output.decode()))
        self.event('turn/completed', threadId=thread,
                   turn=dict(id=turn_id, status='completed', error=None))
        if self.owner.late:
            self.drain_extra.append(s.canonical(dict(method='item/agentMessage/delta',
                params=dict(threadId=thread, turnId=turn_id,
                            itemId=item['id'], delta='late'))) + b'\n')

    def read(self, deadline):
        if not self.queue:
            raise EOFError('synthetic empty transport')
        return self.queue.pop(0)

    def drain(self, deadline):
        result = self.queue + self.drain_extra
        self.queue, self.drain_extra = [], []
        return result

    def close(self):
        self.closed = True
        return dict(reaped=True, returncode=0, stderr_bytes=0,
                    cleanup_finished=True, group_state='absent', cleanup_errors=[],
                    termination_attempted=False,
                    cleanup_started_monotonic=self.owner.clock(),
                    cleanup_finished_monotonic=self.owner.clock(), cleanup_deadline=self.owner.clock() + 2,
                    stderr_complete=True, stdout_complete=True,
                    partial_stdout_bytes=0, watchdog_fired=False,
                    watchdog_error=None, tail_frames=[])


def rate_limits():
    return dict(rateLimits=dict(credits=dict(balance=None, hasCredits=False, unlimited=True),
        individualLimit=None, limitId='synthetic', limitName=None, normalModelSlug=None,
        planType='synthetic', primary=dict(resetsAt=100, usedPercent=1, windowDurationMins=300),
        rateLimitReachedType=None, secondary=None, spendControlReached=None))


def token_usage(thread, turn):
    breakdown = dict.fromkeys(('cacheWriteInputTokens', 'cachedInputTokens', 'inputTokens',
        'outputTokens', 'reasoningOutputTokens', 'totalTokens'), 0)
    return dict(threadId=thread, turnId=turn, tokenUsage=dict(last=breakdown,
        total=dict(breakdown), modelContextWindow=10000))


class ObservedTransport(Transport):
    """Finite native-shaped synthetic frames; no real trace bodies copied."""
    def write(self, raw, deadline):
        method = s.decode(raw)['method']
        super().write(raw, deadline)
        frame = lambda method, params: s.canonical(dict(method=method, params=params)) + b'\n'
        if method == 'initialize':
            self.queue[:0] = [frame('remoteControl/status/changed', dict(environmentId=None,
                installationId='synthetic', serverName='synthetic', status='disabled')),
                frame('account/updated', dict(authMode='synthetic', planType='synthetic'))]
        elif method == 'config/read':
            self.queue.insert(-1, frame('account/rateLimits/updated', rate_limits()))
        elif method == 'thread/start':
            actual = s.decode(self.queue[-1])['result']['thread']
            self.queue.append(frame('thread/started', dict(thread=actual)))
        elif method == 'turn/start':
            thread, turn = 'thread-' + str(self.context), 'turn-%s-%s' % (self.context, self.turn)
            self.queue.insert(1, frame('thread/status/changed',
                dict(threadId=thread, status=dict(type='active', activeFlags=[]))))
            self.queue.insert(3, frame('thread/tokenUsage/updated', token_usage(thread, turn)))
            self.queue.insert(4, frame('turn/diff/updated', dict(threadId=thread, turnId=turn, diff='')))
            self.queue.insert(-1, frame('thread/status/changed', dict(threadId=thread, status=dict(type='idle'))))


class Harness:
    def __init__(self, directory, branch='N7-B-default', optional=False):
        self.directory, self.branch, self.optional = directory, branch, optional
        self.clock = Clock()
        self.transports, self.decisions, self.judgments, self.baselines = [], [], [], []
        self.partial = self.expire = self.foreign = self.late = False
        self.mismatch = self.cache = self.drift = self.bad_baseline = False
        self.root_expire = self.missing_command = False
        self.preclose_drift = False
        self.claims = o.DonorClaims(directory)
        self.hooks = o.TrustedCallbacks(self.context, self.snapshot, self.baseline,
                                        self.root, self.judge)
        self.operator = o.SetupOperator(branch, frozenset(), self.hooks,
                                        self.factory, self.claims, self.clock)

    def context(self, index, deadline):
        expected = {k: None for k in o.current_native().THREAD_FIELDS}
        expected.update(model='synthetic-model', modelProvider='synthetic-provider',
                        cwd=str(self.directory), approvalPolicy='never',
                        sandbox=dict(type='workspaceWrite', networkAccess=False),
                        multiAgentMode='explicitRequestOnly')
        return dict(root=str(self.directory), model='synthetic-model', expected=expected)

    def factory(self, spec, deadline):
        transport = Transport(spec, len(self.transports) + 1, self)
        self.transports.append(transport)
        return transport

    def snapshot(self, stage, context, deadline):
        if self.preclose_drift and stage == 'before-close':
            result = state()
            result['records'][1]['sha256'] = s.digest(b'changed')
            return result
        if self.drift and stage == 'post-close':
            result = state()
            result['grants']['drift'] = True
            return result
        if self.cache and stage.startswith('postturn'):
            return state(True)
        return state()

    def baseline(self, context, config, catalog, native, snapshot, deadline):
        self.baselines.append((context, native, deadline))
        return dict(synthetic='drift' if self.bad_baseline and len(self.baselines) > 1 else 'stable')

    def root(self, kind, predecessor, observation, deadline):
        # Assert the runtime calls this only after an actual healthy drain.
        if kind != 'premise':
            assert observation is not None and predecessor['turn_id'] == observation['receipt']['turn_id']
            assert not self.transports[-1].queue
        self.decisions.append((kind, predecessor, observation, deadline))
        if self.root_expire:
            self.clock.now = deadline
        body = (b'Execute ' + s.EXECUTED_COMMAND.encode() if kind == 'premise'
                else b'Actual synthetic Root judgment after observed output.')
        result = s.root_decision(kind, body, predecessor)
        if self.mismatch and predecessor is not None:
            result['predecessor']['turn_id'] = 'wrong'
        return result

    def turn_plan(self, context, turn):
        if self.branch != 'Duplicate-B-copy':
            return b'Actual question?', True, False
        command = (context == 1 and turn == (3 if self.optional else 2)) or (context == 2 and turn == 2)
        question = context == 1 and turn == 2 and self.optional
        return (b'Actual question?' if question else b'Completed.'), question, command and not self.missing_command

    def judge(self, receipt, records, before, after, deadline):
        question = receipt['output'] == b'Actual question?'
        duplicate = self.branch == 'Duplicate-B-copy'
        needs_command = duplicate and self.operator.gate.phase in ('initial', 'answer', 'repeat') and not question
        self.judgments.append((receipt, records, deadline))
        return dict(questions=(b'Actual question?',) if question else (),
                    configured_command=s.CONFIGURED_COMMAND if duplicate else None,
                    receipt=command_receipt() if needs_command else None)


class OperatorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='setup-operator-synthetic-')
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name).resolve()

    def harness(self, **kw):
        return Harness(self.directory, **kw)

    def hold(self, harness):
        with self.assertRaises((s.Hold, OSError)):
            harness.operator.run()
        self.assertEqual(harness.operator.gate.phase, 'stopped')
        self.assertTrue(all(t.closed for t in harness.transports))
        self.assertFalse(harness.operator.gate.accounting()['runtime_PASS'])
        return harness.operator.gate.attempts


    def observed(self, h):
        def factory(spec, deadline):
            transport = ObservedTransport(spec, len(h.transports) + 1, h)
            h.transports.append(transport)
            return transport
        h.operator.factory = factory
        return h

    def test_observed_startup_config_interleaving_status_usage_rate_diff(self):
        h = self.observed(self.harness(branch='Duplicate-B-copy', optional=True))
        self.assertEqual(h.operator.run()['accounting']['actual_charged_turns'], 5)
        self.assertEqual(len(h.operator.rpcs), 2)

    def test_wrapped_configured_test_among_reads_requires_explicit_scope_callback(self):
        h = self.harness(branch='Duplicate-B-copy')
        judgments = []
        def scope(extras, receipt, records, before, after, deadline):
            judgments.append(extras)
            return True
        h.operator.hooks = o.TrustedCallbacks(h.context, h.snapshot, h.baseline,
                                              h.root, h.judge, command_scope=scope)
        original = h.factory
        def factory(spec, deadline):
            transport = original(spec, deadline)
            write = transport.write
            def wrapped(raw, limit):
                write(raw, limit)
                if s.decode(raw)['method'] != 'turn/start':
                    return
                for index, raw_frame in enumerate(transport.queue):
                    obj = s.decode(raw_frame)
                    item = obj.get('params', {}).get('item', {})
                    if item.get('type') == 'commandExecution':
                        item['command'] = "/bin/zsh -lc '" + s.EXECUTED_COMMAND + "'"
                        transport.queue[index] = s.canonical(obj) + b'\n'
                if any(s.decode(frame).get('params', {}).get('item', {}).get('type') ==
                       'commandExecution' for frame in transport.queue):
                    thread, turn = 'thread-' + str(transport.context), 'turn-%s-%s' % (transport.context, transport.turn)
                    item = dict(id='read-' + turn, type='commandExecution', command="/bin/zsh -lc 'cat AGENTS.md'", cwd=spec['root'])
                    frames = [dict(method='item/started', params=dict(threadId=thread, turnId=turn, item=item)),
                        dict(method='item/completed', params=dict(threadId=thread, turnId=turn,
                            item=dict(item, status='completed', exitCode=0)))]
                    transport.queue[2:2] = [s.canonical(f) + b'\n' for f in frames]
            transport.write = wrapped
            return transport
        h.operator.factory = factory
        self.assertEqual(h.operator.run()['accounting']['actual_charged_turns'], 4)
        self.assertEqual(len(judgments), 2)
        self.assertTrue(all(len(extras) == 1 for extras in judgments))


    def test_one_finite_startup_metadata_notification_may_arrive_after_turn_dispatch(self):
        for method in ('remoteControl/status/changed', 'account/updated'):
            with self.subTest(method=method):
                directory = self.directory / method.replace('/', '-')
                directory.mkdir()
                h = self.observed(Harness(directory))
                original = h.operator.factory
                def factory(spec, deadline):
                    transport = original(spec, deadline)
                    write = transport.write
                    delayed = []
                    def wrapped(raw, limit):
                        write(raw, limit)
                        name = s.decode(raw)['method']
                        if name == 'initialize':
                            delayed.extend(frame for frame in transport.queue
                                           if s.decode(frame).get('method') == method)
                            transport.queue[:] = [frame for frame in transport.queue
                                                  if s.decode(frame).get('method') != method]
                        elif name == 'turn/start' and delayed:
                            transport.queue[:0] = delayed
                            delayed.clear()
                    transport.write = wrapped
                    return transport
                h.operator.factory = factory
                self.assertEqual(h.operator.run()['accounting']['actual_charged_turns'], 2)

    def test_observed_unknown_shapes_foreign_identities_and_waiting_hold(self):
        cases = (
            ('remoteControl/status/changed', lambda p: p.update(status='enabled'), 0),
            ('account/updated', lambda p: p.update(extra='unrecognized'), 0),
            ('thread/started', lambda p: p['thread'].update(id='foreign'), 0),
            ('account/rateLimits/updated', lambda p: p['rateLimits'].update(secondary={}), 0),
            ('account/rateLimits/updated', lambda p: p['rateLimits']['primary'].update(usedPercent=True), 0),
            ('thread/status/changed', lambda p: p.update(threadId='foreign'), 1),
            ('thread/status/changed', lambda p: p.update(status=dict(type='active', activeFlags=['waitingOnUserInput'])), 1),
            ('thread/tokenUsage/updated', lambda p: p.update(turnId='foreign'), 1),
            ('thread/tokenUsage/updated', lambda p: p['tokenUsage']['last'].update(totalTokens=-1), 1),
            ('thread/tokenUsage/updated', lambda p: p['tokenUsage']['total'].update(inputTokens=True), 1),
            ('turn/diff/updated', lambda p: p.update(turnId='foreign'), 1),
            ('turn/diff/updated', lambda p: p.update(diff=None), 1),
        )
        for number, (method, change, charged) in enumerate(cases):
            with self.subTest(method=method, number=number):
                directory = self.directory / str(number)
                directory.mkdir()
                h = self.observed(Harness(directory))
                original = h.operator.factory
                def factory(spec, deadline):
                    transport = original(spec, deadline)
                    write = transport.write
                    def mutate(raw, limit):
                        write(raw, limit)
                        for index, frame in enumerate(transport.queue):
                            obj = s.decode(frame)
                            if obj.get('method') == method:
                                change(obj['params'])
                                transport.queue[index] = s.canonical(obj) + b'\n'
                    transport.write = mutate
                    return transport
                h.operator.factory = factory
                self.assertEqual(len(self.hold(h)), charged)

    def test_thread_started_before_ack_is_not_invented_as_supported(self):
        h = self.observed(self.harness())
        original = h.operator.factory
        def factory(spec, deadline):
            transport = original(spec, deadline)
            write = transport.write
            def reorder(raw, limit):
                write(raw, limit)
                if s.decode(raw)['method'] == 'thread/start':
                    transport.queue.reverse()
            transport.write = reorder
            return transport
        h.operator.factory = factory
        self.assertEqual(self.hold(h), [])

    def test_metadata_never_opens_or_completes_turn_and_is_finitely_bounded(self):
        h = self.harness()
        rpc = o.MultiTurnRPC(Transport(h.context(1, 100), 1, h), 100, h.clock)
        for _ in range(256):
            rpc.event(dict(method='account/rateLimits/updated', params=rate_limits()))
        self.assertFalse(rpc.turn_active)
        self.assertFalse(rpc.started)
        self.assertFalse(rpc.terminal)
        self.assertIsNone(rpc.turn_id)
        with self.assertRaises(s.Hold):
            rpc.event(dict(method='account/rateLimits/updated', params=rate_limits()))
        with self.assertRaises(s.Hold):
            rpc.event(dict(method='thread/status/changed',
                           params=dict(threadId='x', status=dict(type='idle'))))

    def test_unknown_notification_and_server_request_still_hold(self):
        h = self.harness()
        for obj in (dict(method='unknown/native/event', params={}),
                    dict(id='server-owned', method='item/commandExecution/requestApproval', params={})):
            rpc = o.MultiTurnRPC(Transport(h.context(1, 100), 1, h), 100, h.clock)
            with self.assertRaises(s.Hold):
                rpc.receive(100, s.canonical(obj) + b'\n')

    def test_other_commands_need_exact_true_scope_and_preserve_cache(self):
        h = self.harness(branch='Duplicate-B-copy')
        h.operator.deadline = 100
        configured = dict(id='test', command="/bin/zsh -lc '" + s.EXECUTED_COMMAND + "'",
                          cwd=str(self.directory), status='completed', exitCode=0)
        read = dict(id='read', command="/bin/zsh -lc 'cat AGENTS.md'",
                    cwd=str(self.directory), status='completed', exitCode=0)
        rpc = SimpleNamespace(commands=[configured, read], wire=SimpleNamespace(records=[]))
        receipt = dict(request_index=0)
        judgment = dict(receipt=command_receipt())
        with self.assertRaisesRegex(s.Hold, 'Root scope/cache'):
            h.operator.duplicate_commands(rpc, h.context(1, 100), receipt, judgment, state(), state(), 100)
        for result in (None, False, 1, {'approved': True}):
            h.operator.hooks = o.TrustedCallbacks(h.context, h.snapshot, h.baseline,
                h.root, h.judge, command_scope=lambda *args: result)
            with self.assertRaises(s.Hold):
                h.operator.duplicate_commands(rpc, h.context(1, 100), receipt, judgment, state(), state(), 100)
        h.operator.hooks = o.TrustedCallbacks(h.context, h.snapshot, h.baseline,
            h.root, h.judge, command_scope=lambda *args: True)
        with self.assertRaisesRegex(s.Hold, 'cache mutation'):
            h.operator.duplicate_commands(rpc, h.context(1, 100), receipt, judgment, state(), state(True), 100)
        # The callback is needed for extras on premise/question/ack turns too.
        with self.assertRaisesRegex(s.Hold, 'Root scope/cache'):
            h.operator.hooks = h.hooks
            h.operator.duplicate_commands(rpc, h.context(1, 100), receipt,
                dict(receipt=None), state(), state(), 100)

    def test_exact_one_configured_command_current_turn_and_completed_int_zero(self):
        h = self.harness(branch='Duplicate-B-copy')
        h.operator.deadline = 100
        command = dict(id='test', command=s.EXECUTED_COMMAND, cwd=str(self.directory),
                       status='completed', exitCode=0)
        variants = ([], [command, dict(command, id='second', exitCode=1)],
                    [dict(command, exitCode=True)], [dict(command, cwd='/foreign')],
                    [dict(command, status='failed')],
                    [dict(command, command="/bin/zsh -lc '" + s.EXECUTED_COMMAND + "; cat AGENTS.md'")])
        for commands in variants:
            with self.subTest(commands=len(commands)):
                rpc = SimpleNamespace(commands=commands, wire=SimpleNamespace(records=[]))
                with self.assertRaises(s.Hold):
                    h.operator.duplicate_commands(rpc, h.context(1, 100), dict(request_index=0),
                        dict(receipt=command_receipt()), state(), state(), 100)

    def test_command_parser_pin_failure_prevents_transport(self):
        h = self.harness()
        with mock.patch.object(o, 'COMMAND_CORE_SHA256', '0' * 64):
            self.assertEqual(self.hold(h), [])
        self.assertEqual(h.transports, [])

    def test_two_turns_exact_input_predecessor_and_fixed_deadlines(self):
        h = self.harness()
        result = h.operator.run()
        self.assertEqual(result['accounting']['actual_charged_turns'], 2)
        self.assertEqual(result['status'], 'SOURCE_ONLY_OBSERVED')
        self.assertFalse(result['runtime_PASS'])
        turns = [(s.decode(raw), deadline) for raw, deadline in h.transports[0].writes
                 if s.decode(raw)['method'] == 'turn/start']
        self.assertEqual(turns[0][0]['params']['input'][0]['text'].encode(), s.SETUP_INPUT)
        self.assertEqual(turns[0][1], 181)
        self.assertEqual(turns[1][1], 181)
        self.assertEqual(len(h.decisions), 1)
        self.assertEqual(h.decisions[0][1]['turn_id'], 'turn-1-1')
        self.assertGreaterEqual(len(h.baselines), 6)
        with self.assertRaises(s.Hold):
            h.operator.run()

    def test_copy_branch_two_turns(self):
        h = self.harness(branch='N7-B-copy')
        self.assertEqual(h.operator.run()['accounting']['actual_charged_turns'], 2)

    def test_predecessor_mismatch_before_second_claim(self):
        h = self.harness(); h.mismatch = True
        self.assertEqual(len(self.hold(h)), 1)
        self.assertEqual(len(list(self.directory.iterdir())), 1)

    def test_duplicate_no_question_four_turns_two_contexts(self):
        h = self.harness(branch='Duplicate-B-copy')
        result = h.operator.run()
        self.assertEqual(result['accounting']['actual_charged_turns'], 4)
        self.assertEqual(result['accounting']['contexts_started'], 2)
        self.assertEqual([d[0] for d in h.decisions], ['premise', 'content-ack'])
        self.assertEqual(h.operator.deadline, 901)
        self.assertEqual(len(list(self.directory.iterdir())), 4)

    def test_duplicate_optional_actual_answer_five_turns(self):
        h = self.harness(branch='Duplicate-B-copy', optional=True)
        self.assertEqual(h.operator.run()['accounting']['actual_charged_turns'], 5)
        self.assertEqual([d[0] for d in h.decisions], ['premise', 'answer', 'content-ack'])

    def test_claim_collision_no_user_write_no_refund(self):
        h = self.harness()
        prepared = dict(row='N7-B/default/first', claim_key=s.claim_key('N7-B/default/first'),
                        thread_id='earlier', body=s.SETUP_INPUT)
        h.claims.reserve(prepared)
        before = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        self.assertEqual(self.hold(h), [])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.directory.iterdir()})
        self.assertFalse(any(s.decode(raw)['method'] == 'turn/start'
                             for raw, _ in h.transports[0].writes))

    def test_unknown_claim_is_durable_before_partial_delivery(self):
        h = self.harness(); h.partial = True
        attempts = self.hold(h)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]['status'], 'UNKNOWN')
        self.assertEqual(attempts[0]['delivery'], 'UNKNOWN')
        claim = s.decode(next(self.directory.iterdir()).read_bytes())
        self.assertEqual(claim['status'], 'UNKNOWN')
        self.assertEqual(claim['key'], s.claim_key('N7-B/default/first'))

    def test_late_lifecycle_stops_and_retains_charge(self):
        h = self.harness(); h.late = True
        self.assertEqual(self.hold(h)[0]['status'], 'UNKNOWN')

    def test_foreign_item_stops(self):
        h = self.harness(); h.foreign = True
        self.assertEqual(self.hold(h)[0]['status'], 'UNKNOWN')

    def test_expired_turn_does_not_extend_read_deadline(self):
        h = self.harness(); h.expire = True
        self.assertEqual(self.hold(h)[0]['status'], 'UNKNOWN')

    def test_root_wait_cannot_extend_context_deadline(self):
        h = self.harness(); h.root_expire = True
        self.assertEqual(len(self.hold(h)), 1)

    def test_cache_mutation_rejected(self):
        h = self.harness(branch='Duplicate-B-copy'); h.cache = True
        self.assertEqual(self.hold(h)[0]['status'], 'UNKNOWN')

    def test_postclose_grant_drift_rejected(self):
        h = self.harness(); h.drift = True
        self.assertEqual(len(self.hold(h)), 2)

    def test_state_drift_between_completion_and_close_rejected(self):
        h = self.harness(); h.preclose_drift = True
        self.assertEqual(len(self.hold(h)), 2)

    def test_failed_write_retains_primary_when_close_also_fails(self):
        h = self.harness(); h.partial = True
        original = h.factory
        def factory(spec, deadline):
            transport = original(spec, deadline)
            def close():
                transport.closed = True
                raise RuntimeError('secondary synthetic close failure')
            transport.close = close
            return transport
        h.operator.factory = factory
        with self.assertRaisesRegex(OSError, 'synthetic partial delivery'):
            h.operator.run()
        self.assertEqual(h.operator.cleanup_failures, ['RuntimeError'])
        self.assertEqual(h.operator.gate.attempts[0]['status'], 'UNKNOWN')
        self.assertTrue(any(sample['stage'] == 'post-close' for sample in h.operator.samples))

    def test_postclose_tail_is_hold(self):
        h = self.harness()
        original = h.factory
        def factory(spec, deadline):
            transport = original(spec, deadline)
            close = transport.close
            transport.close = lambda: dict(close(), tail_frames=[b'late\n'])
            return transport
        h.operator.factory = factory
        self.assertEqual(len(self.hold(h)), 2)

    def test_owned_cleanup_errors_are_not_hidden_by_reaped_zero_exit(self):
        h = self.harness()
        original = h.factory
        def factory(spec, deadline):
            transport = original(spec, deadline)
            close = transport.close
            transport.close = lambda: dict(close(), cleanup_errors=[dict(
                operation='terminate', exception_type='PermissionError', errno=1)])
            return transport
        h.operator.factory = factory
        self.assertEqual(len(self.hold(h)), 2)
        self.assertTrue(h.operator.closures[0]['cleanup_errors'])

    def test_native_source_pin_failure_before_any_transport_or_claim(self):
        h = self.harness()
        with mock.patch.object(o, 'NATIVE_SHA256', '0' * 64):
            self.assertEqual(self.hold(h), [])
        self.assertEqual(h.transports, [])
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_primitive_source_pin_failure_before_any_transport_or_claim(self):
        h = self.harness()
        with mock.patch.object(o, 'SETUP_SOURCE_SHA256', '0' * 64):
            self.assertEqual(self.hold(h), [])
        self.assertEqual(h.transports, [])

    def test_baseline_drift_prevents_claim(self):
        h = self.harness(); h.bad_baseline = True
        self.assertEqual(self.hold(h), [])

    def test_declared_receipt_without_actual_command_holds(self):
        h = self.harness(branch='Duplicate-B-copy'); h.missing_command = True
        self.assertEqual(self.hold(h)[-1]['status'], 'UNKNOWN')

    def test_noargs_inert_execute_failclosed(self):
        with mock.patch.object(o, 'process_transport', side_effect=AssertionError('launch')):
            self.assertEqual(o.main([]), 0)
            with self.assertRaises(SystemExit) as error:
                o.main(['--execute'])
            self.assertEqual(error.exception.code, 2)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_unknown_string_response_id_rejected(self):
        h = self.harness()
        t = Transport(h.context(1, 100), 1, h)
        rpc = o.MultiTurnRPC(t, 100, h.clock)
        rpc.send('initialize', {}, 100)
        with self.assertRaises(s.Hold):
            rpc.receive(100, s.canonical(dict(id='1', result={}))+b'\n')

    def test_duplicate_completed_response_id_rejected(self):
        h = self.harness()
        t = Transport(h.context(1, 100), 1, h)
        rpc = o.MultiTurnRPC(t, 100, h.clock)
        rpc.call('initialize', {}, 100)
        with self.assertRaises(s.Hold):
            rpc.receive(100, s.canonical(dict(id=1, result={}))+b'\n')

    def test_terminal_before_turn_reply_correlates_without_extra_turn(self):
        h = self.harness()
        original = h.factory
        def factory(spec, deadline):
            transport = original(spec, deadline)
            write = transport.write
            def reordered(raw, limit):
                write(raw, limit)
                if s.decode(raw)['method'] == 'turn/start':
                    transport.queue.append(transport.queue.pop(0))
            transport.write = reordered
            return transport
        h.operator.factory = factory
        self.assertEqual(h.operator.run()['accounting']['actual_charged_turns'], 2)

    def test_observer_receives_only_validated_original_completed_frames(self):
        h = self.harness(branch='Duplicate-B-copy')
        seen = []
        h.operator.hooks = o.TrustedCallbacks(h.context, h.snapshot, h.baseline,
            h.root, h.judge, observe=lambda event, deadline: seen.append((event, deadline)))
        h.operator.run()
        self.assertEqual(len(seen), 2)
        for event, deadline in seen:
            rpc = next(rpc for rpc in h.operator.rpcs if rpc.thread_id == event['thread_id'])
            record = rpc.wire.records[event['wire_index']]
            self.assertEqual(record['payload']['method'], 'item/completed')
            self.assertEqual(record['payload']['params']['item'], event['item'])
            self.assertEqual(s.digest(record['raw']), event['raw_sha256'])
            self.assertEqual(record['payload']['params']['turnId'], event['turn_id'])
            request = next(attempt for attempt in h.operator.gate.attempts
                           if attempt.get('turn_id') == event['turn_id'])
            self.assertLessEqual(deadline, request['deadline'])
        h = self.harness(branch='Duplicate-B-copy')
        h.foreign = True
        rejected = []
        h.operator.hooks = o.TrustedCallbacks(h.context, h.snapshot, h.baseline,
            h.root, h.judge, observe=lambda *args: rejected.append(args))
        self.hold(h)
        self.assertEqual(rejected, [])

    def test_observer_cannot_extend_original_deadline_or_resume(self):
        h = self.harness(branch='Duplicate-B-copy')
        def expired(event, deadline):
            h.clock.now = deadline
        h.operator.hooks = o.TrustedCallbacks(h.context, h.snapshot, h.baseline,
            h.root, h.judge, observe=expired)
        attempts = self.hold(h)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[-1]['status'], 'UNKNOWN')
        with self.assertRaisesRegex(s.Hold, 'single-use'):
            h.operator.run()

    def test_observer_rejects_overlapping_side_effect_lifecycle(self):
        h = self.harness(branch='Duplicate-B-copy')
        h.operator.hooks = o.TrustedCallbacks(h.context, h.snapshot, h.baseline,
            h.root, h.judge, observe=lambda *args: None)
        factory = h.factory
        def overlapped(spec, deadline):
            transport = factory(spec, deadline)
            write = transport.write
            def wrapped(raw, limit):
                write(raw, limit)
                if s.decode(raw)['method'] == 'turn/start':
                    for index, frame in enumerate(transport.queue):
                        obj = s.decode(frame)
                        item = obj.get('params', {}).get('item', {})
                        if obj.get('method') == 'item/started' and item.get('type') == 'commandExecution':
                            duplicate = copy.deepcopy(obj)
                            duplicate['params']['item']['id'] += '-overlap'
                            transport.queue.insert(index + 1, s.canonical(duplicate) + b'\n')
                            break
            transport.write = wrapped
            return transport
        h.operator.factory = overlapped
        with self.assertRaisesRegex(s.Hold, 'overlapping side effect'):
            h.operator.run()
        self.assertEqual(len(h.operator.gate.attempts), 2)
        self.assertEqual(h.operator.gate.phase, 'stopped')

    def overlap_rpc(self, classifier=None, diagnostic=None):
        seen = []
        rpc = o.MultiTurnRPC(None, 100, Clock(),
            observe=lambda event, deadline: seen.append(event),
            read_intent=classifier, diagnose=diagnostic)
        rpc.thread_id, rpc.turn_id = 'owned-thread', 'owned-turn'
        rpc.turn_active = rpc.started = True
        return rpc, seen

    def overlap_item(self, rpc, ident, command='cat AGENTS.md', kind='commandExecution',
                     completed=False, cwd='/fixture'):
        item = dict(id=ident, type=kind, command=command, cwd=cwd,
                    status='completed' if completed else 'inProgress',
                    exitCode=0 if completed else None)
        method = 'item/completed' if completed else 'item/started'
        raw = s.canonical(dict(method=method, params=dict(threadId='owned-thread',
            turnId='owned-turn', item=item))) + b'\n'
        rpc.receive(100, raw)
        return raw

    def test_independently_classified_reads_overlap_in_both_completion_orders(self):
        def classify(item, deadline):
            return 'read' if item.get('command') in ('cat AGENTS.md', 'cat CLAUDE.md') else None
        for order in (('a', 'b'), ('b', 'a')):
            with self.subTest(order=order):
                rpc, seen = self.overlap_rpc(classify)
                self.overlap_item(rpc, 'a')
                self.overlap_item(rpc, 'b', 'cat CLAUDE.md')
                for ident in order:
                    command = 'cat AGENTS.md' if ident == 'a' else 'cat CLAUDE.md'
                    self.overlap_item(rpc, ident, command, completed=True)
                self.assertEqual([item['item']['id'] for item in seen], list(order))
                self.assertFalse(rpc.active_items)
                for event in seen:
                    self.assertEqual(event['raw_sha256'], s.digest(rpc.wire.records[event['wire_index']]['raw']))

    def test_overlap_without_any_optional_callback_still_holds(self):
        rpc = o.MultiTurnRPC(None, 100, Clock())
        rpc.thread_id, rpc.turn_id = 'owned-thread', 'owned-turn'
        rpc.turn_active = rpc.started = True
        self.overlap_item(rpc, 'a')
        with self.assertRaisesRegex(s.Hold, 'overlapping side effect'):
            self.overlap_item(rpc, 'b')

    def test_overlap_requires_every_item_to_be_a_finite_read(self):
        def classify(item, deadline):
            return 'read' if item.get('command') == 'cat AGENTS.md' else None
        cases = ((None, 'cat AGENTS.md', 'cat AGENTS.md', 'commandExecution'),
                 (classify, 'cat AGENTS.md', 'python3 -c pass', 'commandExecution'),
                 (classify, 'python3 -c pass', 'cat AGENTS.md', 'commandExecution'),
                 (classify, 'cat AGENTS.md', s.EXECUTED_COMMAND, 'commandExecution'),
                 (classify, s.EXECUTED_COMMAND, 'cat AGENTS.md', 'commandExecution'),
                 (classify, 'cat AGENTS.md', 'cat AGENTS.md', 'fileChange'))
        for classifier, first, second, kind in cases:
            with self.subTest(first=first, second=second, kind=kind):
                diagnostics = []
                rpc, seen = self.overlap_rpc(classifier, lambda event, deadline: diagnostics.append(event))
                self.overlap_item(rpc, 'a', first)
                with self.assertRaisesRegex(s.Hold, 'overlapping side effect'):
                    self.overlap_item(rpc, 'b', second, kind)
                self.assertEqual(seen, [])
                self.assertEqual(diagnostics[-1]['reason_code'], 'OVERLAP_NOT_READ_ONLY')
                self.assertEqual(diagnostics[-1]['item']['id'], 'b')
                self.assertEqual(diagnostics[-1]['active_items'][0]['id'], 'a')
                self.assertEqual(diagnostics[-1]['raw_sha256'], s.digest(rpc.wire.records[-1]['raw']))

    def test_read_classifier_cannot_extend_the_turn_deadline(self):
        rpc, seen = self.overlap_rpc()
        def expire(item, deadline):
            self.assertEqual(deadline, 100)
            rpc.clock.now = deadline
            return 'read'
        rpc.read_intent = expire
        self.overlap_item(rpc, 'a')
        with self.assertRaisesRegex(s.Hold, 'deadline'):
            self.overlap_item(rpc, 'b')
        self.assertTrue(rpc.failed)
        self.assertEqual(seen, [])

    def test_read_overlap_preserves_completed_command_identity(self):
        for field, changed in (('command', 'cat CLAUDE.md'), ('cwd', '/other')):
            with self.subTest(field=field):
                diagnostics = []
                rpc, seen = self.overlap_rpc(lambda *args: 'read',
                    lambda event, deadline: diagnostics.append(event))
                self.overlap_item(rpc, 'a')
                self.overlap_item(rpc, 'b')
                kwargs = {'command': 'cat AGENTS.md', 'cwd': '/fixture', field: changed}
                with self.assertRaisesRegex(s.Hold, 'command lifecycle changed'):
                    self.overlap_item(rpc, 'a', completed=True, **kwargs)
                self.assertEqual(seen, [])
                self.assertEqual(diagnostics[-1]['stage'], 'completed')
                self.assertEqual(diagnostics[-1]['reason_code'], 'COMPLETION_PRE_ADMISSION')

    def test_second_context_cannot_replace_independent_instruction_expectations(self):
        h = self.harness(branch='Duplicate-B-copy')
        def changed(index, deadline):
            spec = h.context(index, deadline)
            if index == 2:
                spec['expected']['instructionSources'] = ['/foreign/AGENTS.md']
            return spec
        h.operator.hooks = o.TrustedCallbacks(changed, h.snapshot, h.baseline, h.root, h.judge)
        with self.assertRaisesRegex(s.Hold, 'native expectation changed'):
            h.operator.run()
        self.assertEqual(len(h.transports), 1)
        self.assertEqual(len(h.operator.gate.attempts), 2)


if __name__ == '__main__':
    unittest.main()
