#!/usr/bin/env python3
"""Inert N7-C operator candidate; fake-IO core, no native execution adapter.

--validate-only checks bytes and closed DAG structure without a launch. --execute
requires an external exact command digest, validates it, then HOLDs: native peer
identity, startup retention, terminal and protected claim adapters remain blocked.
No process/PTY/socket is created here. Synthetic receipts are never N7 admission.
"""
import argparse
import hashlib
import os
from pathlib import Path
import stat
import sys

import question_contract as c

NATIVE13 = ('model', 'modelProvider', 'serviceTier', 'reasoningEffort', 'cwd',
            'runtimeWorkspaceRoots', 'instructionSources', 'approvalPolicy',
            'approvalsReviewer', 'sandbox', 'activePermissionProfile',
            'disabledPluginIds', 'multiAgentMode')
BLOCKERS = (
    'No independently admitted native process/socket PID/start identity adapter',
    'No independently admitted protected capability/atomic durable lifetime claim adapter',
    'No independently admitted nonsecret startup RPC schema/profile/raw spool adapter',
    'No independently admitted native terminal decoder/keymap/Root decision adapter',
    'No frozen source/install/native13/B1/current16-all42 live observation adapter',
)


def read_ref(reference):
    """Bounded regular-file read; no symlink components or writable actions.

    Component lstat is diagnostic only; future live authority needs race-safe
    descriptor-relative traversal and protected roots, not this read-only helper.
    """
    c.ref(reference)
    target = Path(reference['path'])
    for part in (target, *target.parents):
        c.require(not stat.S_ISLNK(part.lstat().st_mode), 'symlink reference')
    fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        c.require(stat.S_ISREG(before.st_mode) and before.st_size <= c.MAX_RECORD, 'record file type/size')
        raw = bytearray()
        while len(raw) <= c.MAX_RECORD:
            chunk = os.read(fd, min(65536, c.MAX_RECORD + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(fd)
        c.require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                   before.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_size,
                                         after.st_mtime_ns, after.st_ctime_ns), 'record changed while reading')
        c.require(len(raw) <= c.MAX_RECORD and hashlib.sha256(raw).hexdigest() == reference['sha256'],
                  'record hash/size mismatch')
        return bytes(raw)
    finally:
        os.close(fd)


def run_released(command_ref, expected_command_sha256, *, validate_only=False):
    c.ref(command_ref); c.sha(expected_command_sha256)
    c.require(command_ref['sha256'] == expected_command_sha256, 'external command pin mismatch')
    command = c.loads(read_ref(command_ref))
    continuation = command.get('continuation', '') if type(command) is dict else ''
    suffix = '/' + c.CONTINUATION
    c.require(type(continuation) is str and continuation.endswith(suffix), 'exact continuation required')
    root = continuation[:-len(suffix)]
    c.validate_header(command, expected_command_sha256, root)
    c.require(c.beneath(command_ref['path'], command['control_root']), 'foreign command path')
    records = {kind: read_ref(value) for kind, value in command['records'].items()}
    result = c.validate_command(command, expected_command_sha256, root, records)
    if validate_only:
        return result
    raise c.Hold('execution unavailable: ' + '; '.join(BLOCKERS))


class NativeGuard:
    """Finite native client policy; IDs are observed, never predicted or injected.

    startup is an exact source-reviewed sequence of full native method/params
    shapes. Unknown additions (including TUI instructions) cannot be stripped.
    This does not authenticate a process; the missing live adapter must do that.
    """
    def __init__(self, generation, startup, first_params):
        c.require(type(generation) is str and generation, 'generation')
        c.require(type(startup) is list and len(startup) <= 32, 'startup sequence')
        self.startup = c.loads(c.canonical(startup))
        for row in self.startup:
            c.closed(row, ('method', 'params', 'request'), 'startup row')
            c.require(row['method'] in ('initialize', 'initialized', 'thread/start',
                                      'model/list', 'config/read', 'configRequirements/read',
                                      'account/read', 'collaborationMode/list') and
                      type(row['request']) is bool, 'startup route')
            if row['method'] == 'account/read':
                c.equal(row['params'], {'refreshToken': False}, 'account refresh')
        c.require(sum(row['method'] == 'thread/start' for row in self.startup) == 1,
                  'one native thread required')
        c.require(type(first_params) is dict and 'clientUserMessageId' not in first_params and
                  'threadId' in first_params and 'input' in first_params, 'first params')
        self.first_params = c.loads(c.canonical(first_params))
        self.generation, self.position = generation, 0
        self.rpc_ids, self.message_ids, self.attempts = set(), set(), []
        self.active_turn = None
        self.terminal = False

    def __call__(self, value, metadata):
        c.require(metadata.get('generation') == self.generation and
                  metadata.get('direction') == 'client_to_server', 'foreign connection')
        method = value.get('method')
        if method in ('turn/start', 'turn/steer'):
            c.require(len(self.attempts) < 4, 'attempt capture exhausted')
            self.attempts.append(c.loads(c.canonical(value)))
            c.require(len(self.attempts) <= 2 and not self.terminal, 'native retry/race/late dispatch')
            c.require(self.position == len(self.startup), 'dispatch before startup complete')
            c.closed(value, ('id', 'method', 'params'), 'native dispatch')
            ident = c.typed_id(value['id'])
            c.require(ident not in self.rpc_ids, 'reused RPC ID')
            self.rpc_ids.add(ident)
            params = value['params']
            c.require(type(params) is dict, 'native params')
            msg_id = params.get('clientUserMessageId')
            c.require(type(msg_id) is str and 0 < len(msg_id) <= 256 and
                      msg_id not in self.message_ids, 'fresh native client message ID required')
            self.message_ids.add(msg_id)
            if len(self.attempts) == 1:
                c.require(method == 'turn/start', 'initial start required')
                c.equal({k: v for k, v in params.items() if k != 'clientUserMessageId'},
                        self.first_params, 'entire first native USER')
            return True
        c.require(not self.attempts and self.position < len(self.startup), 'late startup/unknown USER')
        row = self.startup[self.position]
        c.closed(value, ('id', 'method', 'params') if row['request'] else ('method', 'params'), 'startup envelope')
        c.equal({'method': method, 'params': value['params']},
                {'method': row['method'], 'params': row['params']}, 'startup profile')
        if row['request']:
            ident = c.typed_id(value['id'])
            c.require(ident not in self.rpc_ids, 'reused startup ID')
            self.rpc_ids.add(ident)
        self.position += 1
        return True

    def answer_matcher(self, *, decision_ref, question_id, question_title, selected,
                       exact_input, exact_start_settings, active_turn):
        """Match actual full wire envelope against an already reviewed fragment.

        exact_input must be derived by a pinned native fragment renderer from the
        genuine decision. This source stage has no such renderer/admission, so
        callers must not treat these synthetic parameters as live proof.
        """
        c.ref(decision_ref)
        c.require(all(type(x) is str and x for x in (question_id, question_title, selected)), 'question identity')
        c.require(type(exact_input) is list and len(exact_input) == 1, 'one native answer item')
        expected_input = c.loads(c.canonical(exact_input))
        settings = c.loads(c.canonical(exact_start_settings))
        used = False
        def matcher(value, metadata):
            nonlocal used
            c.require(not used, 'matcher already consumed')
            used = True
            c.require(not self.terminal and len(self.attempts) == 2 and
                      metadata.get('generation') == self.generation and
                      metadata.get('direction') == 'client_to_server', 'stale answer lifecycle')
            c.closed(value, ('id', 'method', 'params'), 'answer envelope')
            params = value['params']
            c.require(type(params) is dict, 'answer params')
            if active_turn is not None:
                c.require(self.active_turn == active_turn and value['method'] == 'turn/steer', 'active turn changed')
                expected = {'threadId': self.first_params['threadId'],
                            'expectedTurnId': active_turn, 'input': expected_input,
                            'responsesapiClientMetadata': None,
                            'responsesapiClientMetadataPatch': None, 'additionalContext': None}
            else:
                c.require(self.active_turn is None and value['method'] == 'turn/start', 'unexpected new turn')
                expected = dict(settings, threadId=self.first_params['threadId'], input=expected_input)
            c.equal({k: v for k, v in params.items() if k != 'clientUserMessageId'}, expected,
                    'complete native answer')
            return True
        return matcher


class ObserverGuard:
    """One separately identified connection; no thread, USER, answer or writes."""
    def __init__(self, generation, requests):
        c.require(type(requests) is list and len(requests) <= 16, 'observer profile')
        self.generation, self.requests = generation, c.loads(c.canonical(requests))
        self.ids = set()
        self.position = 0
        for row in self.requests:
            c.closed(row, ('method', 'params'), 'observer request')
            c.require(row['method'] in ('initialize', 'model/list', 'config/read',
                                      'configRequirements/read', 'account/read'), 'observer mutation')
            if row['method'] == 'account/read':
                c.equal(row['params'], {'refreshToken': False}, 'observer refresh')

    def __call__(self, value, metadata):
        c.require(metadata.get('generation') == self.generation and
                  metadata.get('direction') == 'client_to_server', 'observer identity')
        c.require(self.position < len(self.requests), 'observer request budget')
        c.closed(value, ('id', 'method', 'params'), 'observer envelope')
        ident = c.typed_id(value['id'])
        c.require(ident not in self.ids, 'observer reused ID')
        c.equal({k: v for k, v in value.items() if k != 'id'}, self.requests[self.position], 'observer request')
        self.ids.add(ident)
        self.position += 1
        return True


class FirstGate:
    """Immutable B1 plus exact full13, instructions and current install binding."""
    def __init__(self, proof):
        c.closed(proof, ('native13', 'tui_instructions', 'first_envelope', 'B1_first',
                         'B1_second', 'installed16', 'installed42', 'fixture',
                         'process', 'source_review', 'async_capability'), 'first gate')
        c.closed(proof['native13'], NATIVE13, 'native13')
        for key in ('fixture', 'process', 'source_review', 'async_capability'):
            c.ref(proof[key])
        c.require(type(proof['tui_instructions']) is str and bool(proof['tui_instructions']), 'native instructions missing')
        for key, count in (('installed16', 16), ('installed42', 42)):
            rows = proof[key]
            c.require(type(rows) is list and len(rows) == count, 'current install count')
            for row in rows:
                c.ref(row)
            c.require(len({row['path'] for row in rows}) == count, 'duplicate installed file')
        self.proof = c.loads(c.canonical(proof))
        self.failed = False
        self.check(proof['B1_second'])

    def check(self, current):
        if self.failed or c.canonical(current) != c.canonical(self.proof['B1_first']):
            self.failed = True
            raise c.Hold('B1 drift permanently closed')

    def release(self, relay, current, actual_native13, actual_instructions):
        self.check(current)
        c.equal(actual_native13, self.proof['native13'], 'actual native13')
        c.equal(actual_instructions, self.proof['tui_instructions'], 'native TUI additional instructions')
        c.require(relay.pending is not None, 'no held native first request')
        c.equal(relay.pending[1], self.proof['first_envelope'], 'full initial native envelope')
        # Authentication, full input semantic equivalence, B1 sampling and
        # durable first claim must precede this method in the admitted adapter.
        relay.resolve_first(True)


class Capture:
    """Bounded byte receipts, partial writes and stable raw-prefix cuts."""
    def __init__(self, deadline, byte_limit=1048576, record_limit=4096):
        c.require(type(byte_limit) is int and 0 < byte_limit <= 8388608 and
                  type(record_limit) is int and 0 < record_limit <= 8192, 'capture limits')
        self.deadline, self.byte_limit, self.record_limit = deadline, byte_limit, record_limit
        self.records, self.offsets, self.size = [], {}, 0

    def add(self, kind, raw=b'', detail=None):
        now = self.deadline.check()
        c.require(type(raw) is bytes and self.size + len(raw) <= self.byte_limit and
                  len(self.records) < self.record_limit, 'capture full/type')
        detail_size = 0
        if detail is not None:
            detail_raw = c.canonical(detail)
            detail_size = len(detail_raw)
            detail = c.loads(detail_raw)
        c.require(self.size + len(raw) + detail_size <= self.byte_limit, 'capture detail full')
        start = self.offsets.get(kind, 0)
        self.records.append({'ordinal': len(self.records), 'time': now, 'kind': kind,
                             'start': start, 'end': start + len(raw), 'raw': raw, 'detail': detail})
        self.offsets[kind] = start + len(raw)
        self.size += len(raw) + detail_size

    def cut(self):
        # Explicit bytes encoding for reproducible prefix provenance; raw stays
        # authoritative in memory, no sanitize/redact transformation is used.
        return c.digest([{**r, 'raw': r['raw'].hex()} for r in self.records])


class SyntheticOperator:
    """Finite fake-IO scheduling core, explicitly excluded from live admission.

    Backend must be a source-owned fake in tests. No process launcher, real PTY,
    observer thread, filesystem claim writer or generic plugin loader exists.
    step() performs one fair relay/observer/output/key round and never waits for
    Root. Server lifecycle must continue during first gate and Root waits.
    """
    runtime_admitted = False
    def __init__(self, mode, clock, claims, backend):
        c.require(mode in c.CONTEXTS, 'fixed mode required')
        self.deadline = c.Deadline(clock)  # before even fake startup
        self.mode, self.claims, self.backend = mode, claims, backend
        self.claims.context(mode)
        self.capture = Capture(self.deadline)
        self.relay = self.observer = self.guard = None
        self.closed = self.failed = False
        self.decision = self.answer_intent = None
        self.keys = bytearray()
        self.accounting = {'owner_decisions': 0, 'key_attempts': 0, 'native_attempts': [],
                           'accepted_starts': [], 'accepted_steers': [], 'queues': [],
                           'races': [], 'provider_usage': None}

    def start(self):
        self.deadline.check()
        self.backend.start(self.deadline.end)
        self.deadline.check()

    def attach(self, relay, guard, observer=None):
        c.require(self.relay is None and relay.deadline == self.deadline.end and
                  relay.client_guard is guard and relay.capture.generation == guard.generation and
                  (observer is None or
                   (observer.deadline == self.deadline.end and
                    isinstance(observer.client_guard, ObserverGuard) and
                    observer.capture.generation == observer.client_guard.generation and
                    observer.capture.generation != guard.generation)), 'connection/deadline identity')
        self.relay, self.guard, self.observer = relay, guard, observer

    def release_first(self, gate, current, native13, instructions):
        self.deadline.check()
        self.claims.input(self.mode, 'first')
        self.capture.add('first-intent', detail={'gate': c.digest(gate.proof)})
        gate.release(self.relay, current, native13, instructions)
        self.deadline.check()

    def choose(self, decision, receipt, matcher, submit_keys):
        """A synthetic stand-in for an authenticated Root/terminal adapter.

        The finite receipt binds three independently viewed genuine question IDs
        to a capture prefix. It is not a decoder or an authenticity assertion.
        """
        self.deadline.check()
        c.require(self.decision is None and self.relay.first_released and not self.guard.terminal,
                  'owner decision unavailable')
        c.closed(receipt, ('capture_sha256', 'questions', 'visited', 'all_unanswered',
                           'first_fixture_question', 'active_turn', 'generation'), 'question receipt')
        c.require(receipt['capture_sha256'] == self.capture.cut() and receipt['all_unanswered'] is True and
                  type(receipt['questions']) is list and len(receipt['questions']) == 3 and
                  c.canonical(receipt['visited']) == c.canonical([0, 1, 2]) and receipt['generation'] == self.guard.generation and
                  receipt['active_turn'] == self.guard.active_turn, 'stale/incomplete three-question receipt')
        ids = []
        for question in receipt['questions']:
            c.closed(question, ('id', 'title', 'options'), 'actual question')
            c.require(type(question['id']) is str and question['id'] and
                      type(question['title']) is str and question['title'] and
                      type(question['options']) is list and 2 <= len(question['options']) <= 5 and
                      all(type(x) is str and x for x in question['options']) and
                      len(set(question['options'])) == len(question['options']), 'question bounds')
            ids.append(question['id'])
        c.require(len(set(ids)) == 3 and receipt['first_fixture_question'] == ids[0], 'fixture question identity')
        c.closed(decision, ('ref', 'question_id', 'value', 'receipt_sha256'), 'owner decision')
        c.ref(decision['ref'])
        c.require(decision['question_id'] == ids[0] and
                  decision['value'] in receipt['questions'][0]['options'] and
                  decision['receipt_sha256'] == c.digest(receipt), 'foreign owner decision')
        c.require(type(submit_keys) is bytes and 0 < len(submit_keys) <= 64, 'native key bytes')
        # Persist intent before arming/submission, even if the claim or arm fails.
        self.backend.persist_intent(c.canonical({'decision': decision, 'receipt': receipt}))
        self.deadline.check()
        self.claims.input(self.mode, 'answer')
        self.decision = c.loads(c.canonical(decision))
        self.accounting['owner_decisions'] += 1
        self.capture.add('answer-intent', detail={'decision_ref': decision['ref'], 'keys_sha256': hashlib.sha256(submit_keys).hexdigest()})
        self.relay.arm_answer('async', matcher, decision['ref'])
        self.keys.extend(submit_keys)

    def step(self):
        c.require(not self.closed and not self.failed and self.relay is not None, 'operator stopped/unattached')
        try:
            self.deadline.check()
            self.relay.step()
            self.deadline.check()
            if self.observer is not None:
                self.observer.step()
            raw = self.backend.read_output(16384)
            self.deadline.check()
            if raw:
                self.capture.add('pty-output', raw)
            if self.keys:
                self.capture.add('key-attempt', bytes(self.keys))
                self.accounting['key_attempts'] += 1
                count = self.backend.write_keys(bytes(self.keys))
                self.deadline.check()
                c.require(type(count) is int and 0 <= count <= len(self.keys), 'invalid partial key write')
                if count:
                    self.capture.add('key-egress', bytes(self.keys[:count]))
                    del self.keys[:count]
            self.deadline.check()
        except Exception:
            self.failed = True
            raise
        finally:
            self.accounting['native_attempts'] = list(self.guard.attempts)
            self.accounting['turn_start_attempts'] = sum(x.get('method') == 'turn/start' for x in self.guard.attempts)
            self.accounting['turn_steer_attempts'] = sum(x.get('method') == 'turn/steer' for x in self.guard.attempts)

    def resize(self, rows, columns):
        self.deadline.check()
        c.require(type(rows) is int and type(columns) is int and 1 <= rows <= 300 and
                  1 <= columns <= 500, 'terminal dimensions')
        self.capture.add('resize-intent', detail={'rows': rows, 'columns': columns})
        self.backend.resize(rows, columns)
        self.capture.add('resize-applied', detail={'rows': rows, 'columns': columns})

    def observe_race(self, value):
        c.require(not self.failed and not self.accounting['races'], 'operator already stopped')
        self.accounting['races'].append(c.loads(c.canonical(value)))
        self.failed = self.guard.terminal = True
        raise c.Hold('native steer race/queue; no retry/refund')

    def close(self):
        c.require(not self.closed, 'already closed')
        self.deadline.check()
        self.backend.close_owned(self.deadline.end)
        self.deadline.check()
        self.closed = True
        return {'N7': 'UNVERIFIED', 'runtime_admitted': False, 'business_PASS': False,
                'accounting': self.accounting, 'capture_sha256': self.capture.cut()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--validate-only', action='store_true')
    parser.add_argument('--command')
    parser.add_argument('--command-sha256')
    args = parser.parse_args(argv)
    if not args.execute and not args.validate_only:
        print('INERT: N7 UNVERIFIED; no launch requested')
        return 0
    try:
        c.require(args.command and args.command_sha256, 'external command path and digest required')
        result = run_released({'path': args.command, 'sha256': args.command_sha256},
                              args.command_sha256, validate_only=args.validate_only)
        print(c.canonical(result).decode())
        return 0
    except (c.Hold, OSError) as exc:
        print('HOLD UNVERIFIED: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
