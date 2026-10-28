"""Isolated contract tests. No model/native process, actual donor or fixture edits."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import remaining_evidence as c


class EvidenceContracts(unittest.TestCase):
    def test_old_temporary_write_extent_accepts_os_trailing_separator(self):
        snapshot = dict(runtimeWorkspaceRoots=['/owned-old'], activePermissionProfile=None,
            sandbox=dict(type='workspaceWrite', writableRoots=[]))
        roots = c._recovery_write_roots(snapshot, '/private/tmp/synthetic-temp/')
        self.assertIn(Path('/private/tmp/synthetic-temp').resolve(), roots)
        self.assertEqual(snapshot['runtimeWorkspaceRoots'], ['/owned-old'])
        with self.assertRaises(c.Hold):
            c._recovery_write_roots(snapshot, '/private/tmp/../unreviewed/')

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        claim_root = mock.patch.object(c, 'CLAIM_ROOT', self.root / 'claims')
        claim_root.start()
        self.addCleanup(claim_root.stop)
        self.serial = 0

    def put(self, value):
        self.serial += 1
        p = self.root / ('record-%d.json' % self.serial)
        p.write_text(json.dumps(value, ensure_ascii=False))
        return c.ref(p)

    def campaign(self):
        old = c.CONTINUATION
        return dict(schema='remaining-campaign-v1', branch_id=c.BRANCH_ID,
            planning=c.ref(old / 'remaining-evidence-planning-r1/ROOT-PLANNING-DECISION.json'),
            historical_snapshot=c.frozen.CLOSED_HISTORY,
            saved_task_audit=c.ref(old / 'recovery-tasks-saved-audit-r2/RESULT.json'),
            failed_result=c.ref(old / 'postclosure-recovery-r1/tasks-initial-failure-adoption-r1/rejected-result.json'),
            relocation=c.ref(old / 'reset-recovery-r1/RESULT.json'),
            source_set=self.put(dict(schema='remaining-source-set-v1', files=[], official_sources=[])),
            rows=dict(c.ROWS), accounting=dict(c.ACCOUNTING), preserved_failures=dict(c.FAILURES))

    def test_saved_history_remains_usable_without_old_physical_fixture(self):
        value = self.campaign()
        with mock.patch.object(c, 'CONTROL_ROOT', self.root), mock.patch.object(c, 'validate_source_set'):
            result = c.validate_campaign(self.put(value))
        self.assertEqual(result['accounting']['actual_arithmetic'], 77)
        self.assertEqual(result['preserved_failures']['plan_question'], 'FAIL')
        old = c.frozen.decode(c.read_ref(c.frozen.CLOSED_HISTORY))
        self.assertTrue(old['accounting']['blocked'])
        self.assertEqual(old['accounting']['actual'], 76)

    def test_campaign_refund_budget_retry_or_failure_erasure_rejected(self):
        for key, replacement in [('actual_arithmetic', 76), ('planning_whole', 108),
                                  ('prospective_held', True)]:
            value = self.campaign(); value['accounting'][key] = replacement
            with self.subTest(key=key), mock.patch.object(c, 'CONTROL_ROOT', self.root), self.assertRaises(c.Hold):
                c.validate_campaign(self.put(value))
        value = self.campaign(); value['preserved_failures']['plan_question'] = 'PASS'
        with mock.patch.object(c, 'CONTROL_ROOT', self.root), self.assertRaises(c.Hold):
            c.validate_campaign(self.put(value))

    def test_only_nonce_is_comparable_without_modifying_actual_environment(self):
        original = {'PATH': '/bin', 'CODEX_TOOL_CALL_ID': 'one', 'PYTHONPATH': ''}
        kept = dict(original)
        first = c.environment_identity(original)
        second = c.environment_identity(dict(original, CODEX_TOOL_CALL_ID='two'))
        c.validate_current_environment(second, first)
        self.assertNotEqual(first['full_sha256'], second['full_sha256'])
        self.assertEqual(first['comparison_sha256'], second['comparison_sha256'])
        self.assertEqual(original, kept)
        for drift in ({'PATH': '/other'}, {'PYTHONPATH': '/injected'}, {'NEW': 'value'}):
            with self.subTest(drift=drift), self.assertRaises(c.Hold):
                c.validate_current_environment(c.environment_identity(dict(original, **drift)), first)
        malicious = dict(second, excluded_keys=['CODEX_TOOL_CALL_ID', 'PATH'])
        with self.assertRaises(c.Hold):
            c.validate_current_environment(malicious, first)

    def test_absent_nonce_is_explicit_and_only_string_actual_environment_allowed(self):
        a = c.environment_identity({'PATH': '/bin'})
        self.assertIs(a['nonce_present'], False); self.assertIsNone(a['nonce_sha256'])
        c.validate_current_environment(c.environment_identity({'PATH': '/bin', 'CODEX_TOOL_CALL_ID': 'new'}), a)
        for value in ({'PATH': None}, {'PATH': 1}, {'PATH': True}):
            with self.assertRaises(c.Hold):
                c.environment_identity(value)

    def test_source_set_has_exact_original_eighteen_and_current_owned_sources(self):
        original = c.frozen.read_record(c.ref(c.FROZEN_SOURCE_SET), 'source-set')
        value = dict(schema='remaining-source-set-v1', files=original['files'] +
                     [c.ref(c.HERE / name, executable=True) for name in c.NEW_SOURCES],
                     official_sources=original['official_sources'])
        with mock.patch.object(c, 'CONTROL_ROOT', self.root):
            self.assertEqual(len(c.validate_source_set(self.put(value))['files']), 18 + len(c.NEW_SOURCES))
            missing = copy.deepcopy(value); missing['files'].pop()
            with self.assertRaises(c.Hold):
                c.validate_source_set(self.put(missing))
            substituted = copy.deepcopy(value)
            substituted['files'][-1] = substituted['files'][-2]
            with self.assertRaises(c.Hold):
                c.validate_source_set(self.put(substituted))
            historical = copy.deepcopy(value)
            historical['files'] = historical['files'][:26]
            with self.assertRaisesRegex(c.Hold, 'exact original18 plus current owned source closure'):
                c.validate_source_set(self.put(historical))

    def test_historical_source_override_cannot_admit_runtime(self):
        from remaining_evidence_replay import _HistoricalSources
        with self.assertRaisesRegex(c.Hold, 'historical sources cannot admit a current runtime'):
            c.validate_recovery_seed(self.put({}), historical_sources={'sources': 'untrusted'})
        proof = _HistoricalSources.__new__(_HistoricalSources)
        with self.assertRaisesRegex(c.Hold, 'historical sources cannot admit a current runtime'):
            c.validate_recovery_seed(self.put({}), historical_sources=proof, graph={'stage': 'runtime'})

    def test_closed_schema_cannot_sneak_question_or_authority_fields(self):
        decision = dict(schema='remaining-decision-v1', stage=next(iter(c.ROWS)),
            input='Approve only the reviewed draft plan status.', authority_kind='proactive_plan_approval',
            reviewed_artifacts=[self.put({'mock': 'draft'})], actor='Root', prerequisite_evidence=[])
        c.validate_record(decision, 'decision')
        for extra in ('question', 'final_message', 'ignore_failure', 'automatic_retry'):
            with self.subTest(extra=extra), self.assertRaises(c.Hold):
                c.validate_record(dict(decision, **{extra: True}), 'decision')
        with self.assertRaises(c.Hold):
            c.validate_record(dict(decision, actor='model'), 'decision')

    def policy_pair(self, permission=None):
        pin = self.put({'mock': 'control'})
        zero = dict(schema='postclosure-process-policy-v1', row_plan=pin, scope=pin,
            argv=['/fixture/codex'], session={}, session_sha256='0' * 64,
            metadata_paths={}, native_expectation=pin, official_sources=[], turn_permission=None)
        return zero, dict(zero, turn_permission=permission)

    def test_stage_policy_admits_only_exact_git_turn_permission_difference(self):
        grant = self.put({'mock': 'separately validated by frozen Git guard'})
        zero, business = self.policy_pair(grant)
        command = self.put({'schema': 'remaining-observe-command-v1', **dict(
            campaign=zero['scope'], scope=zero['scope'], policy=self.put(zero),
            native_binding=zero['scope'], manifest=zero['scope'], source_set=zero['scope'],
            output=str(self.root / 'zero'), expected_state=zero['scope'],
            environment=c.environment_identity({'PATH': '/bin'}))})
        baseline = {'command': command}
        release = {'stage': 'D2-tail/Git-AC9', 'policy': self.put(business)}
        self.assertEqual(c.stage_policy_relation(release, baseline), release['policy'])
        for key, replacement in [('argv', ['/unreviewed/codex']), ('scope', grant),
                                  ('metadata_paths', {'extra': True}), ('turn_permission', None)]:
            changed = dict(business, **{key: replacement})
            with self.subTest(key=key), self.assertRaises(c.Hold):
                c.stage_policy_relation(dict(release, policy=self.put(changed)), baseline)
        with self.assertRaises(c.Hold):
            c.stage_policy_relation(dict(release, stage='D2-tail/plan-approval'), baseline)

    def test_task_progress_is_validated_before_any_claim_or_launch(self):
        workspace = self.root / 'progress-workspace'; workspace.mkdir()
        path = workspace / 'tasks.md'
        body = b'---\nstatus: approved\n---\n\n# Tasks\n\n- [ ] T1\n\n## Notes\nOld note\n'
        path.write_bytes(body)
        state = {'tasks.md': dict(kind='file', sha256=c.ref(path)['sha256'])}
        stage = 'D2-tail/content-to-operation-question'
        contract = dict(row_id=stage, roles=dict(spec='spec.md', tasks='tasks.md',
            application=[], tests=[], callers=[], progress=[], packet=[], review=None,
            local_pr=None, off=None), authored=['tasks.md'], derived=[], immutable_paths=[],
            expected_before=c.canonical_hash(state), expected_after=None,
            obligations=c.OBLIGATIONS[stage], evidence={}, git_profile=None,
            cache_profile=None, capability_profile=None, tasks_progress=None)
        graph = dict(state=state, graph_pins={}, scope={'realroot': str(workspace)})
        plan = dict(row_id=stage, feasibility=None)
        valid = dict(path='tasks.md', checkboxes=[6], memo_heading='## Notes', max_memo_bytes=128)
        for progress in (None, {}, dict(valid, checkboxes=[0]), dict(valid, checkboxes=[True]),
                         dict(valid, memo_heading='## Missing'), dict(valid, max_memo_bytes=1)):
            with self.subTest(progress=progress), self.assertRaises(c.Hold):
                c._profile_pins(graph, plan, dict(contract, tasks_progress=progress))
        c._profile_pins(graph, plan, dict(contract, tasks_progress=valid))
        with self.assertRaises(c.Hold):
            c._profile_pins(graph, plan, dict(contract, authored=[], tasks_progress=valid))

    def test_distinct_reviewer_identity_requires_projection_and_return_validators(self):
        import remaining_evidence_handoff as handoff
        bridge = self.put({'mock': 'explicit captured handoff'})
        predecessor = self.put({'mock': 'actual predecessor assessment'})
        evidence = self.put({'mock': 'immutable source bytes'})
        for stage, method in (('D2-tail/independent-review', 'validate_projection'),
                              ('D2-tail/local-ship', 'validate_return')):
            graph = dict(state={'new-workspace-identity': {}}, graph_pins={})
            release = dict(stage=stage, handoff=bridge, predecessor=predecessor)
            prior = {'state_after': {'different-workspace-identity': {}}}
            with self.subTest(stage=stage), mock.patch.object(c, '_controlled'), \
                 mock.patch.object(handoff, method, return_value={'pins': {evidence['path']: evidence}}) as validate:
                c.predecessor_state_relation(release, prior, graph)
                validate.assert_called_once_with(bridge, predecessor, graph)
                self.assertEqual(graph['graph_pins'], {evidence['path']: evidence})
                with self.assertRaises(c.Hold):
                    c.predecessor_state_relation(dict(release, handoff=None), prior, graph)

    def test_ordinary_successor_cannot_use_a_projection_to_bypass_predecessor_state(self):
        graph = dict(state={'approved-current-state': {}}, graph_pins={})
        release = dict(stage='D2-tail/TDD-build', handoff=None, predecessor=None)
        with self.assertRaises(c.Hold):
            c.predecessor_state_relation(release, {'state_after': {}}, graph)
        c.predecessor_state_relation(release, {'state_after': graph['state']}, graph)
        with self.assertRaises(c.Hold):
            c.predecessor_state_relation(dict(release, handoff=self.put({'mock': 'extra'})),
                                         {'state_after': graph['state']}, graph)

    def test_expected_native_grants_cannot_expose_root_control(self):
        root = self.root / 'workspace'; root.mkdir()
        expected = {name: None for name in c.frozen.load_legacy().THREAD_FIELDS}
        expected.update(cwd=str(root), runtimeWorkspaceRoots=[str(root)], approvalPolicy='never',
            approvalsReviewer='user', sandbox={'type': 'workspaceWrite', 'networkAccess': False,
                                              'writableRoots': [str(c.CONTINUATION.parent)]})
        native = dict(forward_thread_expectation=expected,
                      official_commit=c.frozen.load_legacy().SEMANTIC_COMMIT, codex_version='codex-cli 0.164.0')
        with self.assertRaisesRegex(c.Hold, 'exposes protected'):
            c._expected_workspace(native, root)
        expected['sandbox']['writableRoots'] = []
        self.assertEqual(c._expected_workspace(native, root), expected)
        with self.assertRaises(c.Hold):
            c._canonical_root(str(c.CONTINUATION))

    def release_fixture(self):
        workspace = self.root / 'workspace'; workspace.mkdir()
        (workspace / '.git').mkdir()
        actual = c.CONTINUATION / 'postclosure-recovery-r1/tasks-initial-actual'
        capture = c.frozen.decode(c.read_ref(c.ref(actual / 'review-target-capture.json')))
        spec_path = 'spec.md'; tasks_path = 'tasks.md'
        original_spec = next(p for p in capture['files'] if p.startswith('docs/changes/') and p.endswith('/spec.md'))
        original_tasks = next(p for p in capture['files'] if p.startswith('docs/changes/') and p.endswith('/tasks.md'))
        for name, original in ((spec_path, original_spec), (tasks_path, original_tasks)):
            (workspace / name).write_bytes(c.read_ref(capture['files'][original]))
        state = {name: dict(kind='file', sha256=c.ref(workspace / name)['sha256']) for name in (spec_path, tasks_path)}
        dummy = self.put({'mock': 'upstream DATA'})
        scope = {'root': str(workspace), 'realroot': str(workspace), 'topology': 'author-git'}
        decision = dict(schema='remaining-decision-v1', stage=next(iter(c.ROWS)),
            input='Approve this exact plan. Change only its status to approved.',
            authority_kind='proactive_plan_approval', reviewed_artifacts=[c.ref(workspace / tasks_path)],
            actor='Root', prerequisite_evidence=[])
        decision_ref = self.put(decision)
        roles = dict(spec=spec_path, tasks=tasks_path, application=[], tests=[], callers=[],
                     progress=[], packet=[], review=None, local_pr=None, off=None)
        contract = dict(schema='postclosure-contract-v1', row_id=next(iter(c.ROWS)), roles=roles,
            authored=[tasks_path], derived=[], immutable_paths=[spec_path],
            expected_before=c.canonical_hash(state), expected_after=None,
            obligations=['actual_plan_question', 'separate_plan_decision', 'tasks_content_identical', 'tasks_approved'],
            evidence={}, git_profile=None, cache_profile=None, capability_profile=None, tasks_progress=None)
        contract_ref = self.put(contract)
        output = str(self.root / 'uncreated-output')
        claim = str(c.donor_claim_path(c.ROWS[next(iter(c.ROWS))]))
        plan = dict(schema='postclosure-row-plan-v1', branch_id=c.BRANCH_ID, row_id=next(iter(c.ROWS)),
            donor_slot=c.ROWS[next(iter(c.ROWS))], scope=dummy, predecessor=dummy, predecessor_review=dummy,
            contract=contract_ref, input=decision_ref, source_set=dummy, admission=dummy,
            output=output, claim=claim, limits=dict(c.frozen.LIMITS), feasibility=None)
        plan_ref = self.put(plan)
        policy = dict(schema='postclosure-process-policy-v1', row_plan=plan_ref, scope=dummy,
            argv=[], session={}, session_sha256='0' * 64, metadata_paths={},
            native_expectation=dummy, official_sources=[], turn_permission=None)
        policy_ref = self.put(policy)
        env = c.environment_identity({'PATH': '/bin', 'CODEX_TOOL_CALL_ID': 'prepared'})
        baseline = dict(campaign=dummy, source_set=dummy, scope=dummy, command=dummy,
                        manifest=dummy, state=state, environment=env)
        baseline['command'] = self.put(dict(schema='remaining-observe-command-v1', campaign=dummy,
            scope=dummy, policy=policy_ref, native_binding=dummy, manifest=dummy, source_set=dummy,
            output=str(self.root / 'zero-output'), expected_state=self.put(state), environment=env))
        release = dict(schema='remaining-stage-release-v1', campaign=dummy, baseline=dummy, policy=policy_ref,
            predecessor=None, handoff=None, stage=next(iter(c.ROWS)), donor=c.ROWS[next(iter(c.ROWS))],
            decision=decision_ref, plan=plan_ref, source_set=dummy, environment=env)
        release_ref = self.put(release)
        command_ref = self.put(dict(schema='remaining-command-v1', release=release_ref, output=output))
        graph = dict(scope=scope, policy=policy,
                     graph_pins={}, state=state)
        return command_ref, release, decision, baseline, graph

    def test_proactive_approval_binds_actual_draft_without_a_question(self):
        command_ref, _, _, baseline, graph = self.release_fixture()
        with mock.patch.object(c, '_controlled'), mock.patch.object(c, 'validate_baseline', return_value=baseline), \
             mock.patch.object(c, '_base_graph', return_value=graph), mock.patch.object(c, 'check_unspent_donor'):
            result = c.validate_release(command_ref, command_ref['sha256'])
        self.assertEqual(result['decision']['authority_kind'], 'proactive_plan_approval')
        self.assertNotIn('question', result['decision'])
        self.assertEqual(result['input'], result['decision']['input'])
        tasks = str(Path(graph['scope']['root']) / 'tasks.md')
        self.assertNotIn(tasks, result['graph_pins'])
        self.assertIn(result['plan']['contract']['path'], result['graph_pins'])

    def test_proactive_approval_cannot_approve_an_unreviewed_draft(self):
        command_ref, release, decision, baseline, graph = self.release_fixture()
        decision['reviewed_artifacts'] = [self.put({'different': 'document'})]
        release['decision'] = self.put(decision)
        # Keep the plan/decision edges genuine so the intended check is reached.
        plan = c.frozen.read_record(release['plan'], 'row-plan'); plan['input'] = release['decision']
        release['plan'] = self.put(plan); graph['policy']['row_plan'] = release['plan']
        release['policy'] = self.put(graph['policy'])
        observe = c.read_record(baseline['command'], 'observe-command')
        observe['policy'] = release['policy']; baseline['command'] = self.put(observe)
        command_ref = self.put(dict(schema='remaining-command-v1', release=self.put(release), output=plan['output']))
        with mock.patch.object(c, '_controlled'), mock.patch.object(c, 'validate_baseline', return_value=baseline), \
             mock.patch.object(c, '_base_graph', return_value=graph), mock.patch.object(c, 'check_unspent_donor'), \
             self.assertRaisesRegex(c.Hold, 'review exact actual draft'):
            c.validate_release(command_ref, command_ref['sha256'])

    def test_invalid_role_contracts_never_reach_execution_or_donor_acquisition(self):
        import remaining_evidence_operator as operator
        command_ref, release, _, baseline, graph = self.release_fixture()
        plan = c.frozen.read_record(release['plan'], 'row-plan')
        original = c.frozen.read_record(plan['contract'], 'contract')
        for changes in ({'application': ['tasks.md']}, {'application': ['app.py', 'app.py']},
                        {'application': 'app.py'}, {'application': ['../escape.py']},
                        {'application': [True]}, {'local_pr': []}, {'callers': ['tasks.md']}):
            contract = dict(original, roles=dict(original['roles'], **changes))
            changed_plan = dict(plan, contract=self.put(contract))
            changed_release = dict(release, plan=self.put(changed_plan))
            graph['policy']['row_plan'] = changed_release['plan']
            changed_release['policy'] = self.put(graph['policy'])
            observe = c.read_record(baseline['command'], 'observe-command')
            baseline['command'] = self.put(dict(observe, policy=changed_release['policy']))
            command_ref = self.put(dict(schema='remaining-command-v1',
                release=self.put(changed_release), output=plan['output']))
            with self.subTest(changes=changes), mock.patch.object(c, '_controlled'), \
                 mock.patch.object(c, 'validate_baseline', return_value=baseline), \
                 mock.patch.object(c, '_base_graph', return_value=graph), \
                 mock.patch.object(operator, '_execute') as execute, \
                 mock.patch.object(c, 'acquire_donor_claim') as claim, self.assertRaises(c.Hold):
                operator.run_stage(command_ref, command_ref['sha256'])
            self.assertFalse(execute.called, 'invalid roles reached execution')
            self.assertFalse(claim.called, 'invalid roles reached donor acquisition')

    def test_donor_claim_is_exclusive_stable_and_survives_failure(self):
        claims = self.root / 'claims'; claims.mkdir(mode=0o700)
        stage = next(iter(c.ROWS)); donor = c.ROWS[stage]
        graph = dict(release=dict(stage=stage, donor=donor), command_ref=self.put({'mock': 'command'}))
        with mock.patch.object(c, 'CLAIM_ROOT', claims), mock.patch.object(c, 'check_unspent_donor'):
            path = c.acquire_donor_claim(graph); raw = path.read_bytes()
            with self.assertRaises(FileExistsError):
                c.acquire_donor_claim(graph)
            self.assertEqual(path.read_bytes(), raw)
            value = json.loads(raw); self.assertEqual(value['delivery'], 'UNKNOWN'); self.assertFalse(value['refund'])
        with self.assertRaises(c.Hold):
            c.donor_claim_path('R7/spec/5')

    def test_old_claim_or_dangling_alias_rejects_transferred_donor(self):
        path = self.root / 'old-claim'
        for dangling in (False, True):
            if path.exists() or path.is_symlink(): path.unlink()
            path.symlink_to(self.root / 'missing') if dangling else path.write_text('retained')
            with mock.patch.object(c.frozen, 'claim_path', return_value=path), self.assertRaises(c.Hold):
                c.check_unspent_donor(next(iter(c.ROWS)))

    def test_raw_and_assessment_cannot_claim_question_or_goal_success(self):
        # Closed schema and mandatory preserved failure apply before any verdict reuse.
        pin = self.put({'mock': 'observation'})
        assessment = dict(schema='remaining-assessment-v1', campaign=pin, observation=pin,
            stage=next(iter(c.ROWS)), verdicts={}, preserved_failures=dict(c.FAILURES),
            integrity='PASS', admissible_for=[], goal_complete=False)
        with mock.patch.object(c, '_controlled'):
            for value in (dict(assessment, goal_complete=True),
                          dict(assessment, preserved_failures={'plan_question': 'PASS'})):
                with self.assertRaises(c.Hold):
                    c.validate_assessment(self.put(value))

    def test_profiles_and_write_scope_fail_before_any_claim(self):
        _, release, _, baseline, graph = self.release_fixture()
        plan = c.frozen.read_record(release['plan'], 'row-plan')
        contract = c.frozen.read_record(plan['contract'], 'contract')
        for change in ({'authored': ['spec.md']}, {'expected_after': 'a' * 64},
                       {'derived': ['__pycache__/x.pyc'], 'cache_profile': self.put({'fake': 'cache'})}):
            with self.subTest(change=change), self.assertRaises(c.Hold):
                c._profile_pins(graph, plan, dict(contract, **change))
        for stage in ('D2-tail/Git-AC9', 'D2-tail/unavailable-review'):
            changed_plan = dict(plan, row_id=stage)
            changed_contract = dict(contract, row_id=stage, authored=[], obligations=c.OBLIGATIONS[stage])
            with self.subTest(stage=stage), self.assertRaisesRegex(c.Hold, 'required finite stage profile'):
                c._profile_pins(graph, changed_plan, changed_contract)

    def test_baseline_binds_actual_retained_native_wire_not_a_declared_snapshot(self):
        # Protocol data are retained actual ZERO bytes. The surrounding command
        # and comparison identity are mock-only; this is not a new baseline grant.
        root = c.CONTINUATION / 'postclosure-recovery-r1'
        lookup = c.frozen.read_record(c.ref(root / 'zero-anchor-actual/lookup.json'), 'lookup')
        policy = c.frozen.read_record(lookup['policy'], 'process-policy')
        facts = lookup['native_facts']
        invariant = c.frozen.read_record(facts['invariant_candidate'], 'invariant-anchor')
        identity = dict(full_sha256=invariant['environment']['sha256'], comparison_sha256='a' * 64,
            excluded_keys=list(c.EXCLUDED_ENVIRONMENT_KEYS), nonce_present=False, nonce_sha256=None)
        dummy = self.put({'mock': 'campaign/source-set'})
        command = dict(schema='remaining-observe-command-v1', campaign=dummy, scope=policy['scope'],
            policy=lookup['policy'], native_binding=facts['native_binding'], manifest=invariant['product_manifest'],
            source_set=dummy, output=str(self.root / 'zero'), expected_state=self.put(lookup['state_after']),
            environment=identity)
        baseline = dict(schema='remaining-baseline-v1', command=self.put(command), campaign=dummy,
            scope=policy['scope'], source_set=dummy, manifest=invariant['product_manifest'],
            state=lookup['state_after'], environment=identity, invariant=invariant,
            native=facts['native13'], wire=lookup['wire'], close=facts['close'], failure=None,
            accounting=dict(actual=0, attempted=0, charged=0, status='ZERO', accepted=0))
        with mock.patch.object(c, '_controlled'):
            self.assertEqual(c.validate_baseline(self.put(baseline))['native'], facts['native13'])
            changed = copy.deepcopy(baseline); changed['native']['thread_id'] = 'foreign'
            with self.assertRaises(RuntimeError):
                c.validate_baseline(self.put(changed))
            changed = copy.deepcopy(baseline); changed['wire'] = changed['wire'][1:]
            with self.assertRaises(c.Hold):
                c.validate_baseline(self.put(changed))

    def assessment_fixture(self, failure=None, integrity='PASS'):
        _, release, decision, _, _ = self.release_fixture()
        plan = c.frozen.read_record(release['plan'], 'row-plan')
        dummy = self.put({'mock': 'source evidence'})
        scope = dict(schema='postclosure-scope-v1', scope_id='mock', root=str(self.root / 'workspace'),
            realroot=str(self.root / 'workspace'), topology='author-git', materialization=dummy,
            instruction_sources=[], install=[], process_choice=dummy)
        plan['scope'] = self.put(scope)
        release['plan'] = self.put(plan)
        release_ref = self.put(release)
        command_ref = self.put(dict(schema='remaining-command-v1', release=release_ref, output=plan['output']))
        output = Path(plan['output']); output.mkdir()
        observation = dict(schema='remaining-observation-v1', command=command_ref,
            campaign=release['campaign'], baseline=release['baseline'], stage=release['stage'],
            donor=release['donor'], root=scope['root'], process_id=1, thread_id='t', turn_id='u',
            wire=[dict(direction='request', payload=dict(method='turn/start', params=dict(
                threadId='t', input=[dict(type='text', text=decision['input'])])))], samples=[],
            environment=release['environment'], state_before={}, state_after={}, capture=dummy,
            input_delivery=dict(request_sha256=c.frozen.digest(decision['input'].encode()), USER=1),
            close=dict(reaped=True, returncode=0, stderr_bytes=0, partial_stdout_bytes=0,
                       watchdog_fired=False, watchdog_error=None), failure=failure,
            accounting=dict(actual=1, attempted=1, charged=1, status='ACTUAL', accepted=1), business_PASS=False)
        p = output / 'observation.json'; p.write_text(json.dumps(observation))
        obligations = c.frozen.read_record(plan['contract'], 'contract')['obligations']
        verdicts = {key: dict(verdict='FAIL' if key == 'actual_plan_question' else 'PASS',
            sources=[dummy], judgment='Independent mock-only finding.') for key in obligations}
        assessment = dict(schema='remaining-assessment-v1', campaign=release['campaign'],
            observation=c.ref(p), stage=release['stage'], verdicts=verdicts,
            preserved_failures=dict(c.FAILURES), integrity=integrity,
            admissible_for=['D2-tail/TDD-build'], goal_complete=False)
        return assessment, observation

    def test_quality_failure_is_preserved_while_named_dependency_is_assessed(self):
        assessment, observation = self.assessment_fixture()
        with mock.patch.object(c, '_controlled'), \
             mock.patch.object(c.frozen, 'validate_wire', return_value=observation['accounting']), \
             mock.patch.object(c.frozen, 'validate_review_capture'):
            result = c.validate_assessment(self.put(assessment))
        self.assertEqual(result['verdicts']['actual_plan_question']['verdict'], 'FAIL')
        self.assertEqual(result['preserved_failures'], c.FAILURES)
        self.assertEqual(result['admissible_for'], ['D2-tail/TDD-build'])
        self.assertIs(result['goal_complete'], False)

    def test_unsafe_or_unknown_observation_cannot_authorize_dependency(self):
        assessment, observation = self.assessment_fixture(failure={'primary': 'mock transport failure'})
        with mock.patch.object(c, '_controlled'), \
             mock.patch.object(c.frozen, 'validate_wire', return_value=observation['accounting']), \
             self.assertRaisesRegex(c.Hold, 'cannot claim integrity PASS'):
            c.validate_assessment(self.put(assessment))

    def test_assessment_cannot_skip_stage_or_relabel_missing_question(self):
        assessment, observation = self.assessment_fixture()
        for changed in (dict(assessment, admissible_for=['D2-tail/local-ship']),
                        dict(assessment, verdicts=dict(assessment['verdicts'], actual_plan_question=dict(
                            assessment['verdicts']['actual_plan_question'], verdict='PASS')))):
            with mock.patch.object(c, '_controlled'), \
                 mock.patch.object(c.frozen, 'validate_wire', return_value=observation['accounting']), \
                 mock.patch.object(c.frozen, 'validate_review_capture'), self.assertRaises(c.Hold):
                c.validate_assessment(self.put(changed))

    def test_new_core_never_calls_old_orchestration_or_rebinds_globals(self):
        tree = ast.parse(Path(c.__file__).read_bytes())
        forbidden = {'run_released', 'produce_lookup', 'validate_graph', 'validate_history',
                     'validate_adjudication', 'validate_f1_adjudication'}
        calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)}
        self.assertFalse(calls & forbidden)
        self.assertFalse(any(isinstance(node, ast.Global) for node in ast.walk(tree)))


class RecoverySeedContracts(unittest.TestCase):
    """Pure new-epoch guards; all native/failed-turn primitives are synthetic."""
    def setUp(self):
        import os
        self.temp = tempfile.TemporaryDirectory(prefix='recovery-seed-test-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.root = self.home / 'control'; self.root.mkdir(mode=0o700)
        self.clone = self.home / 'clone'; self.clone.mkdir(mode=0o700)
        self.serial = 0
        self.stack = __import__('contextlib').ExitStack(); self.addCleanup(self.stack.close)
        for name, value in (('CONTINUATION', self.root), ('CONTROL_ROOT', self.root),
                            ('CLAIM_ROOT', self.root / 'claims')):
            self.stack.enter_context(mock.patch.object(c, name, value))
        self.content = {'spec.md': b'---\nstatus: approved\n---\nspec',
            'tasks.md': b'---\nstatus: approved\n---\n- [ ] T7: final owner review\n',
            'app.py': b'code', 'test_app.py': b'test', '.git/HEAD': b'ref: refs/heads/main\n'}
        self.content.update({'file-%02d' % i: b'unchanged' for i in range(77)})
        (self.clone / '.git').mkdir()
        for i in range(69): (self.clone / ('dir-%02d' % i)).mkdir()
        for path, data in self.content.items(): (self.clone / path).write_bytes(data)
        self.state = c.frozen.inventory(self.clone)
        self.assertEqual(len(self.state), 153)
        self.old_root = self.home / 'absent-old-root'
        self.old_state = copy.deepcopy(self.state)
        for index, (path, item) in enumerate(self.old_state.items()):
            item['identity'] = [1, index + 1]
            item['realpath'] = str(self.old_root if path == '.' else self.old_root / path)
        self.capture_files = {path: self.put(data) for path, data in self.content.items()}
        state_pin = self.put(json.dumps(self.old_state).encode())
        self.capture = dict(scope=self.save(dict(root=str(self.old_root))),
            state_before=state_pin, state_after=state_pin, files=self.capture_files)
        self.capture_ref = self.save(self.capture)
        self.campaign = self.save({'synthetic': 'campaign'})
        self.sources = dict(files=[self.put(('source%d' % i).encode()) for i in range(26)],
                            official_sources=[])
        source_ref = self.save(self.sources)
        self.env = c.environment_identity(dict(os.environ))
        close = dict(reaped=True, returncode=0, stderr_bytes=0, partial_stdout_bytes=0,
                     watchdog_fired=False, watchdog_error=None)
        self.old_baseline = dict(native=dict(snapshot=dict(runtimeWorkspaceRoots=[str(self.old_root)],
            activePermissionProfile=None, sandbox=dict(type='workspaceWrite', writableRoots=[],
                excludeSlashTmp=True, excludeTmpdirEnvVar=True))))
        self.old_base_ref = self.save(self.old_baseline)
        self.scope = dict(root=str(self.clone), realroot=str(self.clone), topology='author-git')
        scope_ref = self.save(self.scope); native_ref = self.save({'synthetic': 'native'})
        self.policy = dict(turn_permission=None, scope=scope_ref, native_expectation=native_ref)
        zero = dict(schema='remaining-observe-command-v1', campaign=self.campaign, scope=scope_ref,
            policy=self.save(self.policy), native_binding=native_ref, manifest=self.put(b'manifest'),
            source_set=source_ref, output=str(self.root / 'zero-output'),
            expected_state=self.save(self.state), environment=self.env)
        zero_ref = self.save(zero)
        self.baseline = dict(failure=None, close=close, campaign=self.campaign, command=zero_ref,
            source_set=source_ref, scope=scope_ref, state=self.state, environment=self.env)
        self.baseline_ref = self.save(self.baseline)
        self.roles = dict(spec='spec.md', tasks='tasks.md', application=['app.py'], tests=['test_app.py'])
        old_scope_ref = self.save(dict(root=str(self.old_root), realroot=str(self.old_root)))
        self.old_plan = dict(scope=old_scope_ref, contract=self.save(dict(roles=self.roles)))
        old_release = self.save(dict(schema='remaining-stage-release-v1', campaign=self.campaign,
            baseline=self.old_base_ref, policy=zero['policy'], predecessor=None, handoff=None,
            stage='D2-tail/TDD-build', donor=c.ROWS['D2-tail/TDD-build'],
            decision=self.save(dict(synthetic='old-decision')), plan=self.save(self.old_plan),
            source_set=source_ref, environment=self.env))
        old_command = self.save(dict(schema='remaining-command-v1', release=old_release,
                                    output=str(self.root / 'failed-output')))
        self.raw = dict(schema='remaining-observation-v1', **{k: None for k in c.SCHEMAS['observation'].split()})
        self.raw.update(command=old_command, campaign=self.campaign, baseline=self.old_base_ref,
            stage='D2-tail/TDD-build', donor=c.ROWS['D2-tail/TDD-build'], root=str(self.old_root),
            capture=self.capture_ref, failure={'primary': 'timeout'}, environment=self.env, business_PASS=False)
        raw_ref = self.save(self.raw)
        self.failed = dict(stage='D2-tail/TDD-build', integrity='FAIL', admissible_for=[],
            goal_complete=False, observation=raw_ref, verdicts={'owner_review_stop': {'verdict': 'FAIL'}})
        failed_ref = self.save(self.failed)
        adoption = self.save(dict(decision='ROOT_ADOPT_ACTUAL_TDD_FAILURE_NO_DEPENDENT_RELEASE',
            assessment=failed_ref, preserved_failures=c.FAILURES, no_retry=True,
            no_root_code_rescue=True, raw_observation_unchanged=True))
        self.material = dict(scope='DATA_ONLY_NEW_PHYSICAL_SNAPSHOT_NOT_OLD_COMPLETION_OR_RUNTIME_RELEASE',
            source_capture=self.capture_ref, source_state=state_pin, new_root=str(self.clone),
            new_state=self.state, records=153, copied_files=82,
            byte_mode_kind_link_projection_equal=True, old_PID_or_close_repaired=False,
            old_stage_integrity='FAIL', model_USER=0,
            copies=[dict(relative=path, captured=self.capture_files[path],
                         current=dict(path=str(self.clone / path), sha256=c.frozen.digest(data)))
                    for path, data in self.content.items()])
        mat_ref = self.save(self.material)
        required = ['spec.md', 'tasks.md', 'app.py', 'test_app.py', '.git/HEAD']
        self.review = dict(decision='ROOT_REVIEW_CURRENT_RECOVERED_CONTENT', actor='Root',
            materialization=mat_ref, state_sha256=c.canonical_hash(self.state),
            artifacts={path: self.capture_files[path] for path in required},
            git_state_sha256=c.canonical_hash({p: v for p, v in self.state.items()
                                              if p == '.git' or p.startswith('.git/')}),
            preserved_failures=c.FAILURES, inherited_failures=c.RECOVERY_FAILURES,
            judgment='Synthetic owner review of these exact captured bytes; old failure remains.')
        review_ref = self.save(self.review)
        self.planning = dict(decision='PLAN_FRESH_POST_TDD_COMPONENT_EVIDENCE', actor='Root',
            campaign=self.campaign, failed_adoption=adoption, accounting=c.RECOVERY_ACCOUNTING,
            remaining_rows=dict(list(c.ROWS.items())[2:]), claim_root=str(c.CLAIM_ROOT),
            preserved_failures=c.FAILURES, inherited_failures=c.RECOVERY_FAILURES,
            no_retry=True, no_extra_capacity=True)
        planning_ref = self.save(self.planning)
        decision = dict(schema='remaining-decision-v1', stage=c.RECOVERY_STAGE,
            authority_kind='content_decision', actor='Root', input='Synthetic proactive content decision.',
            reviewed_artifacts=[dict(path=str(self.clone / path), sha256=self.state[path]['sha256'])
                                for path in required],
            prerequisite_evidence=[review_ref, planning_ref, adoption])
        self.seed = dict(schema='remaining-recovery-seed-v1', campaign=self.campaign,
            failed_assessment=failed_ref, failed_observation=raw_ref, source_capture=self.capture_ref,
            failure_adoption=adoption, materialization=mat_ref, baseline=self.baseline_ref,
            planning=planning_ref, review=review_ref, decision=self.save(decision),
            old_tmpdir=os.environ.get('TMPDIR'), preserved_failures=c.FAILURES)
        self.graph = dict(state=self.state, scope=self.scope, source_set=source_ref)
        self.stack.enter_context(mock.patch.object(c, 'validate_assessment', return_value=self.failed))
        self.stack.enter_context(mock.patch.object(c, 'validate_baseline', side_effect=
            lambda pin: self.old_baseline if pin == self.old_base_ref else self.baseline))
        self.stack.enter_context(mock.patch.object(c, 'validate_source_set', return_value=self.sources))
        self.stack.enter_context(mock.patch.object(c.frozen, 'validate_review_capture',
            return_value=(self.capture, self.old_state, self.content)))
        self.stack.enter_context(mock.patch.object(c.frozen, 'read_record',
            side_effect=lambda pin, kind: c.frozen.decode(c.read_ref(pin))))
        self.stack.enter_context(mock.patch.object(c, 'check_unspent_donor'))

    def put(self, data):
        self.serial += 1
        path = self.root / ('record-%03d' % self.serial); path.write_bytes(data)
        return c.ref(path)

    def save(self, value):
        return self.put(json.dumps(value).encode())

    def seed_proof(self, *, current=False, stage=None):
        pin = self.save(self.seed)
        release = dict(stage=stage or c.RECOVERY_STAGE, predecessor=pin,
            baseline=self.seed['baseline'], decision=self.seed['decision'], campaign=self.campaign,
            source_set=self.baseline['source_set'])
        return c.validate_recovery_seed(pin, release=release, graph=self.graph if current else None)

    def test_seed_new_owned_close_cannot_hide_errors_group_or_termination(self):
        legacy = copy.deepcopy(self.baseline['close'])
        self.assertTrue(c._closed(legacy))
        owned = dict(legacy, cleanup_started_monotonic=1, cleanup_finished_monotonic=2,
            cleanup_deadline=3, cleanup_finished=True, cleanup_errors=[], group_state='absent',
            termination_attempted=False, stdout_complete=True, stderr_complete=True)
        self.baseline['close'] = owned
        self.assertTrue(self.seed_proof()['pins'])
        for change in ({'cleanup_errors': [{'operation': 'signal', 'type': 'PermissionError'}]},
                       {'group_state': 'present'}, {'termination_attempted': True},
                       {'cleanup_finished_monotonic': 4}):
            with self.subTest(change=change):
                self.baseline['close'] = dict(owned, **change)
                with self.assertRaisesRegex(c.Hold, 'healthy recovery ZERO'):
                    self.seed_proof()

    def test_seed_admits_only_new_snapshot_and_keeps_failed_turn_blocked(self):
        proof = self.seed_proof(current=True)
        self.assertEqual(proof['state'], self.state)
        self.assertEqual(self.failed['integrity'], 'FAIL')
        self.assertEqual(self.failed['admissible_for'], [])
        self.assertIn(self.seed['source_capture']['path'], proof['pins'])

    def test_seed_cannot_recover_at_another_stage_or_unhealthy_zero(self):
        with self.assertRaises(c.Hold): self.seed_proof(stage='D2-tail/Git-AC9')
        self.baseline['close']['returncode'] = 1
        with self.assertRaises(c.Hold): self.seed_proof()

    def test_seed_rejects_clone_identity_alias_projection_and_mapping_drift(self):
        for mutation in ('old_identity', 'alias', 'bytes', 'mapping'):
            original = copy.deepcopy(self.material)
            try:
                if mutation == 'old_identity':
                    self.material['new_state']['app.py']['identity'] = self.old_state['app.py']['identity']
                elif mutation == 'alias':
                    self.material['new_state']['app.py']['identity'] = self.material['new_state']['test_app.py']['identity']
                elif mutation == 'bytes': self.material['new_state']['app.py']['sha256'] = '0' * 64
                else: self.material['copies'].pop()
                self.seed['materialization'] = self.save(self.material)
                reason = ('clone identity' if mutation in ('old_identity', 'alias') else
                          'clone paths' if mutation == 'bytes' else 'materialization mapping')
                with self.subTest(mutation=mutation), self.assertRaisesRegex(c.Hold, reason): self.seed_proof()
            finally:
                self.material = original
                self.state = self.material['new_state']
                self.baseline['state'] = self.state
                self.graph['state'] = self.state

    def test_seed_rejects_missing_review_refunded_planning_and_failure_erasure(self):
        self.review['artifacts'].pop('app.py'); self.seed['review'] = self.save(self.review)
        with self.assertRaises(c.Hold): self.seed_proof()
        self.seed['review'] = self.save({'actor': 'PENDING'})
        with self.assertRaises(c.Hold): self.seed_proof()
        self.seed['preserved_failures'] = dict(c.FAILURES, plan_question='PASS')
        with self.assertRaises(c.Hold): self.seed_proof()

    def test_seed_rejects_refund_extra_donor_or_old_failure_rehabilitation(self):
        original = copy.deepcopy(self.planning)
        for mutation in ('refund', 'extra_donor', 'retry'):
            self.planning = copy.deepcopy(original)
            if mutation == 'refund': self.planning['accounting']['charged'] = 82
            elif mutation == 'extra_donor': self.planning['remaining_rows']['extra'] = 'extra'
            else: self.planning['no_retry'] = False
            self.seed['planning'] = self.save(self.planning)
            with self.subTest(mutation=mutation), self.assertRaises(c.Hold): self.seed_proof()
        self.failed['integrity'] = 'PASS'
        with self.assertRaises(c.Hold): self.seed_proof()

    def test_seed_rejects_evidence_under_declared_old_temporary_write_root(self):
        self.old_baseline['native']['snapshot']['sandbox']['excludeTmpdirEnvVar'] = False
        self.seed['old_tmpdir'] = str(self.home)
        with self.assertRaisesRegex(c.Hold, 'old native writable scope'):
            self.seed_proof()

    def test_seed_first_release_checks_all_six_unspent_claims(self):
        c.CLAIM_ROOT.mkdir(mode=0o700)
        c.donor_claim_path(c.ROWS['D2-tail/Git-AC9']).write_text('spent')
        with self.assertRaisesRegex(c.Hold, 'donor already spent'): self.seed_proof(current=True)
        # Historical validation after a later legitimate claim does not refund or reread today’s state.
        self.assertTrue(self.seed_proof()['pins'])

    def test_seed_historical_validation_does_not_read_mutated_clone(self):
        pin = self.save(self.seed)
        (self.clone / 'app.py').write_bytes(b'legitimate later change')
        with mock.patch.object(c.frozen, 'inventory', side_effect=AssertionError('live clone replay')):
            self.assertTrue(c.validate_recovery_seed(pin)['pins'])
        self.graph['state'] = copy.deepcopy(self.state)
        self.graph['state']['app.py']['sha256'] = '0' * 64
        with self.assertRaises(c.Hold): self.seed_proof(current=True)


if __name__ == '__main__':
    unittest.main()
