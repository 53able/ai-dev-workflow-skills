"""Actual saved P7 replay and strict copy/bridge rejection regressions."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import remaining_evidence as c
import remaining_evidence_p7_replay as r


class P7ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observation = dict(path=str(c.CONTROL_ROOT / 'post-TDD-P7-actual-r1/observation.json'), sha256=r.OBSERVATION_SHA)
        cls.packet = dict(path=str(c.CONTINUATION / 'post-TDD-P7-packet-audit-r1/typed-packet.json'), sha256=r.PACKET_SHA)
        cls.capability = dict(path=str(c.CONTINUATION / 'P7-capability-witness-r1/RESULT.json'), sha256=r.CAPABILITY_SHA)
        cls.actual = r.replay_actual_p7(cls.observation, cls.packet, cls.capability)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.serial = 0
        self.author = copy.deepcopy(self.actual.entry)
        self.plan = self.author['plan']
        self.before = self.author['raw']['state_before']
        self.after = self.author['state']
        self.contract = r.read_record(self.plan['contract'], 'contract')
        self.off = self.contract['roles']['off']
        self.destination = r.PREFIX + 'payload/current/' + self.off

    def put(self, value):
        self.serial += 1
        path = self.root / ('mock-control-%d.json' % self.serial)
        path.write_text(json.dumps(value))
        return c.ref(path)

    def copied(self, **changes):
        args = dict(plan=self.plan, before=self.before, after=self.after, captured_files=self.author['content'])
        args.update(changes)
        return r.copied_off_proof(**args)

    def transition(self, proof, **changes):
        args = dict(plan=self.plan, before=self.before, after=self.after, evidence=self.contract['evidence'],
                    capability_proof=self.actual.evidence['capability'], copy_proof=proof)
        args.update(changes)
        return r.validate_transition(**args)

    def test_actual_saved_replay_complete_without_relabeling_failure(self):
        self.assertIs(type(self.actual), r._ReplayedP7)
        self.assertIs(self.actual.entry, self.actual.entries[0])
        self.assertIsNone(self.actual.bridge)
        self.assertIsNone(self.actual.bridge_ref)
        self.assertEqual(self.actual.evidence['packet_audit']['endpoints'], 36)
        self.assertEqual(len(self.actual.evidence['packet_audit']['payloads']), 12)
        self.assertEqual(self.actual.evidence['packet_audit']['origins'], 27)
        self.assertEqual(self.actual.entry['raw']['failure']['primary']['stage'], 'transition')
        self.assertFalse(self.actual.entry['raw']['business_PASS'])
        self.assertFalse(self.actual.evidence['runtime_admission'])
        self.assertEqual(self.actual.evidence['new_model_USER'], 0)

    def test_transition_ast_diff_is_only_optional_proof_and_mode_selection(self):
        def node(module):
            return next(value for value in ast.parse(Path(module.__file__).read_text()).body
                        if isinstance(value, ast.FunctionDef) and value.name == 'validate_transition')
        actual, original = node(r), node(r.f)
        self.assertEqual(actual.args.args[-1].arg, 'copy_proof')
        actual.args.args.pop()
        actual.args.defaults.pop()
        assignments = [value for value in ast.walk(actual) if isinstance(value, ast.Assign) and
                       any(isinstance(target, ast.Name) and target.id == 'expected_mode' for target in value.targets)]
        original_assignments = [value for value in ast.walk(original) if isinstance(value, ast.Assign) and
                       any(isinstance(target, ast.Name) and target.id == 'expected_mode' for target in value.targets)]
        self.assertEqual(ast.unparse(assignments[0].value), '_copied_mode(copy_proof, plan, before, after, path, item)')
        assignments[0].value = original_assignments[0].value
        self.assertEqual(ast.dump(actual), ast.dump(original))

    def test_exact_600_copy_passes_and_missing_or_untyped_proof_fails(self):
        proof = self.copied()
        self.assertIs(type(proof), r._CopiedOffProof)
        self.assertFalse(self.transition(proof)['business_PASS'])
        for invalid in (None, dict(proof)):
            with self.subTest(proof=type(invalid).__name__), self.assertRaises(c.Hold):
                self.transition(invalid)
        with self.assertRaises(c.Hold):
            self.transition(proof, capability_proof=None)

    def test_copy_rejects_changed_bytes_modes_original_and_aliases(self):
        for mutation in ('bytes', 'destination_mode', 'source_mode', 'source_change', 'alias', 'physical_path'):
            after, content = copy.deepcopy(self.after), dict(self.author['content'])
            if mutation == 'bytes':
                content[self.destination] += b'x'
            elif mutation == 'destination_mode':
                after[self.destination]['mode'] = '0o644'
            elif mutation == 'source_mode':
                after[self.off]['mode'] = '0o644'
            elif mutation == 'source_change':
                after[self.off]['sha256'] = '0' * 64
            elif mutation == 'alias':
                after[self.destination]['identity'] = after['app/settings.py']['identity']
            else:
                after[self.destination]['realpath'] = '/other/copied-off.json'
            with self.subTest(mutation=mutation), self.assertRaises(c.Hold):
                self.copied(after=after, captured_files=content)

    def test_copy_does_not_admit_other_600_paths_or_foreign_proof_endpoints(self):
        other = next(path for path in self.contract['roles']['packet'] if path != self.destination)
        after = copy.deepcopy(self.after)
        after[other]['mode'] = '0o600'
        proof = self.copied(after=after)
        with self.assertRaises(c.Hold):
            self.transition(proof, after=after)
        proof = self.copied()
        proof['destination'] = other
        with self.assertRaises(c.Hold):
            self.transition(proof)
        proof = self.copied()
        proof['after'] = '0' * 64
        with self.assertRaises(c.Hold):
            self.transition(proof)

    def test_foreign_observation_and_archive_rejected(self):
        with self.assertRaises(c.Hold):
            r._actual_entry(dict(self.observation, sha256='0' * 64))
        with self.assertRaises(c.Hold):
            r._historical_source30(self.author['release']['source_set'], dict(
                path=str(c.CONTINUATION / 'remaining-evidence-source-freeze-r9/INDEX.json'), sha256='0' * 64))
        real_ref = r.f.ref
        def changed(path, **kwargs):
            value = real_ref(path, **kwargs)
            return dict(value, sha256='0' * 64) if str(path).endswith('remaining_evidence.py.bin') else value
        with mock.patch.object(r.f, 'ref', side_effect=changed), self.assertRaises(c.Hold):
            r._historical_source30(self.author['release']['source_set'], self.actual.evidence['archive'])

    def test_unhealthy_non1_or_foreign_failure_raw_rejected(self):
        read = c.read_record
        for mutation in ('close', 'USER', 'failure'):
            def changed(reference, kind=None):
                value = read(reference, kind)
                if reference == self.observation:
                    value = copy.deepcopy(value)
                    if mutation == 'close':
                        value['close']['returncode'] = 1
                    elif mutation == 'USER':
                        value['accounting']['charged'] = 2
                    else:
                        value['failure']['primary']['stage'] = 'turn-in-flight'
                return value
            with self.subTest(mutation=mutation), mock.patch.object(c, 'read_record', side_effect=changed):
                with self.assertRaises((c.Hold, ValueError)):
                    r._actual_entry(self.observation)

    def test_unsafe_capability_witness_cannot_be_inferred_from_old_hold(self):
        read = r.read_ref
        for mutation in ('close', 'USER', 'capability', 'producer', 'config', 'state'):
            def changed(reference, **kwargs):
                data = read(reference, **kwargs)
                if reference == self.capability:
                    value = json.loads(data)
                    if mutation == 'close':
                        value['close']['returncode'] = 1
                    elif mutation == 'USER':
                        value['model_USER'] = 1
                    elif mutation == 'capability':
                        value['capability']['agents_enabled'] = True
                    elif mutation == 'producer':
                        value['producer']['sha256'] = '0' * 64
                    elif mutation == 'config':
                        value['config_receipt']['sha256'] = '0' * 64
                    else:
                        value['after_sha256'] = '0' * 64
                    data = json.dumps(value).encode()
                return data
            with self.subTest(mutation=mutation), mock.patch.object(r, 'read_ref', side_effect=changed):
                with self.assertRaises((c.Hold, ValueError)):
                    r._capability(self.capability, self.author)

    def test_fake_packet_semantic_origin_rejected(self):
        import remaining_evidence_handoff as h
        read = h.f.read_ref
        def changed(reference, **kwargs):
            data = read(reference, **kwargs)
            if reference == self.packet:
                packet = json.loads(data)
                packet['origins']['/scope'][0]['sha256'] = '0' * 64
                return json.dumps(packet).encode()
            return data
        baseline = c.validate_baseline(self.author['release']['baseline'])
        with mock.patch.object(h.f, 'read_ref', side_effect=changed), self.assertRaises(c.Hold):
            h._packet(self.packet, self.author, self.actual.entries, self.actual.contexts,
                      self.actual.captures, dict(manifest=baseline['manifest']))

    def test_alternate_handoff_only_origins_still_validate_all_actual_endpoints(self):
        packet = r.f.read_record(self.packet, 'review-packet')
        for pointer, origins in packet['origins'].items():
            handoff = [origin for origin in origins if origin.get('kind') == 'artifact' and
                       origin.get('path', '').endswith('/HANDOFF.md')]
            self.assertEqual(len(handoff), 1)
            packet['origins'][pointer] = handoff
        alternate = self.put(packet)
        # Unit alternate wrapper is temporary; production requires protected C.
        with mock.patch.object(r, '_protected_reference'):
            proof = r.replay_actual_p7(self.observation, alternate, self.capability)
        self.assertEqual(proof.evidence['packet'], alternate)
        self.assertEqual(proof.evidence['packet_audit']['endpoints'], 36)
        self.assertEqual(proof.evidence['packet_audit']['origins'], 27)

    def test_changed_saved_new_context_is_not_waived(self):
        baseline = c.validate_baseline(self.author['release']['baseline'])
        baseline['invariant']['external_metadata']['changed-auth'] = {'sha256': '0' * 64}
        with self.assertRaises(c.Hold):
            r._old_chain(self.author, baseline)

    def test_old_source30_cannot_be_current_runtime_source32(self):
        with self.assertRaises(c.Hold):
            c.validate_source_set(self.author['release']['source_set'])

    def bridge_fixture(self):
        # Temporary mock control data only: never an actual adoption/release.
        original = r.f.read_record(dict(path=str(c.FROZEN_SOURCE_SET), sha256=c.FROZEN_SOURCE_SET_SHA), 'source-set')
        source = dict(schema='remaining-source-set-v1', files=original['files'] +
                      [c.ref(c.HERE / name, executable=True) for name in c.NEW_SOURCES],
                      official_sources=original['official_sources'])
        source_ref = self.put(source)
        old_campaign = c.read_record(self.author['raw']['campaign'], 'campaign')
        campaign_ref = self.put(dict(old_campaign, source_set=source_ref))
        result = self.put(self.actual.evidence)
        review = self.put(dict(verdict='APPROVE', issues=0, reviewer='Unit mock reviewer',
            reviewed=[c.ref(c.HERE / 'remaining_evidence_p7_replay.py'), c.ref(c.HERE / 'remaining_evidence_p7_replay_test.py'),
                      result, self.packet, self.capability], independent_recomputed_exact_result=True,
            runtime_admission=False, assessment_admission=False, goal_complete=False))
        adoption = self.put(dict(decision='ROOT_ADOPT_EXACT_SAVED_P7_REPLAY_FOR_P8', actor='Root',
            observation=self.observation, packet=self.packet, capability_witness=self.capability,
            replay_result=result, review=review, current_source_set=source_ref, accounting=r.ACCOUNTING,
            preserved_failures=c.FAILURES, inherited_failures=c.RECOVERY_FAILURES, raw_failure_preserved=True,
            no_retry=True, no_extra_capacity=True, judgment='Unit mock only, not actual Root adoption.'))
        bridge = dict(schema='remaining-p7-replay-bridge-v1', campaign=campaign_ref, current_source_set=source_ref,
            historical_campaign=self.author['raw']['campaign'], historical_source_set=self.author['release']['source_set'],
            archive=self.actual.evidence['archive'], observation=self.observation, packet=self.packet,
            capability_witness=self.capability, replay_result=result, review=review, adoption=adoption,
            verdicts={name: dict(verdict='PASS', sources=[self.observation], judgment='Unit mock finding.')
                      for name in c.OBLIGATIONS[r.P7]}, preserved_failures=c.FAILURES,
            inherited_failures=c.RECOVERY_FAILURES, admissible_for=[r.P8], goal_complete=False)
        return bridge

    def test_typed_bridge_binds_exact_current_P8_without_projection_state_waiver(self):
        bridge = self.bridge_fixture()
        reference = self.put(bridge)
        release = dict(stage=r.P8, predecessor=reference, campaign=bridge['campaign'], source_set=bridge['current_source_set'])
        graph = dict(campaign=bridge['campaign'], source_set=bridge['current_source_set'])
        with mock.patch.object(c, '_controlled'), mock.patch.object(r, '_protected_reference'):
            proof = r.validate_p7_bridge(reference, release=release, graph=graph)
        self.assertIs(type(proof), r._ReplayedP7)
        self.assertEqual(proof.bridge_ref, reference)
        self.assertIs(proof.entry, proof.entries[0])
        self.assertEqual(proof.entry['raw']['failure'], self.author['raw']['failure'])
        for mutation in ('stage', 'campaign'):
            changed = dict(release, **{mutation: 'foreign'})
            with self.subTest(mutation=mutation), mock.patch.object(c, '_controlled'), \
                 mock.patch.object(r, '_protected_reference'), self.assertRaises(c.Hold):
                r.validate_p7_bridge(reference, release=changed, graph=graph)


if __name__ == '__main__':
    unittest.main()
