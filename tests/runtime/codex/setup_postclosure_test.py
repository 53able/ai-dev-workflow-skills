"""Fresh synthetics/mock bytes only; never execute consumed setup fixtures."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import setup_postclosure as s


def encoded(value):
    return (json.dumps(value, ensure_ascii=False) + '\n').encode()


def state(value='initial'):
    return dict(records=[dict(path='.', kind='directory', mode=493, dev=1, ino=2,
                              nlink=2), dict(path='settings', kind='file', mode=420,
                              dev=1, ino=3, nlink=1, sha256=s.digest(value.encode()),
                              size=len(value))], grants={'git': False})


def receipt(**overrides):
    return dict(command=s.EXECUTED_COMMAND, status='completed', exit_code=0,
                earlier_import_cache_writes=False, other_cache_writes=False, **overrides)


class GateTest(unittest.TestCase):
    def gate(self, branch='N7-B-default'):
        g = s.TurnGate(branch, frozenset())
        g.open_context('fresh-thread-1')
        return g

    def dispatch(self, g, body, decision=None, now=None):
        if now is None:
            now = g.last_time + 1
        p = g.prepare(body, decision)
        g.begin(p, now)
        g.delivered(now + 1)
        return p

    def finish(self, g, output=b'actual output', questions=(), **kwargs):
        g.complete(g.last_time + 1, 'turn-' + str(len(g.attempts)), output, questions,
                   **kwargs)

    def duplicate_premise(self, g):
        body = b'Technical execution premise: execute ' + s.EXECUTED_COMMAND.encode()
        d = s.root_decision('premise', body, None)
        self.dispatch(g, body, d)
        self.finish(g, before=state(), after=state(), configured_command=s.CONFIGURED_COMMAND)

    def duplicate_initial(self, g, question=False):
        self.duplicate_premise(g)
        self.dispatch(g, s.SETUP_INPUT)
        self.finish(g, output=b'Actual question?' if question else b'consolidated',
                    questions=(b'Actual question?',) if question else (),
                    before=state(), after=state('consolidated'),
                    configured_command=s.CONFIGURED_COMMAND,
                    receipt=None if question else receipt())

    def duplicate_ack(self, g):
        g.close_context()
        g.open_context('fresh-thread-2')
        body = b'I acknowledge the exact actual content.'
        self.dispatch(g, body, s.root_decision('content-ack', body, g.predecessor()))
        self.finish(g, before=state('consolidated'), after=state('consolidated'),
                    configured_command=s.CONFIGURED_COMMAND)

    def test_original_input_and_exact_closed_funding(self):
        self.assertEqual(hashlib.sha256(s.SETUP_INPUT).hexdigest(), s.SETUP_SHA256)
        self.assertEqual(len(s.ROWS), 9)
        self.assertEqual(len(set(s.ROWS.values())), 9)
        for alias in ['N7-C-default', 'n7-b-default', 'Duplicate-B-default', 'copy']:
            with self.assertRaises(s.Hold):
                s.TurnGate(alias, frozenset())
        with self.assertRaises(s.Hold):
            s.claim_key('N7-B/default/first-v2')

    def test_invalid_active_clock_or_failure_stops_without_recovery(self):
        cases = [('complete', 9), ('complete', float('nan')),
                 ('complete', 10 ** 400), ('delivered', 9),
                 ('delivered', 190), ('fail', 12)]
        for action, now in cases:
            with self.subTest(action=action, now=now):
                g = self.gate(); self.dispatch(g, s.SETUP_INPUT, now=10)
                with self.assertRaises(s.Hold):
                    if action == 'complete':
                        g.complete(now, 'turn-1', b'Actual question?', (b'Actual question?',))
                    elif action == 'delivered':
                        g.delivered(now)
                    else:
                        g.fail(12, '')
                self.assertEqual(g.phase, 'stopped')
                self.assertIsNone(g.active)
                self.assertEqual(g.attempts[0]['status'], 'UNKNOWN')
                with self.assertRaises(s.Hold):
                    g.complete(13, 'turn-1', b'Actual question?', (b'Actual question?',))
                self.assertEqual(len(g.attempts), 1)

    def test_n7_two_exact_contexts_four_turns_and_next_question(self):
        total = []
        for branch in ('N7-B-default', 'N7-B-copy'):
            g = self.gate(branch)
            self.dispatch(g, s.SETUP_INPUT)
            self.finish(g, b'Please decide first?', (b'Please decide first?',))
            body = b'Root actual first decision.'
            d = s.root_decision('answer', body, g.predecessor())
            self.dispatch(g, body, d)
            self.finish(g, b'Please decide next?', (b'Please decide next?',))
            g.close_context()
            a = g.accounting()
            self.assertEqual(a['phase'], 'done')
            self.assertEqual(a['max_model_seconds'], 360)
            self.assertFalse(a['runtime_PASS'])
            self.assertEqual(a['actual_charged_turns'], 2)
            with self.assertRaises(s.Hold):
                g.prepare(body, d)
            total.append(a)
        self.assertEqual(sum(a['contexts_started'] for a in total), 2)
        self.assertEqual(sum(a['actual_charged_turns'] for a in total), 4)

    def test_no_prewritten_or_bundled_answer(self):
        g = self.gate()
        d = s.root_decision('answer', b'premature', dict(row='invented', thread_id='x',
            turn_id='x', output_sha256='x', question_sha256='x'))
        with self.assertRaises(s.Hold):
            g.prepare(b'premature', d)
        self.dispatch(g, s.SETUP_INPUT)
        with self.assertRaises(s.Hold):
            self.finish(g, b'one? two?', (b'one?', b'two?'))
        self.assertEqual(g.phase, 'stopped')
        self.assertEqual(g.accounting()['actual_charged_turns'], 1)

    def test_answer_bound_to_actual_predecessor_and_actual_bytes(self):
        g = self.gate()
        self.dispatch(g, s.SETUP_INPUT)
        self.finish(g, b'observed question?', (b'question?',))
        d = s.root_decision('answer', b'actual decision', g.predecessor())
        d['predecessor']['turn_id'] = 'wrong-turn'
        with self.assertRaises(s.Hold):
            g.prepare(b'actual decision', d)
        with self.assertRaises(s.Hold):
            g.prepare(b'changed', s.root_decision('answer', b'actual decision', g.predecessor()))

    def test_question_must_be_observed_and_healthy_completion(self):
        for questions in [(), (b'never observed?',)]:
            g = self.gate()
            self.dispatch(g, s.SETUP_INPUT)
            with self.assertRaises(s.Hold):
                self.finish(g, b'actual output', questions)
            self.assertEqual(g.phase, 'stopped')

    def test_per_turn_180_not_context_180(self):
        g = self.gate()
        self.dispatch(g, s.SETUP_INPUT, now=1)
        g.complete(180, 'turn1', b'first?', (b'first?',))
        d = s.root_decision('answer', b'decision', g.predecessor())
        self.dispatch(g, b'decision', d, now=181)
        g.complete(360, 'turn2', b'next?', (b'next?',))
        self.assertEqual(g.phase, 'done')
        self.assertEqual([a['deadline'] for a in g.attempts], [181, 361])

    def test_partial_unknown_and_failure_are_charged_without_retry(self):
        g = self.gate()
        p = g.prepare(s.SETUP_INPUT)
        g.begin(p, 1)
        with self.assertRaises(s.Hold):
            g.complete(2, 'turn1', b'question?', (b'question?',))
        self.assertEqual(g.attempts[0]['delivery'], 'UNKNOWN')
        self.assertEqual(g.accounting()['actual_charged_turns'], 1)
        self.assertEqual(g.phase, 'stopped')
        with self.assertRaises(s.Hold):
            g.prepare(s.SETUP_INPUT)

    def test_expired_turn_stops_and_claims_stable(self):
        g = self.gate()
        self.dispatch(g, s.SETUP_INPUT, now=1)
        with self.assertRaises(s.Hold):
            g.complete(181, 'turn1', b'question?', (b'question?',))
        key = s.claim_key('N7-B/default/first')
        g2 = s.TurnGate('N7-B-default', frozenset([key]))
        g2.open_context('new-output-new-source-new-thread')
        with self.assertRaises(s.Hold):
            g2.prepare(s.SETUP_INPUT)
        self.assertEqual(g.accounting()['actual_charged_turns'], 1)
        self.assertEqual(g2.accounting()['actual_charged_turns'], 0)

    def test_duplicate_four_turn_path_optional_held_no_refund(self):
        g = self.gate('Duplicate-B-copy')
        self.duplicate_initial(g)
        self.duplicate_ack(g)
        self.dispatch(g, s.SETUP_INPUT)
        self.finish(g, before=state('consolidated'), after=state('consolidated'),
                    configured_command=s.CONFIGURED_COMMAND, receipt=receipt())
        g.close_context()
        a = g.accounting()
        self.assertEqual((a['phase'], a['contexts_started'], a['actual_charged_turns'],
                          a['remaining_held_slots'], a['max_model_seconds']),
                         ('done', 2, 4, 1, 900))
        self.assertNotIn('duplicate-B/optional-real-answer', [a['row'] for a in g.attempts])
        with self.assertRaises(s.Hold):
            g.open_context('repair')
        with self.assertRaises(s.Hold):
            g.prepare(b'use optional slot for repair')

    def test_duplicate_five_turn_real_answer_path(self):
        g = self.gate('Duplicate-B-copy')
        self.duplicate_initial(g, question=True)
        body = b'Actual Root judgment after observed question.'
        self.dispatch(g, body, s.root_decision('answer', body, g.predecessor()))
        self.finish(g, before=state('consolidated'), after=state('consolidated'),
                    configured_command=s.CONFIGURED_COMMAND, receipt=receipt())
        self.duplicate_ack(g)
        self.dispatch(g, s.SETUP_INPUT)
        self.finish(g, before=state('consolidated'), after=state('consolidated'),
                    configured_command=s.CONFIGURED_COMMAND, receipt=receipt())
        self.assertEqual(g.phase, 'done')
        self.assertEqual(g.accounting()['actual_charged_turns'], 5)
        self.assertEqual([a['donor'] for a in g.attempts], [s.ROWS[r] for r in g.rows])

    def test_duplicate_second_judgment_stops(self):
        g = self.gate('Duplicate-B-copy')
        self.duplicate_initial(g, question=True)
        d = s.root_decision('answer', b'actual decision', g.predecessor())
        self.dispatch(g, b'actual decision', d)
        with self.assertRaises(s.Hold):
            self.finish(g, b'second?', (b'second?',), before=state('consolidated'),
                        after=state('consolidated'), configured_command=s.CONFIGURED_COMMAND)
        self.assertEqual(g.phase, 'stopped')
        self.assertEqual(g.accounting()['actual_charged_turns'], 3)

    def test_duplicate_context_boundary_and_thread_reuse(self):
        g = self.gate('Duplicate-B-copy')
        self.duplicate_initial(g)
        with self.assertRaises(s.Hold):
            g.open_context('second-before-close')
        body = b'ack'
        with self.assertRaises(s.Hold):
            g.prepare(body, s.root_decision('content-ack', body, g.predecessor()))
        g.close_context()
        with self.assertRaises(s.Hold):
            g.open_context('fresh-thread-1')
        g.open_context('second')
        with self.assertRaises(s.Hold):
            g.open_context('third')

    def test_duplicate_ack_cannot_mutate_or_rebaseline(self):
        for before, after in [(state('consolidated'), state('new-cache')),
                              (state('v27-cache-baseline'), state('v27-cache-baseline'))]:
            g = self.gate('Duplicate-B-copy')
            self.duplicate_initial(g)
            g.close_context()
            g.open_context('second')
            body = b'ack actual content'
            self.dispatch(g, body, s.root_decision('content-ack', body, g.predecessor()))
            with self.assertRaises(s.Hold):
                self.finish(g, before=before, after=after, configured_command=s.CONFIGURED_COMMAND)
            self.assertEqual(g.phase, 'stopped')

    def test_duplicate_repeat_is_exact_input_and_fullstate(self):
        g = self.gate('Duplicate-B-copy')
        self.duplicate_initial(g)
        self.duplicate_ack(g)
        with self.assertRaises(s.Hold):
            g.prepare(s.SETUP_INPUT + b' ')
        self.dispatch(g, s.SETUP_INPUT)
        with self.assertRaises(s.Hold):
            self.finish(g, before=state('consolidated'), after=state('cache added'),
                        configured_command=s.CONFIGURED_COMMAND, receipt=receipt())
        self.assertEqual(g.phase, 'stopped')

    def test_receipt_rejects_prompt_wrong_command_flags_and_failed_execution(self):
        for key, value in [('command', s.CONFIGURED_COMMAND), ('command', s.EXECUTED_COMMAND + ' -E'),
                           ('status', 'planned'), ('exit_code', 1), ('exit_code', False),
                           ('earlier_import_cache_writes', True), ('other_cache_writes', True)]:
            r = receipt()
            r[key] = value
            with self.assertRaises(s.Hold):
                s.command_receipt(r)
        with self.assertRaises(s.Hold):
            s.command_receipt(dict(prompt=s.EXECUTED_COMMAND))

    def test_premise_must_be_separate_exact_command_and_unchanged_state(self):
        g = self.gate('Duplicate-B-copy')
        with self.assertRaises(s.Hold):
            g.prepare(s.SETUP_INPUT)
        d = s.root_decision('premise', b'Use another method', None)
        with self.assertRaises(s.Hold):
            g.prepare(d['body'], d)
        d = s.root_decision('premise', s.EXECUTED_COMMAND.encode(), None)
        self.dispatch(g, d['body'], d)
        with self.assertRaises(s.Hold):
            self.finish(g, before=state(), after=state('mutated'),
                        configured_command=s.CONFIGURED_COMMAND)

    def test_prepared_drift_and_strict_typed_ids(self):
        g = self.gate()
        p = g.prepare(s.SETUP_INPUT)
        p['donor'] = 'reserve'
        with self.assertRaises(s.Hold):
            g.begin(p, 1)
        self.assertEqual(g.accounting()['actual_charged_turns'], 0)
        with self.assertRaises(s.Hold):
            g.open_context(1)
        with self.assertRaises(s.Hold):
            s.typed_id(True)
        self.assertNotEqual(s.typed_id(1), s.typed_id('1'))


class SnapshotTest(unittest.TestCase):
    def test_fresh_full_snapshot_preserves_cache_link_directory_identity_mode_grants(self):
        with tempfile.TemporaryDirectory(prefix='setup-postclosure-own-') as tmp:
            root = Path(tmp).resolve()
            (root / '__pycache__').mkdir()
            (root / '__pycache__' / 'old.pyc').write_bytes(b'authentic preexisting cache')
            (root / 'config').write_bytes(s.CONFIGURED_COMMAND.encode())
            (root / 'dangling').symlink_to('absent')
            baseline = s.full_state(root, {'git': False})
            s.strict_equal(baseline, s.full_state(root, {'git': False}))
            self.assertFalse((root / 'absent').exists())
            self.assertEqual(len(baseline['records']), 5)
            for mutation in ['cache', 'mode', 'identity', 'link', 'directory', 'grant']:
                with self.subTest(mutation=mutation):
                    before = s.full_state(root, {'git': False})
                    if mutation == 'cache':
                        (root / '__pycache__' / 'new.pyc').write_bytes(b'new')
                    elif mutation == 'mode':
                        (root / 'config').chmod(0o600)
                    elif mutation == 'identity':
                        # Keep old inode alive while replacing with equal bytes.
                        (root / 'config').rename(root / 'old')
                        (root / 'config').write_bytes((root / 'old').read_bytes())
                    elif mutation == 'link':
                        (root / 'dangling').unlink()
                        (root / 'dangling').symlink_to('another-absent')
                    elif mutation == 'directory':
                        (root / 'extra').mkdir()
                    after = s.full_state(root, {'git': mutation == 'grant'})
                    with self.assertRaises(s.Hold):
                        s.strict_equal(before, after)


class WireTest(unittest.TestCase):
    def setup_request(self, request_id=1):
        g = s.TurnGate('N7-B-default', frozenset())
        g.open_context('thread1')
        p = g.prepare(s.SETUP_INPUT)
        request = dict(id=request_id, method='turn/start', params=dict(threadId='thread1',
                       input=[dict(type='text', text=s.SETUP_INPUT.decode())]))
        return p, request

    def complete_wire(self, wire, request_id=1, turn='turn1', thread='thread1'):
        for value in [dict(id=request_id, result=dict(turn=dict(id=turn))),
                      dict(method='item/completed', params=dict(threadId=thread, turnId=turn,
                           item=dict(type='agentMessage', phase='final_answer', text='actual question?'))),
                      dict(method='turn/completed', params=dict(threadId=thread,
                           turn=dict(id=turn, status='completed')))]:
            wire.feed('server', encoded(value))

    def test_original_bytes_offsets_partial_input_unknown_and_completed_turn(self):
        p, request = self.setup_request()
        wire = s.Wire()
        raw = b'  ' + encoded(request)
        wire.feed('client', raw[:23])
        self.assertEqual(wire.records, [])
        with self.assertRaises(s.Hold):
            wire.require_clean()
        wire.feed('client', raw[23:])
        binding = wire.require_turn_input(0, p)
        self.assertEqual(binding['wire_sha256'], s.digest(raw))
        self.assertEqual((binding['start'], binding['end']), (0, len(raw)))
        self.complete_wire(wire)
        observed = wire.completed_turn(0)
        self.assertEqual(observed['output'], b'actual question?')
        self.assertEqual(observed['turn_id'], 'turn1')
        wire.require_clean()
        self.assertEqual(bytes(wire.raw['client']), raw)

    def test_earlier_failed_or_duplicate_terminal_is_not_ignored(self):
        for status in ('failed', 'completed'):
            with self.subTest(status=status):
                _, request = self.setup_request(); wire = s.Wire()
                wire.feed('client', encoded(request))
                wire.feed('server', encoded(dict(method='turn/completed', params=dict(
                    threadId='thread1', turn=dict(id='turn1', status=status)))))
                self.complete_wire(wire)
                with self.assertRaises(s.Hold):
                    wire.completed_turn(0)

    def test_completed_events_before_rpc_reply_are_still_correlated(self):
        _, request = self.setup_request(); wire = s.Wire()
        wire.feed('client', encoded(request))
        wire.feed('server', encoded(dict(method='item/completed', params=dict(
            threadId='thread1', turnId='turn1', item=dict(
                type='agentMessage', phase='final_answer', text='Actual question?')))))
        wire.feed('server', encoded(dict(method='turn/completed', params=dict(
            threadId='thread1', turn=dict(id='turn1', status='completed')))))
        wire.feed('server', encoded(dict(id=1, result=dict(turn=dict(id='turn1')))))
        self.assertEqual(wire.completed_turn(0)['output'], b'Actual question?')

    def test_typed_rpc_ids_and_foreign_responses(self):
        for bad in [True, None, '1']:
            wire = s.Wire()
            _, request = self.setup_request()
            wire.feed('client', encoded(request))
            with self.assertRaises(s.Hold):
                wire.feed('server', encoded(dict(id=bad, result={})))
        wire = s.Wire()
        for request_id in (1, '1'):
            _, request = self.setup_request(request_id)
            wire.feed('client', encoded(request))
        self.assertEqual(len(wire.requests), 2)

    def test_wrong_thread_input_and_duplicate_id(self):
        p, request = self.setup_request()
        request['params']['input'][0]['text'] += ' '
        wire = s.Wire()
        wire.feed('client', encoded(request))
        with self.assertRaises(s.Hold):
            wire.require_turn_input(0, p)
        with self.assertRaises(s.Hold):
            wire.feed('client', encoded(request))

    def test_closed_json_nonfinite_duplicate_fields_and_bounds(self):
        for raw in [b'{"id": 1, "id": 2}\n', b'{"id": NaN}\n', b'[]\n', b'\xff\n',
                    b'{"id": 1, "result": {}, "error": {}}\n']:
            with self.subTest(raw=raw), self.assertRaises(s.Hold):
                s.Wire().feed('server', raw)
        with self.assertRaises(s.Hold):
            s.Wire().feed('client', b'x' * 1048577)

    def test_failed_missing_foreign_terminal_rejected(self):
        for thread, turn in [('foreign', 'turn1'), ('thread1', 1)]:
            wire = s.Wire()
            _, request = self.setup_request()
            wire.feed('client', encoded(request))
            self.complete_wire(wire, thread=thread, turn=turn)
            with self.assertRaises(s.Hold):
                wire.completed_turn(0)
        wire = s.Wire()
        _, request = self.setup_request()
        wire.feed('client', encoded(request))
        with self.assertRaises(s.Hold):
            wire.completed_turn(0)

    def test_wire_failure_sticky_and_partial_tail_prevents_completion(self):
        wire = s.Wire()
        with self.assertRaises(s.Hold):
            wire.feed('server', b'invalid\n')
        with self.assertRaises(s.Hold):
            wire.feed('server', b'')
        with self.assertRaises(s.Hold):
            wire.require_clean()
        wire = s.Wire()
        _, request = self.setup_request()
        wire.feed('client', encoded(request))
        self.complete_wire(wire)
        wire.feed('server', b'{"partial":')
        with self.assertRaises(s.Hold):
            wire.completed_turn(0)

    def test_turn_envelope_closed_and_exact_unicode_answer_bytes(self):
        p, request = self.setup_request()
        p['body'] = '実際の回答'.encode()
        request['params']['input'][0]['text'] = p['body'].decode()
        wire = s.Wire()
        raw = encoded(request)
        for byte in raw:
            wire.feed('client', bytes([byte]))
        self.assertEqual(wire.require_turn_input(0, p)['input_sha256'], s.digest(p['body']))
        request['extra_authority'] = True
        request['id'] = 2
        wire.feed('client', encoded(request))
        with self.assertRaises(s.Hold):
            wire.require_turn_input(1, p)

    def test_multiple_turn_receipts_remain_indexed_to_own_wire(self):
        wire = s.Wire()
        indexes = []
        for request_id in (1, 2):
            _, request = self.setup_request(request_id)
            indexes.append(len(wire.records))
            wire.feed('client', encoded(request))
            self.complete_wire(wire, request_id=request_id, turn='turn' + str(request_id))
        self.assertEqual([wire.completed_turn(i)['turn_id'] for i in indexes], ['turn1', 'turn2'])


if __name__ == '__main__':
    unittest.main()
