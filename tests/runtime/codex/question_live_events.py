"""Inert, finite post-startup server lifecycle observer for pinned Codex 0.164.

Only decoded wire envelopes drive state. Attach client_guard and server_message
on ONE owned relay after independently reviewed startup. No launch, UI proof,
Root authority or provider-retention claim. Unsupported traffic stops UNVERIFIED.
Pinned v2/{turn,item,thread_data}.rs at question_native_schema.SOURCE_COMMIT.
"""
import question_contract as c
import question_native_schema as n


class LiveEvents:
    runtime_admitted = False

    def __init__(self, guard, *, commit, version, limit=256):
        n.source_pin(commit, version)
        c.require(type(limit) is int and 1 <= limit <= 4096, 'lifecycle bound')
        self.guard, self.limit = guard, limit
        self.generation = guard.generation
        self.thread = guard.first_params['threadId']
        n.string(self.thread)
        self.requests, self.turns, self.items = {}, {}, {}
        self.started_notifications = set()
        self.questions, self.finals, self.events = {}, [], []
        self.accepted, self.user_items, self.races = [], [], []
        self.failed = False
        self.answer = None

    def _record(self, value, metadata, direction):
        c.require(not self.failed, 'lifecycle already stopped')
        c.require(metadata.get('generation') == self.generation and
                  metadata.get('direction') == direction, 'foreign lifecycle connection')
        c.require(len(self.events) < self.limit, 'lifecycle events exhausted')
        self.events.append(c.loads(c.canonical({'value': value, 'metadata': metadata})))

    def _stop(self):
        self.failed = self.guard.terminal = True

    def client_guard(self, value, metadata):
        """Compose the native guard, observing actual dispatch IDs and content.

        Startup belongs to a separately classified adapter. This slice is
        deliberately post-startup; do not pass arbitrary startup RPCs through it.
        """
        try:
            self._record(value, metadata, 'client_to_server')
            c.require(value.get('method') in ('turn/start', 'turn/steer'), 'post-startup dispatch only')
            self.guard(value, metadata)
            key = n.rpc_identity(value['id'])
            c.require(key not in self.requests and len(self.requests) < 2, 'dispatch identity/budget')
            params = value['params']
            c.require(params.get('threadId') == self.thread, 'wrong request thread')
            if value['method'] == 'turn/steer':
                c.require(self.guard.active_turn is not None and
                          params.get('expectedTurnId') == self.guard.active_turn, 'wrong request turn')
            else:
                c.require(self.guard.active_turn is None, 'start while active: possible queue')
            self.requests[key] = {'wire': c.loads(c.canonical(value)), 'reply': False,
                                  'turn': None, 'user': None}
            return True
        except (ValueError, KeyError, TypeError):
            self._stop()
            raise

    def answer_matcher(self, *, item_id, index, decision, start_settings=None):
        """Use after independent Root/UI review; validation grants no authority."""
        c.require(not self.failed and self.answer is None, 'answer already armed/stopped')
        item = self.items.get(item_id, {}).get('completed')
        c.require(item is not None and item_id in self.questions, 'unobserved question item')
        active = self.guard.active_turn
        # Immutable native source validation inputs; no invented dispatch IDs.
        item, decision = c.loads(c.canonical([item, decision]))
        settings = c.loads(c.canonical(start_settings))
        used = False
        def match(value, metadata):
            nonlocal used
            try:
                c.require(not used and not self.failed and not self.guard.terminal and
                          self.guard.active_turn == active, 'answer lifecycle race')
                used = True
                c.require(metadata.get('generation') == self.generation and
                          metadata.get('direction') == 'client_to_server', 'foreign answer')
                key = n.rpc_identity(value['id'])
                c.require(key in self.requests and len(self.requests) == 2, 'unobserved answer attempt')
                prior = [r['wire'] for k, r in self.requests.items() if k != key]
                n.validate_answer_dispatch(value, item=item, index=index, decision=decision,
                    thread_id=self.thread, active_turn_id=active, commit=n.SOURCE_COMMIT,
                    version=n.SOURCE_VERSION, start_settings=settings,
                    seen_request_ids=[r['id'] for r in prior],
                    seen_client_message_ids=[r['params']['clientUserMessageId'] for r in prior])
                self.answer = {'request': key, 'question': decision['questionId'],
                               'rpc_accepted': False, 'user_item': None}
                return True
            except (ValueError, KeyError, TypeError):
                self._stop()
                raise
        # Reservation prevents obtaining multiple matchers before consumption.
        self.answer = {'armed': True}
        return match

    def _turn(self, turn):
        n.closed(turn, ('id', 'rootTurnId', 'items', 'status', 'error',
                        'startedAt', 'completedAt', 'durationMs'), ('itemsView',))
        n.string(turn['id'])
        c.require(turn['rootTurnId'] is None or type(turn['rootTurnId']) is str, 'root turn')
        c.require(turn.get('itemsView', 'full') == 'full' and type(turn['items']) is list,
                  'incomplete turn view')
        c.require(turn['error'] is None, 'turn error profile unsupported')
        for field in ('startedAt', 'completedAt', 'durationMs'):
            c.require(turn[field] is None or type(turn[field]) is int and
                      -(1 << 63) <= turn[field] < (1 << 63), 'turn timestamp')
        c.require(turn['status'] in ('inProgress', 'completed', 'failed', 'interrupted'), 'turn status')
        return turn['id']

    def _activate(self, turn_id):
        c.require(self.turns.get(turn_id) != 'terminal' and
                  self.guard.active_turn in (None, turn_id), 'turn race/overlap')
        self.turns[turn_id] = 'active'
        self.guard.active_turn = turn_id

    def _item(self, item, turn_id, completed):
        c.require(type(item) is dict, 'item object')
        ident = n.string(item.get('id'))
        kind = item.get('type')
        if kind == 'agentMessage':
            n.closed(item, ('type', 'id', 'text'), ('delivery', 'questions', 'phase', 'memoryCitation'))
            n.string(item['text'], empty=True)
            c.require(item.get('phase') in (None, 'commentary', 'final_answer') and
                      item.get('memoryCitation') is None, 'agent profile')
            c.require(item.get('delivery') in (None, 'async'), 'agent delivery')
            if item.get('questions') is not None:
                n.async_questions(item)
        elif kind == 'userMessage':
            n.closed(item, ('type', 'id', 'clientId', 'content'))
            matches = [r for r in self.requests.values()
                       if r['wire']['params']['clientUserMessageId'] == item['clientId']]
            c.require(len(matches) == 1, 'foreign accepted user item')
            request = matches[0]
            c.equal(item['content'], request['wire']['params']['input'], 'accepted user content')
            c.require(request['turn'] in (None, turn_id), 'accepted user wrong turn')
            request['turn'] = turn_id
        else:
            raise c.Hold('unreviewed item variant')
        row = self.items.setdefault(ident, {'turn': turn_id})
        c.require(row['turn'] == turn_id, 'item identity reused across turns')
        if 'started' in row:
            c.require(row['started']['type'] == kind, 'item kind changed during lifecycle')
            if kind == 'userMessage':
                c.equal(row['started'], item, 'accepted user identity/content changed during lifecycle')
        stage = 'completed' if completed else 'started'
        if stage in row:
            c.equal(row[stage], item, 'contradictory duplicate item')
            return
        c.require(completed or 'completed' not in row, 'item start after completion')
        row[stage] = c.loads(c.canonical(item))
        if completed and kind == 'agentMessage':
            if item.get('questions') is not None:
                c.require(not self.questions, 'second question batch unsupported')
                self.questions[ident] = n.async_questions(item)
            if item.get('phase') == 'final_answer':
                self.finals.append(ident)
        if completed and kind == 'userMessage':
            c.require(request['user'] in (None, ident), 'duplicate client user identity')
            request['user'] = ident
            self.user_items.append(ident)
            if self.answer and self.answer.get('request') in self.requests and \
                    self.requests[self.answer['request']] is request:
                self.answer['user_item'] = ident

    def server_message(self, value, metadata):
        try:
            self._record(value, metadata, 'server_to_client')
            if 'method' not in value:
                n.closed(value, ('id',), ('result', 'error'))
                key = n.rpc_identity(value['id'])
                c.require(key in self.requests and not self.requests[key]['reply'], 'foreign/duplicate response')
                request = self.requests[key]
                request['reply'] = True
                if 'error' in value:
                    self.races.append(key)
                    raise c.Hold('dispatch error; no retry or queue inference')
                c.require('result' in value, 'missing dispatch result')
                if request['wire']['method'] == 'turn/start':
                    n.closed(value['result'], ('turn',))
                    turn = value['result']['turn']
                    turn_id = self._turn(turn)
                    c.require(turn['status'] == 'inProgress' and not turn['items'], 'start result race/profile')
                else:
                    n.closed(value['result'], ('turnId',))
                    turn_id = n.string(value['result']['turnId'])
                    c.require(turn_id == request['wire']['params']['expectedTurnId'], 'steer response wrong turn')
                c.require(request['turn'] in (None, turn_id), 'response/user turn mismatch')
                self._activate(turn_id)
                request['turn'] = turn_id
                self.accepted.append(key)
                if self.answer and self.answer.get('request') == key:
                    self.answer['rpc_accepted'] = True
                return True
            n.closed(value, ('method', 'params'))
            method, params = value['method'], value['params']
            c.require(method in ('turn/started', 'turn/completed', 'item/started', 'item/completed'),
                      'unknown lifecycle notification')
            if method.startswith('turn/'):
                n.closed(params, ('threadId', 'turn'))
                c.require(params['threadId'] == self.thread, 'wrong lifecycle thread')
                turn = params['turn']; turn_id = self._turn(turn)
                if method == 'turn/started':
                    c.require(turn['status'] == 'inProgress' and not turn['items'] and
                              turn_id not in self.started_notifications and
                              self.turns.get(turn_id) != 'terminal', 'duplicate/malformed turn start')
                    starts = [r for r in self.requests.values()
                              if r['wire']['method'] == 'turn/start' and
                              (r['turn'] == turn_id or
                               r['turn'] is None and not r['reply'])]
                    c.require(len(starts) == 1, 'unsolicited or ambiguous turn')
                    starts[0]['turn'] = turn_id
                    self.started_notifications.add(turn_id)
                    self._activate(turn_id)
                else:
                    c.require(turn_id == self.guard.active_turn and
                              turn['status'] in ('completed', 'interrupted', 'failed'), 'terminal wrong turn/status')
                    for item in turn['items']:
                        self._item(item, turn_id, True)
                    self.turns[turn_id] = 'terminal'
                    self.guard.active_turn = None
                    # Natural turn completion is not global context closure.
                    # An outstanding steer result cannot resurrect this turn.
                return True
            timestamp = 'startedAtMs' if method == 'item/started' else 'completedAtMs'
            n.closed(params, ('threadId', 'turnId', 'item', timestamp))
            c.require(type(params[timestamp]) is int and -(1 << 63) <= params[timestamp] < (1 << 63), 'item timestamp')
            c.require(params['threadId'] == self.thread and
                      params['turnId'] == self.guard.active_turn, 'wrong/inactive item turn')
            self._item(params['item'], params['turnId'], method == 'item/completed')
            return True
        except (ValueError, KeyError, TypeError):
            self._stop()
            raise

    @property
    def answered_question(self):
        """Server RPC success AND matching completed user item; no UI retention."""
        if self.answer and self.answer.get('rpc_accepted') and self.answer.get('user_item'):
            return self.answer['question']
        return None
