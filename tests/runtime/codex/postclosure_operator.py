#!/usr/bin/env python3
"""One-context D2 operator. No arguments means no process and no filesystem writes.

Only --execute --command PATH --command-sha256 HASH can request a launch. The
command digest must be supplied by the trusted Root caller, never by its file.
--validate-only follows the same acyclic graph without launching a process.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import tempfile
import threading
import time
import sys

sys.dont_write_bytecode = True
import postclosure as core


class ProcessTransport:
    """Owned process only; finite original-byte IO and absolute lifetime."""
    def __init__(self, argv, root, environment, deadline):
        core.require(time.monotonic() < deadline, 'launch deadline')
        self.deadline = deadline
        self.stderr = tempfile.TemporaryFile()
        self.process = None
        self.watchdog = None
        self.buffer = b''
        self.closed = False
        self.watchdog_fired = False
        self.watchdog_error = None
        try:
            self.process = subprocess.Popen(argv, cwd=root, env=environment,
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=self.stderr, start_new_session=True)
            def expire():
                self.watchdog_fired = True
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except BaseException as error:
                    self.watchdog_error = type(error).__name__
            self.watchdog = threading.Timer(max(0, deadline - time.monotonic()), expire)
            self.watchdog.daemon = True
            self.watchdog.start()
            os.set_blocking(self.process.stdin.fileno(), False)
            os.set_blocking(self.process.stdout.fileno(), False)
        except BaseException as primary:
            # The caller cannot own a constructor that never returned. Reap
            # this exact newly-created group here, preserving the first cause.
            cleanup_failures = []
            def cleanup(action):
                try:
                    action()
                except ProcessLookupError:
                    pass
                except BaseException as error:
                    cleanup_failures.append(type(error).__name__)
            if self.watchdog is not None:
                cleanup(self.watchdog.cancel)
            if self.process is not None:
                cleanup(lambda: os.killpg(self.process.pid, signal.SIGKILL))
                cleanup(lambda: self.process.wait(timeout=2))
                for stream in (self.process.stdin, self.process.stdout):
                    if stream is not None:
                        cleanup(stream.close)
            cleanup(self.stderr.close)
            primary._postclosure_cleanup_failures = cleanup_failures
            raise

    @property
    def pid(self):
        return self.process.pid

    def write(self, data, deadline):
        sent = 0
        while sent < len(data):
            remaining = min(deadline, self.deadline) - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('absolute write deadline')
            if not select.select([], [self.process.stdin], [], remaining)[1]:
                raise TimeoutError('write deadline')
            count = os.write(self.process.stdin.fileno(), data[sent:])
            if count <= 0:
                raise core.Hold('partial/zero process write')
            sent += count

    def read(self, deadline):
        while b'\n' not in self.buffer:
            remaining = min(deadline, self.deadline) - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('absolute read deadline')
            if not select.select([self.process.stdout], [], [], remaining)[0]:
                raise TimeoutError('read deadline')
            data = os.read(self.process.stdout.fileno(), 65536)
            if not data:
                raise EOFError('process stdout EOF with %d buffered bytes' % len(self.buffer))
            self.buffer += data
            core.require(len(self.buffer) <= 16 * 1024 * 1024, 'RPC frame size bound')
        line, self.buffer = self.buffer.split(b'\n', 1)
        return line + b'\n'

    def drain(self, deadline):
        result = []
        while time.monotonic() < min(deadline, self.deadline):
            if b'\n' not in self.buffer and not select.select([self.process.stdout], [], [], 0)[0]:
                break
            result.append(self.read(deadline))
        return result

    def close(self):
        if self.closed:
            raise core.Hold('owned process already closed')
        self.closed = True
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        if self.process.poll() is None:
            remaining = max(0, min(1, self.deadline - time.monotonic()))
            try:
                self.process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=1)
        # An exited leader can leave descendants holding its pipes. This is
        # the exact newly owned process group, never a searched host process.
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        while True:
            try:
                tail = os.read(self.process.stdout.fileno(), 65536)
            except BlockingIOError:
                break
            if not tail:
                break
            self.buffer += tail
            core.require(len(self.buffer) <= 16 * 1024 * 1024, 'close-tail frame size')
        frames = []
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            frames.append(line + b'\n')
        for stream in (self.process.stdin, self.process.stdout):
            stream.close()
        self.stderr.seek(0)
        diagnostic = self.stderr.read()
        self.stderr.close()
        self.watchdog.cancel()
        return {'reaped': self.process.poll() is not None, 'returncode': self.process.returncode,
                'stderr_sha256': core.digest(diagnostic), 'stderr_bytes': len(diagnostic),
                'partial_stdout_bytes': len(self.buffer), 'tail_frames': frames,
                'watchdog_fired': self.watchdog_fired, 'watchdog_error': self.watchdog_error}


class RecordingRPC:
    """Mockable transport with original-byte hashes and no answer/resume method.

    Config responses are retained only as locally computed safe identities; the
    unredacted response lives in the caller's memory for raw A==B comparison.
    A logged attempted write is UNKNOWN until an actual matching reply arrives.
    """
    METHODS = frozenset(('initialize', 'initialized', 'config/read', 'skills/list', 'thread/start', 'turn/start'))

    def __init__(self, transport, deadline, clock=time.monotonic, monotonic_ns=time.monotonic_ns, turn_overlay=None):
        self.transport = transport
        self.deadline = deadline
        self.clock = clock
        self.monotonic_ns = monotonic_ns
        self.wire = []
        self.events = []
        self.pending = {}
        self.sequence = 0
        self.thread_id = None
        self.turn_id = None
        self.thread_started = False
        self.dispatched = False
        self.completed = False
        self.failed = False
        self.on_event = None
        self.command_items = {}
        self.active_items = {}
        self.turn_overlay = turn_overlay

    def _deadline(self, timeout=30):
        core.require(self.clock() < self.deadline, 'absolute context deadline')
        return min(self.deadline, self.clock() + timeout)

    def _record(self, direction, obj, raw):
        legacy = core.load_legacy()
        safe = legacy.redacted_config(obj)
        if direction == 'response' and type(obj.get('id')) is int and self.pending.get(obj['id']) == 'config/read' and type(obj.get('result')) is dict:
            safe = {'id': obj['id'], 'result': legacy.safe_config_identity(obj['result'])}
        timestamp = self.monotonic_ns()
        core.require(not self.wire or timestamp > self.wire[-1]['monotonic_ns'], 'nonmonotonic wire clock')
        self.wire.append({'index': len(self.wire), 'monotonic_ns': timestamp,
                          'direction': direction, 'payload': safe,
                          'bytes_sha256': core.digest(raw), 'bytes_length': len(raw)})

    def send(self, method, params=None, notification=False):
        self._deadline()
        core.require(not self.failed and method in self.METHODS, 'forbidden RPC or failed transport')
        if method == 'thread/start':
            core.require(not self.thread_started and not self.dispatched and type(params) is dict and
                         set(params) == {'cwd', 'model', 'approvalPolicy', 'sandbox', 'ephemeral'} and
                         params['ephemeral'] is True, 'thread start shape/count')
            self.thread_started = True
        if method == 'turn/start':
            overlay = self.turn_overlay or {}
            core.require(self.thread_id and not self.dispatched and type(params) is dict and
                         set(params) == {'threadId', 'input'} | set(overlay) and
                         all(params.get(key) == value for key, value in overlay.items()) and
                         params['threadId'] == self.thread_id and
                         type(params['input']) is list and len(params['input']) == 1 and
                         set(params['input'][0]) == {'type', 'text'} and
                         params['input'][0]['type'] == 'text' and
                         type(params['input'][0]['text']) is str, 'second USER/turn shape')
            self.dispatched = True
        obj = {'method': method}
        if params is not None:
            obj['params'] = params
        if not notification:
            self.sequence += 1
            obj['id'] = self.sequence
            self.pending[self.sequence] = method
        raw = (json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
        self._record('request', obj, raw)
        try:
            self.transport.write(raw, self._deadline())
        except BaseException as error:
            self.failed = True
            self._record('transport_error', {'exception_type': type(error).__name__}, b'write-failed')
            raise
        return obj.get('id')

    def receive(self, timeout=30, raw=None):
        try:
            raw = self.transport.read(self._deadline(timeout)) if raw is None else raw
            obj = core.decode(raw)
            core.require(type(obj) is dict, 'RPC object required')
            self._record('response', obj, raw)
            core.require(not ('id' in obj and 'method' in obj), 'server request requires forbidden second input')
            if 'id' in obj:
                core.require(type(obj['id']) is int and obj['id'] in self.pending, 'foreign/duplicate response')
                method = self.pending.pop(obj['id'])
                core.require('error' not in obj and 'result' in obj, 'RPC error/missing result')
                if method == 'thread/start':
                    core.require(type(obj['result']) is dict and type(obj['result'].get('thread')) is dict, 'malformed thread/start result')
                    self.thread_id = core.nonempty(obj['result'].get('thread', {}).get('id'))
                if method == 'turn/start':
                    core.require(type(obj['result']) is dict and type(obj['result'].get('turn')) is dict, 'malformed turn/start result')
                    acknowledged = core.nonempty(obj['result'].get('turn', {}).get('id'))
                    core.require(self.turn_id is None or self.turn_id == acknowledged, 'turn acknowledgement identity changed')
                    self.turn_id = acknowledged
            else:
                params = obj.get('params', {})
                core.require(type(params) is dict, 'event params')
                method = obj.get('method', '')
                core.require(type(method) is str and method, 'event method string required')
                if method == 'turn/started' and self.turn_id is None:
                    core.require(self.dispatched and params.get('threadId') == self.thread_id and type(params.get('turn')) is dict, 'early turn start identity')
                    self.turn_id = core.nonempty(params['turn'].get('id'))
                if method.startswith(('item/', 'turn/')):
                    core.require(self.thread_id is not None and self.turn_id is not None and params.get('threadId') == self.thread_id, 'owned lifecycle thread identity required')
                    if method.startswith('item/'):
                        core.require(params.get('turnId') == self.turn_id, 'owned item turn identity required')
                    elif method in ('turn/started', 'turn/completed'):
                        core.require(type(params.get('turn')) is dict and params['turn'].get('id') == self.turn_id, 'owned turn identity required')
                    else:
                        core.require(params.get('turnId') == self.turn_id, 'owned turn delta identity required')
                if 'threadId' in params:
                    core.require(params['threadId'] == self.thread_id, 'foreign event thread')
                if 'turnId' in params:
                    core.require(self.turn_id is not None and params['turnId'] == self.turn_id, 'foreign event turn')
                turn = params.get('turn')
                if type(turn) is dict and 'id' in turn:
                    core.require(turn['id'] == self.turn_id, 'foreign nested turn')
                method = obj.get('method', '')
                core.require(type(method) is str and method, 'event method string required')
                core.require(not self.completed or not method.startswith(('item/', 'turn/')),
                             'lifecycle event after completed turn')
                core.require(method != 'error' and not params.get('error') and
                             not (type(turn) is dict and turn.get('error')), 'late/runtime error')
                if method == 'turn/completed':
                    core.require(self.dispatched and self.turn_id is not None and not self.completed and
                                 params.get('threadId') == self.thread_id and type(turn) is dict and
                                 turn.get('id') == self.turn_id and turn.get('status') == 'completed',
                                 'invalid/foreign/identity-free/duplicate terminal')
                    self.completed = True
                elif method.startswith('turn/'):
                    core.require(not self.completed, 'turn lifecycle event after terminal')
                item = params.get('item', {})
                core.require(not (type(item) is dict and type(item.get('type')) is str and
                                  item['type'].lower().startswith(('collabagent', 'subagent'))) and
                             not method.lower().startswith(('agent/', 'collab/', 'subagent/')),
                             'unbudgeted nested agent/model context event')
                if method in ('item/started', 'item/completed'):
                    core.require(type(item) is dict, 'item lifecycle payload')
                    identity = core.nonempty(item.get('id'))
                    if method == 'item/started':
                        core.require(identity not in self.active_items, 'duplicate item start')
                        self.active_items[identity] = item.get('type')
                    else:
                        core.require(identity in self.active_items and self.active_items.pop(identity) == item.get('type'),
                                     'foreign/duplicate item completion')
                if type(item) is dict and item.get('type') == 'commandExecution':
                    identity = core.nonempty(item.get('id'))
                    if method == 'item/started':
                        core.require(identity not in self.command_items, 'duplicate command item start')
                        self.command_items[identity] = (item.get('command'), item.get('cwd'))
                    elif method == 'item/completed':
                        core.require(identity in self.command_items and
                                     self.command_items.pop(identity) == (item.get('command'), item.get('cwd')),
                                     'command item start/completion mismatch')
                if method == 'turn/completed':
                    core.require(not self.command_items and not self.active_items, 'terminal while item active')
                self.events.append(obj)
                if self.on_event is not None:
                    self.on_event(obj, len(self.events) - 1)
            return obj
        except BaseException as error:
            self.failed = True
            self._record('transport_error', {'exception_type': type(error).__name__}, b'read-or-protocol-failed')
            raise

    def call(self, method, params, timeout=30):
        ident = self.send(method, params)
        deadline = self._deadline(timeout)
        while True:
            remaining = deadline - self.clock()
            core.require(remaining > 0, 'RPC call deadline')
            obj = self.receive(remaining)
            if obj.get('id') == ident:
                return obj['result']

    def drain(self):
        for raw in self.transport.drain(self._deadline(1)):
            self.receive(raw=raw)
        core.require(not self.pending, 'pending RPC responses at close')


def _save(path, value):
    # Safe identity provenance is checked by the original current serializer.
    safe = core.load_legacy().finite_receipt(value)
    data = (json.dumps(safe, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _save_bytes(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return core.ref(path)


def record_failure(raw, error, stage):
    failure = {'exception_type': type(error).__name__, 'stage': stage,
               'reason_code': 'CONTRACT_HOLD' if isinstance(error, core.Hold) else 'STAGE_EXCEPTION'}
    if raw['failure'] is None:
        raw['failure'] = {'primary': failure, 'secondary': []}
    else:
        raw['failure']['secondary'].append(failure)
    for name in getattr(error, '_postclosure_cleanup_failures', []):
        raw['failure']['secondary'].append({'exception_type': name, 'stage': 'constructor-cleanup', 'reason_code': 'STAGE_EXCEPTION'})


def capture_review_target(graph, raw, output):
    """Post-close complete fixture capture; never create a model handoff."""
    root = Path(raw['root'])
    before = core.inventory(root)
    core.require(before == raw['state_after'], 'review capture starts at actual final state')
    paths = [path for path, value in before.items() if value.get('kind') == 'file']
    core.require(len(paths) <= core.MAX_CAPTURE_FILES and
                 all(value.get('kind') in ('file', 'directory') and value.get('link_text') is None for value in before.values()),
                 'unsupported review capture namespace')
    files = {}
    total = 0
    for index, path in enumerate(sorted(paths)):
        data, info = core.file_bytes(root / path)
        total += len(data)
        core.require(len(data) <= core.MAX_CAPTURE_FILE_BYTES and total <= core.MAX_CAPTURE_BYTES and
                     core.digest(data) == before[path]['sha256'], 'review capture file bound/state drift')
        files[path] = _save_bytes(output / ('review-file-%04d.bin' % index), data)
    after = core.inventory(root)
    core.require(before == after == raw['state_after'], 'review capture complete pair drift')
    _save(output / 'review-state-before.json', before)
    _save(output / 'review-state-after.json', after)
    capture = {'schema': 'postclosure-review-capture-v1', 'scope': graph['plan']['scope'],
               'state_before': core.ref(output / 'review-state-before.json'),
               'state_after': core.ref(output / 'review-state-after.json'), 'files': files}
    _save(output / 'review-target-capture.json', capture)
    reference = core.ref(output / 'review-target-capture.json')
    raw['samples'].append({'phase': 'review-target-capture', 'capture': reference})
    core.validate_review_capture(reference, raw, graph['plan'])
    return reference


def enforce_control_scope(graph):
    """Native workspace-write may also allow /tmp; controls live under Root C."""
    for reference in graph['controls']:
        path = core.absolute(reference['path'])
        core.require(path.is_relative_to(core.CONTROL_ROOT), 'live Root controls outside source-owned C')
    output = core.absolute(graph['command']['output'])
    core.require(output.is_relative_to(core.CONTROL_ROOT) and
                 output.resolve(strict=False) == output and
                 not output.is_relative_to(Path(graph['scope']['realroot'])), 'live output outside protected Root C')


def run_released(command_ref, expected_command_sha256, transport_factory=ProcessTransport):
    """Execute one separately reviewed command; always retain an unadjudicated raw.

    Validation is process-free and precedes the exclusive lifetime claim. A
    launch/transport failure after that claim retains it; no retry is inferred.
    """
    graph = core.validate_graph(command_ref, expected_command_sha256)
    enforce_control_scope(graph)
    plan, scope, policy = (graph[k] for k in ('plan', 'scope', 'policy'))
    # Fail closed BEFORE claim or launch for profiles that cannot yet be proven.
    deadline = time.monotonic() + 180
    work_deadline = deadline - 2
    output = Path(plan['output'])
    output.mkdir(mode=0o700)
    claim = core.acquire_claim(plan['branch_id'], plan['row_id'], Path(plan['claim']).parent, graph['command']['release'])
    core.require(str(claim) == plan['claim'], 'claim path mismatch')
    root = Path(scope['root'])
    transport = None
    rpc = None
    raw = {'schema': 'postclosure-context-v1', 'branch_id': plan['branch_id'],
           'row_id': plan['row_id'], 'donor_slot': plan['donor_slot'],
           'common': graph['root_review']['common'], 'release': graph['command']['release'],
           'prior_history_sha256': graph['common']['history_sha256'],
           'root': scope['root'], 'realroot': scope['realroot'], 'process_id': None,
           'thread_id': None, 'turn_id': None, 'wire': [], 'samples': [],
           'input_delivery': None, 'state_before': graph['state'], 'state_after': None,
           'close': None, 'failure': None, 'accounting': None, 'business_PASS': False}
    stage = 'prelaunch'
    try:
        legacy = core.load_legacy()
        binding = core.decode(core.read_ref(graph['common']['native_binding']))
        environment = dict(os.environ)
        actual_env = legacy.environment_facts(environment)
        core.require(actual_env == graph['choice']['environment'], 'environment identity drift')
        legacy.require_environment(actual_env, binding)
        captured_before = {path: (root / path).read_bytes() for path in
                           (graph['contract']['roles']['spec'], graph['contract']['roles']['tasks'])
                           if path is not None and (root / path).is_file()}
        before_capture_refs = {name: _save_bytes(output / ('artifact-before-%03d.bin' % index), data)
                               for index, (name, data) in enumerate(captured_before.items())}
        raw['samples'].append({'phase': 'artifact-byte-captures-before', 'captures': before_capture_refs})
        git_before_bytes = {}
        if graph['contract']['git_profile'] is not None:
            paths = [name for name, value in graph['state'].items() if value.get('kind') == 'file' and name.startswith('.git/')]
            paths += graph['contract']['roles']['application'] + graph['contract']['roles']['tests']
            paths += [graph['contract']['roles']['off']]
            git_before_bytes = {name: (root / name).read_bytes() for name in paths if name is not None and (root / name).is_file()}
        transport = transport_factory(policy['argv'], root, environment, work_deadline)
        raw['process_id'] = transport.pid
        rpc = RecordingRPC(transport, work_deadline, turn_overlay=graph.get('turn_overlay'))
        cache_profile = core.read_record(graph['contract']['cache_profile'], 'cache-profile') if graph['contract']['cache_profile'] else None
        cache_versions = []
        capability_proof = None
        git_profile = core.read_record(graph['contract']['git_profile'], 'git-profile') if graph['contract']['git_profile'] else None
        off_samples = []
        if cache_profile or git_profile:
            def observed_command(event, event_index):
                item = event.get('params', {}).get('item', {})
                if event.get('method') == 'item/completed' and item.get('type') == 'commandExecution' and cache_profile and any(core.command_matches(item.get('command'), command) for command in core.allowed_cache_commands(cache_profile)):
                    core.require(not rpc.command_items, 'concurrent commands prevent finite source equivalence capture')
                    captured = core.capture_cache_versions(cache_profile, root, event_index)
                    retained = []
                    for index, version in enumerate(captured):
                        reference = _save_bytes(output / ('cache-source-%05d-%03d.bin' % (event_index, index)), version['bytes'])
                        retained.append({**{key: value for key, value in version.items() if key != 'bytes'}, 'capture': reference})
                    cache_versions.extend(captured)
                    raw['samples'].append({'phase': 'post-command-source-equivalence', 'event_index': event_index,
                                           'versions': retained})
                if git_profile and event.get('method') == 'item/completed' and item.get('type') == 'commandExecution' and (core.git_command_kind(git_profile, item.get('command')) in ('add', 'commit', 'revert') or any(core.command_matches(item.get('command'), command) for command in ['python3 -m unittest discover -v'] + git_profile['verification_commands'])):
                    core.require(not rpc.command_items and item.get('status') == 'completed' and item.get('exitCode') == 0 and item.get('cwd') == str(root), 'actual idle successful OFF observation command')
                    path = git_profile['off_path']
                    data, info = core.file_bytes(root / path)
                    observation = {'event_index': event_index, 'command': item['command'], 'path': path,
                        'capture': _save_bytes(output / ('off-observed-%05d.bin' % event_index), data),
                        'identity': [info.st_dev, info.st_ino], 'mode': oct(info.st_mode & 0o777),
                        'relation': 'actual post-command observation; no pre-execution timing claim'}
                    off_samples.append(observation)
                    raw['samples'].append({'phase': 'P6-off-observation', 'observation': observation})
            rpc.on_event = observed_command
        stage = 'initialize'
        rpc.call('initialize', {'clientInfo': {'name': 'ains-postclosure-v1', 'version': '1'}})
        rpc.send('initialized', notification=True)

        def metadata():
            expected = {**policy['metadata_paths'], **graph['graph_pins']}
            core.require(type(expected) is dict and expected, 'metadata scope required')
            actual = core.sample_metadata(expected)
            return actual

        with core.bound_helpers(output / 'helper-output') as (_, (helpers, imports)):
            installed = helpers['activation_r3'].inventory(root)
            structural = helpers['activation_closure_probe'].structural

            def catalog_validator(catalog, config):
                return legacy.validate_catalog(catalog, installed, legacy.config_facts(config, structural), 'live')

            lookup = core.read_record(graph['common']['lookup'], 'lookup')
            lifetime_anchor = core.read_record(graph['anchor'], 'invariant-anchor')
            native_snapshot = lookup['native_facts']['native13']

            def bundle(phase):
                nonlocal capability_proof, stage
                stage = phase
                start = len(rpc.wire)
                core.require(not any(helpers['activation_r3'].mdm_forced().values()), 'managed state outside premise')
                before_meta = metadata()
                before = core.inventory(root)
                legacy.released_source(graph['common']['product_manifest']['path'])
                first = rpc.call('config/read', {'includeLayers': True, 'cwd': str(root)})
                catalog = rpc.call('skills/list', {'cwds': [str(root)], 'forceReload': True})
                second = rpc.call('config/read', {'includeLayers': True, 'cwd': str(root)})
                if graph['contract']['capability_profile'] is not None:
                    capability_proof = core.validate_capability(
                        core.read_record(graph['contract']['capability_profile'], 'capability-profile'),
                        second, supplied_dynamic_tools=[], authorized_methods=RecordingRPC.METHODS)
                after = core.inventory(root)
                after_meta = metadata()
                core.require(not any(helpers['activation_r3'].mdm_forced().values()), 'managed state changed')
                observed_policy = dict(policy, metadata_paths={**policy['metadata_paths'], **graph['graph_pins']})
                frame = core.validate_bundle(first, catalog, second, before, after,
                                             before_meta, after_meta, observed_policy, scope, catalog_validator)
                candidate = core.invariant_projection(scope, graph['common']['product_manifest'], second, catalog, native_snapshot, environment, after_meta)
                core.require(candidate == lifetime_anchor, 'business lifetime baseline drift')
                frame['invariant_sha256'] = core.canonical_hash(candidate)
                core.require(helpers['activation_r3'].inventory(root) == installed and
                             legacy.environment_facts(environment) == actual_env, 'install/environment drift')
                raw['samples'].append({'phase': phase, 'wire_start': start, 'wire_end': len(rpc.wire),
                                       'before': before, 'after': after, 'metadata': after_meta, 'frame': frame})
                return frame, first

            preflight, config = bundle('preflight')
            lookup = core.read_record(graph['common']['lookup'], 'lookup')
            core.require(preflight['config'] == lookup['native_facts']['configuration_identity'], 'actual business config differs from reviewed zero-USER lookup')
            request = {'cwd': str(root), 'model': binding['forward_thread_expectation']['model'],
                       'approvalPolicy': 'never', 'sandbox': 'workspace-write', 'ephemeral': True}
            stage = 'thread-start'
            actual = rpc.call('thread/start', request)
            snapshot = legacy.reconcile_thread(actual, request, binding['forward_thread_expectation'], config['config'])
            native_snapshot = snapshot
            core.require(snapshot['thread_id'] == rpc.thread_id, 'actual native thread binding')
            first, _ = bundle('post-start-1')
            second, _ = bundle('post-start-2')
            baseline = core.Baselines(first, second)
            immediate, _ = bundle('predispatch')
            baseline.check(immediate)
            core.require(core.inventory(root) == graph['state'], 'predispatch full-state drift')
            text = graph['decision']['request']
            raw['input_delivery'] = {'input_sha256': core.canonical_hash(graph['decision']),
                                     'request_sha256': core.digest(text.encode()), 'USER': 1}
            rpc.call('turn/start', {'threadId': rpc.thread_id, 'input': [{'type': 'text', 'text': text}],
                                    **(graph.get('turn_overlay') or {})})
            stage = 'turn-in-flight'
            while not rpc.completed:
                rpc.receive()
            rpc.drain()
            core.require(legacy.healthy_terminal(rpc.events, 'live'), 'unhealthy terminal')
            final, _ = bundle('postterminal')
            rpc.drain()
            core.require(final['config'] == immediate['config'] and
                         final['metadata_sha256'] == immediate['metadata_sha256'], 'terminal immutable config drift')
            raw['state_after'] = core.inventory(root)
            stage = 'postterminal-transition-validation'
            captured_after = {path: (root / path).read_bytes() for path in captured_before if (root / path).is_file()}
            after_capture_refs = {name: _save_bytes(output / ('artifact-after-%03d.bin' % index), data)
                                  for index, (name, data) in enumerate(captured_after.items())}
            raw['samples'].append({'phase': 'artifact-byte-captures-after', 'captures': after_capture_refs})
            cache_proof = core.validate_derived_caches(cache_profile, graph['state'], raw['state_after'],
                                                      cache_versions, rpc.events, root, environment) if cache_profile else None
            git_proof = None
            if graph['contract']['git_profile'] is not None:
                paths = [name for name, value in raw['state_after'].items() if value.get('kind') == 'file' and name.startswith('.git/')]
                paths += graph['contract']['roles']['application'] + graph['contract']['roles']['tests']
                paths += [graph['contract']['roles']['off']]
                git_after_bytes = {name: (root / name).read_bytes() for name in paths if name is not None and (root / name).is_file()}
                git_proof = core.validate_git_rollback(core.read_record(graph['contract']['git_profile'], 'git-profile'),
                                                       graph['state'], raw['state_after'], git_before_bytes, git_after_bytes,
                                                       rpc.events, graph['contract']['roles'], cache_proof, off_samples)
            core.validate_transition(plan, graph['state'], raw['state_after'], graph['contract']['evidence'],
                                     contents_before=captured_before, contents_after=captured_after,
                                     cache_proof=cache_proof, git_proof=git_proof, capability_proof=capability_proof)
    except BaseException as error:
        record_failure(raw, error, stage)
    finally:
        if rpc is not None:
            raw.update(wire=rpc.wire, thread_id=rpc.thread_id, turn_id=rpc.turn_id)
        if transport is not None:
            try:
                raw['close'] = transport.close()
                for frame in raw['close'].pop('tail_frames', []):
                    rpc.receive(raw=frame)
                core.require(raw['close']['reaped'] is True and raw['close']['partial_stdout_bytes'] == 0,
                             'owned process not fully closed')
                core.require(not rpc.command_items and not rpc.active_items and not rpc.pending,
                             'pending/active lifecycle after owned process close')
                core.require(not raw['close'].get('watchdog_fired') and raw['close'].get('watchdog_error') is None,
                             'owned process lifetime watchdog expired')
            except BaseException as error:
                record_failure(raw, error, 'owned-process-close')
        try:
            final_state = core.inventory(root)
            prior_state = raw['state_after']
            raw['state_after'] = final_state
            core.require(prior_state is None or final_state == prior_state,
                         'state changed during owned process shutdown/drain')
            if 'metadata' in locals():
                metadata()
            if 'actual_env' in locals():
                core.require(legacy.environment_facts(environment) == actual_env, 'environment changed during close')
        except BaseException as error:
            record_failure(raw, error, 'post-close-final-state-or-metadata')
        if raw['failure'] is None:
            try:
                capture_review_target(graph, raw, output)
            except BaseException as error:
                record_failure(raw, error, 'post-close-review-target-capture')
        try:
            raw['accounting'] = core.validate_wire(raw['wire'], raw['thread_id'], raw['turn_id'])
        except BaseException:
            starts = sum(e['direction'] == 'request' and e['payload'].get('method') == 'turn/start' for e in raw['wire'])
            raw['accounting'] = {'actual': None, 'attempted': starts, 'charged': starts, 'status': 'UNKNOWN', 'accepted': 0}
            record_failure(raw, core.Hold('wire-reconciliation'), 'wire-reconciliation')
        if time.monotonic() > deadline:
            record_failure(raw, TimeoutError(), 'absolute-context-deadline')
        core.validate_record(raw, 'context')
        _save(output / 'context.json', raw)
    return raw


def produce_lookup(command_ref, expected_command_sha256, transport_factory=ProcessTransport):
    """Separately released zero-USER lookup, never a business-row release."""
    graph = core.validate_lookup_command(command_ref, expected_command_sha256)
    enforce_control_scope(graph)
    command, scope, policy = (graph[key] for key in ('command', 'scope', 'policy'))
    output = Path(command['output'])
    output.mkdir(mode=0o700)
    root = Path(scope['root'])
    before = core.inventory(root)
    environment = dict(os.environ)
    legacy = core.load_legacy()
    native = graph['native']
    facts = {'configuration_identity': None, 'config_facts': None, 'native13': None, 'catalog_proof': None,
             'capability': None, 'supplied_dynamic_tools': [], 'bundles': [],
             'process_id': None, 'close': None, 'failure': None,
             'source_set': command['source_set'], 'native_binding': command['native_binding'], 'invariant_candidate': None}
    raw = {'schema': 'postclosure-lookup-v1', 'policy': command['policy'], 'wire': [],
           'state_before': before, 'state_after': None, 'native_facts': facts, 'USER': 0}
    failures = {'failure': None}
    transport = None
    rpc = None
    stage = 'lookup-prelaunch'
    candidate = None
    deadline = time.monotonic() + 180
    try:
        observed_environment = legacy.environment_facts(environment)
        core.require(observed_environment == graph['choice']['environment'], 'lookup environment drift')
        legacy.require_environment(observed_environment, native)
        transport = transport_factory(policy['argv'], root, environment, deadline - 2)
        facts['process_id'] = transport.pid
        rpc = RecordingRPC(transport, deadline - 2)
        stage = 'lookup-initialize'
        rpc.call('initialize', {'clientInfo': {'name': 'ains-postclosure-lookup-v1', 'version': '1'}})
        rpc.send('initialized', notification=True)
        with core.bound_helpers(output / 'helper-output') as (_, (helpers, imports)):
            installed = helpers['activation_r3'].inventory(root)
            def metadata():
                pins = {**policy['metadata_paths'], **graph['pins']}
                observed = core.sample_metadata(pins)
                return observed
            def bundle():
                nonlocal candidate
                start_meta = metadata()
                start = core.inventory(root)
                core.require(not any(helpers['activation_r3'].mdm_forced().values()), 'lookup managed state')
                first = rpc.call('config/read', {'includeLayers': True, 'cwd': str(root)})
                catalog = rpc.call('skills/list', {'cwds': [str(root)], 'forceReload': True})
                second = rpc.call('config/read', {'includeLayers': True, 'cwd': str(root)})
                end = core.inventory(root)
                end_meta = metadata()
                observed_policy = dict(policy, metadata_paths={**policy['metadata_paths'], **graph['pins']})
                def validate_catalog(value, config):
                    return legacy.validate_catalog(value, installed,
                        legacy.config_facts(config, helpers['activation_closure_probe'].structural), 'live')
                frame = core.validate_bundle(first, catalog, second, start, end, start_meta, end_meta,
                                             observed_policy, scope, validate_catalog)
                core.require(start == before and not any(helpers['activation_r3'].mdm_forced().values()) and
                             helpers['activation_r3'].inventory(root) == installed, 'lookup state/install/managed drift')
                if graph['contract']['capability_profile'] is not None:
                    facts['capability'] = core.validate_capability(
                        core.read_record(graph['contract']['capability_profile'], 'capability-profile'),
                        second, supplied_dynamic_tools=[], authorized_methods=RecordingRPC.METHODS)
                if facts['native13'] is not None:
                    observed_candidate = core.invariant_projection(scope, graph['manifest'], second, catalog, facts['native13'], environment, end_meta)
                    core.require(candidate is None or candidate == observed_candidate, 'zero observation baseline cannot reset')
                    if graph['anchor'] is not None:
                        core.validate_anchor(graph['anchor'], observed_candidate)
                    candidate = observed_candidate
                    frame['invariant_sha256'] = core.canonical_hash(candidate)
                else:
                    frame['invariant_sha256'] = None
                facts['bundles'].append(frame)
                facts['config_facts'] = legacy.config_facts(second, helpers['activation_closure_probe'].structural)
                return frame, second
            stage = 'lookup-preflight'
            _, config = bundle()
            request = {'cwd': str(root), 'model': native['forward_thread_expectation']['model'],
                       'approvalPolicy': 'never', 'sandbox': 'workspace-write', 'ephemeral': True}
            stage = 'lookup-thread-start'
            actual = rpc.call('thread/start', request)
            facts['native13'] = legacy.reconcile_thread(actual, request, native['forward_thread_expectation'], config['config'])
            stage = 'lookup-two-equal-baselines'
            first, _ = bundle()
            second, _ = bundle()
            core.Baselines(first, second)
            facts['configuration_identity'] = second['config']
            facts['catalog_proof'] = second['catalog_proof']
            rpc.drain()
    except BaseException as error:
        record_failure(failures, error, stage)
    finally:
        if transport is not None:
            try:
                facts['close'] = transport.close()
                for frame in facts['close'].pop('tail_frames', []):
                    rpc.receive(raw=frame)
                core.require(facts['close']['reaped'] is True and not rpc.active_items and not rpc.pending and
                             facts['close']['partial_stdout_bytes'] == 0 and not facts['close'].get('watchdog_fired') and
                             facts['close'].get('watchdog_error') is None, 'lookup owned close/lifecycle failure')
            except BaseException as error:
                record_failure(failures, error, 'lookup-owned-close')
        if rpc is not None:
            raw['wire'] = rpc.wire
        try:
            raw['state_after'] = core.inventory(root)
            core.require(raw['state_after'] == before, 'lookup post-close state mutation')
            if 'metadata' in locals():
                metadata()
            if 'observed_environment' in locals():
                core.require(legacy.environment_facts(environment) == observed_environment, 'lookup close environment drift')
        except BaseException as error:
            record_failure(failures, error, 'lookup-final-state-or-metadata')
        if time.monotonic() > deadline:
            record_failure(failures, TimeoutError(), 'lookup-absolute-deadline')
        if failures['failure'] is None:
            try:
                core.require(candidate is not None, 'actual invariant observation missing')
                candidate_ref = _save_bytes(output / 'invariant-candidate.json', (json.dumps(candidate, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode())
                facts['invariant_candidate'] = candidate_ref
            except BaseException as error:
                record_failure(failures, error, 'lookup-invariant-candidate')
        facts['failure'] = failures['failure']
        if facts['failure'] is None:
            try:
                core.validate_lookup(raw, command['policy'], command['source_set'], command['native_binding'])
            except BaseException as error:
                record_failure(failures, error, 'lookup-reconciliation')
                facts['failure'] = failures['failure']
        _save(output / 'lookup.json', raw)
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--validate-only', action='store_true')
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--lookup', action='store_true')
    parser.add_argument('--command')
    parser.add_argument('--command-sha256')
    args = parser.parse_args(argv)
    if not args.validate_only and not args.execute and not args.lookup:
        parser.print_help()
        return 0
    core.require(args.command and args.command_sha256, 'exact command path and caller digest required')
    reference = {'path': args.command, 'sha256': args.command_sha256}
    if args.validate_only:
        record = core.decode(core.read_ref(reference))
        if record.get('schema') == 'postclosure-lookup-command-v1':
            graph = core.validate_lookup_command(reference, args.command_sha256)
        else:
            graph = core.validate_graph(reference, args.command_sha256)
        enforce_control_scope(graph)
        print(json.dumps({'validated': True, 'executed': False}))
        return 0
    if args.lookup:
        raw = produce_lookup(reference, args.command_sha256)
        print(json.dumps({'USER': 0, 'failure': raw['native_facts']['failure']}))
        return 0 if raw['native_facts']['failure'] is None else 1
    raw = run_released(reference, args.command_sha256)
    print(json.dumps({'business_PASS': False, 'failure': raw['failure'], 'accounting': raw['accounting']}))
    return 0 if raw['failure'] is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
