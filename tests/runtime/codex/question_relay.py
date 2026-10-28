"""Inert, bounded Unix-stream WebSocket relay primitives; never launch a process.

Construct explicitly with already-owned connected sockets. step() never waits for
Root: resolve_first()/authorize_answer() are separate caller operations. These
are synthetic-transport primitives, NOT runtime admission, semantic acceptance,
PTY rendering proof, or an authenticated owner-decision mechanism. No CLI runs.
"""
import base64
import hashlib
import json
import math
import posixpath
import socket
import time
from dataclasses import dataclass

CLIENT = 'client_to_server'
SERVER = 'server_to_client'
DIRECTIONS = (CLIENT, SERVER)
CONTEXTS = ('default', 'copy')
POTENTIAL_CHARGED_USERS = 4
CONTEXT_SECONDS = 180


class Hold(ValueError):
    """Fail closed; already-written bytes remain in the capture."""


def require(ok, reason):
    if not ok:
        raise Hold(reason)


@dataclass(frozen=True)
class Limits:
    header: int = 16384
    message: int = 1048576
    pending: int = 2097152
    capture: int = 8388608
    records: int = 8192
    requests: int = 4096

    def __post_init__(self):
        caps = dict(header=16384, message=1048576, pending=2097152,
                    capture=8388608, records=8192, requests=4096)
        require(all(type(v) is int and 0 < v <= caps[k]
                    for k, v in self.__dict__.items()), 'invalid limits')


class Capture:
    """Bounded raw ingress/egress and explicit events, with independent offsets.

    Egress raw is recorded ONLY after send() returns a positive count. Records
    prove local successful writes, never receipt, rendering, or model acceptance.
    """
    def __init__(self, generation, limits):
        require(type(generation) is str and 0 < len(generation) <= 256,
                'invalid connection generation')
        self.generation, self.limits = generation, limits
        self.records, self.offsets, self.bytes = [], {}, 0

    def reserve(self, count):
        require(len(self.records) < self.limits.records and
                self.bytes + count <= self.limits.capture, 'capture exhausted')

    def add(self, kind, direction, now, raw=b'', detail=None):
        self.reserve(len(raw))
        key = (kind, direction)
        start = self.offsets.get(key, 0)
        self.offsets[key] = start + len(raw)
        self.records.append(dict(generation=self.generation, ordinal=len(self.records),
                                 time=now, kind=kind, direction=direction, start=start,
                                 end=start + len(raw), raw=raw, detail=detail))
        self.bytes += len(raw)

    def raw(self, kind, direction):
        return b''.join(r['raw'] for r in self.records
                        if r['kind'] == kind and r['direction'] == direction)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON field')
        result[key] = value
    return result


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, RecursionError) as exc:
        raise Hold('invalid canonical JSON value') from exc


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def envelope(payload):
    try:
        value = json.loads(payload.decode('utf-8'), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(Hold('nonfinite JSON')))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Hold('malformed JSON: ' + str(exc)) from exc
    require(type(value) is dict, 'JSON-RPC object required')
    require(value.get('jsonrpc', '2.0') == '2.0', 'invalid JSON-RPC version')
    if 'method' in value:
        require(type(value['method']) is str and bool(value['method']) and
                'result' not in value and 'error' not in value, 'malformed request')
        require('params' not in value or type(value['params']) in (dict, list),
                'malformed params')
    else:
        require('id' in value and (('result' in value) != ('error' in value)),
                'malformed response')
        if 'error' in value:
            err = value['error']
            require(type(err) is dict and type(err.get('code')) is int and
                    type(err.get('message')) is str, 'malformed error')
    if 'id' in value:
        require(type(value['id']) in (str, int) and value['id'] != '', 'invalid typed ID')
    return value


class Ownership:
    """IDs are namespaced by connection generation, initiating direction and type."""
    def __init__(self, generation, limit):
        self.generation, self.limit, self.requests = generation, limit, {}

    def observe(self, direction, value):
        if 'id' not in value:
            return None
        initiating = direction if 'method' in value else DIRECTIONS[1 - DIRECTIONS.index(direction)]
        key = (self.generation, initiating, type(value['id']).__name__, value['id'])
        if 'method' in value:
            require(key not in self.requests, 'duplicate request ID')
            require(len(self.requests) < self.limit, 'request limit')
            self.requests[key] = dict(method=value['method'], responded=False, forwarded=False)
        else:
            require(key in self.requests and not self.requests[key]['responded'] and
                    self.requests[key]['forwarded'], 'foreign/duplicate/unforwarded response')
            self.requests[key]['responded'] = True
        return key


class Decoder:
    """No reserialization: emitted raw spans contain original frames in order."""
    def __init__(self, client, limits):
        self.client, self.limits = client, limits
        self.buffer, self.parts, self.payload = bytearray(), bytearray(), bytearray()
        self.fragmented, self.closed = False, False
        self.base_offset = self.offset = 0
        self.spans, self.emissions = [], []

    def feed(self, raw, observation=None):
        require(not self.closed or not raw, 'bytes after close')
        self.buffer.extend(raw)
        require(len(self.buffer) + len(self.parts) <= self.limits.pending, 'decoder backpressure')
        output = []
        self.emissions = []
        while len(self.buffer) >= 2:
            first, second = self.buffer[:2]
            fin, opcode, masked = bool(first & 128), first & 15, bool(second & 128)
            require(not first & 112 and opcode in (0, 1, 8, 9, 10), 'unsupported frame/extension')
            require(masked == self.client, 'incorrect masking direction')
            size, pos = second & 127, 2
            if size in (126, 127):
                width = 2 if size == 126 else 8
                if len(self.buffer) < pos + width:
                    break
                size = int.from_bytes(self.buffer[pos:pos + width], 'big')
                require(size >= (126 if width == 2 else 65536) and size < 2 ** 63,
                        'noncanonical/invalid frame length')
                pos += width
            require(size <= self.limits.message, 'frame length limit')
            require(opcode < 8 or fin and size <= 125, 'invalid control frame')
            if masked:
                if len(self.buffer) < pos + 4:
                    break
                mask = self.buffer[pos:pos + 4]
                pos += 4
            if len(self.buffer) < pos + size:
                break
            frame = bytes(self.buffer[:pos + size])
            data = bytes(self.buffer[pos:pos + size])
            del self.buffer[:pos + size]
            span = dict(start=self.base_offset + self.offset,
                        end=self.base_offset + self.offset + len(frame),
                        opcode=opcode, fin=fin)
            self.offset += len(frame)
            if opcode < 8 or self.fragmented:
                require(len(self.spans) < self.limits.records, 'message frame count limit')
                self.spans.append(span)
            if masked:
                data = bytes(v ^ mask[i % 4] for i, v in enumerate(data))
            if opcode >= 8:
                if opcode == 8:
                    require(len(data) != 1, 'invalid close payload')
                    if data:
                        code = int.from_bytes(data[:2], 'big')
                        require((1000 <= code <= 1014 and code not in (1004, 1005, 1006)) or
                                3000 <= code <= 4999, 'invalid close status')
                        try:
                            data[2:].decode('utf-8')
                        except UnicodeError as exc:
                            raise Hold('invalid close UTF-8') from exc
                    require(not self.client or not self.fragmented,
                            'client close during incomplete message')
                    self.fragmented = False
                    self.parts.clear()
                    self.payload.clear()
                    self.spans.clear()
                    self.closed = True
                    require(not self.buffer, 'bytes after close')
                if self.fragmented and self.client:
                    self.parts.extend(frame)
                else:
                    output.append((frame, None))
                    self.emissions.append(None)
                continue
            require((opcode == 0) == self.fragmented, 'invalid fragmentation')
            if self.client:
                self.parts.extend(frame)
            self.payload.extend(data)
            require(len(self.payload) <= self.limits.message and
                    len(self.parts) <= self.limits.pending, 'message length limit')
            self.fragmented = not fin
            if fin:
                value = envelope(bytes(self.payload))
                output.append((bytes(self.parts) if self.client else frame,
                               value))
                self.emissions.append(dict(start=self.spans[0]['start'], end=span['end'],
                                           frame_spans=self.spans,
                                           fin_observation=dict(observation or {}),
                                           decoded_sha256=_digest(value)))
                self.spans = []
                self.parts.clear()
                self.payload.clear()
            elif not self.client:
                # Server bytes never wait for complete-message classification.
                # Observe ownership at FIN independently of forwarding frames.
                output.append((frame, None))
                self.emissions.append(None)
        return output

    def finish(self):
        require(not self.buffer and not self.fragmented, 'EOF with incomplete frame/message')


class Relay:
    """Single connection generation; caller owns sockets and any listener.

    startup_methods MUST be an explicitly reviewed client allowlist. Only initial
    turn/start is gateable; every later dispatch or synchronous question result
    requires one exact, explicitly authorized envelope. Authorization is structural
    only: caller must bind actual native question/Root/PTY and server acceptance.
    Optional absolute deadline includes earlier startup and cannot extend the
    construction+180 bound. Callbacks must be reviewed, bounded synchronous
    source: no I/O, tools, waiting, Root polling, or rendering inside them. The
    relay cannot preempt arbitrary Python code or establish source provenance.
    """
    runtime_admitted = False

    def __init__(self, client, server, *, generation, startup_methods,
                 clock=time.monotonic, limits=None, deadline=None, client_guard=None,
                 server_observer=None):
        require(client.family == socket.AF_UNIX and server.family == socket.AF_UNIX,
                'Unix sockets required')
        self.limits = limits or Limits()
        require(type(startup_methods) in (set, frozenset) and
                all(type(m) is str and m for m in startup_methods) and
                not {'turn/start', 'turn/steer', 'item/tool/requestUserInput'} & startup_methods,
                'invalid startup allowlist')
        self.allowed = frozenset(startup_methods)
        self.clock, self.started = clock, clock()
        require(type(self.started) in (int, float) and math.isfinite(self.started),
                'invalid construction time')
        deadline = self.started + CONTEXT_SECONDS if deadline is None else deadline
        require(type(deadline) in (int, float) and math.isfinite(deadline) and
                self.started < deadline <= self.started + CONTEXT_SECONDS,
                'invalid absolute deadline')
        require(client_guard is None or callable(client_guard), 'invalid client guard')
        self.deadline, self.last_time = deadline, self.started
        require(server_observer is None or callable(server_observer), 'invalid server observer')
        self.client_guard = client_guard
        self.server_observer = server_observer
        self.capture = Capture(generation, self.limits)
        self.owners = Ownership(generation, self.limits.requests)
        self.sockets = {CLIENT: client, SERVER: server}
        for sock in self.sockets.values():
            sock.setblocking(False)
        self.decoders = {d: Decoder(d == CLIENT, self.limits) for d in DIRECTIONS}
        self.headers = {d: bytearray() for d in DIRECTIONS}
        self.upgraded, self.queues, self.eof = set(), {d: bytearray() for d in DIRECTIONS}, set()
        self.pending = None
        self.pending_controls = bytearray()
        self.first_released = self.answer_used = False
        self.answer = None
        self.armed_answer = None
        self.pending_metadata = None
        self.failed = None
        self.key = None
        self.forward_marks = {d: [] for d in DIRECTIONS}
        self.queued_ends, self.written = dict.fromkeys(DIRECTIONS, 0), dict.fromkeys(DIRECTIONS, 0)

    def _now(self):
        now = self.clock()
        require(type(now) in (int, float) and math.isfinite(now), 'invalid clock time')
        require(now >= self.last_time, 'clock moved backwards')
        self.last_time = now
        require(now < self.deadline, 'context deadline reached')
        return now

    def _event(self, direction, detail):
        self.capture.add('event', direction, self.last_time, detail=detail)

    def _fail(self, exc):
        self.failed = str(exc)
        # A reserved event slot normally records failure; exhaustion is itself
        # explicit in failed even when no capture slot remains.
        try:
            self._event(None, dict(error=self.failed))
        except Hold:
            pass
        raise Hold(self.failed) from exc

    def _queue(self, direction, raw, owner=None):
        require(len(self.queues[direction]) + len(raw) <= self.limits.pending,
                'output backpressure')
        self.queues[direction].extend(raw)
        self.queued_ends[direction] += len(raw)
        if owner is not None:
            self.forward_marks[direction].append((self.queued_ends[direction], owner))

    def _handshake(self, direction, raw):
        buf = self.headers[direction]
        buf.extend(raw)
        end = buf.find(b'\r\n\r\n')
        require((end + 4 if end >= 0 else len(buf)) <= self.limits.header, 'HTTP header limit')
        if end < 0:
            return b''
        head, tail = bytes(buf[:end + 4]), bytes(buf[end + 4:])
        lines = head[:-4].split(b'\r\n')
        fields = {}
        for line in lines[1:]:
            require(b':' in line and not line.startswith((b' ', b'\t')), 'malformed HTTP field')
            name, value = line.split(b':', 1)
            name, value = name.lower(), value.strip()
            require(name not in fields, 'duplicate HTTP field')
            fields[name] = value
        require(fields.get(b'upgrade', b'').lower() == b'websocket' and
                b'upgrade' in [v.strip().lower() for v in fields.get(b'connection', b'').split(b',')],
                'invalid HTTP upgrade')
        require(b'sec-websocket-extensions' not in fields and
                b'sec-websocket-protocol' not in fields, 'unsupported negotiation')
        if direction == CLIENT:
            require(len(lines[0].split(b' ')) == 3 and lines[0].startswith(b'GET /') and
                    lines[0].endswith(b' HTTP/1.1') and fields.get(b'host') and
                    fields.get(b'sec-websocket-version') == b'13', 'invalid HTTP request')
            self.key = fields.get(b'sec-websocket-key', b'')
            try:
                require(len(base64.b64decode(self.key, validate=True)) == 16, 'invalid WebSocket key')
            except ValueError as exc:
                raise Hold('invalid WebSocket key') from exc
        else:
            require(CLIENT in self.upgraded and
                    self.written[CLIENT] >= self.request_header_end, 'response before forwarded request')
            expected = base64.b64encode(hashlib.sha1(self.key + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())
            require(lines[0].startswith(b'HTTP/1.1 101 ') and
                    fields.get(b'sec-websocket-accept') == expected, 'invalid HTTP response')
        self.upgraded.add(direction)
        buf.clear()
        self._queue(direction, head)
        self.decoders[direction].base_offset = len(head)
        if direction == CLIENT:
            self.request_header_end = self.queued_ends[CLIENT]
        return tail

    def _callback(self, callback, value, metadata, label):
        """Copies protect the authoritative decoded value and provenance.

        Mutation of either copy is rejected, including nested type changes.
        Before/after clock checks detect overruns; they do not preempt callbacks.
        """
        before = _canonical([value, metadata])
        copied_value, copied_metadata = json.loads(before)
        self._now()
        try:
            accepted = callback(copied_value, copied_metadata)
            after = _canonical([copied_value, copied_metadata])
        except Exception as exc:
            raise Hold(label + ' exception: ' + type(exc).__name__) from exc
        self._now()
        require(before == after, label + ' mutated callback input')
        require(accepted is True, label + ' rejected message')

    def _message(self, direction, raw, value, metadata=None):
        if value is None:
            if direction == CLIENT and self.pending is not None:
                require(len(self.pending[0]) + len(self.pending_controls) + len(raw) <=
                        self.limits.pending, 'pending gate backpressure')
                self.pending_controls.extend(raw)
            else:
                self._queue(direction, raw)
            return
        if direction == CLIENT:
            metadata = dict(metadata or {}, generation=self.capture.generation,
                            direction=direction, wire_sha256=hashlib.sha256(raw).hexdigest())
            self._event(CLIENT, dict(client_message_observed=metadata))
            if self.client_guard is not None:
                self._callback(self.client_guard, value, metadata, 'client guard')
        key = self.owners.observe(direction, value)
        if direction == SERVER and self.server_observer is not None:
            # FIN spans cover original fragments; earlier frames already flowed.
            metadata = dict(metadata or {}, generation=self.capture.generation,
                            direction=direction)
            self._event(SERVER, dict(server_message_observed=metadata))
            self._callback(self.server_observer, value, metadata, 'server observer')
        answer_attempt = False
        if direction == CLIENT:
            require(self.pending is None, 'client work while first dispatch pending')
            method = value.get('method')
            if method in ('turn/start', 'turn/steer'):
                require('id' in value and type(value.get('params')) is dict, 'dispatch request required')
                if not self.first_released:
                    require(method == 'turn/start', 'first dispatch must be turn/start')
                    self.pending = (raw, value, key)
                    self.pending_metadata = metadata
                    self._event(CLIENT, dict(first_dispatch_pending=value))
                    return
                self._consume_answer('async', value, metadata)
                answer_attempt = True
            elif method is None:
                owner = self.owners.requests[key]
                require(owner['method'] == 'item/tool/requestUserInput', 'unadmitted client response')
                self._consume_answer('sync', value, metadata)
                answer_attempt = True
            else:
                require(method in self.allowed, 'unadmitted client method')
        self._queue(direction, raw, key if value.get('method') and key else None)
        if direction == CLIENT:
            self._event(CLIENT, dict(client_message_queued=metadata,
                                    egress_start=self.queued_ends[CLIENT] - len(raw),
                                    egress_end=self.queued_ends[CLIENT],
                                    owner_answer=answer_attempt))

    def resolve_first(self, allow):
        try:
            self._now()
            require(self.failed is None and self.pending is not None and type(allow) is bool,
                    'no pending gate/invalid decision')
            require(allow, 'first dispatch denied')
            raw, value, key = self.pending
            require(len(self.queues[CLIENT]) + len(raw) + len(self.pending_controls) <=
                    self.limits.pending, 'pending release backpressure')
            self._queue(CLIENT, raw, key)
            self._event(CLIENT, dict(client_message_queued=self.pending_metadata,
                                    egress_start=self.queued_ends[CLIENT] - len(raw),
                                    egress_end=self.queued_ends[CLIENT], owner_answer=False))
            self._queue(CLIENT, bytes(self.pending_controls))
            self.pending_controls.clear()
            self.pending = None
            self.pending_metadata = None
            self.first_released = True
            self._event(CLIENT, dict(first_dispatch_released=value))
        except Hold as exc:
            self._fail(exc)

    def authorize_answer(self, route, exact_envelope):
        """One structural token, not Root authentication or semantic admission.

        Exact envelope comparison includes typed RPC ID and every params/result
        field. Async must include caller-bound native question fragments; this
        primitive cannot attest their origin. No automatic retry/second USER.
        """
        try:
            self._now()
            require(self.failed is None and self.first_released and not self.answer_used and
                    self.answer is None and self.armed_answer is None and
                    route in ('sync', 'async'), 'answer authorization unavailable')
            # Bound the immutable copy before retaining a token or capture detail.
            chunks, size = [], 0
            for chunk in json.JSONEncoder(allow_nan=False).iterencode(exact_envelope):
                encoded = chunk.encode()
                size += len(encoded)
                require(size <= self.limits.message, 'answer message length limit')
                chunks.append(encoded)
            value = envelope(b''.join(chunks))
            require('id' in value, 'answer requires typed ID')
            if route == 'async':
                require(value.get('method') in ('turn/start', 'turn/steer') and
                        type(value.get('params')) is dict, 'invalid async route')
            else:
                require('method' not in value and 'result' in value, 'invalid sync route')
                key = (self.capture.generation, SERVER, type(value['id']).__name__, value['id'])
                owner = self.owners.requests.get(key)
                require(owner and owner['method'] == 'item/tool/requestUserInput' and
                        owner['forwarded'] and not owner['responded'], 'foreign sync question owner')
            self.answer = (route, value)
            self._event(CLIENT, dict(answer_authorized=route, envelope=value))
        except (Hold, ValueError, TypeError, RecursionError) as exc:
            self._fail(exc)

    def arm_answer(self, route, matcher, decision_ref):
        """Arm one native attempt after caller validates the genuine Root choice.

        Matcher receives the actual envelope and metadata through protected
        copies. It must validate native question/thread/turn/value/settings and
        fresh native IDs; neither this reference nor a match authenticates Root.
        Exact authorization and matcher arming are mutually exclusive. Any
        native steer race/retry is a second attempt and cannot inherit a token.
        """
        try:
            self._now()
            require(self.failed is None and self.first_released and not self.answer_used and
                    self.answer is None and self.armed_answer is None,
                    'answer authorization unavailable')
            require(route in ('sync', 'async') and callable(matcher), 'invalid answer matcher')
            require(type(decision_ref) is dict and set(decision_ref) == {'path', 'sha256'},
                    'invalid decision reference')
            path, digest = decision_ref['path'], decision_ref['sha256']
            require(type(path) is str and 1 < len(path) <= 4096 and path.startswith('/') and
                    not path.startswith('//') and path == posixpath.normpath(path) and
                    all(ord(c) >= 32 and ord(c) != 127 for c in path) and
                    type(digest) is str and len(digest) == 64 and
                    all(c in '0123456789abcdef' for c in digest), 'invalid decision reference')
            # Syntax only; caller verifies actual canonical path/hash/authority
            # before arming. No file read or alias resolution occurs here.
            reference = dict(decision_ref)
            self.armed_answer = (route, matcher, reference)
            self._event(CLIENT, dict(answer_armed=route, decision_ref=reference))
        except (Hold, ValueError, TypeError) as exc:
            self._fail(exc)

    def _consume_answer(self, route, value, metadata):
        require(self.first_released and not self.answer_used and
                (self.answer is not None or self.armed_answer is not None),
                'unattributed/second answer')
        exact, armed = self.answer, self.armed_answer
        # Consume before evaluating: rejection, exception, overflow, or a later
        # failed write never refunds this observed native attempt.
        self.answer_used, self.answer, self.armed_answer = True, None, None
        decision_ref = armed[2] if armed else None
        self._event(CLIENT, dict(owner_answer_attempt=route, metadata=metadata,
                                decision_ref=decision_ref))
        if armed:
            require(armed[0] == route, 'unattributed/second answer route')
            self._callback(armed[1], value, metadata, 'answer matcher')
        else:
            require(exact[0] == route and _canonical(exact[1]) == _canonical(value),
                    'unattributed/second answer')
        self._event(CLIENT, dict(owner_answer_matched=route, metadata=metadata,
                                actual_envelope_sha256=_digest(value), decision_ref=decision_ref))

    def step(self):
        """One nonblocking fairness round; server lane proceeds during pending gate.

        Returns True after both EOFs and all queued writes drain. Failure is
        terminal, preserves capture, and never retries/reconnects or refunds.
        Caller must keep stepping during Root wait and stop on Hold.
        """
        try:
            require(self.failed is None, 'relay already failed: ' + str(self.failed))
            self._now()
            for direction in (SERVER, CLIENT):
                source = self.sockets[direction]
                if direction not in self.eof:
                    self.capture.reserve(0)
                    available = self.capture.limits.capture - self.capture.bytes
                    require(available > 0, 'capture exhausted')
                    read_start = self._now()
                    try:
                        raw = source.recv(min(65536, self.limits.pending, available))
                    except BlockingIOError:
                        raw = None
                    except OSError as exc:
                        raise Hold('read error: ' + str(exc)) from exc
                    if raw is not None:
                        self.capture.add('ingress', direction, read_start, raw)
                        if not raw:
                            self._event(direction, dict(eof=True))
                            require(direction in self.upgraded, 'EOF before upgrade')
                            self.decoders[direction].finish()
                            require(direction != CLIENT or self.pending is None, 'EOF while gate pending')
                            self.eof.add(direction)
                        else:
                            require(len(raw) + len(self.headers[direction]) <= self.limits.pending,
                                    'input backpressure')
                            if direction not in self.upgraded:
                                raw = self._handshake(direction, raw)
                            require(not raw or len(self.upgraded) == 2,
                                    'WebSocket before upgrade response')
                            decoder = self.decoders[direction]
                            messages = decoder.feed(raw, dict(ordinal=len(self.capture.records) - 1,
                                                              time=read_start))
                            for (frame_raw, value), metadata in zip(messages, decoder.emissions):
                                self._message(direction, frame_raw, value, metadata)
                queue = self.queues[direction]
                if queue:
                    target = self.sockets[DIRECTIONS[1 - DIRECTIONS.index(direction)]]
                    # Reserve maximum possible write BEFORE send so successful bytes
                    # cannot disappear from evidence due to a later capture overflow.
                    self.capture.reserve(len(queue))
                    write_start = self._now()
                    try:
                        count = target.send(queue)
                    except BlockingIOError:
                        self._event(direction, dict(write_blocked=True))
                        continue
                    except OSError as exc:
                        raise Hold('write error: ' + str(exc)) from exc
                    require(count > 0, 'zero-byte write')
                    write_end = self.clock()
                    self.capture.add('egress', direction, write_start, bytes(queue[:count]),
                                     dict(requested=len(queue), partial=count < len(queue),
                                          write_completed=write_end))
                    del queue[:count]
                    self.written[direction] += count
                    require(write_end >= write_start, 'clock moved backwards during write')
                    self.last_time = write_end
                    require(write_end < self.deadline, 'context deadline reached during write')
                    while self.forward_marks[direction] and self.forward_marks[direction][0][0] <= self.written[direction]:
                        _, key = self.forward_marks[direction].pop(0)
                        self.owners.requests[key]['forwarded'] = True
                if direction in self.eof and not queue:
                    target = self.sockets[DIRECTIONS[1 - DIRECTIONS.index(direction)]]
                    shutdown_key = 'shutdown_' + direction
                    if not getattr(self, shutdown_key, False):
                        target.shutdown(socket.SHUT_WR)
                        setattr(self, shutdown_key, True)
                        self._event(direction, dict(write_eof=True))
            return len(self.eof) == 2 and all(not q for q in self.queues.values())
        except (Hold, OSError) as exc:
            self._fail(exc)
