"""Inert SOURCE-ONLY finite N7-B / strict duplicate-B contract primitives.

No process, model, claim, fixture or control-file operation occurs on import.
These objects enforce local sequencing/accounting, not runtime authorization,
Root authenticity, native recognition, installed-body consumption or business PASS.
A future reviewed operator must bind those premises and persist each attempt
before writing. N7-C is deliberately outside this module.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import stat

SETUP_INPUT = b'$ains-setup Set up or migrate this disposable project using the installed procedure. Preserve unrelated text and existing settings.'
SETUP_SHA256 = '291d9707a61d31e49b46740863efa19361faa80cf2ee8a6ee217080620424369'
CONFIGURED_COMMAND = 'python3 -m unittest discover -s tests -v'
EXECUTED_COMMAND = 'PYTHONDONTWRITEBYTECODE=1 ' + CONFIGURED_COMMAND
TURN_SECONDS = 180
ROWS = {
    'N7-B/default/first': 'setup-conflict/observe/3',
    'N7-B/default/answer': 'setup-conflict/observe/4',
    'N7-B/copy/first': 'setup-symlink/observe/2',
    'N7-B/copy/answer': 'R7/tasks/4',
    'duplicate-B/execution-premise': 'setup-duplicate/observe/2',
    'duplicate-B/initial': 'setup-duplicate/observe/3',
    'duplicate-B/optional-real-answer': 'setup-duplicate/observe/4',
    'duplicate-B/content-ack': 'R7/AC9-handoff/3',
    'duplicate-B/exact-repeat': 'R7/AC9-handoff/4',
}
BRANCHES = {
    'N7-B-default': ('N7-B/default/first', 'N7-B/default/answer'),
    'N7-B-copy': ('N7-B/copy/first', 'N7-B/copy/answer'),
    'Duplicate-B-copy': tuple(row for row in ROWS if row.startswith('duplicate-B/')),
}


class Hold(ValueError):
    """Fail closed without implying refund, retry or authority."""


def require(ok, reason):
    if not ok:
        raise Hold(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def fields(value, names):
    require(type(value) is dict and set(value) == set(names.split()), 'closed schema')


def text(value):
    require(type(value) is str and bool(value.strip()), 'nonempty string required')
    return value


def raw_text(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 1048576, 'bounded input bytes required')
    try:
        return text(raw.decode('utf-8'))
    except UnicodeError as error:
        raise Hold('UTF-8 required') from error


def typed_id(value):
    require(type(value) in (str, int) and value != '', 'typed RPC ID required')
    return type(value).__name__, value


def clock_value(now):
    require(type(now) in (int, float), 'finite monotonic time required')
    try:
        finite = math.isfinite(now)
    except OverflowError:
        finite = False
    require(finite and now >= 0, 'finite monotonic time required')
    return now


def claim_key(row):
    """Stable data-only lifetime key: output/source version cannot reset a donor.

    An external durable consumed-claim store must enforce these keys globally.
    This function never reads or creates a claim.
    """
    require(row in ROWS, 'unknown exact row (aliases forbidden)')
    return 'setup-postclosure-donor/' + ROWS[row]


def validate_consumed(keys):
    require(type(keys) is frozenset and all(type(k) is str for k in keys),
            'explicit immutable consumed-key view required')
    return keys


def root_decision(kind, body, predecessor):
    """Closed Root decision DATA, constructed only after observed completion.

    This is not a signature/authentication facility. The operator must obtain
    the separate actual Root judgment after presenting these exact observations.
    """
    require(kind in ('premise', 'answer', 'content-ack'), 'unknown decision kind')
    raw_text(body)
    if kind == 'premise':
        require(predecessor is None, 'premise must precede setup')
    else:
        fields(predecessor, 'row thread_id turn_id output_sha256 question_sha256')
    return dict(kind=kind, body=body, predecessor=copy.deepcopy(predecessor), actor='Root')


def command_receipt(receipt):
    """Validate declared completed-command evidence; prompts are not receipts.

    Independent actual wire/command/cache provenance remains an operator premise.
    Flags explicitly reject earlier automatic-import and other cache writes.
    """
    fields(receipt, 'command status exit_code earlier_import_cache_writes other_cache_writes')
    require(receipt['command'] == EXECUTED_COMMAND and receipt['status'] == 'completed'
            and type(receipt['exit_code']) is int and receipt['exit_code'] == 0
            and receipt['earlier_import_cache_writes'] is False
            and receipt['other_cache_writes'] is False, 'strict command receipt failed')


def full_state(root, grants):
    """Fresh read-only namespace snapshot, including root, caches and identities.

    Never imports archived code, follows directory links or excludes cache/Git.
    grants must be supplied by a separately trusted actual capability observer;
    hashing a declaration does not establish its completeness or truth.
    """
    root = Path(root)
    require(root.is_absolute() and root.resolve(strict=True) == root and
            root.is_dir() and not root.is_symlink(), 'canonical physical directory required')
    require(type(grants) is dict, 'explicit actual grant map required')
    grants = json.loads(canonical(grants))
    records = []

    def visit(path):
        before = path.lstat()
        record = dict(path='.' if path == root else path.relative_to(root).as_posix(),
                      mode=stat.S_IMODE(before.st_mode), dev=before.st_dev,
                      ino=before.st_ino, nlink=before.st_nlink)
        if stat.S_ISLNK(before.st_mode):
            record.update(kind='link', target=os.readlink(path))
        elif stat.S_ISREG(before.st_mode):
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                opened = os.fstat(fd)
                require((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino),
                        'snapshot identity race')
                with os.fdopen(os.dup(fd), 'rb') as stream:
                    raw = stream.read()
                after_read = os.fstat(fd)
                require((opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) ==
                        (after_read.st_size, after_read.st_mtime_ns, after_read.st_ctime_ns),
                        'snapshot file changed')
                record.update(kind='file', size=len(raw), sha256=digest(raw))
            finally:
                os.close(fd)
        elif stat.S_ISDIR(before.st_mode):
            record['kind'] = 'directory'
            for child in sorted(path.iterdir()):
                visit(child)
        else:
            raise Hold('unsupported filesystem object')
        after = path.lstat()
        require((before.st_dev, before.st_ino, before.st_mode, before.st_nlink,
                 before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_dev, after.st_ino, after.st_mode, after.st_nlink,
                 after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'snapshot changed')
        records.append(record)

    visit(root)
    return dict(records=sorted(records, key=lambda r: r['path']), grants=grants)


def strict_equal(before, after):
    fields(before, 'records grants')
    fields(after, 'records grants')
    require(type(before['records']) is list and before['records'] and
            type(after['records']) is list and after['records'], 'complete snapshots required')
    require(canonical(before) == canonical(after), 'strict FULLSTATE inequality')


class TurnGate:
    """Finite local turn gate; no actual dispatch or claim creation.

    N7-B: one context, first -> actual single question -> one answer -> next
    question. Across the two exact N7 branches this is 2 contexts / 4 turns.
    Duplicate: context1 premise -> initial -> optional real answer (at most one);
    context2 fresh content acknowledgment -> byte-identical repeat. Any failed
    attempt or unknown delivery stops this gate permanently, retaining charges.
    """
    def __init__(self, branch, consumed):
        require(branch in BRANCHES, 'unknown exact branch (aliases forbidden)')
        self.branch = branch
        self.consumed = validate_consumed(consumed)
        self.rows = BRANCHES[branch]
        self.duplicate = branch == 'Duplicate-B-copy'
        self.phase = 'premise' if self.duplicate else 'first'
        self.context = 0
        self.context_open = False
        self.threads = []
        self.attempts = []
        self.active = None
        self.last = None
        self.question = None
        self.used_turn_ids = set()
        self.last_time = 0
        self.repeat_baseline = None
        self.last_state = None

    def _now(self, now):
        try:
            clock_value(now)
            require(now >= self.last_time, 'nonmonotonic clock')
            self.last_time = now
            return now
        except Hold as error:
            self._stop(str(error))
            raise

    def _stop(self, reason):
        if self.active is not None:
            self.active.update(status='UNKNOWN', failure=reason)
        self.active = None
        self.phase = 'stopped'

    def open_context(self, thread_id):
        text(thread_id)
        require(not self.context_open and self.active is None and thread_id not in self.threads,
                'context active/reused')
        require((self.context == 0 and not self.threads) or
                (self.duplicate and self.context == 1 and self.phase == 'ack'),
                'context order/ceiling')
        self.threads.append(thread_id)
        self.context += 1
        self.context_open = True

    def close_context(self):
        require(self.context_open and self.active is None and self.context == len(self.threads),
                'active/closed context')
        require((self.duplicate and self.context == 1 and self.phase == 'ack') or
                (self.phase == 'done'), 'premature context close')
        # A closed first context may no longer dispatch; only open_context advances.
        self.context_open = False

    def predecessor(self):
        require(self.last is not None, 'no observed predecessor')
        return copy.deepcopy(self.last)

    def _row(self):
        names = {'premise': 'execution-premise', 'initial': 'initial',
                 'answer': 'optional-real-answer', 'ack': 'content-ack',
                 'repeat': 'exact-repeat'}
        if self.duplicate:
            require(self.phase in names, 'terminal gate')
            return 'duplicate-B/' + names[self.phase]
        require(self.phase in ('first', 'answer'), 'terminal gate')
        return self.rows[0 if self.phase == 'first' else 1]

    def prepare(self, body, decision=None):
        """Validate input before transport; does not charge or authorize anything."""
        require(self.active is None, 'turn still active')
        row = self._row()
        require(claim_key(row) not in self.consumed and
                all(a['row'] != row for a in self.attempts), 'consumed/attempted lifetime donor')
        require(self.context_open and self.context == (2 if self.phase in ('ack', 'repeat') else 1) and
                self.context == len(self.threads), 'wrong context')
        raw_text(body)
        if self.phase in ('first', 'initial', 'repeat'):
            require(body == SETUP_INPUT and digest(body) == SETUP_SHA256 and decision is None,
                    'named setup input bytes changed')
        else:
            fields(decision, 'kind body predecessor actor')
            kind = {'premise': 'premise', 'answer': 'answer', 'ack': 'content-ack'}[self.phase]
            require(decision['actor'] == 'Root' and decision['kind'] == kind and
                    decision['body'] == body, 'separate actual Root decision required')
            if self.phase == 'premise':
                require(decision['predecessor'] is None, 'premise precedes setup observations')
                require(EXECUTED_COMMAND.encode() in body, 'exact technical execution premise required')
            else:
                require(decision['predecessor'] == self.last and self.last is not None,
                        'decision must bind actual predecessor')
            if self.phase == 'answer':
                require(self.question is not None, 'no actual question to answer')
        return dict(row=row, donor=ROWS[row], claim_key=claim_key(row), body=body,
                    thread_id=self.threads[-1], phase=self.phase, decision=copy.deepcopy(decision))

    def begin(self, prepared, now):
        """Call immediately BEFORE an attempted write; UNKNOWN is charged.

        The caller must durably reserve/check the stable claim first. Local
        in-memory accounting cannot replace atomic cross-process ownership.
        """
        fields(prepared, 'row donor claim_key body thread_id phase decision')
        expected = self.prepare(prepared['body'], prepared['decision'])
        require(prepared == expected,
                'prepared input drift')
        self._now(now)
        attempt = dict(row=expected['row'], donor=expected['donor'],
                       claim_key=expected['claim_key'], thread_id=expected['thread_id'],
                       input_sha256=digest(expected['body']), started=now,
                       deadline=now + TURN_SECONDS, delivery='UNKNOWN', status='UNKNOWN')
        self.attempts.append(attempt)
        self.active = attempt
        return copy.deepcopy(attempt)

    def delivered(self, now):
        try:
            self._now(now)
            require(self.active is not None and now < self.active['deadline'], 'missing/expired turn')
            self.active['delivery'] = 'LOCAL_WRITE_COMPLETE'
        except Hold as error:
            self._stop(str(error))
            raise

    def fail(self, now, reason):
        try:
            self._now(now)
            require(self.active is not None, 'no active attempt')
            reason = text(reason)
        except Hold as error:
            self._stop(str(error))
            raise
        self._stop(reason)

    def complete(self, now, turn_id, output, questions=(), before=None, after=None,
                 configured_command=None, receipt=None):
        """Use only completed, drained, matching actual wire observations.

        questions is the caller's separately reviewed single-judgment extraction
        from actual output; substring binding is mechanical, not semantic proof.
        """
        self._now(now)
        require(self.active is not None, 'no active attempt')
        try:
            require(now < self.active['deadline'] and
                    self.active['delivery'] == 'LOCAL_WRITE_COMPLETE', 'expired/partial input')
            text(turn_id)
            key = (self.threads[-1], turn_id)
            require(key not in self.used_turn_ids, 'reused typed turn identity')
            raw_text(output)
            require(type(questions) is tuple and len(questions) <= 1, 'one judgment maximum')
            for question in questions:
                raw_text(question)
                require(question in output, 'question not in actual output')
            if not self.duplicate:
                require(len(questions) == 1, 'N7 first and next actual question required')
            elif self.phase in ('premise', 'ack', 'repeat', 'answer'):
                require(not questions, 'no second judgment/extra answer')
            if self.duplicate:
                require(configured_command == CONFIGURED_COMMAND, 'authentic configured command changed')
                strict_equal(before, before)
                strict_equal(after, after)
                if self.last_state is not None:
                    strict_equal(self.last_state, before)
                if self.phase in ('premise', 'ack', 'repeat'):
                    strict_equal(before, after)
                if (self.phase in ('initial', 'answer') and not questions) or self.phase == 'repeat':
                    command_receipt(receipt)
                if self.phase == 'ack':
                    self.repeat_baseline = copy.deepcopy(after)
                if self.phase == 'repeat':
                    strict_equal(self.repeat_baseline, before)
                self.last_state = copy.deepcopy(after)
            self.used_turn_ids.add(key)
            self.last = dict(row=self.active['row'], thread_id=self.threads[-1],
                             turn_id=turn_id, output_sha256=digest(output),
                             question_sha256=digest(questions[0]) if questions else None)
            self.question = questions[0] if questions else None
            self.active.update(status='OBSERVED_COMPLETED', turn_id=turn_id,
                               output_sha256=digest(output), ended=now)
            self.active = None
            if self.duplicate:
                self.phase = {'premise': 'initial', 'initial': 'answer' if questions else 'ack',
                              'answer': 'ack', 'ack': 'repeat', 'repeat': 'done'}[self.phase]
            else:
                self.phase = 'answer' if self.phase == 'first' else 'done'
        except (Hold, TypeError, ValueError) as error:
            self._stop(str(error))
            raise

    def accounting(self):
        return dict(potential_held_slots=len(self.rows), actual_charged_turns=len(self.attempts),
                    remaining_held_slots=len(self.rows) - len(self.attempts),
                    contexts_started=len(self.threads), max_contexts=2 if self.duplicate else 1,
                    max_turns=len(self.rows), seconds_per_turn=TURN_SECONDS,
                    max_model_seconds=TURN_SECONDS * len(self.rows),
                    phase=self.phase, runtime_PASS=False)


class Wire:
    """Bounded original-byte JSON-lines index for a future JSON-RPC operator.

    No sockets/processes; no serialization on receive. Partial lines stay UNKNOWN.
    Request IDs distinguish integers from strings; thread/turn IDs are strings.
    The caller records successful writes, feeds actual server bytes, and handles
    deadlines/draining. This does not prove remote delivery or healthy closure.
    """
    def __init__(self):
        self.raw = {'client': bytearray(), 'server': bytearray()}
        self.pending = {'client': bytearray(), 'server': bytearray()}
        self.records = []
        self.requests = {}
        self.failed = False

    def feed(self, direction, raw):
        require(not self.failed, 'wire permanently stopped')
        try:
            self._feed(direction, raw)
        except (Hold, TypeError, ValueError, KeyError) as error:
            self.failed = True
            raise Hold(str(error)) from error

    def _feed(self, direction, raw):
        require(direction in self.raw and type(raw) is bytes, 'wire direction/bytes')
        require(sum(map(len, self.raw.values())) + len(raw) <= 8388608, 'wire capture limit')
        self.raw[direction].extend(raw)
        self.pending[direction].extend(raw)
        require(len(self.pending[direction]) <= 1048576, 'partial wire backpressure')
        while b'\n' in self.pending[direction]:
            require(len(self.records) < 8192, 'wire record limit')
            line, _, remainder = self.pending[direction].partition(b'\n')
            start = len(self.raw[direction]) - len(self.pending[direction])
            self.pending[direction] = bytearray(remainder)
            value = decode(line)
            require(value.get('jsonrpc', '2.0') == '2.0', 'JSON-RPC version')
            if 'method' in value:
                text(value['method'])
                require('result' not in value and 'error' not in value, 'mixed RPC request')
                if 'id' in value:
                    key = (direction, *typed_id(value['id']))
                    require(key not in self.requests, 'duplicate RPC request ID')
                    self.requests[key] = dict(method=value['method'], responded=False)
            else:
                fields(value, 'id result' if 'jsonrpc' not in value else 'jsonrpc id result')
                origin = 'server' if direction == 'client' else 'client'
                key = (origin, *typed_id(value['id']))
                require(key in self.requests and not self.requests[key]['responded'],
                        'unowned/duplicate RPC response')
                self.requests[key]['responded'] = True
            self.records.append(dict(direction=direction, start=start, end=start + len(line) + 1,
                                     raw=bytes(line) + b'\n', payload=value))

    def require_turn_input(self, index, prepared):
        require(not self.failed and type(index) is int and 0 <= index < len(self.records),
                'healthy actual wire index required')
        record = self.records[index]
        value = record['payload']
        require(record['direction'] == 'client' and value.get('method') == 'turn/start',
                'actual turn/start required')
        fields(value, 'id method params' if 'jsonrpc' not in value else 'jsonrpc id method params')
        fields(value['params'], 'threadId input')
        require(type(value['params']['threadId']) is str and
                value['params']['threadId'] == prepared['thread_id'] and
                value['params']['input'] == [{'type': 'text', 'text': raw_text(prepared['body'])}],
                'wire input/thread drift')
        typed_id(value['id'])
        return dict(wire_index=index, start=record['start'], end=record['end'],
                    wire_sha256=digest(record['raw']), input_sha256=digest(prepared['body']))

    def completed_turn(self, request_index):
        """Correlate actual result/final/terminal bytes, preserving wire indexes.

        This is a local completed-turn receipt, not process/drain/native proof.
        Caller must reject unhealthy EOF, timeout, partial input and late output.
        """
        self.require_clean()
        require(type(request_index) is int and 0 <= request_index < len(self.records),
                'actual request index required')
        request = self.records[request_index]
        value = request['payload']
        require(request['direction'] == 'client' and value.get('method') == 'turn/start',
                'turn request index required')
        fields(value, 'id method params' if 'jsonrpc' not in value else 'jsonrpc id method params')
        fields(value['params'], 'threadId input')
        request_id = typed_id(value['id'])
        thread_id = text(value['params']['threadId'])
        end = next((i for i, r in enumerate(self.records)
                    if i > request_index and r['direction'] == 'client' and
                    r['payload'].get('method') == 'turn/start'), len(self.records))
        responses = [(i, r['payload']) for i, r in enumerate(self.records[:end])
                     if i > request_index and r['direction'] == 'server'
                     and 'method' not in r['payload'] and
                     typed_id(r['payload']['id']) == request_id]
        require(len(responses) == 1, 'one matching turn response required')
        response_index, response = responses[0]
        require(type(response.get('result')) is dict and
                type(response['result'].get('turn')) is dict, 'turn result required')
        turn_id = text(response['result']['turn'].get('id'))
        terminal, finals = [], []
        for index, record in enumerate(self.records[request_index + 1:end], request_index + 1):
            if record['direction'] != 'server':
                continue
            obj = record['payload']
            if obj.get('method') not in ('turn/completed', 'item/completed'):
                continue
            params = obj.get('params')
            require(type(params) is dict and params.get('threadId') == thread_id,
                    'foreign terminal/item thread')
            if obj['method'] == 'turn/completed':
                turn = params.get('turn')
                require(type(turn) is dict and turn.get('id') == turn_id and
                        turn.get('status') == 'completed' and turn.get('error') is None,
                        'foreign/failed terminal turn')
                terminal.append(index)
            else:
                require(params.get('turnId') == turn_id, 'foreign item turn')
                item = params.get('item')
                require(type(item) is dict, 'item object required')
                if item.get('type') == 'agentMessage' and item.get('phase') == 'final_answer':
                    finals.append((index, text(item.get('text')).encode('utf-8')))
        require(len(terminal) == 1 and finals and all(i < terminal[0] for i, _ in finals),
                'one completed terminal and preceding actual final output required')
        return dict(thread_id=thread_id, turn_id=turn_id, request_index=request_index,
                    response_index=response_index, terminal_index=terminal[0],
                    final_indexes=[i for i, _ in finals], output=b'\n'.join(b for _, b in finals))

    def require_clean(self):
        require(not self.failed and not any(self.pending.values()) and
                all(r['responded'] for r in self.requests.values()), 'partial/unanswered wire UNKNOWN')


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON field')
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(Hold('nonfinite JSON')))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Hold('malformed wire JSON') from error
    require(type(value) is dict, 'JSON object required')
    return value
