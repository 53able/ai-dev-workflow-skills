"""Synthetic decoded-envelope tests only; no native/model/UI evidence."""
import unittest

import question_contract as c
import question_live_events as live
import question_native_schema as n
from question_operator import NativeGuard


C = {'generation': 'g', 'direction': 'client_to_server'}
S = {'generation': 'g', 'direction': 'server_to_client'}


def turn(status='inProgress', items=None):
    return dict(id='t', rootTurnId=None, items=items or [], status=status,
                error=None, startedAt=1, completedAt=None, durationMs=None,
                itemsView='full')


def notify(method, **params):
    return {'method': method, 'params': dict(threadId='thread', **params)}


def agent(ident='q', **extra):
    return dict(type='agentMessage', id=ident, text='Questions', delivery='async',
                phase='final_answer', memoryCitation=None,
                questions=[{'title': title, 'options': ['Yes', 'No']} for title in ('A', 'B', 'C')], **extra)


class LifecycleTests(unittest.TestCase):
    def make(self):
        guard = NativeGuard('g', [{'method': 'thread/start', 'params': {}, 'request': True}],
                            {'threadId': 'thread', 'input': [{'type': 'text', 'text': 'task', 'text_elements': []}]})
        guard({'id': 0, 'method': 'thread/start', 'params': {}}, C)
        obs = live.LiveEvents(guard, commit=n.SOURCE_COMMIT, version=n.SOURCE_VERSION)
        first = {'id': 1, 'method': 'turn/start', 'params': dict(guard.first_params, clientUserMessageId='first')}
        obs.client_guard(first, C)
        return obs

    def started(self):
        obs = self.make()
        obs.server_message(notify('turn/started', turn=turn()), S)
        obs.server_message({'id': 1, 'result': {'turn': turn()}}, S)
        return obs

    def questions(self):
        obs = self.started()
        self.item(obs, agent())
        return obs

    def item(self, obs, item, method='item/completed', **extra):
        key = 'completedAtMs' if method == 'item/completed' else 'startedAtMs'
        obs.server_message(notify(method, turnId='t', item=item, **{key: 10}, **extra), S)

    def answer(self, obs):
        item = obs.items['q']['completed']
        decision = {'questionId': n.question_id('q', 0), 'kind': 'option', 'answer': 'Yes'}
        matcher = obs.answer_matcher(item_id='q', index=0, decision=decision)
        value = {'id': '2', 'method': 'turn/steer', 'params': {
            'threadId': 'thread', 'clientUserMessageId': 'answer', 'expectedTurnId': 't',
            'input': [{'type': 'text', 'text': n.render_answered_question(decision['questionId'], 'A', 'Yes'), 'text_elements': []}],
            'responsesapiClientMetadata': None, 'responsesapiClientMetadataPatch': None,
            'additionalContext': None}}
        obs.client_guard(value, C)
        matcher(value, C)
        return value, matcher

    def test_one_pending_start_cannot_create_a_second_turn(self):
        obs = self.make()
        obs.server_message(notify('turn/started', turn=turn()), S)
        obs.server_message(notify('turn/completed', turn=turn('completed')), S)
        other = dict(turn(), id='unrequested')
        with self.assertRaises(c.Hold):
            obs.server_message(notify('turn/started', turn=other), S)
        self.assertTrue(obs.failed)

    def test_user_item_cannot_switch_from_initial_input_to_answer(self):
        obs = self.questions(); value, _ = self.answer(obs)
        first_input = obs.requests[('int', 1)]['wire']['params']['input']
        self.item(obs, dict(type='userMessage', id='u', clientId='first', content=first_input),
                  method='item/started')
        with self.assertRaises(c.Hold):
            self.item(obs, dict(type='userMessage', id='u', clientId='answer',
                                content=value['params']['input']))
        self.assertTrue(obs.failed)
        self.assertIsNone(obs.answered_question)

    def test_state_from_response_and_notification(self):
        obs = self.started()
        self.assertEqual(obs.guard.active_turn, 't')
        self.assertEqual(obs.accepted, [('int', 1)])
        obs.server_message(notify('turn/completed', turn=turn('completed')), S)
        self.assertIsNone(obs.guard.active_turn)
        self.assertFalse(obs.guard.terminal)

    def test_questions_final_dedup_and_acceptance_separate(self):
        obs = self.questions()
        self.item(obs, agent())
        self.assertEqual(obs.finals, ['q'])
        value, _ = self.answer(obs)
        self.item(obs, dict(type='userMessage', id='u', clientId='answer', content=value['params']['input']))
        self.assertIsNone(obs.answered_question)
        obs.server_message({'id': '2', 'result': {'turnId': 't'}}, S)
        self.assertEqual(obs.answered_question, n.question_id('q', 0))
        self.assertEqual(len(obs.questions['q']), 3)  # pending UI not inferred

    def test_rpc_success_without_user_item_is_not_answered(self):
        obs = self.questions(); self.answer(obs)
        obs.server_message({'id': '2', 'result': {'turnId': 't'}}, S)
        self.assertIsNone(obs.answered_question)

    def test_terminal_before_steer_result_holds_no_resurrection(self):
        obs = self.questions(); self.answer(obs)
        obs.server_message(notify('turn/completed', turn=turn('completed', [agent()])), S)
        with self.assertRaises(c.Hold):
            obs.server_message({'id': '2', 'result': {'turnId': 't'}}, S)
        self.assertIsNone(obs.guard.active_turn)
        self.assertTrue(obs.guard.terminal)

    def test_dispatch_error_records_race_and_stops(self):
        obs = self.questions(); self.answer(obs)
        with self.assertRaises(c.Hold):
            obs.server_message({'id': '2', 'error': {'code': -1, 'message': 'race'}}, S)
        self.assertEqual(obs.races, [('str', '2')])
        self.assertTrue(obs.failed)

    def test_wrong_generation_thread_turn_and_unknown(self):
        for value, metadata in [
            (notify('turn/completed', turn=turn('completed')), dict(S, generation='other')),
            ({'method': 'turn/started', 'params': {'threadId': 'other', 'turn': turn()}}, S),
            (notify('item/completed', turnId='other', item=agent(), completedAtMs=10), S),
            (notify('turn/queued', turnId='t'), S),
        ]:
            with self.subTest(value=value):
                obs = self.started()
                with self.assertRaises(ValueError): obs.server_message(value, metadata)
                self.assertTrue(obs.failed)

    def test_duplicate_response_and_typed_id(self):
        for response in ({'id': 1, 'result': {'turn': turn()}},
                         {'id': '1', 'result': {'turn': turn()}}):
            obs = self.started()
            with self.assertRaises(c.Hold): obs.server_message(response, S)

    def test_contradictory_duplicate_item_and_malformed_timestamp(self):
        obs = self.questions()
        changed = agent(); changed['text'] = 'changed'
        with self.assertRaises(c.Hold): self.item(obs, changed)
        obs = self.started()
        with self.assertRaises(c.Hold):
            obs.server_message(notify('item/completed', turnId='t', item=agent(), completedAtMs=True), S)

    def test_matcher_one_use_and_wrong_fragment(self):
        obs = self.questions(); value, matcher = self.answer(obs)
        with self.assertRaises(c.Hold): matcher(value, C)
        obs = self.questions()
        decision = {'questionId': n.question_id('q', 0), 'kind': 'option', 'answer': 'Yes'}
        matcher = obs.answer_matcher(item_id='q', index=0, decision=decision)
        with self.assertRaises(c.Hold):
            obs.answer_matcher(item_id='q', index=0, decision=decision)

    def test_response_before_start_notification_and_duplicate_start(self):
        obs = self.make()
        obs.server_message({'id': 1, 'result': {'turn': turn()}}, S)
        obs.server_message(notify('turn/started', turn=turn()), S)
        with self.assertRaises(c.Hold):
            obs.server_message(notify('turn/started', turn=turn()), S)

    def test_answer_changed_fragment_is_rejected_after_real_attempt(self):
        obs = self.questions()
        decision = {'questionId': n.question_id('q', 0), 'kind': 'option', 'answer': 'Yes'}
        matcher = obs.answer_matcher(item_id='q', index=0, decision=decision)
        value = {'id': 2, 'method': 'turn/steer', 'params': {
            'threadId': 'thread', 'clientUserMessageId': 'answer', 'expectedTurnId': 't',
            'input': [{'type': 'text', 'text': 'generic extra USER', 'text_elements': []}],
            'responsesapiClientMetadata': None, 'responsesapiClientMetadataPatch': None,
            'additionalContext': None}}
        obs.client_guard(value, C)
        with self.assertRaises(n.UnsupportedNativeShape): matcher(value, C)
        self.assertTrue(obs.failed)
        self.assertEqual(len(obs.guard.attempts), 2)

    def test_start_while_active_and_wrong_accepted_user_content_hold(self):
        obs = self.started()
        value = {'id': 2, 'method': 'turn/start', 'params': {
            'threadId': 'thread', 'clientUserMessageId': 'queued', 'input': []}}
        with self.assertRaises(c.Hold): obs.client_guard(value, C)
        self.assertTrue(obs.failed)
        obs = self.started()
        with self.assertRaises(c.Hold):
            self.item(obs, {'type': 'userMessage', 'id': 'u', 'clientId': 'first', 'content': []})

    def test_unknown_turn_and_item_shape_hold(self):
        obs = self.make(); bad = turn(); bad['queue'] = True
        with self.assertRaises(ValueError): obs.server_message({'id': 1, 'result': {'turn': bad}}, S)
        obs = self.started()
        with self.assertRaises(c.Hold): self.item(obs, {'id': 'x', 'type': 'mystery'})

    def test_item_kind_change_and_arm_completion_race_hold(self):
        obs = self.started()
        self.item(obs, agent(), method='item/started')
        first_input = obs.requests[('int', 1)]['wire']['params']['input']
        with self.assertRaises(c.Hold):
            self.item(obs, {'type': 'userMessage', 'id': 'q', 'clientId': 'first', 'content': first_input})
        obs = self.questions()
        decision = {'questionId': n.question_id('q', 0), 'kind': 'option', 'answer': 'Yes'}
        matcher = obs.answer_matcher(item_id='q', index=0, decision=decision)
        obs.server_message(notify('turn/completed', turn=turn('completed')), S)
        with self.assertRaises(c.Hold): matcher({'id': 2}, C)
        self.assertTrue(obs.failed)

    def test_events_bound_and_inert(self):
        obs = self.started(); obs.limit = len(obs.events)
        with self.assertRaises(c.Hold): self.item(obs, agent())
        self.assertFalse(obs.runtime_admitted)


if __name__ == '__main__': unittest.main()
