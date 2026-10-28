#!/usr/bin/env python3
"""SOURCE-ONLY setup adapter candidate; no import/CLI launch or authorization.

Callbacks are separately reviewed source-owned integration points, NOT proof of
Root authority, grants, semantic judgments, native availability or admission.
run() is for synthetic transports or later separately admitted Root orchestration.
No JSON signature convention, release flag, automatic answer or retry is provided.
Raw wire stays in caller-owned memory; callers must bind approved retention.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
import importlib.util
import os
from pathlib import Path
import sys
import time

import setup_postclosure as setup

NATIVE_SHA256 = 'c02009d36ae11ed3968dde4b32c69f0c591d362a586c49ea1ee99378cd4c7f53'
SETUP_SOURCE_SHA256 = '7c923ea9273f970f8e744cee1919c8461f18d816aaf80b9907e179bf4f4be5de'
COMMAND_CORE_SHA256 = 'd65a6707a197e379cca4aace4d451288f54a2c8494d1d8c2ae1855cf24ec5cdf'
_NATIVE = None
_COMMAND_CORE = None


def command_core():
    """Pinned current inert D2 module; use ONLY its pure command parser/matcher."""
    global _COMMAND_CORE
    path = Path(__file__).resolve().with_name('postclosure.py')
    raw = path.read_bytes()
    setup.require(setup.digest(raw) == COMMAND_CORE_SHA256, 'command parser source drift')
    if _COMMAND_CORE is None:
        spec = importlib.util.spec_from_file_location('_setup_operator_command_core', path)
        module = importlib.util.module_from_spec(spec)
        exec(compile(raw, str(path), 'exec'), module.__dict__)
        _COMMAND_CORE = module
    setup.require(_COMMAND_CORE.__file__ == str(path), 'command parser identity drift')
    return _COMMAND_CORE


def current_native():
    """Read/import the pinned CURRENT source only; never invoke its producers."""
    global _NATIVE
    path = Path(__file__).resolve().with_name('native_delta.py')
    raw = path.read_bytes()
    setup.require(setup.digest(raw) == NATIVE_SHA256, 'current native source drift')
    if _NATIVE is None:
        spec = importlib.util.spec_from_file_location('_setup_operator_current_c020', path)
        module = importlib.util.module_from_spec(spec)
        exec(compile(raw, str(path), 'exec'), module.__dict__)
        _NATIVE = module
    setup.require(_NATIVE.__file__ == str(path), 'native module identity drift')
    return _NATIVE


def process_transport(argv, root, environment, deadline):
    """Explicit integration utility; calling it requires separate runtime release."""
    from owned_transport import ProcessTransport
    return ProcessTransport(argv, root, environment, deadline)


class DonorClaims:
    """Exclusive stable lifetime claims; never refunded, deleted or reset.

    Store directory must already exist at a separately admitted durable location.
    The UNKNOWN record is fsynced, including its directory, BEFORE USER writes.
    A filesystem failure may consume a donor without dispatch; stop and audit it.
    """
    def __init__(self, directory):
        self.directory = Path(directory)
        setup.require(self.directory.is_absolute() and not self.directory.is_symlink()
                      and self.directory.resolve(strict=True) == self.directory
                      and self.directory.is_dir(), 'physical existing claim directory required')

    def reserve(self, prepared):
        key = setup.claim_key(prepared['row'])
        setup.require(key == prepared['claim_key'], 'stable donor key drift')
        raw = setup.canonical(dict(key=key, row=prepared['row'],
                                  thread_id=prepared['thread_id'],
                                  input_sha256=setup.digest(prepared['body']),
                                  delivery='UNKNOWN', status='UNKNOWN')) + b'\n'
        directory = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(setup.digest(key.encode()) + '.json',
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(directory)
        finally:
            os.close(directory)
        return key


@dataclass(frozen=True)
class TrustedCallbacks:
    """Required actual adapters; declarations alone establish no runtime proof.

    context(index, deadline): {root, model, expected}, where expected is the
      independently released exact native13 expectation (not actual-derived).
    snapshot(stage, index, deadline): fresh complete FULLSTATE incl actual grants.
    baseline(index, config, catalog, native13, state, deadline): independently
      verify source/config/catalog/native/grants and return stable invariant dict.
      It must include complete installed body and metadata/config identities.
    root(kind, predecessor, observation, deadline): actual new Root judgment,
      only called between drained healthy turns; returns setup.root_decision DATA.
    judge(receipt, records, before, after, deadline): actual semantic extraction
      {questions: tuple[bytes], configured_command, receipt}; the declaration is
      not command/cache provenance. Native exact command is checked separately.
    command_scope(extras, receipt, records, before, after, deadline): optional;
      required strict True for other completed commands, backed by separately
      verified actual Root scope/cache evidence for these exact observations.
      No command is automatically classified safe. True alone proves nothing.
    observe(event, deadline): optional actual completed-side-effect observer;
      called only after owned lifecycle validation, with original frame hash/index
      and the unextended turn deadline. Observations are not execution barriers.
    read_intent(item, deadline): optional finite start-time classifier returning
      exactly 'read' or 'topology-read' only for scoped, non-writing commands.
      All overlapping side effects must independently pass; it proves no result.
    diagnose(event, deadline): optional pre-admission diagnostic callback. Its
      item and active_items are untrusted; persistent integrations must retain
      only bounded safe shapes/hashes and never label them accepted evidence.
    These callbacks must be bounded, trusted and non-mutating except the actual
    separate Root interaction. No callback may silently launch another model.
    """
    context: object
    snapshot: object
    baseline: object
    root: object
    judge: object
    command_scope: object = None
    observe: object = None
    read_intent: object = None
    diagnose: object = None


class MultiTurnRPC:
    """Typed owned IDs, finite item lifecycle, original-byte setup.Wire capture."""
    METHODS = frozenset(('initialize', 'initialized', 'config/read', 'skills/list',
                         'thread/start', 'turn/start'))
    ITEMS = frozenset(('userMessage', 'agentMessage', 'reasoning', 'commandExecution',
                       'fileChange', 'mcpToolCall', 'dynamicToolCall', 'webSearch',
                       'imageView', 'enteredReviewMode', 'exitedReviewMode',
                       'contextCompaction'))
    DELTAS = frozenset(('item/agentMessage/delta', 'item/reasoning/textDelta',
                        'item/reasoning/summaryTextDelta',
                        'item/reasoning/summaryPartAdded',
                        'item/commandExecution/outputDelta', 'item/fileChange/outputDelta'))

    def __init__(self, transport, deadline, clock, observe=None, read_intent=None, diagnose=None):
        self.transport, self.deadline, self.clock = transport, deadline, clock
        self.observe, self.read_intent, self.diagnose = observe, read_intent, diagnose
        self.wire = setup.Wire()
        self.pending, self.completed_ids = {}, set()
        self.sequence = 0
        self.thread_id = self.turn_id = None
        self.turns, self.item_ids, self.active_items = set(), set(), {}
        self.turn_active = self.started = self.terminal = self.failed = False
        self.commands = []
        self.thread_ack = None
        self.metadata_counts = {}
        self.turn_metadata_counts = {}
        self.observed_status = None

    def check(self, deadline):
        setup.require(not self.failed and self.clock() < min(deadline, self.deadline),
                      'expired/stopped RPC deadline')

    def send(self, method, params, deadline, notification=False):
        self.check(deadline)
        setup.require(method in self.METHODS and not self.pending, 'method/pending RPC')
        obj = dict(method=method, params=params)
        if not notification:
            self.sequence += 1
            obj['id'] = self.sequence
            key = setup.typed_id(self.sequence)
            self.pending[key] = method
        else:
            setup.require(method == 'initialized', 'only initialized notification')
        raw = setup.canonical(obj) + b'\n'
        index = len(self.wire.records)
        # Record attempted original bytes before write. Partial writes remain
        # UNKNOWN; never claim that these bytes were all delivered remotely.
        self.wire.feed('client', raw)
        try:
            self.transport.write(raw, min(deadline, self.deadline))
            self.check(deadline)
        except BaseException:
            self.failed = True
            raise
        return obj.get('id'), index

    def receive(self, deadline, raw=None):
        self.check(deadline)
        try:
            if raw is None:
                raw = self.transport.read(min(deadline, self.deadline))
            start = len(self.wire.records)
            self.wire.feed('server', raw)
            setup.require(len(self.wire.records) == start + 1 and
                          not self.wire.pending['server'], 'one complete original frame required')
            obj = self.wire.records[-1]['payload']
            if 'method' not in obj:
                key = setup.typed_id(obj['id'])
                setup.require(key in self.pending and key not in self.completed_ids,
                              'foreign/completed RPC ID')
                method = self.pending.pop(key)
                self.completed_ids.add(key)
                result = obj['result']
                setup.require(type(result) is dict, 'typed RPC result required')
                if method == 'thread/start':
                    setup.require(self.thread_id is None, 'second thread in context')
                    self.thread_id = setup.text(result.get('thread', {}).get('id'))
                    self.thread_ack = copy.deepcopy(result['thread'])
                elif method == 'turn/start':
                    ident = setup.text(result.get('turn', {}).get('id'))
                    self.bind_turn(ident)
            else:
                setup.require('id' not in obj, 'server request unsupported: HOLD')
                self.event(obj, deadline)
            self.check(deadline)
            return obj
        except BaseException:
            self.failed = True
            raise

    def bind_turn(self, ident):
        setup.require(self.turn_active and ident not in self.turns and
                      (self.turn_id is None or ident == self.turn_id), 'foreign/reused turn')
        self.turn_id = ident

    def side_effect_diagnostic(self, stage, item, deadline, reason_code):
        if self.diagnose is None:
            return
        setup.require(deadline is not None and self.wire.records,
                      'actual original diagnostic frame required')
        self.check(deadline)
        record = self.wire.records[-1]
        self.diagnose(dict(stage=stage, reason_code=reason_code,
            thread_id=self.thread_id, turn_id=self.turn_id, item=copy.deepcopy(item),
            active_items=copy.deepcopy(list(self.active_items.values())),
            wire_index=len(self.wire.records) - 1, raw_sha256=setup.digest(record['raw'])),
            min(deadline, self.deadline))
        self.check(deadline)

    def reads_may_overlap(self, item, active, deadline):
        if self.read_intent is None or item['type'] != 'commandExecution':
            return False
        for candidate in [*active, item]:
            if candidate['type'] != 'commandExecution':
                return False
            self.check(deadline)
            classification = self.read_intent(copy.deepcopy(candidate), min(deadline, self.deadline))
            self.check(deadline)
            if classification not in ('read', 'topology-read'):
                return False
        return True

    def event(self, obj, deadline=None):
        method, params = obj['method'], obj.get('params')
        setup.require(type(params) is dict, 'notification params required')
        if self.observed_metadata(method, params):
            return
        setup.require(type(params) is dict and self.turn_active and not self.terminal,
                      'late/unowned event')
        setup.require(params.get('error') is None, 'runtime event error')
        setup.require(params.get('threadId') == self.thread_id, 'foreign event thread')
        if method == 'turn/started':
            setup.require(not self.started and type(params.get('turn')) is dict,
                          'duplicate/malformed turn start')
            self.bind_turn(setup.text(params['turn'].get('id')))
            self.started = True
        else:
            setup.require(self.turn_id is not None, 'lifecycle before owned turn ID')
        if method == 'turn/completed':
            turn = params.get('turn')
            setup.require(type(turn) is dict and turn.get('id') == self.turn_id and
                          turn.get('status') == 'completed' and turn.get('error') is None
                          and self.started and not self.active_items and
                          self.observed_status in (None, 'idle'),
                          'failed/foreign/active terminal')
            self.terminal = True
        elif method.startswith('item/'):
            setup.require(params.get('turnId') == self.turn_id, 'foreign item turn')
            if method in ('item/started', 'item/completed'):
                item = params.get('item')
                setup.require(type(item) is dict and item.get('type') in self.ITEMS,
                              'unsupported/nested item: HOLD')
                ident = setup.text(item.get('id'))
                if method == 'item/started':
                    setup.require(ident not in self.item_ids, 'reused item ID')
                    if item['type'] in ('commandExecution', 'fileChange'):
                        self.side_effect_diagnostic('started', item, deadline, 'START_PRE_ADMISSION')
                        active = [entry for entry in self.active_items.values()
                                  if entry['type'] in ('commandExecution', 'fileChange')]
                        if active:
                            allowed = self.reads_may_overlap(item, active, deadline)
                            if not allowed:
                                self.side_effect_diagnostic('started', item, deadline, 'OVERLAP_NOT_READ_ONLY')
                            setup.require(allowed, 'overlapping side effect items: HOLD')
                    self.item_ids.add(ident)
                    self.active_items[ident] = copy.deepcopy(item)
                else:
                    if item['type'] in ('commandExecution', 'fileChange'):
                        self.side_effect_diagnostic('completed', item, deadline, 'COMPLETION_PRE_ADMISSION')
                    initial = self.active_items.pop(ident, None)
                    setup.require(initial is not None and initial['type'] == item['type'],
                                  'unowned/duplicate item completion')
                    if item['type'] == 'commandExecution':
                        setup.require((initial.get('command'), initial.get('cwd')) ==
                                      (item.get('command'), item.get('cwd')),
                                      'command lifecycle changed')
                        self.commands.append(copy.deepcopy(item))
                    if self.observe is not None and item['type'] in ('commandExecution', 'fileChange'):
                        setup.require(deadline is not None and self.wire.records,
                                      'actual original observation frame required')
                        self.check(deadline)
                        record = self.wire.records[-1]
                        event = dict(thread_id=self.thread_id, turn_id=self.turn_id,
                            item=copy.deepcopy(item), wire_index=len(self.wire.records) - 1,
                            raw_sha256=setup.digest(record['raw']))
                        self.observe(event, min(deadline, self.deadline))
                        self.check(deadline)
            else:
                active = self.active_items.get(params.get('itemId'), {})
                expected_type = method.split('/')[1]
                setup.require(method in self.DELTAS and active.get('type') == expected_type,
                              'unsupported/unowned item delta: HOLD')
        else:
            setup.require(method == 'turn/started', 'unsupported native event: HOLD')

    def observed_metadata(self, method, params):
        """Finite OBSERVED profile, not a universal API/enum/availability claim.

        Thread shapes use pinned primary thread.rs/turn.rs; remote/account
        envelopes are observed only. Unknown shapes/status/flags remain HOLD.
        Metadata never opens, binds, resumes or completes a model turn.
        """
        limits = {'remoteControl/status/changed': 1, 'account/updated': 1,
                  'thread/started': 1, 'account/rateLimits/updated': 256}
        turn_limits = {'thread/status/changed': 2, 'thread/tokenUsage/updated': 256,
                       'turn/diff/updated': 128}
        if method not in limits and method not in turn_limits:
            return False
        counts, maximum = ((self.metadata_counts, limits[method]) if method in limits
                           else (self.turn_metadata_counts, turn_limits[method]))
        counts[method] = counts.get(method, 0) + 1
        setup.require(counts[method] <= maximum, 'observed metadata occurrence bound')
        if method in ('remoteControl/status/changed', 'account/updated'):
            # These process-wide notifications may be delivered asynchronously.
            # Their finite shapes/counts do not bind or advance a model turn.
            if method == 'remoteControl/status/changed':
                setup.fields(params, 'environmentId installationId serverName status')
                setup.require(params['environmentId'] is None and params['status'] == 'disabled',
                              'unsupported remote status')
                setup.text(params['installationId']); setup.text(params['serverName'])
            else:
                setup.fields(params, 'authMode planType')
                setup.text(params['authMode']); setup.text(params['planType'])
        elif method == 'thread/started':
            setup.fields(params, 'thread')
            setup.require(self.thread_id is not None and not self.turn_active and not self.turns
                          and params['thread'] == self.thread_ack, 'unowned/early/changed threadStarted')
        elif method == 'account/rateLimits/updated':
            setup.fields(params, 'rateLimits')
            rate = params['rateLimits']
            setup.fields(rate, 'credits individualLimit limitId limitName normalModelSlug planType primary rateLimitReachedType secondary spendControlReached')
            setup.require(all(rate[key] is None for key in ('individualLimit', 'limitName',
                'normalModelSlug', 'rateLimitReachedType', 'secondary', 'spendControlReached')),
                'unsupported rate-limit shape/status')
            setup.text(rate['limitId']); setup.text(rate['planType'])
            credits, primary = rate['credits'], rate['primary']
            setup.fields(credits, 'balance hasCredits unlimited')
            setup.require(credits['balance'] is None and type(credits['hasCredits']) is bool and
                          type(credits['unlimited']) is bool, 'unsupported credits shape')
            setup.fields(primary, 'resetsAt usedPercent windowDurationMins')
            setup.require(all(type(value) is int and value >= 0 for value in primary.values())
                          and primary['usedPercent'] <= 100, 'unsupported rate counters')
        else:
            setup.require(self.turn_active and not self.terminal and
                          params.get('threadId') == self.thread_id, 'unowned/late thread metadata')
            if method == 'thread/status/changed':
                setup.fields(params, 'threadId status')
                status = params['status']
                setup.require(type(status) is dict, 'typed status required')
                if status == {'type': 'active', 'activeFlags': []}:
                    setup.require(not self.started and self.observed_status is None,
                                  'unowned/repeated active status')
                    self.observed_status = 'active'
                else:
                    setup.require(status == {'type': 'idle'} and self.started and
                                  self.observed_status == 'active', 'unknown/waiting/foreign status')
                    self.observed_status = 'idle'
            else:
                setup.require(self.turn_id is not None and params.get('turnId') == self.turn_id,
                              'foreign metadata turn')
                if method == 'turn/diff/updated':
                    setup.fields(params, 'threadId turnId diff')
                    setup.require(type(params['diff']) is str, 'typed diff required')
                else:
                    setup.fields(params, 'threadId turnId tokenUsage')
                    usage = params['tokenUsage']
                    setup.fields(usage, 'last total modelContextWindow')
                    setup.require(type(usage['modelContextWindow']) is int and
                                  usage['modelContextWindow'] >= 0, 'unsupported context window')
                    for key in ('last', 'total'):
                        setup.fields(usage[key], 'cacheWriteInputTokens cachedInputTokens inputTokens outputTokens reasoningOutputTokens totalTokens')
                        setup.require(all(type(value) is int and value >= 0
                                          for value in usage[key].values()), 'invalid token counters')
        return True

    def call(self, method, params, deadline):
        ident, _ = self.send(method, params, deadline)
        while True:
            obj = self.receive(deadline)
            if 'method' not in obj and setup.typed_id(obj['id']) == setup.typed_id(ident):
                return obj['result']

    def drain(self, deadline):
        self.check(deadline)
        for raw in self.transport.drain(min(deadline, self.deadline)):
            self.receive(deadline, raw)
        self.check(deadline)
        self.wire.require_clean()
        setup.require(not self.pending, 'pending owned RPC')

    def turn(self, prepared, deadline, delivered):
        setup.require(not self.turn_active and not self.pending, 'turn overlap')
        self.turn_id = None
        self.turn_active = True
        self.started = self.terminal = False
        self.commands = []
        self.turn_metadata_counts = {}
        self.observed_status = None
        ident, index = self.send('turn/start', dict(threadId=self.thread_id,
            input=[dict(type='text', text=setup.raw_text(prepared['body']))]), deadline)
        delivered()
        self.wire.require_turn_input(index, prepared)
        while not self.terminal or setup.typed_id(ident) in self.pending:
            self.receive(deadline)
        self.drain(deadline)
        receipt = self.wire.completed_turn(index)
        self.turns.add(self.turn_id)
        self.turn_active = False
        return receipt

    def closed(self, receipt):
        from owned_transport import require_healthy_close
        try:
            require_healthy_close(receipt)
        except ValueError as error:
            raise setup.Hold('unhealthy owned process closure') from error
        setup.require(type(receipt) is dict and receipt.get('reaped') is True and
                      receipt.get('partial_stdout_bytes') == 0 and
                      receipt.get('watchdog_fired') is False and
                      receipt.get('watchdog_error') is None and
                      receipt.get('tail_frames') == [], 'unhealthy/late process closure')
        self.wire.require_clean()
        setup.require(not self.pending and not self.active_items, 'unclosed RPC lifecycle')


def cache_records(state):
    setup.strict_equal(state, state)
    return [record for record in state['records']
            if '__pycache__' in Path(record['path']).parts or
            Path(record['path']).suffix in ('.pyc', '.pyo')]


class SetupOperator:
    """Finite candidate; trusted callbacks are required but grant no authority.

    No automatic production factory exists. An integration must independently
    establish exact source/native/context release before calling this adapter.
    HOLD keeps claims and UNKNOWN attempts; run() cannot resume a failed object.
    """
    def __init__(self, branch, consumed, callbacks, transport_factory, claims,
                 clock=time.monotonic):
        setup.require(type(callbacks) is TrustedCallbacks and
                      all(callable(getattr(callbacks, name)) for name in
                          ('context', 'snapshot', 'baseline', 'root', 'judge')) and
                      (callbacks.command_scope is None or callable(callbacks.command_scope)) and
                      (callbacks.observe is None or callable(callbacks.observe)) and
                      (callbacks.read_intent is None or callable(callbacks.read_intent)) and
                      (callbacks.diagnose is None or callable(callbacks.diagnose)),
                      'explicit source-owned callbacks required')
        self.gate = setup.TurnGate(branch, consumed)
        self.hooks, self.factory, self.claims, self.clock = callbacks, transport_factory, claims, clock
        self.started = False
        self.deadline = None
        self.samples, self.rpcs, self.closures = [], [], []
        self.baseline = None
        self.spec = None
        self.reserved = []
        self.cleanup_failures = []
        self.failure = None

    def check(self, deadline):
        now = self.clock()
        setup.clock_value(now)
        setup.require(now < min(deadline, self.deadline), 'absolute operator deadline')
        self.gate._now(now)

    def invoke(self, callback, deadline, *args):
        self.check(deadline)
        result = callback(*copy.deepcopy(args), deadline)
        self.check(deadline)
        return copy.deepcopy(result)

    def snapshot(self, stage, context, deadline):
        state = self.invoke(self.hooks.snapshot, deadline, stage, context)
        setup.strict_equal(state, state)
        self.samples.append(dict(stage=stage, context=context, state=state))
        return state

    def bundle(self, rpc, spec, context, deadline, stage, native):
        before = self.snapshot(stage + '/before', context, deadline)
        first = rpc.call('config/read', dict(includeLayers=True, cwd=spec['root']), deadline)
        catalog = rpc.call('skills/list', dict(cwds=[spec['root']], forceReload=True), deadline)
        second = rpc.call('config/read', dict(includeLayers=True, cwd=spec['root']), deadline)
        after = self.snapshot(stage + '/after', context, deadline)
        setup.strict_equal(before, after)
        setup.require(setup.canonical(first) == setup.canonical(second), 'config sandwich drift')
        projection = self.invoke(self.hooks.baseline, deadline,
                                 context, second, catalog, native, after)
        setup.require(type(projection) is dict and projection, 'complete baseline projection required')
        if self.baseline is None:
            self.baseline = copy.deepcopy(projection)
        setup.require(projection == self.baseline, 'immutable lifetime baseline drift')
        return second, after

    def decision(self, deadline, observation):
        phase = self.gate.phase
        if phase in ('first', 'initial', 'repeat'):
            return setup.SETUP_INPUT, None
        kind = {'premise': 'premise', 'answer': 'answer', 'ack': 'content-ack'}[phase]
        predecessor = None if phase == 'premise' else self.gate.predecessor()
        decision = self.invoke(self.hooks.root, deadline, kind, predecessor, observation)
        setup.fields(decision, 'kind body predecessor actor')
        return decision['body'], decision

    def duplicate_commands(self, rpc, spec, receipt, judgment, before, after, deadline):
        setup.require(cache_records(before) == cache_records(after), 'cache mutation')
        matching = []
        if judgment['receipt'] is not None:
            setup.command_receipt(judgment['receipt'])
            matching = [item for item in rpc.commands if command_core().command_matches(
                item.get('command'), setup.EXECUTED_COMMAND)]
            setup.require(len(matching) == 1, 'exact ONE configured command required: HOLD')
            command = matching[0]
            setup.require(command.get('cwd') == spec['root'] and
                          command.get('status') == 'completed' and
                          type(command.get('exitCode')) is int and command['exitCode'] == 0,
                          'native configured command failed/foreign: HOLD')
        extras = [item for item in rpc.commands if not matching or item is not matching[0]]
        if extras:
            setup.require(all(type(item.get('command')) is str and
                              item.get('cwd') == spec['root'] and
                              item.get('status') in ('completed', 'failed') and
                              type(item.get('exitCode')) is int for item in extras),
                          'unsupported other command completion: HOLD')
            setup.require(callable(self.hooks.command_scope),
                          'other commands need actual Root scope/cache evidence')
            judged = self.invoke(self.hooks.command_scope, deadline, extras, receipt,
                rpc.wire.records[receipt['request_index']:], before, after)
            setup.require(judged is True, 'other commands lack actual Root judgment')

    def run(self):
        setup.require(not self.started, 'single-use operator')
        self.started = True
        self.deadline = setup.clock_value(self.clock()) + (900 if self.gate.duplicate else 360)
        observation = None
        try:
            setup_path = Path(__file__).resolve().with_name('setup_postclosure.py')
            setup.require(Path(setup.__file__).resolve() == setup_path and
                          setup.digest(setup_path.read_bytes()) == SETUP_SOURCE_SHA256,
                          'reviewed setup primitives drift')
            current_native()
            command_core()
            while self.gate.phase != 'done':
                context = len(self.rpcs) + 1
                deadline = min(self.deadline, self.clock() +
                               (540 if self.gate.duplicate and context == 1 else 360))
                spec = self.invoke(self.hooks.context, deadline, context)
                setup.fields(spec, 'root model expected')
                setup.text(spec['root']); setup.text(spec['model'])
                setup.require(Path(spec['root']).is_absolute(), 'absolute context root required')
                if self.spec is None:
                    self.spec = copy.deepcopy(spec)
                setup.require(spec == self.spec, 'context root/model/native expectation changed')
                transport = self.factory(copy.deepcopy(spec), deadline)
                rpc = MultiTurnRPC(transport, deadline, self.clock,
                    None if self.hooks.observe is None else
                    lambda event, limit: self.invoke(self.hooks.observe, limit, event),
                    None if self.hooks.read_intent is None else
                    lambda item, limit: self.invoke(self.hooks.read_intent, limit, item),
                    None if self.hooks.diagnose is None else
                    lambda event, limit: self.invoke(self.hooks.diagnose, limit, event))
                self.rpcs.append(rpc)
                try:
                    rpc.call('initialize', dict(clientInfo=dict(name='ains-setup-source-candidate',
                                                               version='1')), deadline)
                    rpc.send('initialized', {}, deadline, notification=True)
                    # Pre-thread bundle is fresh but cannot establish native13.
                    # Native/source baseline is established only after thread/start.
                    config = rpc.call('config/read', dict(includeLayers=True, cwd=spec['root']), deadline)
                    request = dict(cwd=spec['root'], model=spec['model'], approvalPolicy='never',
                                   sandbox='workspace-write', ephemeral=True)
                    actual = rpc.call('thread/start', request, deadline)
                    native = current_native().reconcile_thread(actual, request, spec['expected'],
                                                               config.get('config'))
                    self.gate.open_context(rpc.thread_id)
                    self.bundle(rpc, spec, context, deadline, 'post-start-1', native)
                    self.bundle(rpc, spec, context, deadline, 'post-start-2', native)
                    while self.gate.phase != 'done' and not (
                            self.gate.duplicate and context == 1 and self.gate.phase == 'ack'):
                        rpc.drain(deadline)
                        body, decision = self.decision(deadline, observation)
                        _, before = self.bundle(rpc, spec, context, deadline, 'predispatch', native)
                        if observation is not None:
                            setup.strict_equal(observation['after'], before)
                        prepared = self.gate.prepare(body, decision)
                        self.check(deadline)
                        self.claims.reserve(prepared)
                        self.reserved.append(prepared['claim_key'])
                        self.check(deadline)
                        attempt = self.gate.begin(prepared, self.clock())
                        turn_deadline = min(deadline, attempt['deadline'])
                        receipt = rpc.turn(prepared, turn_deadline,
                                           lambda: self.gate.delivered(self.clock()))
                        # All post-turn observations and callbacks share the
                        # original absolute turn deadline; no timeout extension.
                        _, after = self.bundle(rpc, spec, context, turn_deadline, 'postturn', native)
                        judgment = self.invoke(self.hooks.judge, turn_deadline, receipt,
                            rpc.wire.records[receipt['request_index']:], before, after)
                        setup.fields(judgment, 'questions configured_command receipt')
                        if self.gate.duplicate:
                            self.duplicate_commands(rpc, spec, receipt, judgment, before, after, turn_deadline)
                        self.check(turn_deadline)
                        self.gate.complete(self.clock(), receipt['turn_id'], receipt['output'],
                            judgment['questions'], before, after,
                            judgment['configured_command'], judgment['receipt'])
                        observation = dict(receipt=receipt, judgment=judgment, after=after)
                    rpc.drain(deadline)
                    final = self.snapshot('before-close', context, deadline)
                    setup.strict_equal(observation['after'], final)
                finally:
                    primary = sys.exc_info()[1]
                    try:
                        close = transport.close()
                        self.closures.append(copy.deepcopy(close))
                        rpc.closed(close)
                    except BaseException as cleanup:
                        if primary is None:
                            raise
                        self.cleanup_failures.append(type(cleanup).__name__)
                    try:
                        postclose = self.snapshot('post-close', context, deadline)
                        if primary is None:
                            setup.strict_equal(final, postclose)
                    except BaseException as cleanup:
                        if primary is None:
                            raise
                        self.cleanup_failures.append(type(cleanup).__name__)
                self.gate.close_context()
            return dict(accounting=self.gate.accounting(), runtime_PASS=False,
                        status='SOURCE_ONLY_OBSERVED', snapshots=copy.deepcopy(self.samples))
        except BaseException as error:
            self.failure = type(error).__name__
            self.gate._stop(self.failure)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    if args.execute:
        parser.exit(2, 'HOLD: exact source/native/context release is not integrated; no launch.\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
