"""Saved actual evidence plus bounded mocked bridge-control negative cases."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import remaining_evidence as c
import remaining_evidence_replay as r


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.serial = 0
        self.source = dict(path=str(c.CONTROL_ROOT / 'post-TDD-preparation-r2/source-set.json'), sha256=r.SOURCE26_SHA)
        self.archive = dict(path=str(c.CONTINUATION / 'remaining-evidence-source-freeze-r6/INDEX.json'), sha256=r.ARCHIVE_SHA)
        self.observation = dict(path=str(c.CONTROL_ROOT / 'post-TDD-P6-actual-r1/observation.json'), sha256=r.OBSERVATION_SHA)

    def put(self, value):
        self.serial += 1
        path = self.root / ('record-%d.json' % self.serial)
        path.write_text(json.dumps(value))
        return c.ref(path)

    def historical(self):
        return r.validate_historical_source26(self.source, self.archive)

    def test_real_source26_resolves_eight_protected_copies_without_current_owned_reads(self):
        historical = self.historical()
        self.assertEqual(len(historical.sources['files']), 26)
        for pin in historical.sources['files']:
            resolved = historical.resolve(pin)
            if Path(pin['path']).name in r.OLD_OWNED:
                self.assertEqual(Path(resolved['path']).name, Path(pin['path']).name + '.bin')
            else:
                self.assertEqual(resolved, pin)
        with mock.patch.object(c, 'validate_source_set', side_effect=AssertionError('live current source not historical')):
            self.historical()

    def test_historical_reference_substitution_rejected(self):
        for source, archive in ((dict(self.source, sha256='0' * 64), self.archive),
                                (self.source, dict(self.archive, sha256='0' * 64))):
            with self.subTest(source=source), self.assertRaises(c.Hold):
                r.validate_historical_source26(source, archive)
        historical = self.historical()
        original = next(pin for pin in historical.sources['files'] if Path(pin['path']).name == 'remaining_evidence.py')
        with self.assertRaises(c.Hold):
            historical.resolve(dict(original, sha256='0' * 64))

    def test_changed_archive_bytes_rejected(self):
        real_ref = r.f.ref
        def changed(path, **kwargs):
            value = real_ref(path, **kwargs)
            return dict(value, sha256='0' * 64) if str(path).endswith('remaining_evidence.py.bin') else value
        with mock.patch.object(r.f, 'ref', side_effect=changed), self.assertRaises(c.Hold):
            self.historical()

    def test_real_p6_recomputes_and_preserves_original_failure(self):
        entry, evidence, pins = r._actual_p6(self.observation, self.historical())
        result = json.loads((c.CONTINUATION / 'saved-P6-payload-replay-r1/RESULT.json').read_text())
        self.assertEqual(entry['raw']['failure'], r.FAILURE)
        self.assertFalse(entry['raw']['business_PASS'])
        for name in ('cache', 'git', 'transition'):
            self.assertEqual(evidence[name], result[name])
        self.assertEqual(len(evidence['cache']['matches']), 6)
        self.assertTrue(pins)

    def test_foreign_observation_and_untyped_resolver_rejected(self):
        for reference, historical in ((dict(self.observation, sha256='0' * 64), self.historical()),
                                      (self.observation, object())):
            with self.subTest(reference=reference), self.assertRaises(c.Hold):
                r._actual_p6(reference, historical)

    def test_altered_failure_and_unhealthy_close_rejected(self):
        real_read = c.read_record
        for mutation in ('stage', 'secondary', 'close'):
            def changed(reference, kind=None):
                value = real_read(reference, kind)
                if reference == self.observation:
                    value = copy.deepcopy(value)
                    if mutation == 'stage':
                        value['failure']['primary']['stage'] = 'turn-in-flight'
                    elif mutation == 'secondary':
                        value['failure']['secondary'].append({'reason_code': 'ERROR'})
                    else:
                        value['close']['returncode'] = 1
                return value
            with self.subTest(mutation=mutation), mock.patch.object(c, 'read_record', side_effect=changed):
                with self.assertRaises((c.Hold, ValueError)):
                    r._actual_p6(self.observation, self.historical())

    def test_rejected_recovery_seed_cannot_produce_replayed_predecessor(self):
        historical = self.historical()
        with mock.patch.object(c, 'validate_recovery_seed', side_effect=c.Hold('rejected exact seed')) as validate:
            with self.assertRaisesRegex(c.Hold, 'rejected exact seed'):
                r._actual_p6(self.observation, historical)
        self.assertEqual(validate.call_args.kwargs['historical_sources'], historical)
        self.assertEqual(validate.call_args.kwargs['release']['stage'], 'D2-tail/content-to-operation-question')

    def test_changed_actual_user_input_rejected(self):
        real_read = c.read_record
        def changed(reference, kind=None):
            value = real_read(reference, kind)
            if reference == self.observation:
                value = copy.deepcopy(value)
                value['input_delivery']['request_sha256'] = '0' * 64
            return value
        with mock.patch.object(c, 'read_record', side_effect=changed), self.assertRaises(c.Hold):
            r._actual_p6(self.observation, self.historical())

    def bridge_fixture(self):
        # Control-data unit fixture only; no Root adoption or actual acceptance is written.
        historical = self.historical()
        entry, evidence, _ = r._actual_p6(self.observation, historical)
        old = c.read_record(entry['raw']['campaign'], 'campaign')
        current = dict(old, source_set=self.put({'mock': 'current source closure'}))
        bridge = dict(schema='remaining-replay-bridge-v1', campaign=self.put(current),
            historical_campaign=entry['raw']['campaign'], current_source_set=current['source_set'],
            historical_source_set=self.source, archive=self.archive, observation=self.observation,
            replay_result=c.ref(c.CONTINUATION / 'saved-P6-payload-replay-r1/RESULT.json'),
            review=c.ref(c.CONTINUATION / 'saved-P6-payload-replay-r1/INDEPENDENT-REVIEW.json'),
            adoption=self.put({'mock': 'not an adoption'}), environment_transition=None, verdicts={}, preserved_failures=c.FAILURES,
            inherited_failures=c.RECOVERY_FAILURES, admissible_for=[r.P7], goal_complete=False)
        return bridge, current, entry, evidence

    def bridge(self, value, current, **kwargs):
        with mock.patch.object(c, '_controlled'), mock.patch.object(c, 'validate_campaign', return_value=current), \
             mock.patch.object(c, 'validate_source_set'), mock.patch.object(r, '_reviewed_replay', return_value=[]):
            return r.validate_bridge(self.put(value), **kwargs)

    def test_bridge_preserves_typed_entry_and_restricts_successor(self):
        bridge, current, entry, _ = self.bridge_fixture()
        proof = self.bridge(bridge, current)
        self.assertIs(type(proof), r._ReplayedPredecessor)
        self.assertEqual(proof.entry['raw']['failure'], r.FAILURE)
        for changed in (dict(bridge, admissible_for=['D2-tail/local-ship']),
                        dict(bridge, goal_complete=True), dict(bridge, preserved_failures={})):
            with self.subTest(changed=changed), self.assertRaises(c.Hold):
                self.bridge(changed, current)

    def test_campaign_changes_beyond_source_epoch_rejected(self):
        bridge, current, _, _ = self.bridge_fixture()
        current = dict(current, branch_id='foreign')
        with self.assertRaises(c.Hold):
            self.bridge(bridge, current)

    def test_reviewed_replay_exact_result_and_explicit_mock_adoption(self):
        bridge, _, entry, evidence = self.bridge_fixture()
        bridge['verdicts'] = {name: dict(verdict='PASS', sources=[self.observation],
            judgment='Unit mock finding; not an actual Root adoption.') for name in c.OBLIGATIONS[r.P6]}
        adoption = dict(decision='ROOT_ADOPT_EXACT_SAVED_P6_REPLAY_FOR_P7', actor='Root',
            **{key: bridge[key] for key in ('observation', 'replay_result', 'review', 'current_source_set')},
            accounting=r.ACCOUNTING, preserved_failures=c.FAILURES, inherited_failures=c.RECOVERY_FAILURES,
            raw_failure_preserved=True, no_retry=True, no_extra_capacity=True,
            judgment='Unit mock adoption in a temporary test directory only.')
        bridge['adoption'] = self.put(adoption)
        with self.assertRaises(c.Hold):
            r._reviewed_replay(bridge, evidence, entry)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(c, '_controlled').start()
        self.assertTrue(r._reviewed_replay(bridge, evidence, entry))
        changed = copy.deepcopy(evidence)
        changed['git']['restore'] = '0' * 40
        with self.assertRaises(c.Hold):
            r._reviewed_replay(bridge, changed, entry)
        for mutation in ('review', 'failure', 'verdict'):
            changed = copy.deepcopy(bridge)
            if mutation == 'review':
                changed['review'] = self.put({'verdict': 'APPROVE_SUPPLEMENTAL_ONLY'})
            elif mutation == 'failure':
                changed['adoption'] = self.put(dict(adoption, raw_failure_preserved=False))
            else:
                next(iter(changed['verdicts'].values()))['verdict'] = 'UNPROVEN'
            with self.subTest(mutation=mutation), self.assertRaises(c.Hold):
                r._reviewed_replay(changed, evidence, entry)

    def test_release_wrong_stage_and_different_full_state_rejected(self):
        bridge, current, entry, _ = self.bridge_fixture()
        reference = self.put(bridge)
        release = dict(stage='D2-tail/local-ship', predecessor=reference,
                       campaign=bridge['campaign'], source_set=bridge['current_source_set'])
        with mock.patch.object(c, '_controlled'), mock.patch.object(c, 'validate_campaign', return_value=current), \
             mock.patch.object(c, 'validate_source_set'), mock.patch.object(r, '_reviewed_replay', return_value=[]):
            with self.assertRaises(c.Hold):
                r.validate_bridge(reference, release=release)
            release['stage'] = r.P7
            graph = dict(state={}, source_set=bridge['current_source_set'],
                scope=dict(root=entry['raw']['root'], realroot=entry['raw']['root']),
                expected_environment=entry['raw']['environment'])
            with self.assertRaises(c.Hold):
                r.validate_bridge(reference, release=release, graph=graph)


    def transition_fixture(self):
        bridge, _, entry, _ = self.bridge_fixture()
        directory = c.CONTROL_ROOT / 'post-TDD-P7-current-environment-zero-diagnostic-r1'
        transition = dict(schema='remaining-environment-transition-v1',
            decision='ROOT_CONTINUE_P7_IN_EXPLICIT_NEW_CONTEXT', actor='Root',
            previous_observation=bridge['observation'], diagnostic_baseline=c.ref(directory / 'baseline.json'),
            diagnostic_observation=c.ref(directory / 'observation.json'),
            diagnostic_source_archive=c.ref(c.CONTINUATION / 'remaining-evidence-source-freeze-r7/INDEX.json'),
            current_source_set=bridge['current_source_set'],
            comparison=c.ref(c.CONTROL_ROOT / 'post-TDD-P7-preparation-r1/CURRENT-ENVIRONMENT-COMPARISON.json'),
            accounting=r.ACCOUNTING, preserved_failures=c.FAILURES, inherited_failures=c.RECOVERY_FAILURES,
            old_environment_equivalence='UNPROVEN', old_config_value_equivalence='UNPROVEN',
            old_checks_scope='CAPTURED_P6_CONTEXT_ONLY', no_retry=True, no_extra_capacity=True,
            goal_complete=False, judgment='Unit mock new-context decision, never an actual Root release.')
        return bridge, entry, transition

    def transition(self, transition, bridge, entry, release=None, graph=None):
        with mock.patch.object(c, '_controlled'):
            return r._environment_transition(self.put(transition), bridge, entry, release, graph)

    def test_exact_diagnostic_archive_and_stable_zero_validate_as_data(self):
        bridge, entry, transition = self.transition_fixture()
        pins = self.transition(transition, bridge, entry)
        self.assertTrue(pins)
        self.assertEqual(entry['old_checks_scope'], 'CAPTURED_P6_CONTEXT_ONLY')
        self.assertEqual(entry['raw']['failure'], r.FAILURE)
        for field in ('diagnostic_baseline', 'diagnostic_observation', 'diagnostic_source_archive', 'comparison'):
            changed = copy.deepcopy(transition)
            changed[field]['sha256'] = '0' * 64
            with self.subTest(field=field), self.assertRaises(c.Hold):
                self.transition(changed, bridge, entry)

    def test_transition_cannot_claim_equivalence_or_fresh_checks(self):
        bridge, entry, transition = self.transition_fixture()
        for field, value in (('old_environment_equivalence', 'PASS'), ('old_config_value_equivalence', 'PASS'),
                             ('old_checks_scope', 'CURRENT_CONTEXT'), ('goal_complete', True)):
            with self.subTest(field=field), self.assertRaises(c.Hold):
                self.transition(dict(transition, **{field: value}), bridge, entry)

    def test_nonzero_unhealthy_or_unstable_diagnostic_rejected(self):
        bridge, entry, transition = self.transition_fixture()
        actual_read = c.read_record
        for mutation in ('USER', 'close', 'metadata', 'config', 'invariant'):
            def changed(reference, kind=None):
                value = actual_read(reference, kind)
                if reference == transition['diagnostic_observation']:
                    value = copy.deepcopy(value)
                    if mutation == 'USER':
                        value['accounting']['charged'] = 1
                    elif mutation == 'close':
                        value['close']['returncode'] = 1
                    elif mutation == 'metadata':
                        value['samples'][1]['metadata']['unit-new-field'] = {'sha256': '0' * 64}
                    elif mutation == 'config':
                        value['samples'][1]['frame']['config'] = {'unit': 'changed'}
                    else:
                        value['samples'][2]['frame']['invariant_sha256'] = '0' * 64
                return value
            with self.subTest(mutation=mutation), mock.patch.object(c, 'read_record', side_effect=changed):
                with self.assertRaises((c.Hold, ValueError)):
                    self.transition(transition, bridge, entry)

    def fresh_context(self, bridge, transition):
        diagnostic = c.validate_baseline(transition['diagnostic_baseline'])
        fresh = copy.deepcopy(diagnostic)
        fresh['source_set'] = bridge['current_source_set']
        pin = self.put(fresh)
        release = dict(stage=r.P7, baseline=pin)
        graph = dict(state=fresh['state'], source_set=bridge['current_source_set'],
            manifest=fresh['manifest'], expected_environment=fresh['environment'])
        return fresh, pin, release, graph

    def test_fresh_context_requires_exact_config_metadata_env_python_state_and_native(self):
        bridge, entry, transition = self.transition_fixture()
        fresh, pin, release, graph = self.fresh_context(bridge, transition)
        actual_baseline = c.validate_baseline
        profile = c.frozen.read_record(c.frozen.read_record(entry['plan']['contract'], 'contract')['cache_profile'], 'cache-profile')
        environment = dict(r.os.environ)
        for key, value in profile['environment'].items():
            if value is None:
                environment.pop(key, None)
            else:
                environment[key] = value
        def check(candidate, current_release=release, actual_environment=environment):
            def baseline(reference):
                return candidate if reference == pin else actual_baseline(reference)
            with mock.patch.object(c, 'validate_baseline', side_effect=baseline), \
                 mock.patch.object(r.os, 'environ', actual_environment):
                return self.transition(transition, bridge, entry, current_release, graph)
        self.assertTrue(check(fresh))
        # A new context may have another PATH while selecting the exact same
        # interpreter. This does not claim execution in the new environment.
        self.assertTrue(check(fresh, actual_environment=dict(environment,
            PATH='/nonexistent-p7-context-bin:' + environment['PATH'])))
        with mock.patch.object(r.shutil, 'which', return_value=None), self.assertRaises(c.Hold):
            check(fresh)
        with mock.patch.object(r.shutil, 'which', return_value=__file__), self.assertRaises(c.Hold):
            check(fresh)
        for mutation in ('metadata', 'config', 'environment', 'state', 'native', 'P7', 'Python'):
            changed = copy.deepcopy(fresh)
            current_release = release
            actual_environment = environment
            if mutation == 'metadata':
                changed['invariant']['external_metadata']['unit-new-auth'] = {'sha256': '0' * 64}
            elif mutation == 'config':
                calls = {item['payload']['id'] for item in changed['wire'] if item['direction'] == 'request' and
                         item['payload'].get('method') == 'config/read'}
                replies = [item['payload'] for item in changed['wire'] if item['direction'] == 'response' and
                           item['payload'].get('id') in calls and 'result' in item['payload']]
                replies[-1]['result']['sha256'] = '0' * 64
            elif mutation == 'environment':
                changed['environment']['comparison_sha256'] = '0' * 64
            elif mutation == 'state':
                changed['state'] = {}
            elif mutation == 'native':
                changed['native']['snapshot']['approvalPolicy'] = 'always'
            elif mutation == 'P7':
                current_release = dict(release, stage='D2-tail/independent-review')
            else:
                actual_environment = dict(environment, PYTHONOPTIMIZE='1')
            with self.subTest(mutation=mutation), self.assertRaises(c.Hold):
                check(changed, current_release, actual_environment)

    def test_none_transition_does_not_waive_old_environment_comparison(self):
        bridge, current, entry, _ = self.bridge_fixture()
        reference = self.put(bridge)
        release = dict(stage=r.P7, predecessor=reference, campaign=bridge['campaign'],
                       source_set=bridge['current_source_set'])
        graph = dict(state=entry['state'], source_set=bridge['current_source_set'],
            scope=dict(root=entry['raw']['root'], realroot=entry['raw']['root']),
            expected_environment=dict(entry['raw']['environment'], comparison_sha256='0' * 64))
        with mock.patch.object(c, '_controlled'), mock.patch.object(c, 'validate_campaign', return_value=current), \
             mock.patch.object(c, 'validate_source_set'), mock.patch.object(r, '_reviewed_replay', return_value=[]):
            with self.assertRaisesRegex(c.Hold, 'non-nonce environment drift'):
                r.validate_bridge(reference, release=release, graph=graph)


if __name__ == '__main__':
    unittest.main()
