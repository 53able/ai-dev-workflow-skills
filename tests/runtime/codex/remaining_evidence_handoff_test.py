"""Owned synthetic evidence only; no native processes, claims, or fixture replay."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import postclosure_recovery as f
import remaining_evidence_handoff as h


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='remaining-handoff-test-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.serial = 0

    def put(self, data):
        self.serial += 1
        path = self.home / str(self.serial)
        path.write_bytes(data)
        return f.ref(path)

    def save(self, value):
        return self.put(json.dumps(value, sort_keys=True).encode())

    def read_record(self, pin, kind):
        value = f.decode(f.read_ref(pin))
        self.assertEqual(value['schema'], kind)
        return value

    def record(self, kind, **values):
        return self.save(dict(schema=kind, **values))

    def file(self, data=b'x', mode='0o644', identity=None):
        return dict(kind='file', sha256=f.digest(data), mode=mode,
                    identity=identity or [1, 2], link_text=None)

    def entry(self, content, wire=None):
        return dict(raw=dict(root='/missing/fixture', wire=wire or []), content=content,
                    state={p: self.file(data) for p, data in content.items()})

    def cat(self, command='cat -- a b', output='AB', **changes):
        item = dict(type='commandExecution', status='completed', exitCode=0,
                    command=command, aggregatedOutput=output)
        item.update(changes)
        return dict(direction='response', payload=dict(method='item/completed', params=dict(item=item)))

    def refs(self, content):
        return [dict(path='/missing/fixture/' + path, sha256=f.digest(data)) for path, data in content.items()]

    def test_capture_consumption_does_not_read_or_resolve_absent_fixture(self):
        content = {'a': b'A', 'b': b'B'}
        entry = self.entry(content, [self.cat()])
        with patch.object(f, 'read_ref', side_effect=AssertionError('live resource lookup')):
            results = h._captured_reads(entry, self.refs(content))
        self.assertEqual(len(results), 2)
        self.assertEqual(results[1]['event_index'], 0)

    def test_capture_consumption_rejects_partial_failed_truncated_or_forged_output(self):
        for changes in ({'outputTruncated': True}, {'exitCode': 1}, {'exitCode': False},
                        {'status': 'inProgress'}, {'aggregatedOutput': 'A'}, {'command': 'echo AB'}):
            with self.subTest(changes=changes), self.assertRaises(f.Hold):
                h._captured_reads(self.entry({'a': b'A', 'b': b'B'}, [self.cat(**changes)]),
                                  self.refs({'a': b'A', 'b': b'B'}))

    def test_capture_consumption_rejects_outside_missing_and_wrong_hash(self):
        entry = self.entry({'a': b'A'}, [self.cat(command='cat a', output='A')])
        for pin in (dict(path='/elsewhere/a', sha256=f.digest(b'A')),
                    dict(path='/missing/fixture/b', sha256=f.digest(b'A')),
                    dict(path='/missing/fixture/a', sha256=f.digest(b'forged'))):
            with self.subTest(pin=pin), self.assertRaises(f.Hold):
                h._captured_reads(entry, [pin])

    def prepared_campaign(self):
        return dict(path='/synthetic/campaign', sha256='c'*64)

    def fixture(self):
        self.author = self.entry({'spec': b'spec', 'tasks': b'tasks', 'app': b'app'})
        self.author.update(reference=self.put(b'author'), capture_ref=self.put(b'capture'),
                           plan=dict(contract=self.record('contract', roles=dict(spec='spec', tasks='tasks'))))
        self.author['raw'].update(stage=h.P7, campaign=self.prepared_campaign())
        self.author['assessment'] = dict(admissible_for=[h.P8])
        self.author['state']['app']['identity'] = [9, 12]
        self.packet = dict(target=['app'], callers=[], spec=self.put(b'spec'), tasks=self.put(b'tasks'),
                           commit={}, index={}, worktree={}, untracked={}, origins={}, checks=[])
        self.packet_ref = self.save(self.packet)
        self.predecessor = self.put(b'assessment')
        self.payload = {p: data for p, data in self.author['content'].items()}
        self.skill = {p: ('resource ' + p).encode() for p in h.REVIEW}
        self.manifest = self.save(dict(suite_files={p.replace('.agents/skills/', 'skills/', 1):
            dict(sha256=f.digest(data), mode='0o644') for p, data in self.skill.items()}))
        state = {p: self.file(data, identity=[4, i + 1])
                 for i, (p, data) in enumerate((self.payload | self.skill).items())}
        self.graph = dict(stage=h.P8, campaign=self.prepared_campaign(), scope=dict(root='/missing/reviewer', realroot='/missing/reviewer',
            topology='reviewer-no-git', instruction_sources=[], install=[]), state=state, manifest=self.manifest)
        files = [dict(source=self.put(data), destination=p, mode='0o644', role=p if p in ('spec', 'tasks') else 'endpoint')
                 for p, data in sorted(self.payload.items())]
        self.bridge = dict(source_result=self.predecessor, source_packet=self.packet_ref,
            source_capture=self.author['capture_ref'], destination_root='/missing/reviewer',
            destination_state=self.save(state), files=files)

    def project(self, **changes):
        bridge = dict(self.bridge, **changes)
        pin = self.record('review-projection', **bridge)
        with patch.object(h, '_chain', return_value=([self.author], {}, {})), \
             patch.object(h, '_packet', return_value=self.packet), \
             patch.object(f, 'read_record', side_effect=self.read_record):
            return h.validate_projection(pin, self.predecessor, self.graph)

    def test_projection_exact_bytes_and_narrow_no_git_root(self):
        self.fixture()
        result = self.project()
        self.assertEqual(set(result['delivered']), set(self.payload))
        self.assertEqual(result['delivered']['app']['sha256'], f.digest(b'app'))

    def test_projection_uses_typed_replayed_p7_without_a_success_assessment(self):
        import remaining_evidence_p7_replay as replay
        self.fixture()
        self.author.pop('assessment')
        self.author['raw'].update(campaign=self.put(b'historical campaign'),
                                  failure={'primary': 'preserved mode HOLD'})
        proof = replay._ReplayedP7.__new__(replay._ReplayedP7)
        proof.entry, proof.bridge_ref, proof.pins = self.author, self.predecessor, {}
        proof.bridge = dict(campaign=self.graph['campaign'], observation=self.author['reference'],
                            admissible_for=[h.P8], packet=self.packet_ref)
        self.author['p7_replay_proof'] = proof
        self.assertEqual(set(self.project()['delivered']), set(self.payload))
        self.assertIsNotNone(self.author['raw']['failure'])
        proof.bridge['campaign'] = self.put(b'foreign current campaign')
        with self.assertRaises(f.Hold):
            self.project()
        proof.bridge['campaign'] = self.graph['campaign']
        with self.assertRaises(f.Hold):
            self.project(source_packet=self.put(b'unreviewed packet'))
        self.author['p7_replay_proof'] = {'verified': True}
        with self.assertRaises(f.Hold):
            self.project()

    def test_projection_rejects_missing_extra_wrong_mode_or_root(self):
        self.fixture()
        cases = [dict(files=self.bridge['files'][:-1]),
                 dict(files=self.bridge['files'] + [self.bridge['files'][0]]),
                 dict(destination_root='/missing/fixture')]
        wrong = copy.deepcopy(self.bridge['files']); wrong[0]['mode'] = '0o755'
        cases.append(dict(files=wrong))
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(f.Hold):
                self.project(**changes)
        for name in ('.git/config', 'author-chat.txt'):
            self.graph['state'][name] = self.file(b'private')
            with self.subTest(extra=name), self.assertRaises(f.Hold):
                self.project(destination_state=self.save(self.graph['state']))
            del self.graph['state'][name]

    def test_projection_rejects_missing_review_body_or_source42_drift(self):
        self.fixture()
        del self.graph['state'][h.REVIEW[0]]
        with self.assertRaises(f.Hold):
            self.project(destination_state=self.save(self.graph['state']))
        self.fixture()
        self.graph['state'][h.REVIEW[0]]['sha256'] = f.digest(b'changed')
        with self.assertRaises(f.Hold):
            self.project(destination_state=self.save(self.graph['state']))

    def return_fixture(self, final=True):
        self.fixture()
        report = b'Actual synthetic reviewer final report.'
        self.reviewer = self.entry({}, [dict(direction='response', payload=dict(method='item/completed',
            params=dict(item=dict(type='agentMessage', phase='final_answer', text=report.decode()))))] if final else [])
        self.reviewer.update(capture_ref=self.put(b'reviewer capture'), plan=dict(contract=
            self.record('contract', roles=dict(review='review/report.md'))))
        self.reviewer['raw'].update(stage=h.P8, campaign=self.prepared_campaign(), root='/missing/reviewer', state_before={})
        self.reviewer['assessment'] = dict(admissible_for=['D2-tail/local-ship'])
        self.author['raw']['state_before'] = copy.deepcopy(self.author['state'])
        state = copy.deepcopy(self.author['state'])
        state['review'] = dict(kind='directory', mode='0o755', identity=[1, 9])
        state['review/report.md'] = self.file(report)
        self.graph.update(stage='D2-tail/local-ship', scope=dict(root='/missing/fixture', realroot='/missing/fixture'),
                          state=state, contract=dict(roles=dict(review='review/report.md')))
        self.return_bridge = dict(source_result=self.predecessor, source_capture=self.reviewer['capture_ref'],
            destination_root='/missing/fixture', destination_state=self.save(state),
            report='review/report.md', source=self.put(report))

    def returned(self, **changes):
        pin = self.record('review-return', **dict(self.return_bridge, **changes))
        with patch.object(h, '_chain', return_value=([self.reviewer, self.author], {}, {})), \
             patch.object(f, 'read_record', side_effect=self.read_record):
            return h.validate_return(pin, self.predecessor, self.graph)

    def test_return_actual_final_bytes_preserves_author_file_identity(self):
        self.return_fixture()
        self.assertEqual(set(self.returned()['delivered']), {'review/report.md'})

    def test_return_rejects_root_filled_report_changed_author_or_wrong_destination(self):
        self.return_fixture(final=False)
        with self.assertRaises(f.Hold):
            self.returned()
        self.return_fixture()
        for changes in (dict(source=self.put(b'Root supplied summary')), dict(destination_root='/elsewhere')):
            with self.subTest(changes=changes), self.assertRaises(f.Hold):
                self.returned(**changes)
        self.graph['state']['app']['identity'] = [999, 999]
        with self.assertRaises(f.Hold):
            self.returned(destination_state=self.save(self.graph['state']))

    def test_return_model_created_file_requires_actual_change_and_provenance(self):
        self.return_fixture(final=False)
        data = f.read_ref(self.return_bridge['source'])
        self.reviewer['content']['review/report.md'] = data
        self.reviewer['state']['review/report.md'] = self.file(data)
        item = dict(type='fileChange', status='completed', changes=[dict(path='review/report.md')])
        self.reviewer['raw']['wire'] = [dict(direction='response', payload=dict(method='item/completed', params=dict(item=item)))]
        self.assertTrue(self.returned()['delivered'])
        self.reviewer['raw']['state_before'] = copy.deepcopy(self.reviewer['state'])
        with self.assertRaises(f.Hold):
            self.returned()

    def packet_fixture(self):
        self.fixture()
        resources = self.skill
        content = self.author['content'] | resources | {'test': b'test'}
        author = self.entry(content)
        author.update(reference=self.put(b'actual P7 observation'), capture_ref=self.put(b'actual P7 capture'),
                      plan=dict(row_id=h.P7, contract=self.record('contract', roles=dict(application=['app'], tests=['test']))))
        author['raw'].update(stage=h.P7, thread_id='thread', turn_id='turn', samples=[])
        check_item = dict(type='commandExecution', status='completed', exitCode=0,
            command='python3 -m unittest discover -v', cwd='/missing/fixture', aggregatedOutput='checks OK')
        def frame(item):
            return dict(direction='response', payload=dict(method='item/completed',
                params=dict(threadId='thread', turnId='turn', item=item)))
        resource_command = self.cat(command='cat ' + ' '.join(resources),
            output=b''.join(resources.values()).decode())
        text = '/missing/fixture ' + 'a' * 40 + ' app test spec tasks commit clean index clean worktree clean untracked clean python3 -m unittest discover -v passed'
        author['raw']['wire'] = [resource_command, frame(check_item), frame(dict(
            type='agentMessage', phase='final_answer', text=text))]
        versions = [dict(source=path, capture=self.put(content[path])) for path in ('app', 'test')]
        author['raw']['samples'] = [dict(phase='post-command-source-equivalence', event_index=1, versions=versions)]
        def sliced(index, field):
            item = author['raw']['wire'][index]['payload']['params']['item']; data = item[field].encode()
            return dict(kind='wire', context=author['reference'], wire_index=index,
                item_sha256=f.canonical_hash(item), field=field, start=0, end=len(data), sha256=f.digest(data))
        expected = dict(scope=dict(root='/missing/fixture', realroot='/missing/fixture'),
            base='a'*40, head='a'*40, merge_base='a'*40, target=['app', 'test'], callers=[],
            roles=dict(spec='spec', tasks='tasks'), layers={k: {} for k in ('commit', 'index', 'worktree', 'untracked')})
        author['content']['spec'] = b'---\nstatus: approved\n---\nspec'
        author['content']['tasks'] = b'---\nstatus: approved\n---\ntasks'
        self.packet = dict(scope=expected['scope'], capture=author['capture_ref'], base='a'*40, head='a'*40,
            merge_base='a'*40, target=['app', 'test'], callers=[], spec=self.put(author['content']['spec']),
            tasks=self.put(author['content']['tasks']), commit={}, index={}, worktree={}, untracked={},
            resources=h._resources(author, self.graph), checks=[dict(context=author['reference'], wire_index=1,
                item_sha256=f.canonical_hash(check_item), command=check_item['command'], cwd='/missing/fixture',
                source_capture=author['capture_ref'], result=sliced(1, 'aggregatedOutput'))], origins={})
        required = ['/scope', '/base', '/head', '/merge_base', '/spec', '/tasks', '/commit', '/index',
                    '/worktree', '/untracked', '/target/0', '/target/1', '/checks/0']
        self.packet['origins'] = {key: [sliced(2, 'text')] for key in required}
        profile = self.record('git-profile')
        git = dict(raw=dict(stage='D2-tail/Git-AC9'), plan=dict(contract=self.record('contract', git_profile=profile)))
        return author, git, expected

    def packet_check(self, author, git, expected):
        packet = self.record('review-packet', **self.packet)
        contexts = {f.canonical_hash(author['reference']): author}
        captures = {f.canonical_hash(author['capture_ref']): author}
        with patch.object(f, 'derive_review_target', return_value=expected), \
             patch.object(f, 'read_record', side_effect=self.read_record):
            return h._packet(packet, author, [author, git], contexts, captures, self.graph)

    def test_packet_binds_actual_origins_current_check_and_source42_reads(self):
        author, git, expected = self.packet_fixture()
        self.assertEqual(self.packet_check(author, git, expected), dict(schema='review-packet', **self.packet))
        author['raw']['samples'][0]['versions'][0]['capture'] = self.put(b'stale source')
        with self.assertRaises(f.Hold):
            self.packet_check(author, git, expected)

    def test_packet_cannot_present_historical_context_checks_without_boundary(self):
        author, git, expected = self.packet_fixture()
        author['old_checks_scope'] = 'CAPTURED_P6_CONTEXT_ONLY'
        with self.assertRaisesRegex(f.Hold, 'historical P6 environment boundary'):
            self.packet_check(author, git, expected)
        item = author['raw']['wire'][2]['payload']['params']['item']
        item['text'] += ' CAPTURED_P6_CONTEXT_ONLY'
        data = item['text'].encode()
        for origins in self.packet['origins'].values():
            for origin in origins:
                origin.update(item_sha256=f.canonical_hash(item), end=len(data), sha256=f.digest(data))
        self.assertTrue(self.packet_check(author, git, expected))

    def test_packet_rejects_missing_origins_layer_paths_and_resource_read(self):
        for mutation in ('origin', 'layer', 'read'):
            author, git, expected = self.packet_fixture()
            if mutation == 'origin':
                del self.packet['origins']['/head']
            elif mutation == 'layer':
                self.packet['index']['invented'] = dict(before=None, after=None)
            else:
                author['raw']['wire'][0]['payload']['params']['item']['outputTruncated'] = True
            with self.subTest(mutation=mutation), self.assertRaises(f.Hold):
                self.packet_check(author, git, expected)

    def test_chain_requires_complete_order_and_rejects_cycles(self):
        c = h._core()
        stages = list(c.ROWS)[:2]
        pins = [self.put(stage.encode()) for stage in stages]
        campaign = self.prepared_campaign()
        assessments = {f.canonical_hash(pin): dict(schema='remaining-assessment-v1', verdicts={},
            observation=pin, integrity='PASS', stage=stage,
            campaign=campaign, preserved_failures=c.FAILURES, goal_complete=False,
            admissible_for=list(c.ROWS)[i+1:i+2]) for i, (pin, stage) in enumerate(zip(pins, stages))}
        entries = {f.canonical_hash(pin): dict(reference=pin, capture_ref=self.put(b'capture'+stage.encode()),
            raw=dict(stage=stage, campaign=campaign), release=dict(predecessor=pins[i-1] if i else None))
            for i, (pin, stage) in enumerate(zip(pins, stages))}
        def read(pin, kind=None):
            self.assertIn(kind, (None, 'assessment'))
            return assessments[f.canonical_hash(pin)]
        def entry(pin):
            return copy.deepcopy(entries[f.canonical_hash(pin)])
        with patch.object(c, 'read_record', side_effect=read), patch.object(h, '_entry', side_effect=entry):
            self.assertEqual(len(h._chain(pins[-1])[0]), 2)
            entries[f.canonical_hash(pins[0])]['release']['predecessor'] = pins[-1]
            with self.assertRaises(f.Hold):
                h._chain(pins[-1])
            entries[f.canonical_hash(pins[0])]['release']['predecessor'] = None
            entries[f.canonical_hash(pins[-1])]['release']['predecessor'] = None
            with self.assertRaises(f.Hold):
                h._chain(pins[-1])

    def test_recovery_chain_terminates_at_seed_without_accepting_failed_tdd(self):
        c = h._core(); campaign = self.prepared_campaign()
        seed = self.put(b'synthetic immutable seed')
        observation = self.put(b'healthy actual P5')
        assessment_ref = self.put(b'healthy assessment')
        failed_observation = self.put(b'failed historical TDD')
        release = dict(stage=c.RECOVERY_STAGE, predecessor=seed, baseline=self.put(b'zero'))
        assessment = dict(schema='remaining-assessment-v1', verdicts={}, observation=observation,
            integrity='PASS', stage=c.RECOVERY_STAGE, campaign=campaign,
            preserved_failures=c.FAILURES, goal_complete=False,
            admissible_for=['D2-tail/Git-AC9'])
        entry = dict(reference=observation, capture_ref=self.put(b'healthy capture'),
            raw=dict(stage=c.RECOVERY_STAGE, campaign=campaign), release=release)
        def read(pin, kind=None):
            return assessment if pin == assessment_ref else {'schema': 'remaining-recovery-seed-v1'}
        proof = {'pins': {failed_observation['path']: failed_observation}}
        with patch.object(c, 'read_record', side_effect=read), \
             patch.object(h, '_entry', return_value=entry), \
             patch.object(c, 'validate_recovery_seed', return_value=proof) as validate:
            entries, contexts, captures = h._chain(assessment_ref)
            validate.assert_called_once_with(seed, release=release)
            self.assertEqual(len(entries), 1)
            self.assertEqual(set(contexts), {f.canonical_hash(observation)})
            self.assertNotIn(f.canonical_hash(failed_observation), contexts)
            self.assertEqual(entries[0]['recovery_seed_pins'], proof['pins'])
            assessment['integrity'] = 'FAIL'
            with self.assertRaises(f.Hold): h._chain(assessment_ref)
            assessment['integrity'] = 'PASS'
            with patch.object(c, 'validate_recovery_seed', side_effect=f.Hold('baseline mismatch')):
                with self.assertRaises(f.Hold): h._chain(assessment_ref)
            entry['raw']['stage'] = 'D2-tail/Git-AC9'; assessment['stage'] = entry['raw']['stage']
            with self.assertRaises(f.Hold): h._chain(assessment_ref)

    def test_replay_bridge_crosses_only_p7_edge_and_preserves_failed_raw(self):
        from types import SimpleNamespace
        import remaining_evidence_replay as replay
        c = h._core()
        current, historical = self.put(b'current campaign'), self.put(b'old campaign')
        seed, bridge = self.put(b'seed'), self.put(b'bridge')
        p5, p6, p7 = [self.put(stage.encode()) for stage in ('P5', 'P6', 'P7')]
        a5, a7 = self.put(b'P5 assessment'), self.put(b'P7 assessment')
        entries = {}
        for reference, stage, campaign, predecessor in (
                (p5, c.RECOVERY_STAGE, historical, seed),
                (p6, 'D2-tail/Git-AC9', historical, a5),
                (p7, h.P7, current, bridge)):
            entries[f.canonical_hash(reference)] = dict(reference=reference,
                capture_ref=self.put(stage.encode()), raw=dict(stage=stage, campaign=campaign,
                    failure={'primary': 'preserved transition HOLD'} if reference == p6 else None),
                release=dict(predecessor=predecessor))
        def assessment(reference, stage, campaign, successor):
            return dict(schema='remaining-assessment-v1', observation=reference, stage=stage,
                campaign=campaign, integrity='PASS', preserved_failures=c.FAILURES,
                goal_complete=False, admissible_for=[successor], verdicts={})
        records = {f.canonical_hash(a5): assessment(p5, c.RECOVERY_STAGE, historical, 'D2-tail/Git-AC9'),
            f.canonical_hash(a7): assessment(p7, h.P7, current, h.P8),
            f.canonical_hash(bridge): dict(schema='remaining-replay-bridge-v1',
                campaign=current, observation=p6),
            f.canonical_hash(seed): dict(schema='remaining-recovery-seed-v1')}
        source_proof = object()
        proof = SimpleNamespace(historical_sources=source_proof, pins={})
        with patch.object(c, 'read_record', side_effect=lambda pin, kind=None: records[f.canonical_hash(pin)]), \
             patch.object(h, '_entry', side_effect=lambda pin, replay_proof=None: copy.deepcopy(entries[f.canonical_hash(pin)])), \
             patch.object(replay, 'validate_bridge', return_value=proof), \
             patch.object(c, 'validate_recovery_seed', return_value={'pins': {}}) as validate:
            chain, contexts, _ = h._chain(a7)
            self.assertEqual([item['raw']['stage'] for item in chain], [h.P7, 'D2-tail/Git-AC9', c.RECOVERY_STAGE])
            self.assertIsNotNone(contexts[f.canonical_hash(p6)]['raw']['failure'])
            self.assertNotIn('assessment', chain[1])
            validate.assert_called_once_with(seed, release=entries[f.canonical_hash(p5)]['release'],
                                            historical_sources=source_proof)
            entries[f.canonical_hash(p7)]['raw']['stage'] = h.P8
            with self.assertRaises(f.Hold):
                h._chain(a7)
            entries[f.canonical_hash(p7)]['raw']['stage'] = h.P7
            records[f.canonical_hash(bridge)]['campaign'] = historical
            with self.assertRaises(f.Hold):
                h._chain(a7)

    def test_replay_entry_rejects_untyped_success_claim(self):
        with self.assertRaises(f.Hold):
            h._entry(self.put(b'observation'), replay_proof={'valid': True})

    def test_recovered_packet_excludes_old_tdd_checks(self):
        author, git, expected = self.packet_fixture()
        author['recovery_seed_pins'] = {}
        author['raw']['stage'] = 'D2-tail/TDD-build'
        with self.assertRaisesRegex(f.Hold, 'healthy current P6/P7 checks'):
            self.packet_check(author, git, expected)

    def test_review_consumption_requires_every_delivered_payload_and_resources(self):
        self.fixture()
        content = self.skill | {'payload.txt': b'actual payload'}
        entry = self.entry(content, [self.cat(command='cat ' + ' '.join(content),
            output=b''.join(content.values()).decode())])
        entry['raw']['stage'] = h.P8
        entry['release'] = dict(handoff=self.put(b'bridge'), predecessor=self.predecessor)
        entry['plan'] = {'row_id': h.P8}
        self.graph.update(plan=entry['plan'])
        assessment = dict(schema='remaining-assessment-v1', observation=self.put(b'actual observation'))
        proof = dict(pins={}, delivered={'payload.txt': dict(sha256=f.digest(b'actual payload'), mode='0o644')})
        with patch.object(h, '_entry', return_value=entry), patch.object(h, 'validate_projection', return_value=proof):
            self.assertEqual(h.validate_review_consumption(assessment, self.graph), proof)
            entry['raw']['wire'] = [self.cat(command='cat ' + ' '.join(self.skill),
                output=b''.join(self.skill.values()).decode())]
            with self.assertRaises(f.Hold):
                h.validate_review_consumption(assessment, self.graph)

    def test_no_legacy_history_admission_or_live_consumption_calls(self):
        import ast
        source = Path(h.__file__).read_text()
        tree = ast.parse(source)
        banned = {'validate_review_projection', 'validate_review_return', 'validate_f1_adjudication',
                  'validate_history', 'validate_graph', '_actual_reads', 'installed_review_reads',
                  'validate_resource_consumption', 'validate_review_packet'}
        calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and
                 isinstance(node.func, ast.Attribute)}
        self.assertFalse(calls & banned)
        self.assertFalse(any(isinstance(node, ast.Global) for node in ast.walk(tree)))


if __name__ == '__main__':
    unittest.main()
