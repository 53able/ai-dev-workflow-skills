"""Inert Codex 0.164 native async-question adapter; no runtime admission.

Primary sources at SOURCE_COMMIT: tui/bottom_pane/async_questions/state.rs,
context-fragments/src/{answered_question,fragment}.rs, protocol/src/items.rs,
app-server-protocol/src/protocol/v2/{item,turn}.rs, and tui/app_server_session.rs.
Accepts decoded data only. Root authority, UI visibility, connection provenance,
one-use callback consumption, deadlines and delivery evidence belong to callers.
"""
import json

SOURCE_COMMIT = '6aaac694803004a63c6f393d153c96d22521a6b9'
SOURCE_VERSION = '0.164.0'
MAX_TEXT_CHARS = 1 << 20
OPEN = '<send_user_message_question_reply>'
CLOSE = '</send_user_message_question_reply>'
# Fields serialized by the pinned native AppServerSession, including nulls.
START_FIELDS = frozenset('threadId disabledPluginIds clientUserMessageId input '
    'turnTrigger parentTurnId rootTurnId toolOutput responsesapiClientMetadata '
    'responsesapiClientMetadataPatch additionalContext environments cwd '
    'runtimeWorkspaceRoots approvalPolicy approvalsReviewer sandboxPolicy '
    'permissions model serviceTierForTurn effort summary personality outputSchema '
    'collaborationMode multiAgentMode cyberAccessProgram'.split())
STEER_FIELDS = frozenset('threadId clientUserMessageId input '
    'responsesapiClientMetadata responsesapiClientMetadataPatch additionalContext '
    'expectedTurnId'.split())
START_NULLS = frozenset('disabledPluginIds parentTurnId rootTurnId toolOutput '
    'responsesapiClientMetadata responsesapiClientMetadataPatch additionalContext '
    'environments serviceTierForTurn personality multiAgentMode'.split())


class UnsupportedNativeShape(ValueError):
    """Source profile mismatch; stop without forwarding another input."""


def require(condition, reason):
    if not condition:
        raise UnsupportedNativeShape(reason)


def source_pin(commit, version):
    require(commit == SOURCE_COMMIT and version == SOURCE_VERSION,
            'native source/version drift')


def closed(value, required, optional=()):
    require(type(value) is dict and set(required) <= value.keys() and
            value.keys() <= set(required) | set(optional), 'unsupported fields')


def string(value, *, empty=False):
    require(type(value) is str and (empty or bool(value)), 'expected string')
    try:
        value.encode('utf-8')
    except UnicodeError as exc:
        raise UnsupportedNativeShape('invalid UTF-8 string') from exc
    return value


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                      sort_keys=True, allow_nan=False)


def rpc_identity(value):
    # JSON-RPC RequestId is an i64 or String; bool is never an integer ID.
    require(type(value) is str or
            (type(value) is int and -(1 << 63) <= value < 1 << 63),
            'invalid typed native request ID')
    if type(value) is str:
        string(value, empty=True)
    return type(value).__name__, value


def question_id(message_id, index):
    string(message_id)
    require(type(index) is int and 0 <= index < 5, 'question index outside C profile')
    return compact(['request_user_input_async', message_id, index])


def classify_route(envelope):
    require(type(envelope) is dict, 'expected envelope')
    method = envelope.get('method')
    if method == 'item/tool/requestUserInput':
        return 'sync-request-user-input'
    if method in ('turn/start', 'turn/steer'):
        return 'async-user-dispatch'
    if method in ('item/started', 'item/completed'):
        return 'turn-item'
    return 'unsupported'


def async_questions(item, *, outstanding_count=0):
    """Validate an actual app-server AgentMessage under bounded N7-C profile.

    Exactly three newly observed questions; at most five pending overall. The
    count is caller evidence, not a claim that the native renderer enforces it.
    Returns derived identities without changing the supplied item or options.
    """
    closed(item, ('type', 'id', 'text', 'delivery', 'questions'),
           ('phase', 'memoryCitation'))
    require(item['type'] == 'agentMessage' and item['delivery'] == 'async',
            'C requires async AgentMessage')
    string(item['id']); string(item['text'], empty=True)
    require(item.get('phase') in (None, 'commentary', 'final_answer'), 'unknown phase')
    require(item.get('memoryCitation') is None, 'unreviewed memory citation profile')
    questions = item['questions']
    require(type(questions) is list and len(questions) == 3,
            'C requires three actual questions')
    require(type(outstanding_count) is int and 0 <= outstanding_count <= 2,
            'C maximum five pending questions')
    result = []
    for index, question in enumerate(questions):
        closed(question, ('title',), ('options',))
        require(bool(native_trim(string(question['title']))), 'empty async title')
        options = question.get('options')
        require(options is None or type(options) is list, 'invalid options')
        if options is not None:
            require(bool(options), 'empty async options')
            for option in options:
                require(bool(native_trim(string(option))), 'empty async option')
        # Native state takes 32 labels BEFORE filtering byte lengths.
        visible = None if options is None else tuple(
            option for option in options[:32] if len(option.encode('utf-8')) <= 512)
        result.append({'questionId': question_id(item['id'], index),
                       'title': question['title'], 'options': visible})
    return tuple(result)


def render_answered_question(identity, title, answer):
    """Exact AnsweredQuestion::new(...).render() including legacy fallback."""
    string(identity); string(title, empty=True); string(answer, empty=True)
    title = title.encode('utf-8')[:512].decode('utf-8', errors='ignore')
    title = title.replace('\n', ' ').replace('\r', ' ')
    if len(identity.encode('utf-8')) > 512:
        return f'> {title}\n\n{answer}'
    body = compact([{'answer': answer, 'question': title,
                     'questionItemId': identity}])
    return OPEN + '\n' + body + '\n' + CLOSE


def native_trim(value):
    # Rust str::trim uses Unicode White_Space, unlike Python's extra U+001C..1F.
    whitespace = ' \t\n\r\v\f\x85\xa0\u1680' + ''.join(
        chr(n) for n in range(0x2000, 0x200b)) + '\u2028\u2029\u202f\u205f\u3000'
    return value.strip(whitespace)


def validate_text_elements(text, elements):
    require(type(elements) is list, 'text_elements must remain a list')
    boundaries = {0}
    offset = 0
    for char in text:
        offset += len(char.encode('utf-8'))
        boundaries.add(offset)
    for element in elements:
        closed(element, ('byteRange', 'placeholder'))
        span = element['byteRange']
        closed(span, ('start', 'end'))
        require(type(span['start']) is int and type(span['end']) is int and
                span['start'] in boundaries and span['end'] in boundaries and
                span['start'] <= span['end'], 'invalid UTF-8 text-element range')
        require(element['placeholder'] is None or
                type(element['placeholder']) is str, 'invalid placeholder')


def validate_answer_dispatch(envelope, *, item, index, decision, thread_id,
                             active_turn_id, commit, version, start_settings=None,
                             seen_request_ids=(), seen_client_message_ids=(),
                             outstanding_count=0):
    """Match one complete native answer; never allocate/predict IDs or retry.

    decision is ALREADY independently validated Root data {questionId, kind,
    answer}; kind is option or freeText. start_settings is the full admitted
    native parameter map excluding input/clientUserMessageId, including any
    serviceTier presence/null distinction. This function grants no authority and
    consumes no token; the caller must consume its one-use callback on attempt.
    """
    source_pin(commit, version)
    require(classify_route(envelope) == 'async-user-dispatch',
            'sync RPC/unsupported route cannot satisfy C async answer')
    closed(envelope, ('id', 'method', 'params'))
    request_id = rpc_identity(envelope['id'])
    require(all(request_id != rpc_identity(old) for old in seen_request_ids),
            'reused typed request ID')
    questions = async_questions(item, outstanding_count=outstanding_count)
    require(type(index) is int and 0 <= index < len(questions), 'wrong question index')
    question = questions[index]
    closed(decision, ('questionId', 'kind', 'answer'))
    require(decision['questionId'] == question['questionId'], 'wrong question identity')
    require(len(question['questionId'].encode('utf-8')) <= 512,
            'unmarked legacy answer cannot establish C identity')
    answer = native_trim(string(decision['answer']))
    require(bool(answer), 'empty trimmed answer')
    if decision['kind'] == 'option':
        require(question['options'] is not None and
                any(native_trim(option) == answer for option in question['options']),
                'answer is not a native displayed-option candidate')
    else:
        require(decision['kind'] == 'freeText', 'unsupported decision kind')
    text = render_answered_question(question['questionId'], question['title'], answer)
    require(len(text) <= MAX_TEXT_CHARS, 'native answer exceeds text limit')
    params = envelope['params']
    string(thread_id)
    if active_turn_id is not None:
        string(active_turn_id)
        require(envelope['method'] == 'turn/steer', 'active turn requires steer')
        closed(params, STEER_FIELDS)
        require(params['expectedTurnId'] == active_turn_id, 'wrong active turn')
        require(all(params[field] is None for field in
                    ('responsesapiClientMetadata', 'responsesapiClientMetadataPatch',
                     'additionalContext')), 'extra steer context')
    else:
        require(envelope['method'] == 'turn/start', 'inactive turn requires start')
        closed(params, START_FIELDS, ('serviceTier',))
        require(type(start_settings) is dict, 'missing admitted native start settings')
        actual_settings = {k: v for k, v in params.items()
                           if k not in ('input', 'clientUserMessageId')}
        require(compact(actual_settings) == compact(start_settings),
                'native start settings changed')
        require(params['turnTrigger'] == 'user' and
                all(params[field] is None for field in START_NULLS),
                'non-native additional start input')
    require(params['threadId'] == thread_id, 'wrong native thread')
    client_id = string(params['clientUserMessageId'])
    require(client_id not in seen_client_message_ids, 'reused native client message ID')
    inputs = params['input']
    require(type(inputs) is list and len(inputs) == 1, 'exactly one answered input required')
    closed(inputs[0], ('type', 'text', 'text_elements'))
    require(inputs[0]['type'] == 'text' and inputs[0]['text'] == text,
            'wrong answer fragment or extra answer/text')
    validate_text_elements(text, inputs[0]['text_elements'])
    # The native async state renders a String; it creates no rich-input spans.
    require(inputs[0]['text_elements'] == [], 'unexpected async answer text elements')
    return True
