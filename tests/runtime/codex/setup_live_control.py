#!/usr/bin/env python3
"""Finite setup live integration. Import and no-argument CLI are inert.

run_released(ref, sha) is a source-owned caller boundary, not an authorization
service: the invoking Root tool call must separately authorize this exact source
and command. JSON fields only route the already authorized operation. No native
process, fixture mutation, C claim, or model is exercised by this module's tests.

Command schema setup-live-command-v1 (closed): branch, root, model, expected,
continuation, output, claims, adoption, source_pins, executable, argv, environment,
environment_binding, scope, policy, manifest, initial_state. Each of adoption,
manifest and initial_state is a {path, sha256} reference. source_pins are current
core.ref(..., executable=True) records, including this integration/test and the
reviewed operator/primitives/core/native/transport/helpers. environment is the
released native environment_facts result; expected is independently supplied
THREAD_FIELDS, never copied from the actual response. policy is current core
process-policy DATA, including exact mandatory metadata. scope uses current core
scope fields. output and claims must be pre-existing protected directories under
C. output must be empty, exclusive per command; claims are lifetime stable.

Root reads sequential *.observation.json then creates the advertised
*.decision.json with O_EXCL, mode 0600, AFTER observing it. Decision schema is
{kind, predecessor_sha256, value}; predecessor_sha256 hashes the original retained
observation bytes. judge value is {question_spans, configured_command, receipt};
spans are UTF-8 BYTE [start,end] offsets into the presented completed output.
The live setup profile also requires business_acceptance, the digest of the
presented exact business_transition. Extra commands have a separate one-use
command-scope decision value {observation_sha256}. These are actual Root
judgments after observation, never declarations that snapshots stop execution.
Other values are {body} with actual Root premise/answer/ack text. Nothing here
classifies semantic questions, creates future answers, or grants tool authority.
"""
from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import stat
import time

import postclosure as core
import setup_postclosure as setup
import setup_postclosure_operator as operator
from owned_transport import diagnostic_receipt

CORE_SHA256 = 'd65a6707a197e379cca4aace4d451288f54a2c8494d1d8c2ae1855cf24ec5cdf'
OPERATOR_SHA256 = '9ee2999fb73302b273cf02c9e7a3ae13706951c7e5ee514812e9a375dd6a7cd9'
C = core.CONTROL_ROOT
MAX_RECORD = 1048576


def physical(path, directory=True):
    path = Path(path)
    setup.require(path.is_absolute() and path.resolve(strict=True) == path and
                  not path.is_symlink(), 'physical canonical path required')
    info = path.stat()
    setup.require(info.st_uid == os.getuid() and
                  (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)),
                  'owned physical object required')
    return path


def protected(path):
    path = physical(path)
    setup.require(path.stat().st_mode & 0o077 == 0, 'protected directory mode required')
    return path


def read_json(path):
    path = physical(path, False)
    setup.require(path.stat().st_nlink == 1 and path.stat().st_size <= MAX_RECORD,
                  'bounded unaliased record required')
    raw, _ = core.file_bytes(path)
    return setup.decode(raw), raw


def save_new(directory, name, value):
    """Only new names; fsync record and directory, no overwrite or refunds."""
    directory = protected(directory)
    setup.require(Path(name).name == name, 'local record name required')
    raw = setup.canonical(value) + b'\n'
    setup.require(len(raw) <= MAX_RECORD, 'retention size bound')
    parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(parent)
    finally:
        os.close(parent)
    return setup.digest(raw)


def business(raw, native):
    """Admit only unchanged nonsecret business text; ambiguous bytes HOLD."""
    text = setup.raw_text(raw)
    setup.require(native.redacted_config(text) == text,
                  'business text requires secret redaction: HOLD')
    return text

class BusinessProfile:
    """Finite setup-owned transition, separate from immutable runtime inputs.

    Snapshots are observations, never execution barriers. Only the exact test
    and finite read commands below have a cache provenance classification.
    Root reviews actual business semantics and Duplicate's extra commands.
    N7 reads pass this finite classifier and the actual turn judgment.
    """
    def __init__(self, branch, root, initial, native):
        self.root, self.native = physical(root), native
        self.duplicate = branch == 'Duplicate-B-copy'
        setup.strict_equal(initial, setup.full_state(self.root, initial['grants']))
        self.original = copy.deepcopy(initial)
        self.checkpoint = copy.deepcopy(initial)
        self.actual_grants = None
        self.original_bodies = self.bodies(initial)
        self.observations = []
        self.phase = None
        if self.duplicate:
            setup.require(set(self.original_bodies) == {'AGENTS.md', 'CLAUDE.md'},
                          'duplicate instruction prestate required')
            agents = self.section(self.original_bodies['AGENTS.md'].encode())
            claude = self.section(self.original_bodies['CLAUDE.md'].encode())
            setup.require(agents[1].rstrip(b'\n') == claude[1].rstrip(b'\n'),
                          'actual duplicate sections differ')
            setup.require(b'@AGENTS.md' not in self.original_bodies['CLAUDE.md'].encode(),
                          'preexisting import unsupported')
            self.migrated = claude[0] + b'@AGENTS.md\n\n' + claude[2]
        else:
            setup.require(not self.original_bodies, 'N7 absent instructions required')
            self.migrated = None

    @staticmethod
    def section(raw):
        # The admitted fixtures use one exact h2 section; do not normalize text.
        marker = b'## Agent skills\n'
        setup.require(raw.count(marker) == 1, 'one actual managed section required')
        start = raw.index(marker)
        setup.require(start == 0 or raw[start - 1:start] == b'\n', 'managed section boundary')
        end = raw.find(b'\n## ', start + len(marker))
        end = len(raw) if end < 0 else end + 1
        return raw[:start], raw[start:end], raw[end:]

    @staticmethod
    def records(state):
        setup.strict_equal(state, state)
        records = {record['path']: record for record in state['records']}
        setup.require(len(records) == len(state['records']), 'duplicate FULLSTATE path')
        return records

    def bodies(self, state):
        records, result = self.records(state), {}
        for name in ('AGENTS.md', 'CLAUDE.md'):
            if name in records:
                record = records[name]
                setup.require(record['kind'] == 'file' and record['mode'] == 0o644 and
                              record['nlink'] == 1, 'instruction file topology/mode')
                raw, info = core.file_bytes(self.root / name)
                setup.require(record['sha256'] == setup.digest(raw) and record['size'] == len(raw)
                              and (record['dev'], record['ino']) == (info.st_dev, info.st_ino),
                              'business file snapshot/body mismatch')
                result[name] = business(raw, self.native)
        return result

    def validate(self, state, phase):
        current, previous = self.records(state), self.records(self.checkpoint)
        if self.actual_grants is None:
            self.actual_grants = copy.deepcopy(state['grants'])
            self.checkpoint['grants'] = copy.deepcopy(state['grants'])
        setup.require(state['grants'] == self.actual_grants, 'actual grants drift')
        mutable = self.duplicate and phase in ('initial', 'answer')
        if not mutable:
            setup.strict_equal(self.checkpoint, state)
            return self.bodies(state)
        setup.require(set(current) == set(previous), 'business namespace drift')
        setup.require(all(current[path] == record for path, record in previous.items()
                          if path != 'CLAUDE.md'), 'immutable FULLSTATE drift')
        bodies = self.bodies(state)
        raw = bodies['CLAUDE.md'].encode()
        setup.require(raw in (self.original_bodies['CLAUDE.md'].encode(), self.migrated),
                      'only exact duplicate span replacement permitted')
        setup.require(current['CLAUDE.md']['dev'] == previous['CLAUDE.md']['dev'],
                      'business device changed')
        # A byte-identical rewrite is not a permitted replacement.
        if current['CLAUDE.md']['sha256'] == previous['CLAUDE.md']['sha256']:
            setup.require(current['CLAUDE.md'] == previous['CLAUDE.md'],
                          'unchanged business inode replaced')
        return bodies

    def transition(self, phase, before, after):
        setup.strict_equal(self.checkpoint, before)
        bodies = self.validate(after, phase)
        return dict(phase=phase, before=copy.deepcopy(self.original_bodies if
            self.checkpoint['records'] == self.original['records'] else self.accepted_bodies),
            after=bodies, before_state_sha256=setup.digest(setup.canonical(before)),
            after_state_sha256=setup.digest(setup.canonical(after)),
            delta='duplicate-section-to-import' if before != after else 'none')

    def accept(self, proof, after, acceptance):
        setup.require(type(acceptance) is str and acceptance == setup.digest(setup.canonical(proof)),
                      'exact business acceptance digest required')
        setup.require(proof['after_state_sha256'] == setup.digest(setup.canonical(after)) and
                      proof == self.transition(proof['phase'], self.checkpoint, after),
                      'stale business acceptance')
        self.checkpoint = copy.deepcopy(after)
        self.accepted_bodies = copy.deepcopy(proof['after'])

    def sample_metadata(self, expected):
        immutable = {path: pin for path, pin in expected.items()
                     if not (self.duplicate and path == str(self.root / 'CLAUDE.md'))}
        core.sample_metadata(immutable)
        # Mutable business is still observed, retained in FULLSTATE and checked
        # against its original span; it is never an immutable baseline refresh.
        return {path: core.metadata_receipt(path) for path in expected}

    def validate_contributors(self, scope, config):
        if self.duplicate:
            mutable = str(self.root / 'CLAUDE.md')
            setup.require(all(pin['path'] != mutable for pin in scope['instruction_sources']) and
                          all(config['config'].get(key) != mutable for key in
                              ('model_instructions_file', 'instructions_file',
                               'developer_instructions_file')),
                          'mutable business slot is a native instruction contributor')

    def projection(self, candidate):
        result = copy.deepcopy(candidate)
        if self.duplicate:
            setup.require('CLAUDE.md' in result['fixture_metadata'], 'business contributor missing')
            result['fixture_metadata'].pop('CLAUDE.md')
        return result

    def _read_profile(self, item):
        setup.require(item.get('cwd') == str(self.root), 'local read cwd required')
        try:
            argv = operator.command_core().decode_command(item.get('command'))
        except (operator.command_core().Hold, TypeError) as error:
            raise setup.Hold('unreviewable compound/indirect command') from error
        # A false shell predicate is a successful observation, with exit 1.
        # Admit only the setup procedure's finite instruction-file probes.
        predicate = argv[1:-1] if argv[0] == '[' and argv[-1] == ']' else (
            argv[1:] if argv[0] == 'test' else [])
        targets = {'AGENTS.md', 'CLAUDE.md'}
        expected = None
        if len(predicate) == 2 and predicate[0] == '-L' and predicate[1] in targets:
            expected = int(not (self.root / predicate[1]).is_symlink())
        elif (len(predicate) == 3 and predicate[1] == '-ef'
              and predicate[0] in targets and predicate[2] in targets):
            first, second = (self.root / predicate[index] for index in (0, 2))
            same = first.exists() and second.exists() and first.samefile(second)
            expected = int(not same)
        if expected is not None:
            return 'topology-read', expected
        # No other interpreter or shell is inferred cache-safe from a clean
        # endpoint. Reads are confined to preexisting, regular business files.
        args = argv[1:]
        if argv[0] in ('cat', '/bin/cat') and args and args[0] == '--':
            args = args[1:]
        setup.require(argv[0] in ('cat', '/bin/cat') and args and
                      all(not arg.startswith('-') for arg in args),
                      'command lacks finite read/cache provenance')
        original = self.records(self.original)
        for arg in args:
            path = Path(arg)
            path = path if path.is_absolute() else self.root / path
            setup.require('..' not in path.parts and path.is_relative_to(self.root),
                          'read outside actual root')
            relative = str(path.relative_to(self.root))
            setup.require(relative in original and original[relative]['kind'] == 'file'
                          and not path.is_symlink(), 'read target outside original regular scope')
        return 'read', 0

    def read_intent(self, item):
        # This is only a finite intent classification, never completion evidence.
        if item.get('type') != 'commandExecution':
            return None
        try:
            return self._read_profile(item)[0]
        except (setup.Hold, operator.command_core().Hold, TypeError, KeyError, IndexError):
            return None

    def classify_command(self, item):
        setup.require(item.get('cwd') == str(self.root) and item.get('status') in ('completed', 'failed')
                      and type(item.get('exitCode')) is int,
                      'completed local command required')
        if operator.command_core().command_matches(item.get('command'), setup.EXECUTED_COMMAND):
            setup.require(item['status'] == 'completed' and item['exitCode'] == 0,
                          'completed successful local command required')
            return 'configured-test'
        classification, expected = self._read_profile(item)
        setup.require(item['exitCode'] == expected and
                      (item['status'] == 'completed' or expected == 1),
                      'read command result mismatch')
        return classification

    def observe(self, event, phase, state):
        setup.fields(event, 'thread_id turn_id item wire_index raw_sha256')
        item = event['item']
        setup.require(item['type'] in ('commandExecution', 'fileChange'), 'side effect observation kind')
        setup.require(type(event['wire_index']) is int and event['wire_index'] >= 0 and
                      type(event['raw_sha256']) is str and len(event['raw_sha256']) == 64 and
                      all(character in '0123456789abcdef' for character in event['raw_sha256']),
                      'actual wire identity required')
        key = (event['thread_id'], event['turn_id'], item['id'])
        setup.require(key not in {(o['thread_id'], o['turn_id'], o['item']['id'])
                                  for o in self.observations},
                      'duplicate side effect observation')
        self.validate(state, phase)
        if item['type'] == 'commandExecution':
            classification = self.classify_command(item)
        else:
            setup.require(self.duplicate and phase in ('initial', 'answer') and
                          item.get('status') == 'completed', 'file change outside business phase')
            changes = item.get('changes')
            setup.require(type(changes) is list and len(changes) == 1 and
                          changes[0].get('path') == str(self.root / 'CLAUDE.md'),
                          'file change outside exact business slot')
            classification = 'business-change'
        self.observations.append(copy.deepcopy(event) | dict(phase=phase,
            classification=classification, state=copy.deepcopy(state)))

    def evidence(self, receipt, records):
        expected = []
        for offset, record in enumerate(records):
            obj = record['payload']
            if obj.get('method') != 'item/completed':
                continue
            params, item = obj['params'], obj['params']['item']
            setup.require(item['type'] in ('agentMessage', 'userMessage', 'reasoning',
                                          'commandExecution', 'fileChange'),
                          'unclassified side effect tool: HOLD')
            if item['type'] in ('commandExecution', 'fileChange'):
                setup.require((params.get('threadId'), params.get('turnId')) ==
                              (receipt['thread_id'], receipt['turn_id']),
                              'foreign side effect coverage')
                expected.append(dict(thread_id=receipt['thread_id'], turn_id=receipt['turn_id'],
                    item=item, wire_index=receipt['request_index'] + offset,
                    raw_sha256=setup.digest(record['raw'])))
        observed = [event for event in self.observations if
                    (event['thread_id'], event['turn_id']) ==
                    (receipt['thread_id'], receipt['turn_id'])]
        setup.require([{k: value[k] for k in ('thread_id', 'turn_id', 'item', 'wire_index', 'raw_sha256')}
                       for value in observed] == expected, 'incomplete actual side effect coverage')
        return copy.deepcopy(observed)


class RootExchange:
    def __init__(self, directory, native, clock=time.monotonic, pause=time.sleep):
        self.directory = protected(directory)
        self.identity = (self.directory.stat().st_dev, self.directory.stat().st_ino)
        self.native, self.clock, self.pause = native, clock, pause
        self.sequence = 0
        self.profile = None
        self.phase = None
        self.scope_receipts = set()

    def check(self, deadline):
        info = protected(self.directory).stat()
        setup.require((info.st_dev, info.st_ino) == self.identity,
                      'Root control directory identity changed')
        setup.require(self.clock() < deadline, 'Root decision deadline')

    def request(self, kind, observation, deadline):
        self.check(deadline)
        self.sequence += 1
        stem = 'root-%03d' % self.sequence
        decision_path = self.directory / (stem + '.decision.json')
        setup.require(not decision_path.exists() and not decision_path.is_symlink(),
                      'prewritten Root decision forbidden')
        document = dict(kind=kind, observation=observation,
                        decision_file=decision_path.name, runtime_PASS=False)
        predecessor = save_new(self.directory, stem + '.observation.json', document)
        observed_at = (self.directory / (stem + '.observation.json')).stat().st_mtime_ns
        while True:
            self.check(deadline)
            if decision_path.exists() or decision_path.is_symlink():
                value, raw = read_json(decision_path)
                info = decision_path.stat()
                setup.require(info.st_mode & 0o077 == 0 and info.st_mtime_ns >= observed_at,
                              'late-created protected Root decision required')
                setup.fields(value, 'kind predecessor_sha256 value')
                setup.require(value['kind'] == kind and value['predecessor_sha256'] == predecessor,
                              'Root decision observation identity mismatch')
                self.check(deadline)
                save_new(self.directory, stem + '.accepted.json',
                         dict(decision_sha256=setup.digest(raw), predecessor_sha256=predecessor))
                return value['value']
            self.pause(min(0.05, max(0, deadline - self.clock())))

    def judge(self, receipt, records, before, after, deadline):
        output = receipt['output']
        text = business(output, self.native)
        proof = evidence = None
        if self.profile is not None:
            proof = self.profile.transition(self.phase(), before, after)
            evidence = self.profile.evidence(receipt, records)
            # Check secret classification before exposing actual command/diff.
            business(setup.canonical(evidence), self.native)
        value = self.request('judge', dict(
            completed_turn={k: v for k, v in receipt.items() if k != 'output'},
            output=text, output_sha256=setup.digest(output),
            records_sha256=setup.digest(setup.canonical([dict(
                direction=record.get('direction'), start=record.get('start'), end=record.get('end'),
                bytes=len(record['raw']), sha256=setup.digest(record['raw'])) for record in records])),
            before=before, after=after, business_transition=proof,
            actual_side_effects=evidence), deadline)
        setup.fields(value, 'question_spans configured_command receipt' +
                     (' business_acceptance' if self.profile is not None else ''))
        spans = value['question_spans']
        setup.require(type(spans) is list and len(spans) <= 1, 'finite actual question spans')
        questions = []
        for span in spans:
            setup.require(type(span) is list and len(span) == 2 and
                          all(type(i) is int for i in span) and
                          0 <= span[0] < span[1] <= len(output), 'exact actual byte span required')
            question = output[span[0]:span[1]]
            business(question, self.native)
            questions.append(question)
        setup.require(value['configured_command'] in (None, setup.CONFIGURED_COMMAND),
                      'configured command judgment mismatch')
        if value['receipt'] is not None:
            setup.command_receipt(value['receipt'])
        if self.profile is not None:
            if proof['delta'] != 'none':
                setup.require(any(event['classification'] == 'business-change' for event in evidence),
                              'business replacement lacks observed file change')
            tests = [event for event in evidence if event['classification'] == 'configured-test']
            setup.require(len(tests) <= 1 and bool(tests) == (value['receipt'] is not None),
                          'actual configured command/Root receipt mismatch')
            if tests:
                expected = dict(command=setup.EXECUTED_COMMAND, status='completed', exit_code=0,
                    earlier_import_cache_writes=False, other_cache_writes=False)
                setup.require(value['receipt'] == expected, 'actual cache receipt mismatch')
            # All commands were finitely classified; endpoint cache equality is
            # additional evidence, never a claim that snapshots are barriers.
            setup.require(operator.cache_records(before) == operator.cache_records(after),
                          'cache endpoint mutation')
            self.profile.accept(proof, after, value['business_acceptance'])
        return dict(questions=tuple(questions), configured_command=value['configured_command'],
                    receipt=value['receipt'])

    def command_scope(self, extras, receipt, records, before, after, deadline):
        setup.require(self.profile is not None, 'actual setup profile required')
        evidence = self.profile.evidence(receipt, records)
        commands = [event['item'] for event in evidence if
                    event['item']['type'] == 'commandExecution' and
                    event['classification'] != 'configured-test']
        setup.require(commands == extras, 'extra command observation coverage mismatch')
        key = (receipt['thread_id'], receipt['turn_id'])
        setup.require(key not in self.scope_receipts, 'command scope receipt already consumed')
        observation = dict(thread_id=key[0], turn_id=key[1], actual_side_effects=evidence,
            before=before, after=after, snapshots_are_execution_barriers=False)
        digest = setup.digest(setup.canonical(observation))
        value = self.request('command-scope', observation, deadline)
        setup.fields(value, 'observation_sha256')
        setup.require(value['observation_sha256'] == digest, 'exact command scope approval required')
        self.scope_receipts.add(key)
        return True

    def root(self, kind, predecessor, observation, deadline):
        # The prior judge observation is already durable before asking for any
        # actual answer. Present its exact predecessor, not a future prediction.
        presented = None
        if observation is not None:
            receipt = observation['receipt']
            presented = dict(turn_id=receipt['turn_id'],
                             output=business(receipt['output'], self.native),
                             output_sha256=setup.digest(receipt['output']))
        setup.require(kind == 'premise' or presented is not None,
                      'completed receipt required before Root answer')
        value = self.request(kind, dict(predecessor=predecessor,
                                       completed_turn=presented,
                                       accepted_business=None if self.profile is None else
                                       self.profile.bodies(self.profile.checkpoint)), deadline)
        setup.fields(value, 'body')
        body = setup.text(value['body']).encode('utf-8')
        business(body, self.native)
        return setup.root_decision(kind, body, predecessor)


class Retention:
    """Hash raw wire, retain safe config identities, never dump raw operator vars."""
    def __init__(self, directory, native):
        self.directory, self.native = protected(directory), native
        self.sequence = 0

    def write(self, kind, value):
        self.sequence += 1
        return save_new(self.directory, 'event-%05d.json' % self.sequence,
                        dict(kind=kind, value=value, runtime_PASS=False))

    def wire(self, direction, raw, method=None):
        summary = dict(direction=direction, bytes=len(raw), sha256=setup.digest(raw), method=method)
        # Payload is intentionally absent. A config response gets its safe full
        # identity in baseline(), startup/account/error payloads get hashes only.
        self.write('wire', summary)

    def side_effect_diagnostic(self, event, root):
        """Hash-only untrusted strings; fixed enums/types for rejected observations."""
        root = Path(root)
        def hashed(value):
            return setup.digest(setup.canonical(value))
        def item_shape(item):
            cwd = item.get('cwd')
            relation = 'missing'
            if type(cwd) is str:
                path = Path(cwd)
                relation = ('exact-root' if path == root else
                            'within-root' if path.is_absolute() and '..' not in path.parts
                            and path.is_relative_to(root) else 'outside-root')
            status = item.get('status')
            status = status if status in ('inProgress', 'completed', 'failed', 'declined') else 'unknown'
            kind = item.get('type')
            kind = kind if kind in ('commandExecution', 'fileChange') else 'unknown'
            code = item.get('exitCode')
            return dict(kind=kind, item_sha256=hashed(item), command_sha256=hashed(item.get('command')),
                id_sha256=hashed(item.get('id')), cwd_type=type(cwd).__name__, cwd_relation=relation,
                status=status, status_sha256=hashed(item.get('status')), exit_code_type=type(code).__name__,
                exit_code=code if type(code) is int and -(1 << 31) <= code < (1 << 31) else None)
        setup.require(type(event['wire_index']) is int and event['wire_index'] >= 0 and
                      type(event['raw_sha256']) is str and len(event['raw_sha256']) == 64 and
                      all(char in '0123456789abcdef' for char in event['raw_sha256']),
                      'actual diagnostic frame identity required')
        setup.require(event['stage'] in ('started', 'completed') and event['reason_code'] in
                      ('START_PRE_ADMISSION', 'COMPLETION_PRE_ADMISSION', 'OVERLAP_NOT_READ_ONLY'),
                      'finite diagnostic stage/reason required')
        self.write('side-effect-diagnostic', dict(diagnostic_only=True, stage=event['stage'],
            reason_code=event['reason_code'], wire_index=event['wire_index'],
            raw_sha256=event['raw_sha256'], thread_sha256=hashed(event['thread_id']),
            turn_sha256=hashed(event['turn_id']), item=item_shape(event['item']),
            active_items=[item_shape(item) for item in event['active_items']]))

    def finish(self, runner, primary):
        constructor_cleanup = diagnostic_receipt(getattr(primary, 'cleanup_receipt', None))
        constructor_failures = getattr(primary, '_postclosure_cleanup_failures', [])
        # ProcessTransport supplies type-name codes, never diagnostic messages.
        setup.require(type(constructor_failures) is list and all(
            type(code) is str and len(code) <= 128 and code.isidentifier()
            for code in constructor_failures), 'invalid constructor cleanup type codes')
        if runner is None:
            self.write('final', dict(primary_failure=None if primary is None else type(primary).__name__,
                constructor_cleanup=constructor_cleanup,
                secondary_failures=list(constructor_failures), attempts=[], reserved=[], snapshots=[],
                accounting=None, final_state_observed=False, stage='before-operator'))
            return
        self.write('final', dict(primary_failure=None if primary is None else type(primary).__name__,
            constructor_cleanup=constructor_cleanup,
            secondary_failures=list(runner.cleanup_failures) + constructor_failures,
            accounting=runner.gate.accounting(), attempts=runner.gate.attempts,
            final_state_observed=bool(runner.samples and runner.samples[-1]['stage'] == 'post-close'),
            reserved=runner.reserved, closures=[{
                k: v for k, v in close.items() if k != 'tail_frames'} | {
                'tail_frames': [dict(bytes=len(raw), sha256=setup.digest(raw))
                                for raw in close.get('tail_frames', [])]}
                for close in runner.closures], snapshots=runner.samples))


class ObservedTransport:
    """Persist pre-write charges and reconcile actual thread grants in memory."""
    def __init__(self, transport, runner, retention, native, spec):
        self.transport, self.runner, self.retention = transport, runner, retention
        self.native, self.spec = native, spec
        self.requests, self.actual, self.config = {}, None, None

    def write(self, raw, deadline):
        obj = setup.decode(raw)
        method = obj['method']
        if 'id' in obj:
            self.requests[setup.typed_id(obj['id'])] = obj
        if method == 'turn/start':
            self.retention.write('attempt-before-write', copy.deepcopy(self.runner.gate.active))
        self.retention.wire('client', raw, method)
        try:
            self.transport.write(raw, deadline)
        except BaseException as error:
            self.retention.write('write-failure', dict(failure=type(error).__name__, delivery='UNKNOWN'))
            raise
        if method == 'turn/start':
            self.retention.write('local-write-complete', dict(delivery='LOCAL_WRITE_COMPLETE'))

    def observe(self, raw):
        self.retention.wire('server', raw)
        obj = setup.decode(raw)
        if 'method' not in obj:
            request = self.requests.get(setup.typed_id(obj.get('id')))
            if request and request['method'] == 'config/read':
                self.config = obj['result'].get('config')
            if request and request['method'] == 'thread/start':
                self.actual = self.native.reconcile_thread(obj['result'], request['params'],
                                                          self.spec['expected'], self.config)
        return raw

    def read(self, deadline):
        return self.observe(self.transport.read(deadline))

    def drain(self, deadline):
        raws = self.transport.drain(deadline)
        return [self.observe(raw) for raw in raws]

    def close(self):
        return self.transport.close()


def validate_materialization_adoption(command):
    """Bind a fresh Root-owned copy without overwriting historical adoption."""
    path = Path(command['adoption']['path'])
    setup.require(path.is_relative_to(C), 'materialization adoption outside current continuation')
    adoption = setup.decode(core.read_ref(command['adoption']))
    setup.require(adoption['decision'] == 'ADOPT_PROPOSED_SETUP_BRANCH_MATERIALIZATION_DATA_ONLY' and
                  adoption['roots'][command['branch']] == command['root'] and
                  command['manifest'] == adoption['composite_manifest'], 'adopted exact root/source relation')
    for key in ('materializer_result', 'materializer_index', 'independent_verifier',
                'independent_report', 'independent_index'):
        core.read_ref(adoption[key])
    return adoption


def released(command_ref, expected_sha256):
    """Validate current exact bytes/identities before any claim or process."""
    setup.require(type(command_ref) is dict and command_ref.get('sha256') == expected_sha256,
                  'externally supplied exact command digest required')
    raw = core.read_ref(command_ref)
    command = setup.decode(raw)
    setup.fields(command, 'schema branch root model expected continuation output claims adoption '
                 'source_pins executable argv environment environment_binding scope policy manifest initial_state')
    setup.require(command['schema'] == 'setup-live-command-v1' and command['branch'] in setup.BRANCHES,
                  'exact finite command branch required')
    continuation = physical(command['continuation'])
    setup.require(continuation == C and Path(command_ref['path']).parent == C,
                  'exact current continuation command required')
    output, claims = protected(command['output']), protected(command['claims'])
    setup.require(output.is_relative_to(C) and claims.is_relative_to(C) and
                  claims == C / 'setup-postclosure-claims' and
                  output != claims and not output.is_relative_to(claims) and
                  not claims.is_relative_to(output) and not any(output.iterdir()),
                  'fresh protected C output/stable lifetime claims required')
    validate_materialization_adoption(command)
    root = physical(command['root'])
    setup.require(not C.is_relative_to(root) and not root.is_relative_to(C), 'protected Root controls overlap model root')
    pins = command['source_pins']
    setup.require(type(pins) is list and len(pins) <= 32, 'finite current source pins required')
    by_path = {pin['path']: pin for pin in pins}
    required = {str(core.HERE / name) for name in (
        'setup_live_control.py', 'setup_live_control_test.py', 'setup_postclosure.py',
        'setup_postclosure_operator.py', 'postclosure.py', 'postclosure_operator.py', 'native_delta.py',
        'owned_transport.py', 'owned_transport_test.py')}
    required |= {str(core.HERE / (name + '.py')) for name in core.HELPERS}
    setup.require(len(by_path) == len(pins) and set(by_path) == required, 'complete exact integration source closure')
    for pin in pins:
        core.read_ref(pin, executable=True)
        setup.require(pin['nlink'] == 1, 'source alias forbidden')
    setup.require(by_path[str(core.HERE / 'postclosure.py')]['sha256'] == CORE_SHA256 and
                  by_path[str(core.HERE / 'setup_postclosure_operator.py')]['sha256'] == OPERATOR_SHA256,
                  'reviewed current source epoch drift')
    native = operator.current_native()
    environment = dict(os.environ)
    facts = native.environment_facts(environment)
    setup.require(facts == command['environment'], 'actual environment drift')
    native.require_environment(facts, command['environment_binding'])
    executable = command['executable']
    core.read_ref(executable, executable=True)
    binding = command['environment_binding']
    setup.require(os.access(executable['path'], os.X_OK) and
                  executable['sha256'] == 'd8990e3ee7acfbc26f91265b12a1a83f0fee40d0e0f8f1f40a37d4ec21f499cf' and
                  binding.get('official_commit') == native.SEMANTIC_COMMIT and
                  binding.get('codex_version') == 'codex-cli 0.164.0' and
                  binding.get('executable_identity', {}).get('sha256') == executable['sha256'],
                  'exact current native executable/source binding required')
    scope, policy = command['scope'], command['policy']
    core.validate_record(scope, 'scope')
    core.validate_record(policy, 'process-policy')
    setup.require(core.read_record(policy['scope'], 'scope') == scope and
                  setup.decode(core.read_ref(policy['native_expectation'])) == command['expected'] and
                  policy['turn_permission'] is None, 'policy scope/native expectation/overlay mismatch')
    for reference in policy['official_sources']:
        core.read_ref(reference)
    setup.require(scope['root'] == scope['realroot'] == str(root), 'scope/root mismatch')
    setup.require(command['argv'] == policy['argv'] == core.argv_for(executable['path'], str(root)),
                  'exact finite native argv required')
    setup.require(type(command['expected']) is dict and
                  set(command['expected']) == set(native.THREAD_FIELDS), 'independent exact native13 expectations required')
    setup.require(command['expected']['runtimeWorkspaceRoots'] == [str(root)] and
                  command['expected']['instructionSources'] ==
                  [pin['path'] for pin in scope['instruction_sources']],
                  'released actual context roots/instruction metadata closure mismatch')
    core.validate_required_metadata(policy, scope)
    core.sample_metadata(policy['metadata_paths'])
    manifest = setup.decode(core.read_ref(command['manifest']))
    setup.require(command['manifest']['sha256'] == core.COMPOSITE_SHA and
                  len(manifest['suite_files']) == 42, 'adopted all16/source42 required')
    native.released_source(command['manifest']['path'])
    initial = setup.decode(core.read_ref(command['initial_state']))
    setup.require(initial == setup.full_state(root, {}), 'released initial materialization FULLSTATE drift')
    # This is a routing release, not an authenticity scheme. Actual Root tool
    # authorization stays with run_released's caller, outside these records.
    return command, native, environment, by_path


def grants(native13, control):
    snapshot = native13['snapshot']
    roots = snapshot['runtimeWorkspaceRoots']
    setup.require(type(roots) is list and roots and all(type(p) is str for p in roots),
                  'actual native runtime root schema unsupported')
    for root in roots:
        path = physical(root)
        setup.require(not control.is_relative_to(path) and not path.is_relative_to(control),
                      'actual runtime grants expose protected Root controls')
    sandbox = snapshot['sandbox']
    setup.fields(sandbox, 'type writableRoots networkAccess excludeTmpdirEnvVar excludeSlashTmp')
    setup.require(sandbox['type'] == 'workspaceWrite' and sandbox['writableRoots'] == [] and
                  sandbox['networkAccess'] is False and
                  all(type(sandbox[key]) is bool for key in ('excludeTmpdirEnvVar', 'excludeSlashTmp')) and
                  snapshot['activePermissionProfile'] is None,
                  'unsupported actual sandbox/profile grants: HOLD')
    setup.require(snapshot['approvalPolicy'] == 'never' and snapshot['approvalsReviewer'] == 'user' and
                  snapshot['multiAgentMode'] == 'explicitRequestOnly' and
                  type(snapshot['disabledPluginIds']) is list and
                  all(type(value) is str for value in snapshot['disabledPluginIds']),
                  'unsupported actual native capability schema: HOLD')
    # Preserve actual capability metadata, including active profile and sandbox;
    # instructionSources are provenance, never a substitute for actual grants.
    return {key: copy.deepcopy(snapshot[key]) for key in
            ('runtimeWorkspaceRoots', 'approvalPolicy', 'approvalsReviewer', 'sandbox',
             'activePermissionProfile', 'disabledPluginIds', 'multiAgentMode')}


def run_released(command_ref, expected_command_sha256):
    command, native, environment, pins = released(command_ref, expected_command_sha256)
    output, root = Path(command['output']), Path(command['root'])
    # Existing-only C dirs. One lifetime command claim, no automatic reset.
    save_new(output, 'command-claim.json', dict(command=command_ref, delivery='UNKNOWN', runtime_PASS=False))
    retention, exchange = Retention(output, native), RootExchange(output, native)
    runner = None
    primary = None
    try:
        claims = operator.DonorClaims(command['claims'])
        consumed = set()
        for path in Path(command['claims']).iterdir():
            record, _ = read_json(path)
            consumed.add(record['key'])
        state = {'transport': None}
        with core.bound_helpers(output / 'helper-output') as (legacy, (helpers, _)):
            installed = helpers['activation_r3'].inventory(root)
            profile = BusinessProfile(command['branch'], root,
                setup.decode(core.read_ref(command['initial_state'])), native)
            exchange.profile = profile
            exchange.phase = lambda: runner.gate.phase
            def context(index, deadline):
                if index > 1:
                    setup.require(profile.actual_grants is not None, 'prior actual grants missing')
                    profile.sample_metadata(command['policy']['metadata_paths'])
                    profile.validate(setup.full_state(root, profile.actual_grants), runner.gate.phase)
                    # Existing AGENTS and every discovered contributor remain
                    # exact. CLAUDE consolidation adds no native AGENTS source.
                    setup.require(command['expected']['instructionSources'] ==
                        [pin['path'] for pin in command['scope']['instruction_sources']],
                        'independently released instruction source list changed')
                for pin in pins.values():
                    core.read_ref(pin, executable=True)
                return dict(root=str(root), model=command['model'], expected=command['expected'])

            def snapshot(stage, index, deadline):
                current = state['transport']
                setup.require(current is not None and current.actual is not None,
                              'fresh actual native grants unavailable')
                profile.sample_metadata(command['policy']['metadata_paths'])
                for pin in pins.values():
                    core.read_ref(pin, executable=True)
                actual = setup.full_state(root, grants(current.actual, C))
                profile.validate(actual, runner.gate.phase)
                retention.write('snapshot', dict(stage=stage, context=index, state=actual))
                return actual

            def baseline(index, config, catalog, actual, fullstate, deadline):
                setup.require(actual == state['transport'].actual, 'actual native baseline mismatch')
                native.released_source(command['manifest']['path'])
                setup.require(helpers['activation_r3'].inventory(root) == installed and
                              not any(helpers['activation_r3'].mdm_forced().values()), 'install/managed drift')
                profile.validate_contributors(command['scope'], config)
                metadata = profile.sample_metadata(command['policy']['metadata_paths'])
                identity = core.policy_projection(config, command['policy'], command['scope'])
                structural = helpers['activation_closure_probe'].structural
                proof = native.validate_catalog(catalog, installed, native.config_facts(config, structural), 'live')
                candidate = core.invariant_projection(command['scope'], command['manifest'], config,
                                                      catalog, actual, environment, metadata)
                # Baseline serialization deliberately strips per-context thread ID.
                result = dict(candidate=profile.projection(candidate), config=dict(identity), catalog_proof=proof,
                              actual_grants=fullstate['grants'])
                retention.write('baseline', result)
                return result

            def factory(spec, deadline):
                transport = operator.process_transport(command['argv'], root, environment, deadline)
                current = ObservedTransport(transport, runner, retention, native, spec)
                state['transport'] = current
                return current

            def observe(event, deadline):
                actual = snapshot('validated-side-effect', len(runner.rpcs), deadline)
                profile.observe(event, runner.gate.phase, actual)
                # Safe classified payload plus complete observed state; no raw config.
                retained = profile.observations[-1]
                business(setup.canonical(retained), native)
                retention.write('validated-side-effect', retained)

            callbacks = operator.TrustedCallbacks(context, snapshot, baseline, exchange.root, exchange.judge,
                exchange.command_scope, observe,
                read_intent=lambda item, deadline: profile.read_intent(item),
                diagnose=lambda event, deadline: retention.side_effect_diagnostic(event, root))
            runner = operator.SetupOperator(command['branch'], frozenset(consumed), callbacks, factory, claims)
            return runner.run()
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            retention.finish(runner, primary)
        except BaseException as error:
            if primary is None:
                raise
            # Preserve both causes without exposing exception messages.
            primary._setup_retention_failure = type(error).__name__
            primary.add_note('setup-live-control stage=final-retention failure=' + type(error).__name__)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--command-ref')
    parser.add_argument('--command-sha256')
    args = parser.parse_args(argv)
    if args.command_ref is None and args.command_sha256 is None:
        return 0
    if args.command_ref is None or args.command_sha256 is None:
        parser.error('Both the externally supplied exact command reference and digest are required.')
    # The authorizing Root tool invocation remains external to these arguments.
    run_released(dict(path=args.command_ref, sha256=args.command_sha256), args.command_sha256)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
