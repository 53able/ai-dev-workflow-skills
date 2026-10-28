"""Fresh socketpair-only synthetic transport tests; no native fixture imports."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import struct
import sys
import unittest

SPEC = importlib.util.spec_from_file_location('question_relay', Path(__file__).with_name('question_relay.py'))
r = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = r
SPEC.loader.exec_module(r)
KEY = b'MDEyMzQ1Njc4OWFiY2RlZg=='
REQUEST = (b'GET /native HTTP/1.1\r\nHost: owned\r\nConnection: keep-alive, Upgrade\r\n'
           b'Upgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: ' + KEY + b'\r\n\r\n')
ACCEPT = base64.b64encode(hashlib.sha1(KEY + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())
RESPONSE = b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + ACCEPT + b'\r\n\r\n'


def frame(payload=b'', *, client=True, opcode=1, final=True):
    if not isinstance(payload, bytes):
        payload = json.dumps(payload, separators=(',', ':')).encode()
    size = len(payload)
    prefix = bytes([(128 if final else 0) | opcode])
    prefix += bytes([(128 if client else 0) | (size if size < 126 else 126 if size < 65536 else 127)])
    if size >= 126:
        prefix += struct.pack('!H' if size < 65536 else '!Q', size)
    if client:
        mask = b'\x01\x02\x03\x04'
        return prefix + mask + bytes(v ^ mask[i % 4] for i, v in enumerate(payload))
    return prefix + payload


def drain(sock):
    result = bytearray()
    while True:
        try:
            data = sock.recv(1048576)
        except BlockingIOError:
            break
        if not data:
            break
        result.extend(data)
    return bytes(result)


class Pair:
    def __init__(self, **kwargs):
        self.client, inside_client = socket.socketpair()
        inside_server, self.server = socket.socketpair()
        self.sockets = (self.client, inside_client, inside_server, self.server)
        self.time = 10.0
        self.relay = r.Relay(inside_client, inside_server, generation=kwargs.pop('generation', 'fresh-1'),
                             startup_methods={'initialize', 'initialized', 'thread/start'},
                             clock=lambda: self.time, **kwargs)
        self.client.setblocking(False)
        self.server.setblocking(False)

    def upgrade(self):
        # Deliberately split the HTTP request and preserve exact casing/spacing.
        self.client.sendall(REQUEST[:17]); self.relay.step()
        assert drain(self.server) == b''
        self.client.sendall(REQUEST[17:]); self.relay.step()
        assert drain(self.server) == REQUEST
        self.server.sendall(RESPONSE); self.relay.step()
        assert drain(self.client) == RESPONSE

    def initial(self):
        value = {'id': 1, 'method': 'turn/start', 'params': {'threadId': 'fresh-thread'}}
        raw = frame(value)
        self.client.sendall(raw); self.relay.step()
        assert self.relay.pending is not None
        self.relay.resolve_first(True); self.relay.step()
        assert drain(self.server) == raw
        return value

    def close(self):
        for sock in self.sockets:
            sock.close()


class RelayTests(unittest.TestCase):
    def pair(self, **kwargs):
        pair = Pair(**kwargs)
        self.addCleanup(pair.close)
        return pair

    def test_server_observer_complete_fragment_provenance_and_raw_forwarding(self):
        seen = []
        def observe(value, metadata):
            seen.append((value, metadata))
            return True
        p = self.pair(server_observer=observe); p.upgrade()
        value = {'method': 'turn/completed', 'params': {'threadId': 't'}}
        payload = json.dumps(value).encode()
        first = frame(payload[:11], client=False, final=False)
        ping = frame(b'ping', client=False, opcode=9)
        last = frame(payload[11:], client=False, opcode=0)
        p.server.sendall(first + ping); p.relay.step()
        self.assertEqual(drain(p.client), first + ping)
        self.assertEqual(seen, [])
        p.server.sendall(last); p.relay.step()
        self.assertEqual(drain(p.client), last)
        self.assertEqual(len(seen), 1)
        actual, metadata = seen[0]
        self.assertEqual(actual, value)
        self.assertEqual(metadata['generation'], 'fresh-1')
        self.assertEqual(metadata['direction'], r.SERVER)
        spans = metadata['frame_spans']
        self.assertEqual([span['opcode'] for span in spans], [1, 9, 0])
        self.assertEqual(metadata['start'], len(RESPONSE))
        self.assertEqual(metadata['end'], len(RESPONSE + first + ping + last))
        self.assertEqual(p.relay.capture.raw('egress', r.SERVER), RESPONSE + first + ping + last)
        self.assertIn('ordinal', metadata['fin_observation'])
        self.assertEqual(metadata['decoded_sha256'], r._digest(value))

    def test_server_observer_mutation_exception_false_and_deadline_hold(self):
        def mutate(value, metadata):
            value['params']['changed'] = True
            return True
        def mutate_metadata(value, metadata):
            metadata['generation'] = 'foreign'
            return True
        def exception(value, metadata):
            raise RuntimeError('untrusted')
        for callback in (mutate, mutate_metadata, exception, lambda v, m: False,
                         lambda v, m: 1):
            with self.subTest(callback=callback):
                p = self.pair(server_observer=callback); p.upgrade()
                value = {'method': 'turn/started', 'params': {}}
                p.server.sendall(frame(value, client=False))
                with self.assertRaises(r.Hold): p.relay.step()
                self.assertIsNotNone(p.relay.failed)
        p = self.pair(); p.upgrade()
        def overrun(value, metadata):
            p.time = p.relay.deadline
            return True
        p.relay.server_observer = overrun
        p.server.sendall(frame({'method': 'turn/started', 'params': {}}, client=False))
        with self.assertRaises(r.Hold): p.relay.step()

    def test_import_and_cli_inert(self):
        self.assertFalse(r.Relay.runtime_admitted)
        self.assertEqual(r.CONTEXTS, ('default', 'copy'))
        self.assertEqual(r.POTENTIAL_CHARGED_USERS, 4)
        self.assertNotIn('subprocess', r.__dict__)
        self.assertNotIn('pty', r.__dict__)

    def test_original_upgrade_preserved_and_directional_capture(self):
        p = self.pair(); p.upgrade()
        for kind in ('ingress', 'egress'):
            self.assertEqual(p.relay.capture.raw(kind, r.CLIENT), REQUEST)
            self.assertEqual(p.relay.capture.raw(kind, r.SERVER), RESPONSE)

    def test_fragmented_dispatch_zero_prefix_and_server_terminal_during_gate(self):
        p = self.pair(); p.upgrade()
        text = json.dumps({'id': 7, 'method': 'turn/start', 'params': {'input': 'actual'}}).encode()
        fragments = [frame(text[:13], final=False), frame(b'ping', opcode=9), frame(text[13:], opcode=0)]
        p.client.sendall(fragments[0]); p.relay.step()
        self.assertEqual(drain(p.server), b'')
        p.client.sendall(fragments[1]); p.relay.step()
        self.assertEqual(drain(p.server), b'')
        p.client.sendall(fragments[2]); p.relay.step()
        self.assertEqual(drain(p.server), b'')
        self.assertIsNotNone(p.relay.pending)
        terminal = frame({'method': 'turn/completed', 'params': {'turn': 'actual'}}, client=False)
        p.server.sendall(terminal); p.relay.step()
        self.assertEqual(drain(p.client), terminal)
        self.assertEqual(p.relay.capture.raw('egress', r.CLIENT), REQUEST)
        p.relay.resolve_first(True); p.relay.step()
        self.assertEqual(drain(p.server), b''.join(fragments))

    def test_control_after_pending_dispatch_cannot_overtake_it(self):
        p = self.pair(); p.upgrade()
        raw = frame({'id': 1, 'method': 'turn/start', 'params': {}})
        ping = frame(b'ping', opcode=9)
        p.client.sendall(raw + ping); p.relay.step()
        self.assertEqual(drain(p.server), b'')
        p.relay.resolve_first(True); p.relay.step()
        self.assertEqual(drain(p.server), raw + ping)

    def test_coalesced_non_dispatch_and_dispatch_do_not_leak_dispatch(self):
        p = self.pair(); p.upgrade()
        setup = frame({'id': '1', 'method': 'initialize', 'params': {}})
        model = frame({'id': 1, 'method': 'turn/start', 'params': {}})
        p.client.sendall(setup + model); p.relay.step()
        self.assertEqual(drain(p.server), setup)
        self.assertEqual(p.relay.pending[0], model)

    def test_typed_ids_and_independent_request_directions(self):
        p = self.pair(); p.upgrade()
        client = frame({'id': 1, 'method': 'initialize'}) + frame({'id': '1', 'method': 'thread/start'})
        p.client.sendall(client); p.relay.step(); self.assertEqual(drain(p.server), client)
        server = frame({'id': 1, 'method': 'server/read'}, client=False)
        responses = frame({'id': 1, 'result': {}}, client=False) + frame({'id': '1', 'result': {}}, client=False)
        p.server.sendall(server + responses); p.relay.step()
        self.assertEqual(drain(p.client), server + responses)
        self.assertEqual(len(p.relay.owners.requests), 3)

    def test_foreign_duplicate_and_malformed_responses_fail_before_forward(self):
        for value in ({'id': 17, 'result': {}}, {'id': True, 'result': {}},
                      {'id': 1, 'result': {}, 'error': {}}, {'id': 1},
                      {'id': 1, 'error': {'code': 'bad', 'message': 'bad'}}):
            with self.subTest(value=value):
                p = self.pair(); p.upgrade()
                p.server.sendall(frame(value, client=False))
                with self.assertRaises(r.Hold): p.relay.step()
                self.assertEqual(drain(p.client), b'')
        p = self.pair(); p.upgrade()
        p.client.sendall(frame({'id': 1, 'method': 'initialize'})); p.relay.step(); drain(p.server)
        reply = frame({'id': 1, 'result': {}}, client=False)
        p.server.sendall(reply); p.relay.step(); self.assertEqual(drain(p.client), reply)
        p.server.sendall(reply)
        with self.assertRaisesRegex(r.Hold, 'duplicate'): p.relay.step()
        self.assertEqual(drain(p.client), b'')

    def test_connection_generation_cannot_borrow_request_owner(self):
        a = self.pair(generation='a'); b = self.pair(generation='b')
        a.upgrade(); b.upgrade()
        a.client.sendall(frame({'id': 1, 'method': 'initialize'})); a.relay.step(); drain(a.server)
        b.server.sendall(frame({'id': 1, 'result': {}}, client=False))
        with self.assertRaisesRegex(r.Hold, 'foreign'): b.relay.step()
        self.assertEqual(drain(b.client), b'')

    def test_sync_answer_exact_owner_and_no_second_answer(self):
        p = self.pair(); p.upgrade(); p.initial()
        question = {'id': 3, 'method': 'item/tool/requestUserInput', 'params': {'itemId': 'call'}}
        p.server.sendall(frame(question, client=False)); p.relay.step(); drain(p.client)
        answer = {'id': 3, 'result': {'answers': {'q1': {'answers': ['chosen']}}}}
        p.relay.authorize_answer('sync', answer)
        raw = frame(answer); p.client.sendall(raw); p.relay.step()
        self.assertEqual(drain(p.server), raw)
        self.assertTrue(p.relay.answer_used)
        with self.assertRaisesRegex(r.Hold, 'unavailable'): p.relay.authorize_answer('sync', answer)

    def test_sync_route_cannot_authorize_foreign_question(self):
        p = self.pair(); p.upgrade(); p.initial()
        with self.assertRaisesRegex(r.Hold, 'foreign sync'): p.relay.authorize_answer('sync', {'id': 3, 'result': {}})

    def test_async_exact_envelope_and_no_generic_second_user(self):
        for method in ('turn/start', 'turn/steer'):
            p = self.pair(); p.upgrade(); p.initial()
            answer = {'id': 2, 'method': method, 'params': {'input': [{'type': 'text', 'text': 'actual native fragment'}]}}
            p.relay.authorize_answer('async', answer)
            raw = frame(answer); p.client.sendall(raw); p.relay.step()
            self.assertEqual(drain(p.server), raw)
            second = frame({'id': 4, 'method': 'turn/start', 'params': {}})
            p.client.sendall(second)
            with self.assertRaisesRegex(r.Hold, 'second answer'): p.relay.step()
            self.assertEqual(drain(p.server), b'')

    def test_wrong_answer_and_unauthorized_dispatch_never_forward_prefix(self):
        for authorized in (False, True):
            p = self.pair(); p.upgrade(); p.initial()
            if authorized:
                p.relay.authorize_answer('async', {'id': 2, 'method': 'turn/steer', 'params': {'input': 'chosen'}})
            raw = frame({'id': 2, 'method': 'turn/steer', 'params': {'input': 'other'}})
            p.client.sendall(raw[:8]); p.relay.step(); self.assertEqual(drain(p.server), b'')
            p.client.sendall(raw[8:])
            with self.assertRaisesRegex(r.Hold, 'unattributed'): p.relay.step()
            self.assertEqual(drain(p.server), b'')

    def test_no_cross_protocol_token_and_no_typed_id_confusion(self):
        p = self.pair(); p.upgrade(); p.initial()
        p.relay.authorize_answer('async', {'id': 2, 'method': 'turn/steer', 'params': {}})
        p.client.sendall(frame({'id': '2', 'method': 'turn/steer', 'params': {}}))
        with self.assertRaises(r.Hold): p.relay.step()
        self.assertEqual(drain(p.server), b'')

    def test_deadline_equality_gate_does_not_restart_clock(self):
        p = self.pair(); p.upgrade()
        p.client.sendall(frame({'id': 1, 'method': 'turn/start', 'params': {}})); p.relay.step()
        p.time = 189.999; p.relay.resolve_first(True); p.relay.step(); drain(p.server)
        self.assertEqual(p.relay.deadline, 190)
        p.time = 190
        with self.assertRaisesRegex(r.Hold, 'deadline'): p.relay.step()

    def test_deadline_checked_immediately_before_write(self):
        p = self.pair(); p.upgrade()
        p.server.sendall(frame({'method': 'notice'}, client=False))
        ticks = iter((10, 190))
        p.relay.clock = lambda: next(ticks)
        with self.assertRaisesRegex(r.Hold, 'deadline'): p.relay.step()
        self.assertEqual(drain(p.client), b'')
        self.assertEqual(p.relay.capture.raw('egress', r.SERVER), RESPONSE)

    def test_write_crossing_deadline_retains_successful_bytes(self):
        p = self.pair(); p.upgrade()
        raw = frame({'method': 'notice'}, client=False)
        p.server.sendall(raw)
        ticks = iter((10, 10, 189.9, 190))
        p.relay.clock = lambda: next(ticks)
        with self.assertRaisesRegex(r.Hold, 'during write'): p.relay.step()
        self.assertEqual(drain(p.client), raw)
        self.assertEqual(p.relay.capture.raw('egress', r.SERVER), RESPONSE + raw)

    def test_denied_gate_terminal_and_no_bytes_sent(self):
        p = self.pair(); p.upgrade()
        p.client.sendall(frame({'id': 1, 'method': 'turn/start', 'params': {}})); p.relay.step()
        with self.assertRaisesRegex(r.Hold, 'denied'): p.relay.resolve_first(False)
        with self.assertRaises(r.Hold): p.relay.step()
        self.assertEqual(drain(p.server), b'')

    def test_eof_incomplete_and_orderly_halfclose(self):
        p = self.pair(); p.upgrade()
        p.client.sendall(b'\x81'); p.client.shutdown(socket.SHUT_WR)
        p.relay.step()
        with self.assertRaisesRegex(r.Hold, 'incomplete'): p.relay.step()
        p = self.pair(); p.upgrade()
        p.client.shutdown(socket.SHUT_WR); p.server.shutdown(socket.SHUT_WR)
        self.assertTrue(p.relay.step())
        self.assertEqual(sum(bool(x.get('detail', {}).get('eof')) for x in p.relay.capture.records if isinstance(x.get('detail'), dict)), 2)

    def test_capture_overflow_has_no_unrecorded_egress(self):
        p = self.pair(limits=r.Limits(capture=600)); p.upgrade()
        before = p.relay.capture.raw('egress', r.SERVER)
        raw = frame({'method': 'notice', 'params': {'text': 'a' * 500}}, client=False)
        p.server.sendall(raw)
        with self.assertRaisesRegex(r.Hold, 'capture exhausted'): p.relay.step()
        self.assertEqual(p.relay.capture.raw('egress', r.SERVER), before)
        self.assertEqual(drain(p.client), b'')

    def test_backpressure_bounded(self):
        p = self.pair(limits=r.Limits(pending=256)); p.upgrade()
        raw = frame({'method': 'notice', 'params': {'text': 'x' * 300}}, client=False)
        p.server.sendall(raw)
        with self.assertRaisesRegex(r.Hold, 'backpressure'):
            p.relay.step(); p.relay.step()

    def test_partial_write_and_blocked_write_record_actual_bytes(self):
        p = self.pair(); p.upgrade()
        # Wrap only the connected Unix destination: deterministic short writes
        # still reach an actual fresh socketpair peer.
        sock = p.relay.sockets[r.CLIENT]
        class Short:
            def __init__(self): self.block = True
            def recv(self, n): return sock.recv(n)
            def send(self, raw):
                if self.block:
                    self.block = False
                    raise BlockingIOError()
                return sock.send(raw[:7])
            def shutdown(self, how): return sock.shutdown(how)
        p.relay.sockets[r.CLIENT] = Short()
        raw = frame({'method': 'notice', 'params': {'text': 'actual'}}, client=False)
        p.server.sendall(raw); p.relay.step()
        self.assertEqual(drain(p.client), b'')
        self.assertEqual(p.relay.capture.raw('egress', r.SERVER), RESPONSE)
        received = bytearray()
        for _ in range(len(raw)):
            p.relay.step(); received.extend(drain(p.client))
            if not p.relay.queues[r.SERVER]: break
        self.assertEqual(bytes(received), raw)
        self.assertEqual(p.relay.capture.raw('egress', r.SERVER), RESPONSE + raw)
        self.assertTrue(any(x.get('detail', {}).get('partial') for x in p.relay.capture.records if isinstance(x.get('detail'), dict)))

    def test_explicit_write_error(self):
        p = self.pair(); p.upgrade(); p.client.close()
        p.server.sendall(frame({'method': 'notice'}, client=False))
        with self.assertRaisesRegex(r.Hold, 'write error'): p.relay.step()
        self.assertEqual(p.relay.capture.raw('egress', r.SERVER), RESPONSE)

    def test_decoder_rejects_unsupported_and_malformed(self):
        bad = [b'\xc1\x80\x00\x00\x00\x00', frame(b'{}', client=False),
               frame(b'{}', opcode=2), frame(b'{}', opcode=0),
               frame(b'x' * 126, opcode=9), frame(b'{}', opcode=9, final=False),
               b'\x81\xfe\x00\x01' + b'1234' + b'x',
               frame(b'{"method":"a","method":"b"}'), frame(b'\xff'),
               frame(b'NaN'), frame(b'{'), frame(b'\x03', opcode=8)]
        for raw in bad:
            with self.subTest(raw=raw[:20]):
                with self.assertRaises(r.Hold): r.Decoder(True, r.Limits()).feed(raw)

    def test_extended_lengths_server_fragments_controls_coalesced(self):
        for length in (126, 65536):
            value = {'method': 'notice', 'params': {'text': 'x' * length}}
            raw = frame(value, client=False)
            decoder = r.Decoder(False, r.Limits()); items = []
            for start in range(0, len(raw), 19): items.extend(decoder.feed(raw[start:start + 19]))
            decoder.finish()
            self.assertEqual(items, [(raw, value)])
        p = self.pair(); p.upgrade()
        text = b'{"method":"notice"}'
        raw = frame(text[:6], client=False, final=False) + frame(b'p', client=False, opcode=10) + frame(text[6:], client=False, opcode=0) + frame(b'', client=False, opcode=9)
        p.server.sendall(raw); p.relay.step()
        self.assertEqual(drain(p.client), raw)

    def test_server_fragment_and_ping_forward_before_message_fin(self):
        p = self.pair(); p.upgrade()
        first = frame(b'{"method":', client=False, final=False)
        ping = frame(b'live', client=False, opcode=9)
        last = frame(b'"notice"}', client=False, opcode=0)
        for raw in (first, ping, last):
            p.server.sendall(raw); p.relay.step()
            self.assertEqual(drain(p.client), raw)

    def test_server_close_can_end_an_incomplete_message(self):
        p = self.pair(); p.upgrade()
        first = frame(b'{"method":', client=False, final=False)
        close = frame(b'\x03\xe8', client=False, opcode=8)
        p.server.sendall(first); p.relay.step()
        self.assertEqual(drain(p.client), first)
        p.server.sendall(close); p.relay.step()
        self.assertEqual(drain(p.client), close)
        p.server.shutdown(socket.SHUT_WR); p.relay.step()

    def test_ingress_time_follows_previous_lane_write(self):
        p = self.pair(); p.upgrade()
        tick = iter(range(11, 100))
        p.relay.clock = lambda: next(tick)
        p.server.sendall(frame({'method': 'notice'}, client=False))
        p.client.sendall(frame({'id': 8, 'method': 'initialize'}))
        p.relay.step()
        times = [item['time'] for item in p.relay.capture.records]
        self.assertEqual(times, sorted(times))

    def test_capture_limit_leaves_unrecorded_ingress_in_socket(self):
        p = self.pair(); p.upgrade()
        limits = r.Limits(capture=p.relay.capture.bytes + 18)
        p.relay.limits = p.relay.capture.limits = limits
        raw = frame({'method': 'notice', 'params': {'text': 'x' * 100}}, client=False)
        p.server.sendall(raw)
        with self.assertRaisesRegex(r.Hold, 'capture exhausted'):
            p.relay.step()
        recorded = p.relay.capture.raw('ingress', r.SERVER)[len(RESPONSE):]
        remaining = p.relay.sockets[r.SERVER].recv(4096)
        self.assertEqual(recorded, raw[:18])
        self.assertEqual(recorded + remaining, raw)

    def test_frames_before_upgrade_response_rejected(self):
        p = self.pair()
        p.client.sendall(REQUEST + frame({'id': 1, 'method': 'turn/start', 'params': {}}))
        with self.assertRaisesRegex(r.Hold, 'before upgrade'): p.relay.step()
        self.assertEqual(drain(p.server), b'')

    def test_read_error_recorded_and_terminal(self):
        p = self.pair(); p.upgrade()
        sock = p.relay.sockets[r.SERVER]
        class BrokenRead:
            def recv(self, n): raise OSError('synthetic socket read error')
            def send(self, raw): return sock.send(raw)
            def shutdown(self, how): return sock.shutdown(how)
        p.relay.sockets[r.SERVER] = BrokenRead()
        with self.assertRaisesRegex(r.Hold, 'read error'): p.relay.step()
        self.assertIn('read error', p.relay.failed)
        self.assertTrue(any('error' in x.get('detail', {}) for x in p.relay.capture.records if isinstance(x.get('detail'), dict)))

    def test_server_proceeds_when_client_egress_blocked(self):
        p = self.pair(); p.upgrade()
        sock = p.relay.sockets[r.SERVER]
        class Blocked:
            def recv(self, n): return sock.recv(n)
            def send(self, raw): raise BlockingIOError()
            def shutdown(self, how): return sock.shutdown(how)
        p.relay.sockets[r.SERVER] = Blocked()
        p.client.sendall(frame({'id': 3, 'method': 'initialize'})); p.relay.step()
        terminal = frame({'method': 'turn/completed', 'params': {}}, client=False)
        p.server.sendall(terminal); p.relay.step()
        self.assertEqual(drain(p.client), terminal)
        self.assertTrue(p.relay.queues[r.CLIENT])

    def test_answer_nested_numeric_types_are_exact(self):
        p = self.pair(); p.upgrade(); p.initial()
        p.relay.authorize_answer('async', {'id': 2, 'method': 'turn/steer', 'params': {'value': 1}})
        p.client.sendall(frame({'id': 2, 'method': 'turn/steer', 'params': {'value': True}}))
        with self.assertRaisesRegex(r.Hold, 'unattributed'): p.relay.step()
        self.assertEqual(drain(p.server), b'')

    def test_oversized_answer_is_rejected_before_retention(self):
        p = self.pair(limits=r.Limits(message=256)); p.upgrade(); p.initial()
        before = p.relay.capture.bytes
        answer = {'id': 2, 'method': 'turn/steer', 'params': {'text': 'x' * 500}}
        with self.assertRaisesRegex(r.Hold, 'answer message length limit'):
            p.relay.authorize_answer('async', answer)
        self.assertIsNone(p.relay.answer)
        self.assertFalse(p.relay.answer_used)
        self.assertEqual(p.relay.capture.bytes, before)
        self.assertFalse(any('answer_authorized' in (item.get('detail') or {})
                             for item in p.relay.capture.records))

    def decision_ref(self):
        # Syntactic provenance only; no fixture/file is created or read.
        return {'path': '/synthetic/root/decision.json', 'sha256': 'a' * 64}

    def test_absolute_deadline_includes_preconstruction_time(self):
        p = self.pair(deadline=100)
        self.assertEqual(p.relay.started, 10)
        p.upgrade(); p.initial()
        self.assertEqual(p.relay.deadline, 100)
        p.time = 100
        with self.assertRaisesRegex(r.Hold, 'deadline'): p.relay.step()

    def test_absolute_deadline_rejects_extension_nonfinite_and_expiry(self):
        for deadline in (190.01, 10, 9, True, '190', float('inf'), float('nan')):
            with self.subTest(deadline=deadline):
                sockets = [socket.socketpair(), socket.socketpair()]
                try:
                    with self.assertRaisesRegex(r.Hold, 'absolute deadline'):
                        r.Relay(sockets[0][0], sockets[1][0], generation='fresh',
                                startup_methods=set(), clock=lambda: 10, deadline=deadline)
                finally:
                    for pair in sockets:
                        for sock in pair: sock.close()

    def test_guard_full_message_params_and_provenance_before_any_prefix(self):
        seen = []
        def guard(value, metadata):
            seen.append((value, metadata))
            return value.get('params') == {'threadId': 'owned'}
        p = self.pair(client_guard=guard); p.upgrade()
        value = {'id': 9, 'method': 'thread/start', 'params': {'threadId': 'foreign'}}
        data = json.dumps(value).encode()
        a = frame(data[:15], final=False); ping = frame(b'hi', opcode=9)
        b = frame(data[15:], opcode=0)
        p.client.sendall(a + ping); p.relay.step()
        self.assertEqual(seen, [])
        self.assertEqual(drain(p.server), b'')
        p.client.sendall(b)
        with self.assertRaisesRegex(r.Hold, 'client guard rejected'): p.relay.step()
        self.assertEqual(drain(p.server), b'')
        self.assertEqual(seen[0][0], value)
        metadata = seen[0][1]
        self.assertEqual(metadata['generation'], 'fresh-1')
        self.assertEqual(metadata['direction'], r.CLIENT)
        self.assertEqual(metadata['start'], len(REQUEST))
        self.assertEqual(metadata['end'], len(REQUEST) + len(a + ping + b))
        self.assertEqual([x['opcode'] for x in metadata['frame_spans']], [1, 9, 0])
        self.assertEqual(metadata['wire_sha256'], hashlib.sha256(a + ping + b).hexdigest())
        self.assertEqual(metadata['decoded_sha256'], r._digest(value))
        observation = metadata['fin_observation']
        receipt = p.relay.capture.records[observation['ordinal']]
        self.assertEqual(receipt['kind'], 'ingress')
        self.assertEqual(receipt['time'], observation['time'])

    def test_guard_literal_true_only_exceptions_and_deadline_fail_closed(self):
        for result in (False, None, 1, 'yes'):
            p = self.pair(client_guard=lambda value, metadata: result); p.upgrade()
            p.client.sendall(frame({'id': 2, 'method': 'initialize'}))
            with self.assertRaisesRegex(r.Hold, 'client guard rejected'): p.relay.step()
            self.assertEqual(drain(p.server), b'')
        def error(value, metadata): raise RuntimeError('synthetic')
        p = self.pair(client_guard=error); p.upgrade()
        p.client.sendall(frame({'id': 2, 'method': 'initialize'}))
        with self.assertRaisesRegex(r.Hold, 'client guard exception'): p.relay.step()
        self.assertEqual(drain(p.server), b'')
        p = self.pair(); p.upgrade()
        def overrun(value, metadata):
            p.time = p.relay.deadline
            return True
        p.relay.client_guard = overrun
        p.client.sendall(frame({'id': 2, 'method': 'initialize'}))
        with self.assertRaisesRegex(r.Hold, 'deadline'): p.relay.step()
        self.assertEqual(drain(p.server), b'')

    def test_callback_copies_reject_nested_value_and_metadata_mutation(self):
        for target in ('value', 'metadata'):
            seen = []
            def mutate(value, metadata):
                seen.append((value, metadata))
                if target == 'value': value['params']['nested'][0] = False
                else: metadata['frame_spans'][0]['opcode'] = 0
                return True
            p = self.pair(client_guard=mutate); p.upgrade()
            original = {'id': 2, 'method': 'initialize', 'params': {'nested': [1]}}
            raw = frame(original); p.client.sendall(raw)
            with self.assertRaisesRegex(r.Hold, 'mutated callback input'): p.relay.step()
            self.assertEqual(drain(p.server), b'')
            self.assertEqual(p.relay.capture.raw('ingress', r.CLIENT), REQUEST + raw)
            observed = next(x['detail']['client_message_observed'] for x in p.relay.capture.records
                            if 'client_message_observed' in (x.get('detail') or {}))
            self.assertEqual(observed['frame_spans'][0]['opcode'], 1)
            self.assertEqual(observed['decoded_sha256'], r._digest(original))

    def test_guard_receives_all_client_json_including_sync_response(self):
        seen = []
        p = self.pair(client_guard=lambda value, metadata: seen.append(value) is None)
        p.upgrade(); initial = p.initial()
        question = {'id': 17, 'method': 'item/tool/requestUserInput', 'params': {}}
        p.server.sendall(frame(question, client=False)); p.relay.step(); drain(p.client)
        answer = {'id': 17, 'result': {'answers': {}}}
        p.relay.authorize_answer('sync', answer)
        p.client.sendall(frame(answer)); p.relay.step(); drain(p.server)
        self.assertEqual(seen, [initial, answer])

    def test_arm_matches_actual_unknown_id_and_both_async_native_routes(self):
        for method in ('turn/steer', 'turn/start'):
            p = self.pair(); p.upgrade(); p.initial()
            calls = []
            def matcher(value, metadata):
                calls.append((value, metadata))
                return value['params'] == {'threadId': 'fresh-thread', 'input': 'chosen'}
            ref = self.decision_ref()
            p.relay.arm_answer('async', matcher, ref)
            ref['sha256'] = 'b' * 64  # caller cannot mutate retained provenance
            value = {'id': 'native-unknown-918', 'method': method,
                     'params': {'threadId': 'fresh-thread', 'input': 'chosen'}}
            raw = frame(value)
            p.client.sendall(raw[:9]); p.relay.step()
            self.assertEqual(calls, [])
            self.assertEqual(drain(p.server), b'')
            terminal = frame({'method': 'turn/completed', 'params': {}}, client=False)
            p.server.sendall(terminal); p.relay.step()
            self.assertEqual(drain(p.client), terminal)
            p.client.sendall(raw[9:]); p.relay.step()
            self.assertEqual(drain(p.server), raw)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], value)
            matched = next(x for x in p.relay.capture.records
                           if 'owner_answer_matched' in (x.get('detail') or {}))
            self.assertEqual(matched['detail']['decision_ref'], self.decision_ref())
            self.assertEqual(matched['detail']['actual_envelope_sha256'], r._digest(value))
            queued = next(x for x in p.relay.capture.records
                          if (x.get('detail') or {}).get('owner_answer'))
            egress = next(x for x in p.relay.capture.records
                          if x['kind'] == 'egress' and x['direction'] == r.CLIENT
                          and x['start'] == queued['detail']['egress_start'])
            self.assertLess(matched['ordinal'], queued['ordinal'])
            self.assertLess(queued['ordinal'], egress['ordinal'])
            self.assertEqual(egress['raw'], raw)
            self.assertTrue(p.relay.answer_used)
            p.client.sendall(frame({'id': 'native-retry', 'method': 'turn/start', 'params': {}}))
            with self.assertRaisesRegex(r.Hold, 'second answer'): p.relay.step()
            self.assertEqual(len(calls), 1)
            self.assertEqual(drain(p.server), b'')

    def test_native_steer_error_then_automatic_start_retry_is_retained_and_denied(self):
        p = self.pair(); p.upgrade(); p.initial()
        calls = []
        p.relay.arm_answer('async', lambda value, metadata: calls.append(value) is None,
                           self.decision_ref())
        attempt = {'id': 917, 'method': 'turn/steer', 'params': {'input': 'chosen'}}
        p.client.sendall(frame(attempt)); p.relay.step(); drain(p.server)
        error = frame({'id': 917, 'error': {'code': -32000, 'message': 'native turn race'}}, client=False)
        p.server.sendall(error); p.relay.step()
        self.assertEqual(drain(p.client), error)
        retry = frame({'id': 918, 'method': 'turn/start', 'params': {'input': 'chosen'}})
        p.client.sendall(retry)
        with self.assertRaisesRegex(r.Hold, 'second answer'): p.relay.step()
        self.assertEqual(calls, [attempt])
        self.assertTrue(p.relay.answer_used)
        self.assertEqual(drain(p.server), b'')
        self.assertTrue(p.relay.capture.raw('ingress', r.SERVER).endswith(error))
        self.assertTrue(p.relay.capture.raw('ingress', r.CLIENT).endswith(retry))
        self.assertFalse(p.relay.capture.raw('egress', r.CLIENT).endswith(retry))

    def test_matcher_route_mismatch_consumes_without_cross_protocol_callback(self):
        p = self.pair(); p.upgrade(); p.initial()
        calls = []
        p.relay.arm_answer('sync', lambda value, metadata: calls.append(value) is None,
                           self.decision_ref())
        p.client.sendall(frame({'id': 3, 'method': 'turn/steer', 'params': {}}))
        with self.assertRaisesRegex(r.Hold, 'route'): p.relay.step()
        self.assertTrue(p.relay.answer_used)
        self.assertEqual(calls, [])
        self.assertEqual(drain(p.server), b'')

    def test_client_guard_can_close_observer_params_and_thread_scope(self):
        seen = []
        def guard(value, metadata):
            seen.append(metadata['generation'])
            return value.get('method') == 'initialize' and value.get('params') == {'readOnly': True}
        p = self.pair(client_guard=guard, generation='observer-generation'); p.upgrade()
        admitted = frame({'id': 3, 'method': 'initialize', 'params': {'readOnly': True}})
        p.client.sendall(admitted); p.relay.step()
        self.assertEqual(drain(p.server), admitted)
        p.client.sendall(frame({'id': 4, 'method': 'thread/start', 'params': {'threadId': 'foreign'}}))
        with self.assertRaisesRegex(r.Hold, 'client guard rejected'): p.relay.step()
        self.assertEqual(drain(p.server), b'')
        self.assertEqual(seen, ['observer-generation', 'observer-generation'])

    def test_nonfinite_numeric_payload_holds_before_client_forward(self):
        p = self.pair(); p.upgrade()
        p.client.sendall(frame(b'{"id":3,"method":"initialize","params":{"value":1e999}}'))
        with self.assertRaisesRegex(r.Hold, 'canonical JSON'): p.relay.step()
        self.assertIsNotNone(p.relay.failed)
        self.assertEqual(drain(p.server), b'')

    def test_arm_sync_matcher_requires_actual_request_owner(self):
        p = self.pair(); p.upgrade(); p.initial()
        question = {'id': 'native-question', 'method': 'item/tool/requestUserInput', 'params': {}}
        p.server.sendall(frame(question, client=False)); p.relay.step(); drain(p.client)
        calls = []
        p.relay.arm_answer('sync', lambda value, metadata: calls.append(value) is None, self.decision_ref())
        answer = {'id': 'native-question', 'result': {'answers': {'q': {'answers': ['chosen']}}}}
        p.client.sendall(frame(answer)); p.relay.step()
        self.assertEqual(drain(p.server), frame(answer))
        self.assertEqual(calls, [answer])

    def test_rejected_matcher_exception_mutation_and_overrun_consume_attempt(self):
        for behavior in ('reject', 'truthy', 'error', 'mutate', 'metadata', 'overrun'):
            with self.subTest(behavior=behavior):
                p = self.pair(); p.upgrade(); p.initial()
                calls = []
                def matcher(value, metadata):
                    calls.append(value)
                    if behavior == 'error': raise RuntimeError('synthetic')
                    if behavior == 'mutate': value['params']['input'] = 'changed'
                    if behavior == 'metadata': metadata['generation'] = 'other'
                    if behavior == 'overrun': p.time = p.relay.deadline
                    return 1 if behavior == 'truthy' else behavior != 'reject'
                p.relay.arm_answer('async', matcher, self.decision_ref())
                p.client.sendall(frame({'id': 3, 'method': 'turn/steer', 'params': {'input': 'chosen'}}))
                with self.assertRaises(r.Hold): p.relay.step()
                self.assertEqual(len(calls), 1)
                self.assertTrue(p.relay.answer_used)
                self.assertIsNone(p.relay.armed_answer)
                self.assertEqual(drain(p.server), b'')
                self.assertTrue(any('owner_answer_attempt' in (x.get('detail') or {})
                                    for x in p.relay.capture.records))
                with self.assertRaises(r.Hold): p.relay.step()
                self.assertEqual(len(calls), 1)

    def test_arm_and_exact_authorization_are_mutually_exclusive(self):
        answer = {'id': 3, 'method': 'turn/steer', 'params': {}}
        for first in ('exact', 'armed'):
            p = self.pair(); p.upgrade(); p.initial()
            if first == 'exact':
                p.relay.authorize_answer('async', answer)
                with self.assertRaisesRegex(r.Hold, 'unavailable'):
                    p.relay.arm_answer('async', lambda value, metadata: True, self.decision_ref())
            else:
                p.relay.arm_answer('async', lambda value, metadata: True, self.decision_ref())
                with self.assertRaisesRegex(r.Hold, 'unavailable'):
                    p.relay.authorize_answer('async', answer)

    def test_arm_rejects_invalid_closed_reference_route_callback_and_phase(self):
        refs = ['a' * 64, {}, dict(self.decision_ref(), extra=True),
                {'path': 'relative', 'sha256': 'a' * 64},
                {'path': '/a/../b', 'sha256': 'a' * 64},
                {'path': '/a//b', 'sha256': 'a' * 64},
                {'path': '/a/', 'sha256': 'a' * 64},
                {'path': '//alias/a', 'sha256': 'a' * 64},
                {'path': '/a', 'sha256': 'A' * 64}]
        for ref in refs:
            p = self.pair(); p.upgrade(); p.initial()
            with self.assertRaisesRegex(r.Hold, 'decision reference'):
                p.relay.arm_answer('async', lambda value, metadata: True, ref)
        for route, matcher in (('unknown', lambda value, metadata: True), ('async', {})):
            p = self.pair(); p.upgrade(); p.initial()
            with self.assertRaisesRegex(r.Hold, 'matcher'):
                p.relay.arm_answer(route, matcher, self.decision_ref())
        p = self.pair(); p.upgrade()
        with self.assertRaisesRegex(r.Hold, 'unavailable'):
            p.relay.arm_answer('async', lambda value, metadata: True, self.decision_ref())

    def test_extensions_bad_accept_and_incomplete_upgrade_rejected(self):
        p = self.pair()
        p.client.sendall(REQUEST.replace(b'\r\n\r\n', b'\r\nSec-WebSocket-Extensions: permessage-deflate\r\n\r\n'))
        with self.assertRaisesRegex(r.Hold, 'negotiation'): p.relay.step()
        self.assertEqual(drain(p.server), b'')
        p = self.pair(); p.client.sendall(REQUEST); p.relay.step(); drain(p.server)
        p.server.sendall(RESPONSE.replace(ACCEPT, b'invalid'))
        with self.assertRaisesRegex(r.Hold, 'HTTP response'): p.relay.step()
        self.assertEqual(drain(p.client), b'')


if __name__ == '__main__':
    unittest.main()
