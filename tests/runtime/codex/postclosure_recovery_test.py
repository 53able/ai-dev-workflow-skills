#!/usr/bin/env python3
"""Recovery contracts: read-only historical replay and owned temporary mock records."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import postclosure_recovery as c


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.serial = 0

    def put(self, value):
        self.serial += 1
        path = self.root / ('record-%d.json' % self.serial)
        path.write_text(json.dumps(value, ensure_ascii=False))
        return c.ref(path)

    def closed(self):
        return c.decode(c.read_ref(c.CLOSED_HISTORY))

    def prefix(self):
        value = dict(schema='postclosure-recovery-prefix-v1', branch_id=c.BRANCH_ID,
                     legacy_prefix=c.ref(c.OLD_CONTROL_ROOT / 'postclosure-P1-preparation-data/legacy-prefix.json'),
                     closed_history=c.CLOSED_HISTORY, old_source_set=c.OLD_SOURCE_SET,
                     new_source_set=self.put(dict(schema='postclosure-source-set-v1', files=[], official_sources=[])),
                     planning_decision=c.ref(c.OLD_CONTROL_ROOT / 'recovery-planning-r1/ROOT-PLANNING-DECISION.json'),
                     funding_selection=self.put({'data': 'mock selection; never adopted'}),
                     expected_actual=76, expected_held=31, whole=107, reserve=1)
        value['prefix_sha256'] = c.canonical_hash(value)
        return value

    def test_original_eleven_and_historical_replay_remain_closed(self):
        old = c.load_old_core()
        closed = self.closed()
        prefix = old.read_record(c.ref(c.OLD_CONTROL_ROOT / 'postclosure-P1-preparation-data/legacy-prefix.json'), 'legacy-prefix')
        old.validate_legacy(prefix)
        replay = old.validate_history(c.LEGACY_PREFIX_SHA, closed['closed_results'], closed['branch'],
                                      c.OLD_SOURCE_SET, closed['invariant_anchor'])
        self.assertEqual(replay, closed['accounting'])
        self.assertEqual((replay['actual'], replay['held'], replay['whole'], replay['blocked']), (76, 30, 106, True))
        self.assertEqual(len(c.old_source_set()['files']), 11)

    def test_genuine_prefix_hash_binds_every_field(self):
        value = self.prefix()
        with mock.patch.object(c, 'CONTROL_ROOT', self.root), mock.patch.object(c, 'validate_source_set'):
            self.assertEqual(c.validate_recovery_prefix(self.put(value)), value)
            changed = copy.deepcopy(value)
            changed['new_source_set'] = self.put({'different': True})
            with self.assertRaisesRegex(c.Hold, 'complete recovery prefix hash'):
                c.validate_recovery_prefix(self.put(changed))

    def test_prefix_refund_whole_and_omission_rejected(self):
        for key, replacement in [('expected_actual', 75), ('expected_held', 32), ('whole', 106), ('reserve', True)]:
            value = self.prefix()
            value[key] = replacement
            value['prefix_sha256'] = c.canonical_hash({k: v for k, v in value.items() if k != 'prefix_sha256'})
            with self.subTest(key=key), mock.patch.object(c, 'CONTROL_ROOT', self.root), self.assertRaises(c.Hold):
                c.validate_recovery_prefix(self.put(value))
        value = self.prefix()
        del value['closed_history']
        with mock.patch.object(c, 'CONTROL_ROOT', self.root), self.assertRaises(c.Hold):
            c.validate_recovery_prefix(self.put(value))

    def test_prefix_cannot_use_old_control_location(self):
        with self.assertRaisesRegex(c.Hold, 'outside current control root'):
            c.validate_recovery_prefix(c.CLOSED_HISTORY)

    def test_new_history_starts_after_both_charges(self):
        result = c.validate_history('a' * 64, [], c.BRANCH_ID)
        self.assertEqual((result['actual'], result['held'], result['whole'], result['contexts']), (76, 31, 107, 0))
        self.assertFalse(result['blocked'])
        self.assertEqual(result['history_sha256'], 'a' * 64)
        self.assertEqual(list(c.ROWS.values()), ['deadline-repair/tasks-initial/1', 'R7/spec/6', 'R7/spec/7',
            'R7/spec/8', 'R7/spec/9', 'unavailable-review/1', 'independent-review/1', 'R7/spec/10', 'R7/tasks/3'])
        self.assertNotIn('D2-tail/spec-approval', c.ROWS)

    def test_old_results_cannot_be_new_history(self):
        closed = self.closed()
        for records in (closed['closed_results'], closed['closed_results'][::-1], closed['accepted_results_only']):
            with self.subTest(records=records), self.assertRaises(c.Hold):
                c.validate_history('a' * 64, records, c.BRANCH_ID)

    def test_recovery_dispatch_is_first_row_only(self):
        pin = self.put(dict(schema='postclosure-recovery-decision-v1', predecessor=self.put({}),
                            final_message=self.put({}), request='Create draft tasks after failed transport.',
                            reviewed_artifacts=[self.put({})], actor='Root'))
        plan = {'row_id': 'D2-tail/tasks-initial', 'input': pin}
        self.assertEqual(c.read_input_decision(plan)['actor'], 'Root')
        plan['row_id'] = 'D2-tail/plan-approval'
        with self.assertRaisesRegex(c.Hold, 'wrong record kind'):
            c.read_input_decision(plan)
        value = c.decode(c.read_ref(pin)); value['question'] = value['final_message']
        with self.assertRaisesRegex(c.Hold, 'closed fields'):
            c.validate_record(value)

    def test_consumed_old_donor_rejected_before_claim(self):
        old = mock.Mock(BRANCH_ID='old', CLAIM_ROOT=self.root)
        old.claim_path.return_value = self.root / 'consumed'
        old.claim_path.return_value.write_text('retained claim')
        with mock.patch.object(c, 'load_old_core', return_value=old), self.assertRaisesRegex(c.Hold, 'already claimed'):
            c.validate_unspent_transfers()

    def test_dangling_donor_alias_is_not_unspent(self):
        old = mock.Mock(BRANCH_ID='old', CLAIM_ROOT=self.root)
        old.claim_path.return_value = self.root / 'alias'
        old.claim_path.return_value.symlink_to(self.root / 'missing')
        with mock.patch.object(c, 'load_old_core', return_value=old), self.assertRaises(c.Hold):
            c.validate_unspent_transfers()

    def test_exclusive_new_claim_has_no_second_attempt(self):
        release = self.put({'mock': 'release'})
        with mock.patch.object(c, 'CLAIM_ROOT', self.root), mock.patch.object(c, 'validate_unspent_transfers'):
            path = c.acquire_claim(c.BRANCH_ID, list(c.ROWS)[0], self.root, release)
            first = path.read_bytes()
            with self.assertRaises(FileExistsError):
                c.acquire_claim(c.BRANCH_ID, list(c.ROWS)[0], self.root, release)
            self.assertEqual(path.read_bytes(), first)
            with self.assertRaises(c.Hold):
                c.acquire_claim('old branch', list(c.ROWS)[0], self.root, release)

    def funding(self):
        retired = ['R7/AC9-handoff/5'] + ['R7/localship/%d' % n for n in range(1, 6)] + ['R7/scope-invalidation/1', 'R7/scope-invalidation/2']
        selection = dict(schema='postclosure-recovery-funding-selection-v1', branch_id=c.BRANCH_ID,
                         new_slot_mapping=[{'from': donor, 'to': row} for row, donor in c.ROWS.items()],
                         new_capacity=1, transferred=list(c.ROWS.values())[1:], retained_other=13,
                         retired_nonspendable=retired, reserve=1, source_activation=False, runtime_release=False)
        selected = self.put(selection)
        prefix_ref = self.put({'mock': 'prefix'})
        adopted = dict(schema='postclosure-recovery-funding-adoption-v1', selection=selected,
                       recovery_prefix=prefix_ref, branch_id=c.BRANCH_ID, mapping=selection['new_slot_mapping'],
                       new_capacity=1, transferred=selection['transferred'], retained_other=13, retired=retired,
                       reserve=1, decision='ADOPT_EXACT_RECOVERY_NINE_ONLY')
        admission = dict(branch_id=c.BRANCH_ID, funding_selection=selected, funding_adoption=self.put(adopted), recovery_prefix=prefix_ref)
        return selection, adopted, admission, {'funding_selection': selected}

    def test_exact_nine_donors_and_eight_transfers(self):
        _, _, admission, prefix = self.funding()
        with mock.patch.object(c, 'CONTROL_ROOT', self.root), mock.patch.object(c, 'validate_unspent_transfers'):
            c.validate_funding(admission, prefix)
        self.assertEqual(76 + len(c.ROWS) + 13 + 8 + 1, c.WHOLE)
        self.assertEqual((76 + 9, 107 - 76 - 9), (85, 22))
        self.assertEqual((76 + 9 + 13, 107 - 76 - 9 - 13), (98, 9))

    def test_funding_alias_consumed_duplicate_retired_reserve_and_refund_rejected(self):
        mutations = [lambda x: x['new_slot_mapping'][0].update({'from': 'R7/spec/5'}),
                     lambda x: x['new_slot_mapping'][1].update({'from': x['new_slot_mapping'][0]['from']}),
                     lambda x: x.update(new_capacity=2), lambda x: x.update(new_capacity=True),
                     lambda x: x.update(reserve=0), lambda x: x.update(retained_other=12),
                     lambda x: x['transferred'].append('reserve/1'),
                     lambda x: x['retired_nonspendable'].__setitem__(0, list(c.ROWS.values())[1]),
                     lambda x: x['retired_nonspendable'].__setitem__(0, 'invented-retired-donor')]
        for mutate in mutations:
            selection, _, admission, prefix = self.funding()
            mutate(selection)
            admission['funding_selection'] = prefix['funding_selection'] = self.put(selection)
            with mock.patch.object(c, 'CONTROL_ROOT', self.root), self.assertRaises(c.Hold):
                c.validate_funding(admission, prefix)

    def test_original_source_identity_and_extra_alias_rejected(self):
        original = c.old_source_set()
        # Missing current recovery files cannot be presented as a current epoch.
        with self.assertRaises(c.Hold):
            c.validate_source_set(original)
        if all((c.HERE / name).exists() for name in ('postclosure_recovery_operator.py', 'postclosure_recovery_controller.py',
                'postclosure_recovery_operator_test.py', 'postclosure_deadline.py', 'postclosure_deadline_test.py')):
            names = ('postclosure_recovery.py', 'postclosure_recovery_operator.py', 'postclosure_recovery_controller.py',
                     'postclosure_recovery_test.py', 'postclosure_recovery_operator_test.py', 'postclosure_deadline.py', 'postclosure_deadline_test.py')
            current = dict(schema='postclosure-source-set-v1', files=original['files'] + [c.ref(c.HERE / n, executable=True) for n in names],
                           official_sources=original['official_sources'])
            c.validate_source_set(current)
            current['files'][-1] = current['files'][-2]
            with self.assertRaises(c.Hold):
                c.validate_source_set(current)

    def bootstrap(self):
        closed = self.closed()
        accepted_ref = closed['closed_results'][0]
        accepted = c.read_record(accepted_ref, 'independent-result')
        previous = c.read_record(accepted['context'], 'context')
        spec = 'docs/changes/2026-10-25-order-confirmation-email-toggle/spec.md'
        tasks = spec.replace('spec.md', 'tasks.md')
        item = previous['wire'][150]['payload']['params']['item']
        message = self.put(dict(schema='postclosure-final-message-v1', context=accepted['context'], wire_index=150,
                                item_sha256=c.canonical_hash(item), text=item['text']))
        prefix_ref = self.put({'mock': 'prefix reference'})
        predecessor = dict(schema='postclosure-recovery-predecessor-v1', context=accepted['context'],
                           independent_result=accepted_ref, state=self.put(previous['state_after']),
                           final_message=message, recovery_prefix=prefix_ref)
        predecessor_ref = self.put(predecessor)
        plan = dict(row_id='D2-tail/tasks-initial', donor_slot=list(c.ROWS.values())[0], predecessor=predecessor_ref)
        decision = dict(schema='postclosure-recovery-decision-v1', predecessor=predecessor_ref, final_message=message,
                        request='Create draft tasks from the approved spec after the failed attempt; stop for plan review.',
                        reviewed_artifacts=[{'path': str(Path(previous['root']) / spec), 'sha256': previous['state_after'][spec]['sha256']}], actor='Root')
        return plan, predecessor, decision, {'closed_history': c.CLOSED_HISTORY}, dict(root=previous['root'], realroot=previous['root']), previous['state_after'], {'roles': {'spec': spec, 'tasks': tasks}}, prefix_ref

    def test_actual_p1_ack_bootstrap_and_changed_state_rejection(self):
        args = self.bootstrap()
        with mock.patch.object(c, 'plan_prefix', return_value=args[-1]):
            c.validate_recovery_bootstrap(*args[:-1])
            changed = copy.deepcopy(args[:-1]); changed[5]['unexpected'] = {'kind': 'file'}
            with self.assertRaisesRegex(c.Hold, 'physical state'):
                c.validate_recovery_bootstrap(*changed)

    def test_failed_p2_is_never_business_predecessor(self):
        args = self.bootstrap()
        args[1]['independent_result'] = self.closed()['closed_results'][1]
        with mock.patch.object(c, 'plan_prefix', return_value=args[-1]), self.assertRaisesRegex(c.Hold, 'accepted P1 only'):
            c.validate_recovery_bootstrap(*args[:-1])

    def test_fake_ack_and_ack_as_instruction_rejected(self):
        args = self.bootstrap()
        message = c.read_record(args[1]['final_message'], 'final-message')
        args[2]['request'] = message['text']
        with mock.patch.object(c, 'plan_prefix', return_value=args[-1]), self.assertRaisesRegex(c.Hold, 'separate genuine Root'):
            c.validate_recovery_bootstrap(*args[:-1])
        message['text'] = 'Synthetic approval question?'
        args[1]['final_message'] = self.put(message)
        with mock.patch.object(c, 'plan_prefix', return_value=args[-1]), self.assertRaisesRegex(c.Hold, 'completed ACK'):
            c.validate_recovery_bootstrap(*args[:-1])

    def test_observed_new_anchor_only_and_epoch_drift(self):
        closed = self.closed()
        anchor = c.read_record(closed['invariant_anchor'], 'invariant-anchor')
        with self.assertRaisesRegex(c.Hold, 'new owned observed anchor'):
            c.validate_recovery_anchor(closed['invariant_anchor'], anchor)
        fresh = copy.deepcopy(anchor)
        fresh['environment']['sha256'] = 'a' * 64
        with mock.patch.object(c, 'CONTROL_ROOT', self.root):
            pin = self.put(fresh)
            self.assertEqual(c.validate_recovery_anchor(pin, fresh), fresh)
            changed = copy.deepcopy(fresh); changed['catalog'] = {}
            with self.assertRaisesRegex(c.Hold, 'baseline drift'):
                c.validate_recovery_anchor(self.put(changed), changed)
            with self.assertRaisesRegex(c.Hold, 'lifetime'):
                c.validate_recovery_anchor(pin, changed)

    def test_all_semantic_guard_bodies_preserved(self):
        def bodies(path):
            return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(path.read_text()).body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        original = bodies(c.HERE / 'postclosure.py')
        recovery = bodies(c.HERE / 'postclosure_recovery.py')
        allowed = {'validate_record', 'validate_source_set', 'validate_funding', 'acquire_claim', 'validate_history',
                   'validate_sample_replay', 'validate_lookup', 'validate_lookup_command', 'validate_source_slice',
                   'validate_adjudication', 'installed_review_reads', 'validate_review_projection', 'validate_graph'}
        changed = {name for name in original if original[name] != recovery[name]}
        self.assertLessEqual(changed, allowed)
        for name in ('validate_capability', 'validate_bundle', 'validate_cache', 'validate_derived_caches',
                     'validate_review_capture', 'validate_f1_adjudication', 'validate_git_rollback', 'validate_transition'):
            self.assertEqual(original[name], recovery[name], name)


if __name__ == '__main__':
    unittest.main()
