#!/usr/bin/env python3
"""Bounded F1 source tests: real copied Git bytes, SYNTHETIC RPC, no execution.

These fixtures establish validator behavior only. They are not native runs,
accepted D2 rows, independent business reviews, or runtime authorization.
"""
import copy
import json
from pathlib import Path
import shlex
import shutil
import tempfile
import unittest

import postclosure as c


GIT_BYTES = Path('/private/tmp/ains-Git254-profile-v2-na6r3iuw')
P7 = 'D2-tail/unavailable-review'
P8 = 'D2-tail/independent-review'
SKILL = '.agents/skills/ains-review/SKILL.md'
PROMPT = '.agents/skills/ains-review/review-prompt.md'


class F1Case(unittest.TestCase):
    def setUp(self):
        self.fixture()

    def fixture(self, off_mode='0o644'):
        self.temp = tempfile.TemporaryDirectory(prefix='postclosure-f1-SYNTHETIC-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.serial = 0
        self.placeholder = self.put(b'SYNTHETIC routing placeholder, never approval')
        if not (GIT_BYTES / 'after/.git/index').is_file():
            self.fail('required read-only Git254 v2 byte fixture is absent')
        self.git_meta = json.loads((GIT_BYTES / 'result.json').read_bytes())
        self.author_root = self.home / 'author'
        shutil.copytree(GIT_BYTES / 'after', self.author_root)
        # Permission variation applies only to this new SYNTHETIC fixture copy.
        (self.author_root / 'off.json').chmod(int(off_mode, 8))
        self.resources = {}
        for path in (SKILL, PROMPT):
            data = (c.SOURCE / path.replace('.agents/skills/', 'skills/', 1)).read_bytes()
            self.write(self.author_root, path, data)
            self.resources[path.replace('.agents/skills/', 'skills/', 1)] = {
                'sha256': c.digest(data), 'mode': '0o644'}
        self.manifest = self.save({'suite_files': self.resources})
        self.admission = self.record('D2-admission', branch_id='SYNTHETIC', composite_manifest=self.manifest)
        self.roles = {'application': ['app/a.py'], 'tests': ['tests/test_a.py'],
                      'progress': ['docs/progress.md'], 'spec': 'docs/spec.md',
                      'tasks': 'docs/tasks.md', 'callers': [], 'packet': ['review/handoff.md'], 'off': 'off.json'}
        for name in ('spec', 'tasks'):
            self.write(self.author_root, self.roles[name], b'---\nstatus: approved\n---\nSYNTHETIC feature ' + name.encode() + b'\n')
        self.write(self.author_root, 'docs/progress.md', b'SYNTHETIC implemented; independent review pending.\n')
        self.contract = self.record('contract', row_id=P7, roles=self.roles, expected_after=None,
                                    evidence={}, obligations=['independent_review_incomplete'],
                                    git_profile=None, cache_profile=None, capability_profile=None, tasks_progress=None)
        self.profile = self.record('git-profile', branch='refs/heads/fixture', main_ref='refs/heads/main',
                                   off_path='off.json', off_mode=off_mode)
        # P6/P7 observe the same physical author root: inode identity is part of
        # the unchanged Git namespace, not something relocation can fabricate.
        self.p6 = self.entry(self.author_root, 'D2-tail/Git-AC9')
        self.p6['plan']['contract'] = self.record('contract', row_id='D2-tail/Git-AC9', roles=self.roles,
                                                 git_profile=self.profile)
        self.add_check(self.p6)
        self.finish(self.p6)
        self.freeze(self.p6)
        self.author = self.entry(self.author_root, P7)
        self.author['plan']['contract'] = self.contract
        self.contexts = {c.canonical_hash(entry['reference']): entry for entry in (self.p6, self.author)}
        self.captures = {c.canonical_hash(entry['capture_ref']): entry for entry in (self.p6, self.author)}
        self.expected = c.derive_review_target(self.author, self.profile_value(), self.p6)
        endpoint_text = []
        for layer, paths in self.expected['layers'].items():
            for path, endpoints in paths.items():
                for side, endpoint in zip(('before', 'after'), endpoints):
                    if endpoint is None:
                        endpoint_text.append('%s %s %s: absent' % (layer, path, side))
                    else:
                        mode, oid, data = endpoint
                        filesystem_mode = ('0o755' if mode == '100755' else '0o644')
                        if path == self.roles['off'] and side == 'after':
                            filesystem_mode = self.author['state'][path]['mode']
                        endpoint_text.append('%s %s %s: mode %s blob %s content sha256 %s' %
                                             (layer, path, side, filesystem_mode, oid, c.digest(data)))
        natural = ('SYNTHETIC natural handoff. Scope ' + str(self.author_root) + '\n'
                   'Base ' + self.expected['base'] + '; HEAD ' + self.expected['head'] +
                   '; merge-base ' + self.expected['merge_base'] + '\n' +
                   '\n'.join(self.expected['target']) + '\nCommit: app and tests. Index: empty, equals restored HEAD.\n'
                   'Worktree: no tracked differences. Untracked: approved local docs listed above.\n'
                   + '\n'.join(endpoint_text) + '\n' +
                   'Check python3 -m unittest discover -v: passed; source equivalence retained.\n'
                   'Independent review unavailable on this SYNTHETIC route; review remains incomplete.\n')
        self.final_index = self.add_item(self.author, {'type': 'agentMessage', 'id': 'SYNTHETIC-final',
                                                     'phase': 'final_answer', 'text': natural})
        self.finish(self.author)
        self.freeze(self.author)
        self.contexts = {c.canonical_hash(entry['reference']): entry for entry in (self.p6, self.author)}
        self.packet = self.make_packet()
        self.packet_ref = self.record('review-packet', **self.packet)
        self.adjudication = {'packet': self.packet_ref, 'projection': None,
                             'observations': {'independent_review_incomplete': {
                                 'sources': [self.slice(self.author, self.final_index, 'text')],
                                 'judgment': 'SYNTHETIC source-test judgment only'}}}

    def put(self, data):
        self.serial += 1
        path = self.home / 'immutable' / ('%05d.bin' % self.serial)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return c.ref(path)

    def save(self, value):
        return self.put(json.dumps(value, sort_keys=True).encode())

    def record(self, kind, **values):
        value = {name: self.placeholder for name in c.SCHEMAS[kind].split()}
        for name in ('prefix_sha256', 'session_sha256', 'predecessor_state_sha256', 'history_sha256',
                     'input_sha256', 'prior_history_sha256', 'expected_before'):
            if name in value:
                value[name] = '0' * 64
        value.update(schema='postclosure-' + kind + '-v1', **values)
        if kind == 'scope':
            value.update(instruction_sources=values.get('instruction_sources', []), install=values.get('install', []))
        if kind == 'decision':
            value.update(actor='SYNTHETIC Root decision', reviewed_artifacts=[])
        return self.save(value)

    def write(self, root, path, data):
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        destination.chmod(0o644)

    def profile_value(self):
        return c.read_record(self.profile, 'git-profile')

    def frame(self, entry, direction, payload):
        data = (json.dumps(payload) + '\n').encode()
        wire = entry['raw']['wire']
        wire.append({'index': len(wire), 'monotonic_ns': len(wire) + 1,
                     'direction': direction, 'payload': payload,
                     'bytes_sha256': c.digest(data), 'bytes_length': len(data)})
        return len(wire) - 1

    def add_item(self, entry, item):
        params = {'threadId': entry['raw']['thread_id'], 'turnId': entry['raw']['turn_id']}
        started = dict(item)
        if item['type'] == 'commandExecution':
            started.update(status='inProgress', exitCode=None, aggregatedOutput='')
        elif item['type'] == 'agentMessage':
            started['text'] = ''
        self.frame(entry, 'response', {'method': 'item/started', 'params': dict(params, item=started)})
        return self.frame(entry, 'response', {'method': 'item/completed', 'params': dict(params, item=item)})

    def finish(self, entry):
        self.frame(entry, 'response', {'method': 'turn/completed', 'params': {
            'threadId': entry['raw']['thread_id'], 'turn': {'id': entry['raw']['turn_id'], 'status': 'completed'}}})

    def entry(self, root, row):
        state = c.inventory(root)
        content = {path: (root / path).read_bytes() for path, value in state.items() if value['kind'] == 'file'}
        scope = self.record('scope', scope_id='SYNTHETIC-' + root.name, root=str(root), realroot=str(root), topology='author')
        state_ref = self.save(state)
        capture = self.record('review-capture', scope=scope, state_before=state_ref, state_after=state_ref,
                              files={path: self.put(data) for path, data in content.items()})
        decision = self.record('decision', request='SYNTHETIC one USER fixture request')
        lookup = self.record('lookup', native_facts={'capability': {'SYNTHETIC': 'not runtime proof'}})
        common = self.record('common', lookup=lookup)
        raw = {'root': str(root), 'realroot': str(root), 'thread_id': 'SYNTHETIC-thread-' + row,
               'turn_id': 'SYNTHETIC-turn-' + row, 'wire': [], 'common': common, 'business_PASS': False,
               'samples': [{'phase': 'review-target-capture', 'capture': capture}],
               'state_before': copy.deepcopy(state), 'state_after': state}
        raw.update(schema='postclosure-context-v1', branch_id='SYNTHETIC', row_id=row, donor_slot=c.ROWS[row],
                   release=self.placeholder, prior_history_sha256='0' * 64, process_id=None,
                   input_delivery={'SYNTHETIC': True}, close={'reaped': True, 'partial_stdout_bytes': 0},
                   failure=None, accounting={})
        entry = {'reference': self.put(('SYNTHETIC context identity ' + root.name + row).encode()), 'raw': raw,
                 'plan': {'row_id': row, 'scope': scope, 'contract': self.contract,
                          'admission': self.admission, 'input': decision},
                 'capture_ref': capture, 'capture': c.read_record(capture, 'review-capture'), 'state': state, 'content': content}
        self.frame(entry, 'request', {'id': 1, 'method': 'turn/start', 'params': {
            'threadId': raw['thread_id'], 'input': [{'type': 'text', 'text': 'SYNTHETIC one USER fixture request'}]}})
        self.frame(entry, 'response', {'id': 1, 'result': {'turn': {'id': raw['turn_id']}}})
        self.frame(entry, 'response', {'method': 'turn/started', 'params': {
            'threadId': raw['thread_id'], 'turn': {'id': raw['turn_id'], 'status': 'inProgress'}}})
        if SKILL in content:
            self.read_files(entry, [SKILL, 'docs/spec.md', PROMPT])
        return entry

    def read_files(self, entry, paths):
        inner = 'cat -- ' + ' '.join(shlex.quote(path) for path in paths)
        command = '/bin/zsh -lc ' + shlex.quote(inner)
        return self.add_item(entry, {'type': 'commandExecution', 'id': 'SYNTHETIC-read-' + str(len(entry['raw']['wire'])),
            'command': command, 'cwd': entry['raw']['root'], 'status': 'completed', 'exitCode': 0,
            'aggregatedOutput': b''.join(entry['content'][path] for path in paths).decode(), 'outputTruncated': False})

    def freeze(self, entry):
        previous = entry['reference']
        entry['raw']['accounting'] = c.validate_wire(entry['raw']['wire'], entry['raw']['thread_id'], entry['raw']['turn_id'])
        c.validate_record(entry['raw'], 'context')
        entry['reference'] = self.save(entry['raw'])
        if hasattr(self, 'check') and self.check['context'] == previous:
            self.check['context'] = entry['reference']
            self.check['result']['context'] = entry['reference']

    def slice(self, entry, index, field):
        item = entry['raw']['wire'][index]['payload']['params']['item']
        body = item[field].encode()
        return {'kind': 'wire', 'context': entry['reference'], 'wire_index': index,
                'item_sha256': c.canonical_hash(item), 'field': field,
                'start': 0, 'end': len(body), 'sha256': c.digest(body)}

    def add_check(self, entry):
        command = '/bin/zsh -lc ' + shlex.quote('python3 -m unittest discover -v')
        index = self.add_item(entry, {'type': 'commandExecution', 'id': 'SYNTHETIC-check',
            'command': command, 'cwd': entry['raw']['root'], 'status': 'completed', 'exitCode': 0,
            'aggregatedOutput': 'SYNTHETIC unittest output: 1 test, OK\n', 'outputTruncated': False})
        event_index = sum(1 for frame in entry['raw']['wire'][:index] if frame['direction'] == 'response' and 'method' in frame['payload'])
        entry['raw']['samples'].append({'phase': 'post-command-source-equivalence', 'event_index': event_index,
            'versions': [{'source': path, 'capture': self.put(entry['content'][path])}
                         for path in self.roles['application'] + self.roles['tests']]})
        self.check = {'context': entry['reference'], 'wire_index': index,
                      'item_sha256': c.canonical_hash(entry['raw']['wire'][index]['payload']['params']['item']),
                      'command': command, 'cwd': entry['raw']['root'], 'source_capture': entry['capture_ref'],
                      'result': self.slice(entry, index, 'aggregatedOutput')}

    def endpoint(self, value):
        if value is None:
            return None
        mode, oid, data = value
        return {'content': self.put(data), 'mode': '0o755' if mode == '100755' else '0o644', 'oid': oid}

    def make_packet(self):
        expected = self.expected
        packet = {key: expected[key] for key in ('scope', 'base', 'head', 'merge_base', 'target', 'callers')}
        packet.update(capture=self.author['capture_ref'], spec=self.put(self.author['content'][self.roles['spec']]),
                      tasks=self.put(self.author['content'][self.roles['tasks']]), checks=[self.check],
                      resources=c.installed_review_reads(self.author))
        for layer, changes in expected['layers'].items():
            packet[layer] = {path: {'before': self.endpoint(before), 'after': self.endpoint(after)}
                             for path, (before, after) in changes.items()}
            if self.roles['off'] in packet[layer] and packet[layer][self.roles['off']]['after'] is not None:
                packet[layer][self.roles['off']]['after']['mode'] = self.author['state'][self.roles['off']]['mode']
        pointers = {'/scope', '/base', '/head', '/merge_base', '/spec', '/tasks', '/commit', '/index', '/worktree', '/untracked', '/checks/0'}
        pointers |= {'/target/' + str(i) for i in range(len(expected['target']))}
        for layer in ('commit', 'index', 'worktree', 'untracked'):
            pointers |= {'/' + layer + '/' + path.replace('~', '~0').replace('/', '~1') for path in packet[layer]}
        packet['origins'] = {pointer: [self.slice(self.author, self.final_index, 'text')] for pointer in sorted(pointers)}
        return packet

    def adjudicate(self, packet=None, adjudication=None, current=None, prior=()):
        value = copy.deepcopy(adjudication or self.adjudication)
        if packet is not None:
            value['packet'] = self.record('review-packet', **packet)
        return c.validate_f1_adjudication(value, current or self.author, self.contexts, self.captures, list(prior))

    def reviewer(self):
        source_adjudication = self.record('adjudication', context=self.author['reference'], row_contract=self.contract,
            poststate=self.save(self.author['state']), capture=self.author['capture_ref'], **self.adjudication)
        source_result = self.record('independent-result', context=self.author['reference'],
            review=self.put(b'SYNTHETIC independent source-test judgment'), adjudication=source_adjudication,
            decision='ACCEPT_EXACT_D2_ROW', business_PASS=True)
        root = self.home / 'reviewer'
        root.mkdir()
        files = {}

        def deliver(path, data, mode, role):
            self.write(root, path, data)
            (root / path).chmod(int(mode, 8))
            files[path] = {'source': self.put(data), 'destination': path, 'mode': mode, 'role': role}

        for path in self.packet['target'] + self.packet['callers']:
            if path in self.author['content']:
                role = 'spec' if path == self.roles['spec'] else 'tasks' if path == self.roles['tasks'] else 'endpoint'
                deliver(path, self.author['content'][path], self.author['state'][path]['mode'], role)
        for layer in ('commit', 'index', 'worktree', 'untracked'):
            for path, endpoints in self.packet[layer].items():
                for side, endpoint in endpoints.items():
                    if endpoint is not None:
                        deliver('review-material/' + layer + '/' + side + '/' + path,
                                c.read_ref(endpoint['content']), endpoint['mode'], 'endpoint')
        final = self.author['raw']['wire'][self.final_index]['payload']['params']['item']['text'].encode()
        deliver('review-material/handoff-final-%05d.md' % self.final_index, final, '0o644', 'handoff')
        check = self.p6['raw']['wire'][self.check['wire_index']]['payload']['params']['item']['aggregatedOutput'].encode()
        deliver('review-material/check-000.txt', check, '0o644', 'check')
        for path in (SKILL, PROMPT):
            self.write(root, path, self.author['content'][path])
        current = self.entry(root, P8)
        self.read_files(current, sorted(files))
        final_index = self.add_item(current, {'type': 'agentMessage', 'id': 'SYNTHETIC-reviewer-verdict',
            'phase': 'final_answer', 'text': 'SYNTHETIC independent final report: no findings in bounded source fixture. PASS.'})
        self.finish(current)
        self.freeze(current)
        destination_state = self.save(current['state'])
        projection = self.record('review-projection', source_result=source_result, source_packet=self.packet_ref,
            source_capture=self.author['capture_ref'], destination_root=str(root), destination_state=destination_state,
            files=[files[path] for path in sorted(files)])
        material = self.record('materialization', destination_state=destination_state,
            relocation={'independent_projection_review': projection}, topology='reviewer-no-git')
        scope = self.record('scope', scope_id='SYNTHETIC-independent-reviewer', root=str(root), realroot=str(root),
                            topology='reviewer-no-git', materialization=material)
        current['plan']['scope'] = scope
        capture = dict(current['capture'], scope=scope)
        current['capture_ref'] = self.record('review-capture', **{key: value for key, value in capture.items() if key != 'schema'})
        current['capture'] = capture
        current['raw']['samples'][0]['capture'] = current['capture_ref']
        self.freeze(current)
        self.contexts[c.canonical_hash(current['reference'])] = current
        self.captures[c.canonical_hash(current['capture_ref'])] = current
        adjudication = {'packet': self.packet_ref, 'projection': projection,
                        'observations': {'completed_review': {'sources': [self.slice(current, final_index, 'text')],
                                                             'judgment': 'SYNTHETIC final verdict is present'}}}
        return current, adjudication, source_result

    def test_p7_actual_git_capture_natural_handoff_and_installed_bodies(self):
        self.assertEqual(self.expected['base'], self.git_meta['baseline'])
        self.assertEqual(self.expected['head'], self.git_meta['restore'])
        self.assertEqual(set(self.packet['commit']), {'app/a.py', 'tests/test_a.py'})
        self.assertEqual(self.packet['index'], {})
        self.assertEqual(self.packet['worktree'], {})
        self.assertEqual(set(self.packet['untracked']), {'docs/spec.md', 'docs/tasks.md', 'docs/progress.md', 'off.json'})
        self.assertEqual(c.validate_wire(self.author['raw']['wire'], self.author['raw']['thread_id'], self.author['raw']['turn_id'])['accepted'], 1)
        self.assertFalse(self.author['raw']['business_PASS'])
        self.assertTrue(self.adjudicate())
        contract = c.read_record(self.contract, 'contract')
        self.assertIsNone(contract['expected_after'])
        self.assertEqual(contract['evidence'], {})
        capture, state, content = c.validate_review_capture(self.author['capture_ref'], self.author['raw'], self.author['plan'])
        self.assertEqual(content, self.author['content'])
        self.assertEqual(state, self.author['state'])

    def test_missing_model_origins_and_supervisor_fill_hold(self):
        packet = copy.deepcopy(self.packet)
        del packet['origins']['/head']
        with self.assertRaises(c.Hold):
            self.adjudicate(packet)
        packet = copy.deepcopy(self.packet)
        body = self.author['content']['docs/progress.md']
        artifact = {'kind': 'artifact', 'capture': self.author['capture_ref'], 'path': 'docs/progress.md',
                    'start': 0, 'end': len(body), 'sha256': c.digest(body)}
        packet['origins']['/scope'] = [artifact]
        with self.assertRaisesRegex(c.Hold, 'model-authored packet'):
            self.adjudicate(packet)

    def test_supervisor_endpoint_fill_without_actual_model_identity_holds(self):
        packet = copy.deepcopy(self.packet)
        source = self.slice(self.author, self.final_index, 'text')
        body = self.author['raw']['wire'][self.final_index]['payload']['params']['item']['text'].encode()
        prefix = b'SYNTHETIC natural handoff'
        self.assertTrue(body.startswith(prefix))
        source.update(end=len(prefix), sha256=c.digest(prefix))
        packet['origins']['/commit/app~1a.py'] = [source]
        # The trusted capture still has complete real endpoint bytes. It may
        # corroborate the model handoff, but cannot replace omitted origins.
        with self.assertRaisesRegex(c.Hold, 'endpoint origin|omitted endpoint'):
            self.adjudicate(packet)

    def test_persistent_off_cannot_be_omitted_from_packet(self):
        self.assertIn('off.json', self.packet['target'])
        self.assertEqual(c.read_ref(self.packet['untracked']['off.json']['after']['content']),
                         self.author['content']['off.json'])
        for mutation in ('target', 'layer', 'content', 'mode'):
            with self.subTest(mutation=mutation):
                packet = copy.deepcopy(self.packet)
                if mutation == 'target':
                    packet['target'].remove('off.json')
                elif mutation == 'layer':
                    del packet['untracked']['off.json']
                elif mutation == 'content':
                    packet['untracked']['off.json']['after']['content'] = self.put(b'SYNTHETIC changed OFF state')
                else:
                    packet['untracked']['off.json']['after']['mode'] = '0o755'
                with self.assertRaises(c.Hold):
                    self.adjudicate(packet)

    def test_private_off_0600_preserves_bytes_mode_and_git_nonexec_identity(self):
        self.fixture('0o600')
        expected = self.expected['layers']['untracked']['off.json'][1]
        endpoint = self.packet['untracked']['off.json']['after']
        self.assertEqual(expected[0], '100644')
        self.assertEqual(endpoint['mode'], '0o600')
        self.assertEqual(endpoint['oid'], expected[1])
        self.assertEqual(c.read_ref(endpoint['content']), (GIT_BYTES / 'after/off.json').read_bytes())
        self.assertTrue(self.adjudicate())
        current, adjudication, source_result = self.reviewer()
        self.assertTrue(self.adjudicate(adjudication=adjudication, current=current, prior=[source_result]))
        projected = c.read_record(adjudication['projection'], 'review-projection')
        private = {item['destination']: item for item in projected['files'] if item['destination'].endswith('off.json')}
        self.assertEqual(set(private), {'off.json', 'review-material/untracked/after/off.json'})
        self.assertTrue(all(item['mode'] == '0o600' for item in private.values()))
        self.assertEqual(current['state']['off.json']['mode'], '0o600')
        packet = copy.deepcopy(self.packet)
        packet['untracked']['off.json']['after']['mode'] = '0o644'
        with self.assertRaises(c.Hold):
            self.adjudicate(packet)
        changed = copy.deepcopy(current)
        changed['raw']['state_before']['off.json']['mode'] = '0o644'
        with self.assertRaises(c.Hold):
            self.adjudicate(adjudication=adjudication, current=changed, prior=[source_result])

    def test_private_mode_exception_does_not_extend_to_other_targets(self):
        (self.author_root / 'docs/progress.md').chmod(0o600)
        entry = self.entry(self.author_root, P7)
        with self.assertRaisesRegex(c.Hold, 'endpoint file mode'):
            c.derive_review_target(entry, self.profile_value(), self.p6)

    def test_fake_oid_wrong_mode_false_absence_and_omitted_doc_hold(self):
        for mutation in ('oid', 'mode', 'absence', 'omit-doc'):
            with self.subTest(mutation=mutation):
                packet = copy.deepcopy(self.packet)
                if mutation == 'oid':
                    packet['commit']['app/a.py']['after']['oid'] = '0' * 40
                elif mutation == 'mode':
                    packet['commit']['app/a.py']['after']['mode'] = '0o755'
                elif mutation == 'absence':
                    packet['commit']['app/a.py']['after'] = None
                else:
                    del packet['untracked']['docs/progress.md']
                with self.assertRaises(c.Hold):
                    self.adjudicate(packet)

    def test_actual_worktree_difference_is_derived_and_index_drift_holds(self):
        path = self.author_root / 'app/a.py'
        path.write_bytes(path.read_bytes() + b'\n# SYNTHETIC local worktree variation, not P7 admission\n')
        entry = self.entry(self.author_root, P7)
        expected = c.derive_review_target(entry, self.profile_value(), self.p6)
        self.assertEqual(set(expected['layers']['worktree']), {'app/a.py'})
        index = self.author_root / '.git/index'
        index.write_bytes(index.read_bytes()[:-1] + b'X')
        entry = self.entry(self.author_root, P7)
        with self.assertRaises(c.Hold):
            c.derive_review_target(entry, self.profile_value(), self.p6)

    def test_stale_check_source_and_missing_equivalence_hold(self):
        for stale in (True, False):
            with self.subTest(stale=stale):
                author = copy.deepcopy(self.p6)
                contexts = dict(self.contexts)
                contexts[c.canonical_hash(author['reference'])] = author
                if stale:
                    author['raw']['samples'][-1]['versions'][0]['capture'] = self.put(b'SYNTHETIC stale source')
                else:
                    author['raw']['samples'].pop()
                with self.assertRaisesRegex(c.Hold, 'post-command source equivalence'):
                    c.validate_packet_checks(self.packet, self.author, contexts, self.captures)

    def test_failed_truncated_partial_or_wrong_installed_resource_reads_hold(self):
        for mutation in ('failed', 'truncated', 'partial', 'wrong-path'):
            with self.subTest(mutation=mutation):
                entry = copy.deepcopy(self.author)
                item = entry['raw']['wire'][4]['payload']['params']['item']
                if mutation == 'failed':
                    item['exitCode'] = 1
                elif mutation == 'truncated':
                    item['outputTruncated'] = True
                elif mutation == 'partial':
                    item['aggregatedOutput'] = item['aggregatedOutput'][:10]
                else:
                    item['command'] = '/bin/zsh -lc ' + shlex.quote('cat /wrong/ains-review/SKILL.md')
                with self.assertRaises(c.Hold):
                    c.installed_review_reads(entry)

    def test_capture_omission_alias_and_drift_hold(self):
        for mutation in ('omission', 'alias', 'drift'):
            with self.subTest(mutation=mutation):
                capture = copy.deepcopy(self.author['capture'])
                raw = copy.deepcopy(self.author['raw'])
                if mutation == 'omission':
                    del capture['files']['docs/progress.md']
                else:
                    state = copy.deepcopy(self.author['state'])
                    if mutation == 'alias':
                        state['docs/progress.md']['link_text'] = 'spec.md'
                    else:
                        state['docs/progress.md']['sha256'] = '0' * 64
                    capture['state_before'] = capture['state_after'] = self.save(state)
                    raw['state_after'] = state
                reference = self.record('review-capture', **{key: value for key, value in capture.items() if key != 'schema'})
                raw['samples'][0]['capture'] = reference
                with self.assertRaises(c.Hold):
                    c.validate_review_capture(reference, raw, self.author['plan'])

    def test_wire_slice_requires_actual_identity_and_utf8_byte_digest(self):
        source = self.slice(self.author, self.final_index, 'text')
        self.assertIn(b'SYNTHETIC natural handoff', c.validate_source_slice(source, self.contexts, self.captures)[0])
        for field, value in (('item_sha256', '0' * 64), ('end', source['end'] + 1), ('sha256', '0' * 64)):
            with self.subTest(field=field), self.assertRaises(c.Hold):
                c.validate_source_slice(dict(source, **{field: value}), self.contexts, self.captures)

    def test_input_slice_binds_actual_decision_and_cannot_supply_handoff(self):
        decision = c.read_record(self.author['plan']['input'], 'decision')
        body = decision['request'].encode()
        source = {'kind': 'input', 'context': self.author['reference'], 'start': 0,
                  'end': len(body), 'sha256': c.digest(body)}
        self.assertEqual(c.validate_source_slice(source, self.contexts, self.captures)[0], body)
        with self.assertRaisesRegex(c.Hold, 'not model handoff'):
            c.model_handoff_slice(source, self.contexts, self.captures, self.author['reference'])
        changed = copy.deepcopy(self.author)
        changed['raw']['wire'][0]['payload']['params']['input'][0]['text'] = 'SYNTHETIC different delivered request'
        contexts = dict(self.contexts)
        contexts[c.canonical_hash(changed['reference'])] = changed
        with self.assertRaisesRegex(c.Hold, 'actual signed USER delivery'):
            c.validate_source_slice(source, contexts, self.captures)

    def test_model_authored_packet_artifact_has_capture_and_reference_provenance(self):
        before = c.inventory(self.author_root)
        body = b'SYNTHETIC model-authored natural handoff artifact\n'
        self.write(self.author_root, 'review/handoff.md', body)
        entry = self.entry(self.author_root, P7)
        entry['raw']['state_before'] = before
        self.add_item(entry, {'type': 'agentMessage', 'id': 'SYNTHETIC-artifact-final',
            'phase': 'final_answer', 'text': 'SYNTHETIC complete handoff at review/handoff.md; review remains incomplete.'})
        self.finish(entry)
        self.freeze(entry)
        source = {'kind': 'artifact', 'capture': entry['capture_ref'], 'path': 'review/handoff.md',
                  'start': 0, 'end': len(body), 'sha256': c.digest(body)}
        contexts = {c.canonical_hash(entry['reference']): entry}
        captures = {c.canonical_hash(entry['capture_ref']): entry}
        self.assertEqual(c.model_handoff_slice(source, contexts, captures, entry['reference']), body)
        entry['raw']['wire'][-2]['payload']['params']['item']['text'] = 'SYNTHETIC filename-free stop'
        with self.assertRaisesRegex(c.Hold, 'supervisor capture cannot supply'):
            c.model_handoff_slice(source, contexts, captures, entry['reference'])

    def test_future_contract_outcomes_cannot_be_inserted_for_adjudication(self):
        original = c.read_record(self.contract, 'contract')
        for mutation in ('poststate', 'evidence'):
            with self.subTest(mutation=mutation):
                contract = copy.deepcopy(original)
                if mutation == 'poststate':
                    contract['expected_after'] = c.canonical_hash(self.author['state'])
                else:
                    contract['evidence'] = {'independent_review_incomplete': 'SYNTHETIC future outcome'}
                reference = self.record('contract', **{key: value for key, value in contract.items() if key != 'schema'})
                adjudication = self.record('adjudication', context=self.author['reference'], row_contract=reference,
                    poststate=self.save(self.author['state']), capture=self.author['capture_ref'], **self.adjudication)
                with self.assertRaisesRegex(c.Hold, 'prospective and unchanged'):
                    c.validate_adjudication({'context': self.author['reference'], 'adjudication': adjudication},
                                            self.author['raw'], dict(self.author['plan'], contract=reference), [])

    def test_capture_content_ref_alias_is_rejected(self):
        source = Path(self.author['capture']['files']['docs/progress.md']['path'])
        alias = self.home / 'capture-alias'
        alias.symlink_to(source)
        capture = copy.deepcopy(self.author['capture'])
        capture['files']['docs/progress.md'] = {'path': str(alias), 'sha256': c.digest(source.read_bytes())}
        reference = self.record('review-capture', **{key: value for key, value in capture.items() if key != 'schema'})
        raw = copy.deepcopy(self.author['raw'])
        raw['samples'][0]['capture'] = reference
        with self.assertRaises(c.Hold):
            c.validate_review_capture(reference, raw, self.author['plan'])

    def test_capture_actual_byte_limit_is_enforced(self):
        data = b'x' * (c.MAX_CAPTURE_FILE_BYTES + 1)
        self.write(self.author_root, 'review/oversize.txt', data)
        state = c.inventory(self.author_root)
        capture = copy.deepcopy(self.author['capture'])
        capture['files']['review/oversize.txt'] = self.put(data)
        capture['state_before'] = capture['state_after'] = self.save(state)
        reference = self.record('review-capture', **{key: value for key, value in capture.items() if key != 'schema'})
        raw = copy.deepcopy(self.author['raw'])
        raw['samples'][0]['capture'] = reference
        raw['state_after'] = state
        with self.assertRaisesRegex(c.Hold, 'hash/size relation'):
            c.validate_review_capture(reference, raw, self.author['plan'])

    def test_p8_exact_no_git_projection_delivery_consumption_and_report(self):
        current, adjudication, source_result = self.reviewer()
        self.assertNotEqual(current['raw']['root'], self.author['raw']['root'])
        self.assertFalse(any(path == '.git' or path.startswith('.git/') for path in current['state']))
        self.assertTrue(self.adjudicate(adjudication=adjudication, current=current, prior=[source_result]))
        c.validate_review_capture(current['capture_ref'], current['raw'], current['plan'])
        self.assertEqual(c.validate_wire(current['raw']['wire'], current['raw']['thread_id'], current['raw']['turn_id'])['accepted'], 1)
        self.assertFalse(current['raw']['business_PASS'])

    def test_p8_projection_tamper_or_missing_content_hold(self):
        current, adjudication, source_result = self.reviewer()
        for mutation in ('bytes', 'mode', 'omission', 'wrong-p7'):
            with self.subTest(mutation=mutation):
                value = c.read_record(adjudication['projection'], 'review-projection')
                if mutation == 'bytes':
                    value['files'][0]['source'] = self.put(b'SYNTHETIC supervisor replacement')
                elif mutation == 'mode':
                    value['files'][0]['mode'] = '0o755'
                elif mutation == 'omission':
                    value['files'].pop()
                else:
                    value['source_result'] = self.placeholder
                reference = self.record('review-projection', **{key: item for key, item in value.items() if key != 'schema'})
                # Keep the scope/materialization binding exact so each negative
                # reaches content reconciliation rather than a stale Ref guard.
                material = self.record('materialization', destination_state=value['destination_state'],
                    relocation={'independent_projection_review': reference}, topology='reviewer-no-git')
                scope = self.record('scope', scope_id='SYNTHETIC-independent-reviewer', root=current['raw']['root'],
                    realroot=current['raw']['root'], topology='reviewer-no-git', materialization=material)
                changed = copy.deepcopy(current)
                changed['plan']['scope'] = scope
                with self.assertRaises(c.Hold):
                    self.adjudicate(adjudication=dict(adjudication, projection=reference), current=changed, prior=[source_result])

    def test_p8_delivery_without_actual_consumption_or_final_report_holds(self):
        current, adjudication, source_result = self.reviewer()
        for mutation in ('no-read', 'truncated', 'path-only-report', 'foreign-report'):
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(current)
                item = changed['raw']['wire'][6]['payload']['params']['item']
                if mutation == 'no-read':
                    item['command'] = 'echo SYNTHETIC filenames only'
                elif mutation == 'truncated':
                    item['outputTruncated'] = True
                elif mutation == 'path-only-report':
                    item['aggregatedOutput'] = 'docs/spec.md docs/tasks.md review-material/check-000.txt'
                else:
                    verdict = changed['raw']['wire'][-2]['payload']['params']['item']
                    verdict['phase'] = 'commentary'
                contexts = dict(self.contexts)
                contexts[c.canonical_hash(changed['reference'])] = changed
                with self.assertRaises(c.Hold):
                    c.validate_f1_adjudication(adjudication, changed, contexts, self.captures, [source_result])

    def test_p8_author_transcript_extra_payload_holds(self):
        current, adjudication, source_result = self.reviewer()
        root = Path(current['raw']['root'])
        self.write(root, 'author-conversation.json', b'SYNTHETIC author conversation must stay external')
        changed = copy.deepcopy(current)
        changed['raw']['state_before'] = c.inventory(root)
        changed['content']['author-conversation.json'] = (root / 'author-conversation.json').read_bytes()
        projection = c.read_record(adjudication['projection'], 'review-projection')
        projection['destination_state'] = self.save(changed['raw']['state_before'])
        reference = self.record('review-projection', **{key: value for key, value in projection.items() if key != 'schema'})
        material = self.record('materialization', destination_state=projection['destination_state'],
            relocation={'independent_projection_review': reference}, topology='reviewer-no-git')
        changed['plan']['scope'] = self.record('scope', scope_id='SYNTHETIC-independent-reviewer', root=str(root),
            realroot=str(root), topology='reviewer-no-git', materialization=material)
        with self.assertRaisesRegex(c.Hold, 'author history or unrelated files'):
            self.adjudicate(adjudication=dict(adjudication, projection=reference), current=changed, prior=[source_result])

    def test_history_source_set_drift_rejected_before_acceptance(self):
        # An exact closed record graph reaches the source-set freeze guard;
        # the later claim/runtime checks are intentionally outside this test.
        common = self.record('common', source_set=self.put(b'SYNTHETIC source epoch A'))
        reviewed = self.record('root-review', common=common, decision='SYNTHETIC fixture review', release_id='SYNTHETIC-release')
        release = self.record('release', common=common, root_review=reviewed, release_id='SYNTHETIC-release')
        raw = self.record('context', branch_id='SYNTHETIC', row_id='D2-tail/spec-approval',
            donor_slot=c.ROWS['D2-tail/spec-approval'], common=common, release=release,
            root=str(self.author_root), realroot=str(self.author_root), process_id=None,
            thread_id=None, turn_id=None, wire=[], samples=[], failure=None, business_PASS=False)
        result = self.record('independent-result', context=raw, review=self.placeholder,
            adjudication=self.placeholder, decision='ACCEPT_EXACT_D2_ROW', business_PASS=True)
        with self.assertRaisesRegex(c.Hold, 'source set must remain frozen'):
            c.validate_history('0' * 64, [result], source_set=self.put(b'SYNTHETIC source epoch B'))


if __name__ == '__main__':
    unittest.main()
