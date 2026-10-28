"""Zero-runtime source-derived checks, never native UI/delivery evidence.

Renderer Unicode/quoted-answer case is transcribed from pinned official
context-fragments/src/answered_question_tests.rs::
question_context_is_bounded_and_keeps_unicode_boundaries. Dispatch examples
follow actual native AppServerSession constructors, not synthetic caller roles.
"""
import copy
import json
import unittest

import question_native_schema as native


def message():
    questions = [
        {'title': 'é\n' * 1000, 'options': ['Yes', 'A "quoted" answer\nwith a second line']},
        {'title': 'Second question', 'options': ['One', 'Two']},
        {'title': 'Third question', 'options': None}]
    # Pinned RequestUserInputAsyncHandler constructs this ordinary display text.
    text = '\n\n'.join('\n'.join([q['title']] +
        ['- ' + option for option in (q['options'] or [])]) for q in questions)
    return {'type': 'agentMessage', 'id': 'message', 'text': text,
            'phase': 'final_answer', 'memoryCitation': None, 'delivery': 'async',
            'questions': questions}


def steer():
    text = native.render_answered_question(native.question_id('message', 0),
                                          message()['questions'][0]['title'], 'Yes')
    return {'id': 17, 'method': 'turn/steer', 'params': {
        'threadId': 'thread', 'expectedTurnId': 'turn',
        'clientUserMessageId': 'native-client-message',
        'responsesapiClientMetadata': None, 'responsesapiClientMetadataPatch': None,
        'additionalContext': None,
        'input': [{'type': 'text', 'text': text, 'text_elements': []}]}}


def start():
    envelope = steer()
    envelope['method'] = 'turn/start'
    old = envelope['params']
    params = dict.fromkeys(native.START_FIELDS)
    params.update({key: old[key] for key in ('threadId', 'clientUserMessageId', 'input')})
    params.update(turnTrigger='user', cwd='/fixture', runtimeWorkspaceRoots=['/fixture'],
                  model='pinned-model', approvalPolicy='never', approvalsReviewer='user',
                  sandboxPolicy={'type': 'workspaceWrite', 'writableRoots': ['/fixture']},
                  effort='high', summary='auto', collaborationMode={'mode': 'default',
                  'settings': {'model': 'pinned-model', 'reasoning_effort': 'high',
                               'developer_instructions': None}})
    envelope['params'] = params
    return envelope


class NativeSchemaTests(unittest.TestCase):
    def check(self, envelope=None, **updates):
        args = dict(item=message(), index=0,
                    decision={'questionId': native.question_id('message', 0),
                              'kind': 'option', 'answer': 'Yes'},
                    thread_id='thread', active_turn_id='turn',
                    commit=native.SOURCE_COMMIT, version=native.SOURCE_VERSION)
        args.update(updates)
        return native.validate_answer_dispatch(steer() if envelope is None else envelope, **args)

    def test_primary_renderer_unicode_quoted_multiline_example(self):
        identity = '["request_user_input_async","message",1]'
        answer = 'A "quoted" answer\nwith a second line'
        text = native.render_answered_question(identity, 'é\n' * 1000, answer)
        self.assertTrue(text.startswith(native.OPEN + '\n'))
        self.assertTrue(text.endswith('\n' + native.CLOSE))
        data = json.loads(text[len(native.OPEN):-len(native.CLOSE)])
        self.assertEqual(data, [{'answer': answer, 'question': ('é\n' * 1000)
                         .encode()[:512].decode(errors='ignore').replace('\n', ' '),
                         'questionItemId': identity}])
        self.assertEqual(text, native.OPEN + '\n' +
            '[{"answer":"A \\"quoted\\" answer\\nwith a second line","question":' +
            json.dumps(data[0]['question'], ensure_ascii=False) +
            ',"questionItemId":"[\\"request_user_input_async\\",\\"message\\",1]"}]\n' + native.CLOSE)

    def test_id_escaping_and_utf8(self):
        self.assertEqual(native.question_id('日本"\\\n', 2),
                         '["request_user_input_async","日本\\"\\\\\\n",2]')
        self.assertEqual(json.loads(native.question_id('日本"\\\n', 2)),
                         ['request_user_input_async', '日本"\\\n', 2])

    def test_renderer_floor_boundary_and_legacy_identity(self):
        text = native.render_answered_question('q', 'a' * 511 + 'é\rnext', 'ok')
        self.assertEqual(json.loads(text[len(native.OPEN):-len(native.CLOSE)])[0]['question'], 'a' * 511)
        self.assertEqual(native.render_answered_question('é' * 257, 'a\r\nb', 'ok'), '> a  b\n\nok')

    def test_exact_native_steer_and_inert_input(self):
        value = steer()
        before = copy.deepcopy(value)
        self.assertTrue(self.check(value))
        self.assertEqual(value, before)

    def test_actual_start_fields_and_service_tier_presence(self):
        for tier in ((), (None,), ('fast',)):
            value = start()
            if tier:
                value['params']['serviceTier'] = tier[0]
            settings = {k: v for k, v in value['params'].items()
                        if k not in ('input', 'clientUserMessageId')}
            self.assertTrue(self.check(value, active_turn_id=None, start_settings=settings))
            value['params']['model'] = 'changed'
            with self.assertRaisesRegex(native.UnsupportedNativeShape, 'settings changed'):
                self.check(value, active_turn_id=None, start_settings=settings)

    def test_native_optional_and_free_text_paths(self):
        item = message()
        item['questions'][2].pop('options')
        decision = {'questionId': native.question_id('message', 2), 'kind': 'freeText',
                    'answer': '  自由な "回答"\nnext  '}
        value = steer()
        value['params']['input'][0]['text'] = native.render_answered_question(
            decision['questionId'], item['questions'][2]['title'], decision['answer'].strip())
        self.assertTrue(self.check(value, item=item, index=2, decision=decision))
        self.assertEqual(native.native_trim('\x1canswer\x1c'), '\x1canswer\x1c')

    def test_typed_rpc_and_client_ids(self):
        self.assertTrue(self.check(seen_request_ids=('17',)))
        for bad in (True, None, 1.1, 1 << 63):
            value = steer(); value['id'] = bad
            with self.subTest(bad=bad), self.assertRaises(native.UnsupportedNativeShape):
                self.check(value)
        for kwargs in ({'seen_request_ids': (17,)},
                       {'seen_client_message_ids': ('native-client-message',)}):
            with self.assertRaises(native.UnsupportedNativeShape):
                self.check(**kwargs)

    def test_wrong_question_extra_answer_and_wrong_turn_rejected(self):
        for mutate in (
            lambda p: p.update(expectedTurnId='other'),
            lambda p: p.update(threadId='other'),
            lambda p: p['input'].append(copy.deepcopy(p['input'][0])),
            lambda p: p['input'][0].update(text=p['input'][0]['text'] + '\nextra answer'),
            lambda p: p.update(additionalContext={'hidden': 'context'}),
            lambda p: p['input'][0].update(text=p['input'][0]['text'].replace(
                '\\"message\\",0', '\\"message\\",1')),
        ):
            value = steer(); mutate(value['params'])
            with self.assertRaises(native.UnsupportedNativeShape):
                self.check(value)
        with self.assertRaisesRegex(native.UnsupportedNativeShape, 'wrong question'):
            self.check(decision={'questionId': native.question_id('message', 1),
                                 'kind': 'option', 'answer': 'Yes'})

    def test_sync_rpc_is_distinct_and_never_answer_dispatch(self):
        value = {'id': 17, 'method': 'item/tool/requestUserInput', 'params': {}}
        self.assertEqual(native.classify_route(value), 'sync-request-user-input')
        with self.assertRaisesRegex(native.UnsupportedNativeShape, 'sync RPC'):
            self.check(value)
        with self.assertRaises(native.UnsupportedNativeShape):
            self.check({'id': 17, 'result': {'answers': {'q': {'answers': ['Yes']}}}})

    def test_version_drift_and_unsupported_shapes(self):
        for kwargs in ({'version': '0.165.0'}, {'commit': '0' * 40}):
            with self.assertRaisesRegex(native.UnsupportedNativeShape, 'drift'):
                self.check(**kwargs)
        for mutate in (
            lambda v: v.update(jsonrpc='2.0'),
            lambda v: v['params'].update(extra='unknown'),
            lambda v: v['params']['input'][0].update(textElements=[]),
            lambda v: v['params']['input'][0].update(type='input_text'),
        ):
            value = steer(); mutate(value)
            with self.assertRaises(native.UnsupportedNativeShape):
                self.check(value)

    def test_c_batch_profile_without_fabrication(self):
        self.assertEqual(len(native.async_questions(message(), outstanding_count=2)), 3)
        for count in (3, True, -1):
            with self.assertRaises(native.UnsupportedNativeShape):
                native.async_questions(message(), outstanding_count=count)
        for count in (0, 1, 2, 4, 5):
            value = message(); value['questions'] = (value['questions'] * 2)[:count]
            with self.assertRaises(native.UnsupportedNativeShape):
                native.async_questions(value)
        value = message(); value['questions'][0]['id'] = 'invented'
        with self.assertRaises(native.UnsupportedNativeShape):
            native.async_questions(value)

    def test_native_option_bounds_take_before_filter(self):
        value = message(); options = ['é' * 257] + ['Yes'] * 31 + ['excluded']
        value['questions'][0]['options'] = options
        self.assertEqual(len(native.async_questions(value)[0]['options']), 31)
        with self.assertRaises(native.UnsupportedNativeShape):
            self.check(item=value, decision={'questionId': native.question_id('message', 0),
                                           'kind': 'option', 'answer': 'excluded'})

    def test_empty_publication_and_legacy_identity_cannot_establish_c(self):
        for title, options in ((' \n ', None), ('title', []), ('title', [' \n '])):
            value = message(); value['questions'][0] = {'title': title, 'options': options}
            with self.assertRaises(native.UnsupportedNativeShape):
                native.async_questions(value)
        value = message(); value['id'] = 'é' * 257
        decision = {'questionId': native.question_id(value['id'], 0),
                    'kind': 'option', 'answer': 'Yes'}
        with self.assertRaisesRegex(native.UnsupportedNativeShape, 'legacy'):
            self.check(item=value, decision=decision)

    def test_text_elements_use_utf8_byte_ranges_and_remain_explicit(self):
        element = {'byteRange': {'start': 0, 'end': 3}, 'placeholder': '猫'}
        native.validate_text_elements('猫x', [element])
        for end in (1, True, 5):
            bad = copy.deepcopy(element); bad['byteRange']['end'] = end
            with self.assertRaises(native.UnsupportedNativeShape):
                native.validate_text_elements('猫x', [bad])
        value = steer(); value['params']['input'][0]['text_elements'] = [
            {'byteRange': {'start': 0, 'end': 1}, 'placeholder': None}]
        with self.assertRaisesRegex(native.UnsupportedNativeShape, 'unexpected async'):
            self.check(value)
