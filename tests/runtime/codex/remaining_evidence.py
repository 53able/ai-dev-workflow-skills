"""Remaining component evidence; records route an external exact Root release.

Historical FAILs remain FAILs. Current execution prerequisites and independently
reviewed assessments are separate from quality scores. Importing this module is
inert; no old graph/history producer, global rebinding or environment mutation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import postclosure_recovery as frozen

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[2]
CONTINUATION = SOURCE / '.omx/continuations/resume-20261027-j56k2v96'
CONTROL_ROOT = CONTINUATION / 'remaining-evidence-r1'
CLAIM_ROOT = CONTROL_ROOT / 'claims'
BRANCH_ID = 'remaining-evidence-resume20261027-j56k2v96'
ROWS = {row: donor for row, donor in frozen.ROWS.items() if row != 'D2-tail/tasks-initial'}
FAILURES = {'plan_question': 'FAIL', 'actual_plan_question': 'FAIL'}
ACCOUNTING = {'previous_validated_snapshot': 76, 'distinct_saved_actual_USER': 1,
              'actual_arithmetic': 77, 'planning_whole': 107, 'prospective_held': 30}
EXCLUDED_ENVIRONMENT_KEYS = ['CODEX_TOOL_CALL_ID']
DRAFT_TASKS_SHA = '669d9457577de37e76d7ef6283422f4cafcc0c884a0a32e0f43c873e37c3684b'
ACTUAL_TASKS_SHA = '0e042b1a55aa0f17145150a13cbdfd179b6b4c353008755e7584d9ca550f7fb0'
FROZEN_SOURCE_SET = CONTINUATION / 'postclosure-recovery-r1/zero-preparation-DATA/source-set.json'
FROZEN_SOURCE_SET_SHA = '51505f1d0f4567257f06689da0a7d5c0515d5e0269ec78ea056e21f4013af29d'
NEW_SOURCES = ('remaining_evidence.py', 'remaining_evidence_operator.py',
               'remaining_evidence_test.py', 'remaining_evidence_operator_test.py',
               'remaining_evidence_handoff.py', 'remaining_evidence_handoff_test.py',
               'owned_transport.py', 'owned_transport_test.py',
               'cache_payload_replay.py', 'cache_payload_replay_test.py',
               'remaining_evidence_replay.py', 'remaining_evidence_replay_test.py',
               'remaining_evidence_p7_replay.py', 'remaining_evidence_p7_replay_test.py')
ROLE_WRITES = {
    'D2-tail/plan-approval': ('tasks',),
    'D2-tail/TDD-build': ('application', 'tests', 'tasks', 'progress'),
    'D2-tail/content-to-operation-question': ('tasks', 'progress'),
    'D2-tail/Git-AC9': ('off',), 'D2-tail/unavailable-review': ('packet',),
    'D2-tail/independent-review': ('review',), 'D2-tail/local-ship': ('local_pr',),
    'D2-tail/scope-invalidation': ('spec', 'tasks'),
}
OBLIGATIONS = dict(zip(ROWS, (
    ['actual_plan_question', 'separate_plan_decision', 'tasks_content_identical', 'tasks_approved'],
    ['actual_tasks_feasibility', 'red_before_production', 'configured_checks_green', 'AC9_concurrency', 'owner_review_stop'],
    ['actual_content_decision', 'operation_question', 'targets_effects_recovery', 'no_implementation'],
    ['separate_exact_git_grant', 'commit_revert_restore', 'same_persistent_OFF', 'baseline_MAIN_unchanged', 'feature_docs_unchanged', 'actual_AC11'],
    ['complete_current_packet', 'actual_supported_route_unavailable', 'independent_review_incomplete', 'no_root_packet_fill'],
    ['separate_context_no_author_conversation', 'installed_F1_body_consumed', 'installed_template_consumed', 'current_all_layers', 'completed_review'],
    ['current_checks', 'AC_evidence', 'installed_HUMAN_REQUIRED_10', 'local_pr_complete', 'owner_rollback', 'no_external_action'],
    ['actual_scope_change', 'both_approvals_draft', 'no_implementation'],
)))
SCHEMAS = {
    'source-set': 'files official_sources',
    'campaign': 'branch_id planning historical_snapshot saved_task_audit failed_result relocation source_set rows accounting preserved_failures',
    'observe-command': 'campaign scope policy native_binding manifest source_set output expected_state environment',
    'baseline': 'command campaign scope source_set manifest state environment invariant native wire close failure accounting',
    'decision': 'stage input authority_kind reviewed_artifacts actor prerequisite_evidence',
    'stage-release': 'campaign baseline policy predecessor handoff stage donor decision plan source_set environment',
    'command': 'release output',
    'observation': 'command campaign baseline stage donor root process_id thread_id turn_id wire samples environment state_before state_after capture input_delivery close failure accounting business_PASS',
    'assessment': 'campaign observation stage verdicts preserved_failures integrity admissible_for goal_complete',
    'recovery-seed': 'campaign failed_assessment failed_observation source_capture failure_adoption materialization baseline planning review decision old_tmpdir preserved_failures',
    'replay-bridge': 'campaign historical_campaign current_source_set historical_source_set archive observation replay_result review adoption verdicts preserved_failures inherited_failures admissible_for goal_complete environment_transition',
    'environment-transition': 'decision actor previous_observation diagnostic_baseline diagnostic_observation diagnostic_source_archive current_source_set comparison accounting preserved_failures inherited_failures old_environment_equivalence old_config_value_equivalence old_checks_scope no_retry no_extra_capacity goal_complete judgment',
    'p7-replay-bridge': 'campaign current_source_set historical_campaign historical_source_set archive observation packet capability_witness replay_result review adoption verdicts preserved_failures inherited_failures admissible_for goal_complete',
}
REFERENCE_FIELDS = {
    'campaign': 'planning historical_snapshot saved_task_audit failed_result relocation source_set',
    'observe-command': 'campaign scope policy native_binding manifest source_set expected_state',
    'baseline': 'command campaign scope source_set manifest',
    'stage-release': 'campaign baseline policy decision plan source_set',
    'command': 'release',
    'observation': 'command campaign',
    'assessment': 'campaign observation',
    'recovery-seed': 'campaign failed_assessment failed_observation source_capture failure_adoption materialization baseline planning review decision',
    'replay-bridge': 'campaign historical_campaign current_source_set historical_source_set archive observation replay_result review adoption',
    'environment-transition': 'previous_observation diagnostic_baseline diagnostic_observation diagnostic_source_archive current_source_set comparison',
    'p7-replay-bridge': 'campaign current_source_set historical_campaign historical_source_set archive observation packet capability_witness replay_result review adoption',
}
Hold = frozen.Hold
require = frozen.require
canonical_hash = frozen.canonical_hash
ref = frozen.ref
read_ref = frozen.read_ref


def validate_record(value, kind=None):
    require(type(value) is dict and type(value.get('schema')) is str, 'remaining schema required')
    name = value['schema'].removeprefix('remaining-').removesuffix('-v1')
    require(value['schema'] == 'remaining-' + name + '-v1' and name in SCHEMAS,
            'unknown remaining schema')
    require(kind is None or name == kind, 'wrong remaining record kind')
    frozen.fields(value, 'schema ' + SCHEMAS[name])
    for key in REFERENCE_FIELDS.get(name, '').split():
        frozen.ref_shape(value[key])
    if name == 'replay-bridge' and value['environment_transition'] is not None:
        frozen.ref_shape(value['environment_transition'])
    if name == 'stage-release' and value['predecessor'] is not None:
        frozen.ref_shape(value['predecessor'])
    if name == 'stage-release' and value['handoff'] is not None:
        frozen.ref_shape(value['handoff'])
    if name in ('observe-command', 'command'):
        frozen.absolute(value['output'])
    if name in ('decision', 'stage-release', 'assessment'):
        require(value['stage'] in ROWS, 'unfunded remaining stage')
    if name == 'decision':
        frozen.nonempty(value['input'])
        require(value['actor'] == 'Root', 'separate Root decision required')
        for key in ('reviewed_artifacts', 'prerequisite_evidence'):
            require(type(value[key]) is list, 'decision reference list required')
            for pin in value[key]:
                frozen.ref_shape(pin)
        require(value['reviewed_artifacts'], 'review actual artifacts before release')
    if name == 'observation':
        require(value['business_PASS'] is False, 'raw observation cannot assert business PASS')
        if value['stage'] is None:
            require(value['donor'] is None and value['baseline'] is None and
                    value['input_delivery'] is None, 'zero observation cannot carry a business stage')
        else:
            require(value['stage'] in ROWS and value['donor'] == ROWS[value['stage']],
                    'unfunded observed stage')
            frozen.ref_shape(value['baseline'])
    return value


def read_record(reference, kind=None):
    return validate_record(frozen.decode(read_ref(reference)), kind)


def _controlled(reference):
    frozen.ref_shape(reference)
    path = frozen.absolute(reference['path'])
    require(path.is_relative_to(CONTROL_ROOT), 'remaining controls outside current root')
    read_ref(reference)
    return reference


def _canonical_root(root):
    root = frozen.absolute(root)
    require(root.resolve(strict=True) == root and root.is_dir() and
            root.stat().st_uid == os.getuid(), 'owned physical workspace required')
    require(not root.is_relative_to(CONTINUATION) and not CONTINUATION.is_relative_to(root),
            'workspace exposes protected continuation')
    return root


def environment_identity(environment):
    require(type(environment) is dict and all(type(k) is str and type(v) is str
            for k, v in environment.items()), 'actual string environment required')
    nonce = environment.get('CODEX_TOOL_CALL_ID')
    return {'full_sha256': canonical_hash(environment),
            'comparison_sha256': canonical_hash({k: v for k, v in environment.items()
                                                if k not in EXCLUDED_ENVIRONMENT_KEYS}),
            'excluded_keys': list(EXCLUDED_ENVIRONMENT_KEYS),
            'nonce_present': nonce is not None,
            'nonce_sha256': None if nonce is None else frozen.digest(nonce.encode())}


def validate_current_environment(actual, expected):
    for value in (actual, expected):
        frozen.fields(value, 'full_sha256 comparison_sha256 excluded_keys nonce_present nonce_sha256')
        frozen.hash_value(value['full_sha256']); frozen.hash_value(value['comparison_sha256'])
        require(value['excluded_keys'] == EXCLUDED_ENVIRONMENT_KEYS and type(value['nonce_present']) is bool,
                'only named orchestration nonce may differ')
        require((value['nonce_sha256'] is not None) == value['nonce_present'], 'nonce presence/hash mismatch')
        if value['nonce_sha256'] is not None:
            frozen.hash_value(value['nonce_sha256'])
    require(actual['comparison_sha256'] == expected['comparison_sha256'],
            'non-nonce environment drift')
    return actual


def validate_source_set(reference):
    _controlled(reference)
    value = read_record(reference, 'source-set')
    original_pin = {'path': str(FROZEN_SOURCE_SET), 'sha256': FROZEN_SOURCE_SET_SHA}
    original = frozen.read_record(original_pin, 'source-set')
    frozen.validate_source_set(original)
    required = {pin['path']: pin for pin in original['files']}
    for name in NEW_SOURCES:
        pin = ref(HERE / name, executable=True)
        required[pin['path']] = pin
    require(type(value['files']) is list and len(value['files']) == 18 + len(NEW_SOURCES),
            'exact original18 plus current owned source closure required')
    seen = set()
    for pin in value['files']:
        read_ref(pin, executable=True)
        require(pin['path'] not in seen and pin['nlink'] == 1 and required.get(pin['path']) == pin,
                'source substitution or alias')
        seen.add(pin['path'])
    require(seen == set(required) and value['official_sources'] == original['official_sources'],
            'frozen source or original97 primary references changed')
    return value


def validate_campaign(reference):
    _controlled(reference)
    campaign = read_record(reference, 'campaign')
    require(campaign['branch_id'] == BRANCH_ID and campaign['rows'] == ROWS and
            campaign['accounting'] == ACCOUNTING and
            all(type(v) is int for v in campaign['accounting'].values()) and
            campaign['preserved_failures'] == FAILURES, 'campaign cannot refund, retry or erase FAIL')
    planning = frozen.decode(read_ref(campaign['planning']))
    require(campaign['planning']['path'] == str(CONTINUATION / 'remaining-evidence-planning-r1/ROOT-PLANNING-DECISION.json') and
            planning['decision'] == 'PLAN_REMAINING_COMPONENT_EVIDENCE_WITH_SEPARATE_AUTHORIZATION' and
            planning['retry_or_extra_capacity'] is False, 'exact prospective Root plan required')
    require(campaign['historical_snapshot'] == frozen.CLOSED_HISTORY, 'exact historical76 snapshot required')
    historical = frozen.decode(read_ref(campaign['historical_snapshot']))
    require(historical['accounting']['actual'] == 76 and historical['accounting']['blocked'] is True,
            'historical blocked snapshot cannot change')
    audit = frozen.decode(read_ref(campaign['saved_task_audit']))
    rejected = frozen.read_record(campaign['failed_result'], 'independent-result')
    require(audit['verdict'] == 'BUSINESS_FAIL_PLAN_QUESTION' and audit['infrastructure'] == 'PASS' and
            audit['obligations']['plan_question'] == 'FAIL' and
            rejected['business_PASS'] is False and rejected['decision'] == 'REJECT_EXACT_D2_ROW_PLAN_QUESTION' and
            rejected['context'] == audit['actual'] and rejected['context']['sha256'] == ACTUAL_TASKS_SHA,
            'saved task failure must remain independently recorded')
    actual = frozen.read_record(rejected['context'], 'context')
    charge = frozen.validate_wire(actual['wire'], actual['thread_id'], actual['turn_id'])
    require(charge == actual['accounting'] == audit['accounting'] ==
            {'actual': 1, 'attempted': 1, 'charged': 1, 'status': 'ACTUAL', 'accepted': 1},
            'saved distinct USER charge required')
    relocation = frozen.decode(read_ref(campaign['relocation']))
    require(relocation['schema'] == 'DURABLE_FIXTURE_RECONSTRUCTION_DATA_V1' and
            relocation['scope'] == 'DATA_ONLY_NOT_RUNTIME_ADMITTED' and relocation['model_USER'] == 0,
            'new physical relocation provenance required')
    validate_source_set(campaign['source_set'])
    return campaign


def _expected_workspace(native, root):
    legacy = frozen.load_legacy()
    expected = native['forward_thread_expectation']
    require(type(expected) is dict and set(expected) == set(legacy.THREAD_FIELDS) and
            expected['cwd'] == str(root) and expected['runtimeWorkspaceRoots'] == [str(root)] and
            expected['approvalPolicy'] == 'never' and expected['approvalsReviewer'] == 'user',
            'independent exact native workspace/approval expectations required')
    sandbox = expected['sandbox']
    require(type(sandbox) is dict and sandbox.get('type') == 'workspaceWrite' and
            sandbox.get('networkAccess') is False, 'finite workspace sandbox required')
    for path in expected['runtimeWorkspaceRoots'] + sandbox.get('writableRoots', []):
        path = frozen.absolute(path)
        require(not CONTINUATION.is_relative_to(path) and not path.is_relative_to(CONTINUATION),
                'actual/expected grant exposes protected continuation')
    require(native.get('official_commit') == legacy.SEMANTIC_COMMIT and
            native.get('codex_version') == 'codex-cli 0.164.0', 'native version/source binding')
    return expected


def _base_graph(command_ref, command, campaign_ref, scope_ref, policy_ref, native_ref,
                manifest_ref, source_ref, state, environment, output):
    campaign = validate_campaign(campaign_ref)
    require(campaign['source_set'] == source_ref, 'campaign/source-set edge drift')
    sources = validate_source_set(source_ref)
    for pin in (scope_ref, policy_ref, native_ref):
        _controlled(pin)
    scope = frozen.read_record(scope_ref, 'scope')
    root = _canonical_root(scope['realroot'])
    require(scope['root'] == str(root), 'scope physical root mismatch')
    native = frozen.decode(read_ref(native_ref))
    expected = _expected_workspace(native, root)
    require(expected['instructionSources'] == [pin['path'] for pin in scope['instruction_sources']],
            'independent instruction contributors mismatch')
    policy = frozen.read_record(policy_ref, 'process-policy')
    require(policy['scope'] == scope_ref and policy['native_expectation'] == native_ref and
            policy['session'] == frozen.session_for(str(root)) and
            policy['session_sha256'] == canonical_hash(policy['session']) and
            policy['official_sources'] == sources['official_sources'], 'exact finite process policy required')
    require(policy['argv'] == frozen.argv_for(policy['argv'][0], str(root)), 'finite native argv required')
    executable = Path(policy['argv'][0]).resolve(strict=True)
    require(ref(executable, executable=True)['sha256'] ==
            native.get('executable_identity', {}).get('sha256') ==
            'd8990e3ee7acfbc26f91265b12a1a83f0fee40d0e0f8f1f40a37d4ec21f499cf',
            'native executable identity changed')
    require(manifest_ref['sha256'] == frozen.COMPOSITE_SHA, 'exact source42 manifest required')
    read_ref(manifest_ref)
    require(type(state) is dict and frozen.inventory(root) == state, 'fresh whole workspace state mismatch')
    frozen.validate_required_metadata(policy, scope)
    frozen.sample_metadata(policy['metadata_paths'])
    validate_current_environment(environment, environment)
    output_path = frozen.absolute(output)
    require(output_path.is_relative_to(CONTROL_ROOT) and output_path.resolve(strict=False) == output_path and
            not output_path.exists(), 'fresh protected remaining output required')
    pins = [command_ref, campaign_ref, scope_ref, policy_ref, native_ref, manifest_ref,
            source_ref, scope['materialization'], scope['process_choice']] + sources['files'] + sources['official_sources'] + scope['instruction_sources'] + scope['install']
    pins += [campaign[k] for k in ('planning', 'historical_snapshot', 'saved_task_audit', 'failed_result', 'relocation')]
    for path_key, hash_key in (('proof_path', 'proof_sha256'), ('source_index_path', 'source_index_sha256')):
        pins.append({'path': native[path_key], 'sha256': native[hash_key]})
    for pin in pins:
        read_ref(pin, executable='size' in pin)
    return dict(command_ref=command_ref, command=command, campaign=campaign_ref,
        campaign_record=campaign, scope_ref=scope_ref, scope=scope, policy=policy, native=native,
        native_binding=native_ref, manifest=manifest_ref, source_set=source_ref,
        baseline=None, baseline_ref=None, plan=None, contract=None, decision=None,
        input=None, output=output, graph_pins={pin['path']: pin for pin in pins},
        state=state, expected_environment=environment, turn_overlay=None,
        stage=None, donor=None)


def validate_observation_command(reference, expected_sha256):
    require(reference.get('sha256') == frozen.hash_value(expected_sha256), 'external exact observe command digest required')
    _controlled(reference)
    command = read_record(reference, 'observe-command')
    _controlled(command['expected_state'])
    state = frozen.decode(read_ref(command['expected_state']))
    graph = _base_graph(reference, command, command['campaign'], command['scope'], command['policy'],
        command['native_binding'], command['manifest'], command['source_set'], state,
        command['environment'], command['output'])
    require(graph['policy']['turn_permission'] is None, 'zero observation has no turn grant')
    graph['graph_pins'][command['expected_state']['path']] = command['expected_state']
    return graph


def validate_baseline(reference):
    _controlled(reference)
    baseline = read_record(reference, 'baseline')
    _controlled(baseline['command'])
    source_command = read_record(baseline['command'], 'observe-command')
    for key in ('campaign', 'scope', 'source_set', 'manifest'):
        require(baseline[key] == source_command[key], 'baseline observation command edge mismatch')
    validate_current_environment(baseline['environment'], source_command['environment'])
    require(baseline['state'] == frozen.decode(read_ref(source_command['expected_state'])),
            'zero observation changed state')
    require(baseline['failure'] is None and _closed(baseline['close']), 'healthy owned baseline close required')
    charge = frozen.validate_wire(baseline['wire'], baseline['native']['thread_id'], None)
    require(charge == baseline['accounting'] ==
            {'actual': 0, 'attempted': 0, 'charged': 0, 'status': 'ZERO', 'accepted': 0}, 'baseline dispatched USER')
    scope = frozen.read_record(baseline['scope'], 'scope')
    binding = frozen.decode(read_ref(source_command['native_binding']))
    expected = _expected_workspace(binding, Path(scope['realroot']))
    require(baseline['native']['snapshot'] == expected and
            baseline['invariant']['product_manifest'] == baseline['manifest'], 'baseline native/source mismatch')
    requests = [frame['payload'] for frame in baseline['wire'] if frame['direction'] == 'request']
    require([item.get('method') for item in requests] == list(frozen.LOOKUP_METHODS),
            'actual finite zero observation request profile required')
    thread = next(item for item in requests if item.get('method') == 'thread/start')
    responses = [frame['payload'] for frame in baseline['wire'] if frame['direction'] == 'response'
                 and frame['payload'].get('id') == thread['id'] and 'result' in frame['payload']]
    require(len(responses) == 1 and frozen.load_legacy().reconcile_thread(
        responses[0]['result'], thread['params'], expected) == baseline['native'],
        'actual thread response must establish native baseline')
    require(baseline['environment']['full_sha256'] == baseline['invariant']['environment']['sha256'],
            'baseline must retain actual whole environment hash')
    return baseline


def _closed(close):
    if isinstance(close, dict) and any(key in close for key in ('cleanup_finished', 'cleanup_errors')):
        import owned_transport
        try:
            owned_transport.require_healthy_close(close)
        except ValueError:
            return False
        close = dict(close)
    return (type(close) is dict and close.get('reaped') is True and close.get('returncode') == 0 and
            close.get('stderr_bytes') == 0 and close.get('partial_stdout_bytes') == 0 and
            close.get('watchdog_fired') is False and close.get('watchdog_error') is None)


def _retain_proof_pin(graph, pin, contract):
    read_ref(pin, executable='size' in pin)
    root = Path(graph['scope']['realroot'])
    path = Path(pin['path'])
    mutable = set(contract['authored']) | set(contract['derived'])
    if path.is_relative_to(root) and str(path.relative_to(root)) in mutable:
        before = graph['state'].get(str(path.relative_to(root)), {})
        require(before.get('sha256') == pin['sha256'], 'reviewed mutable artifact must bind actual prestate')
        return  # Runtime full-state/transition/captured-byte checks own this slot.
    graph['graph_pins'][pin['path']] = pin


def _profile_pins(graph, plan, contract):
    """Check finite prospective profiles before claiming or launching a USER."""
    require(contract['row_id'] == plan['row_id'] and contract['expected_before'] ==
            canonical_hash(graph['state']) and contract['expected_after'] is None and
            contract['evidence'] == {}, 'contract must remain prospective and bind actual prestate')
    require(contract['obligations'] == OBLIGATIONS[plan['row_id']], 'original stage quality criteria remain unchanged')
    roles = frozen.fields(contract['roles'], 'spec tasks application tests callers progress packet review local_pr off')
    role_paths = []
    for key in ('spec', 'tasks', 'review', 'local_pr', 'off'):
        value = roles[key]
        if value is not None:
            require(type(value) is str, 'scalar role must be a relative path or null')
            frozen.relative(value)
            role_paths.append(value)
    for key in ('application', 'tests', 'callers', 'progress', 'packet'):
        value = roles[key]
        require(type(value) is list and all(type(path) is str for path in value),
                'list role must contain only relative paths')
        require(len(value) == len(set(value)), 'duplicate role path')
        for path in value:
            frozen.relative(path)
        role_paths.extend(value)
    require(len(role_paths) == len(set(role_paths)), 'role path overlap')
    paths = {key: set(value if type(value) is list else [value] if value is not None else [])
             for key, value in roles.items()}
    legal = set().union(*(paths[key] for key in ROLE_WRITES[plan['row_id']]))
    parents = {str(parent) for name in legal for parent in Path(name).parents
               if str(parent) != '.' and str(parent) not in graph['state']}
    for key in ('authored', 'derived', 'immutable_paths'):
        require(type(contract[key]) is list and len(set(contract[key])) == len(contract[key]), 'finite distinct contract paths required')
        for name in contract[key]:
            frozen.relative(name)
    require(set(contract['authored']) <= legal | parents and
            not set(contract['authored']) & set(contract['derived']) and
            not (set(contract['authored']) | set(contract['derived'])) & set(contract['immutable_paths']),
            'unauthorized prospective write scope')
    for name in contract['authored'] + contract['derived']:
        require(not set(Path(name).parts) & {'.git', '.codex', '.agents'} and
                Path(name).name not in ('AGENTS.md', 'CLAUDE.md', 'config.toml'),
                'protected path cannot be authored')
    if plan['row_id'] == 'D2-tail/plan-approval':
        require(set(contract['authored']) == paths['tasks'] and len(paths['tasks']) == 1,
                'proactive approval changes only reviewed tasks')
    if plan['row_id'] == 'D2-tail/scope-invalidation':
        require(set(contract['authored']) == paths['spec'] | paths['tasks'] and len(contract['authored']) == 2,
                'invalidation changes both approval artifacts')
    progress = (plan['row_id'] in ('D2-tail/TDD-build', 'D2-tail/content-to-operation-question')
                and roles['tasks'] in contract['authored'])
    require((contract['tasks_progress'] is not None) == progress,
            'task progress policy required only for authorized task progress')
    if progress:
        path = roles['tasks']
        require(path in graph['state'] and graph['state'][path].get('kind') == 'file',
                'actual approved task progress artifact required')
        data, _ = frozen.file_bytes(Path(graph['scope']['realroot']) / path)
        require(frozen.digest(data) == graph['state'][path]['sha256'], 'task progress prestate drift')
        frozen.validate_tasks_progress(contract['tasks_progress'], path, data, data)
    require(bool(contract['derived']) == (contract['cache_profile'] is not None), 'cache profile requires finite derived outputs')
    require(not contract['derived'] or plan['row_id'] in
            ('D2-tail/TDD-build', 'D2-tail/Git-AC9', 'D2-tail/local-ship'), 'stage forbids derived outputs')
    for key, kind, only_stage in (
            ('git_profile', 'git-profile', 'D2-tail/Git-AC9'),
            ('capability_profile', 'capability-profile', 'D2-tail/unavailable-review')):
        reference = contract[key]
        require((reference is not None) == (plan['row_id'] == only_stage), 'required finite stage profile')
        if reference is None:
            continue
        _controlled(reference)
        profile = frozen.read_record(reference, kind)
        graph['graph_pins'][reference['path']] = reference
        require(type(profile['official_sources']) is list and profile['official_sources'],
                'profile primary-source references required')
        pins = list(profile['official_sources'])
        if kind == 'git-profile':
            require(profile['command_prefix'] == frozen.GIT_ENV_PREFIX and
                    profile['invoked_path'] == profile['executable']['path'] and
                    profile['off_initial'] == 'create' and profile['off_mode'] in ('0o600', '0o644'),
                    'finite isolated Git/OFF profile required')
            pins += [profile[name] for name in ('executable', 'environment_proof', 'off_data', 'env_executable')]
        for pin in pins:
            _retain_proof_pin(graph, pin, contract)
    if contract['cache_profile'] is not None:
        reference = contract['cache_profile']; _controlled(reference)
        profile = frozen.read_record(reference, 'cache-profile')
        require(profile['row_id'] == plan['row_id'], 'cache profile stage mismatch')
        graph['graph_pins'][reference['path']] = reference
        pins = profile['official_sources'] + [profile['command_interpreter_proof'], profile['interpreter']['executable']]
        for pin in pins:
            _retain_proof_pin(graph, pin, contract)
        if contract['git_profile'] is not None:
            git = frozen.read_record(contract['git_profile'], 'git-profile')
            require(profile['extra_commands'] == git['verification_commands'], 'exact Git/cache command relation')
    require(contract['git_profile'] is None or contract['cache_profile'] is not None,
            'Git requires exact cache provenance profile')
    if plan['feasibility'] is not None:
        _controlled(plan['feasibility'])
        feasible = frozen.read_record(plan['feasibility'], 'feasibility')
        for pin in [plan['feasibility'], feasible['tasks'], feasible['AC9_concurrency'], feasible['review']]:
            _retain_proof_pin(graph, pin, contract)


RECOVERY_STAGE = 'D2-tail/content-to-operation-question'
RECOVERY_FAILURES = {'TDD_build': 'FAIL', 'owner_review_stop': 'FAIL',
                     'T7_completion': 'UNPROVEN', 'setup_unknown_attempts': 3}
RECOVERY_ACCOUNTING = {'charged': 83, 'unspent': 24, 'planning_whole': 107,
                       'setup_unknown': 3}


def _recovery_pin(pin):
    frozen.ref_shape(pin)
    path = frozen.absolute(pin['path'])
    require(path.is_relative_to(CONTINUATION) and
            CONTINUATION.resolve(strict=True) == CONTINUATION and
            CONTINUATION.stat().st_uid == os.getuid() and
            not CONTINUATION.stat().st_mode & 0o077,
            'recovery evidence outside protected owned continuation')
    read_ref(pin)
    return pin


def _recovery_projection(state):
    require(type(state) is dict and state and all(type(item) is dict for item in state.values()),
            'complete recovery inventory required')
    return {path: {key: value for key, value in item.items()
                   if key not in ('identity', 'realpath')} for path, item in state.items()}


def _recovery_write_roots(snapshot, tmpdir):
    sandbox = snapshot['sandbox']
    require(sandbox.get('type') == 'workspaceWrite' and
            snapshot.get('activePermissionProfile') is None, 'finite old native write profile required')
    roots = snapshot['runtimeWorkspaceRoots'] + sandbox.get('writableRoots', [])
    if not sandbox.get('excludeSlashTmp', False):
        roots += ['/tmp', '/private/tmp']
    if not sandbox.get('excludeTmpdirEnvVar', False) and tmpdir is not None:
        roots += [str(Path(tmpdir))]
    return [frozen.absolute(path).resolve(strict=False) for path in roots]


def validate_recovery_seed(reference, *, release=None, graph=None, historical_sources=None):
    """Admit a new P5 snapshot, never rehabilitation of the failed TDD turn.

    Immutable validation uses the seed's original ZERO and captured blobs. Only
    first release checks current environment/state/unspent donors; later review
    chains must not compare against the now legitimately mutated author tree.
    """
    if historical_sources is not None:
        from remaining_evidence_replay import _HistoricalSources
        require(type(historical_sources) is _HistoricalSources and graph is None,
                'historical sources cannot admit a current runtime')
    _controlled(reference)
    seed = read_record(reference, 'recovery-seed')
    require(seed['preserved_failures'] == FAILURES, 'recovery cannot erase historical FAIL')
    for key in REFERENCE_FIELDS['recovery-seed'].split():
        _recovery_pin(seed[key])
    failed = validate_assessment(seed['failed_assessment'])
    require(failed['stage'] == 'D2-tail/TDD-build' and failed['integrity'] == 'FAIL' and
            failed['admissible_for'] == [] and failed['goal_complete'] is False and
            failed['observation'] == seed['failed_observation'] and
            failed['verdicts']['owner_review_stop']['verdict'] == 'FAIL',
            'exact failed TDD assessment must remain blocked')
    raw = read_record(seed['failed_observation'], 'observation')
    require(raw['failure'] is not None and raw['capture'] == seed['source_capture'],
            'failed actual observation/capture required')
    command = read_record(raw['command'], 'command')
    old_release = read_record(command['release'], 'stage-release')
    old_plan = frozen.read_record(old_release['plan'], 'row-plan')
    old_scope = frozen.read_record(old_plan['scope'], 'scope')
    capture, old_state, content = frozen.validate_review_capture(seed['source_capture'],
        dict(raw, realroot=old_scope['realroot']), old_plan)
    require(len(content) == 82 and len(old_state) == 153, 'exact failed TDD captured snapshot required')
    adoption = frozen.decode(read_ref(seed['failure_adoption']))
    require(adoption.get('decision') == 'ROOT_ADOPT_ACTUAL_TDD_FAILURE_NO_DEPENDENT_RELEASE' and
            adoption.get('assessment') == seed['failed_assessment'] and
            adoption.get('preserved_failures') == FAILURES and adoption.get('no_retry') is True and
            adoption.get('no_root_code_rescue') is True and adoption.get('raw_observation_unchanged') is True,
            'separate Root failure adoption required')
    baseline = validate_baseline(seed['baseline'])
    require(baseline['failure'] is None and _closed(baseline['close']) and
            baseline['campaign'] == seed['campaign'], 'fresh healthy recovery ZERO required')
    if historical_sources is None:
        sources = validate_source_set(baseline['source_set'])
    else:
        require(read_record(baseline['source_set'], 'source-set') == historical_sources.sources,
                'historical seed must bind the exact archived source epoch')
        sources = historical_sources.sources
    require(len(sources['files']) == 26, 'current source26 recovery closure required')
    zero = read_record(baseline['command'], 'observe-command')
    scope = frozen.read_record(baseline['scope'], 'scope')
    policy = frozen.read_record(zero['policy'], 'process-policy')
    require(policy['turn_permission'] is None and policy['scope'] == baseline['scope'] and
            policy['native_expectation'] == zero['native_binding'] and
            scope['root'] == scope['realroot'] and scope['topology'] == 'author-git',
            'exact fresh recovery scope/native/ZERO policy required')
    material = frozen.decode(read_ref(seed['materialization']))
    require(material.get('scope') == 'DATA_ONLY_NEW_PHYSICAL_SNAPSHOT_NOT_OLD_COMPLETION_OR_RUNTIME_RELEASE' and
            material.get('source_capture') == seed['source_capture'] and
            material.get('source_state') == capture['state_after'] and
            material.get('new_root') == scope['realroot'] and
            material.get('old_PID_or_close_repaired') is False and
            material.get('old_stage_integrity') == 'FAIL' and material.get('model_USER') == 0 and
            material.get('byte_mode_kind_link_projection_equal') is True,
            'data-only materialization cannot repair old completion')
    state = material['new_state']
    require(state == baseline['state'] and material.get('records') == len(state) == 153 and
            material.get('copied_files') == len(content) == 82 and
            _recovery_projection(state) == _recovery_projection(old_state),
            'complete clone paths/bytes/modes/kinds/link projection mismatch')
    identities = set()
    old_ids = {tuple(item['identity']) for item in old_state.values()}
    root = frozen.absolute(scope['realroot'])
    require(state['.']['mode'] == '0o700' and root != Path(old_scope['realroot']),
            'new protected physical recovery root required')
    for path, item in state.items():
        if path != '.':
            frozen.relative(path)
        identity = item['identity']
        require(type(identity) is list and len(identity) == 2 and
                all(type(value) is int and value >= 0 for value in identity) and
                tuple(identity) not in identities | old_ids and
                item['kind'] in ('file', 'directory') and item.get('link_text') is None and
                item['realpath'] == str(root if path == '.' else root / path),
                'clone identity reuse/link/alias/path mismatch')
        identities.add(tuple(identity))
    require(type(material['copies']) is list and len(material['copies']) == len(content),
            'complete captured-file materialization mapping required')
    copied = set()
    for item in material['copies']:
        frozen.fields(item, 'relative captured current')
        path = item['relative']
        require(path in content and path not in copied and item['captured'] == capture['files'][path] and
                item['current'] == {'path': str(root / path), 'sha256': state[path]['sha256']},
                'materialization must bind exact captured bytes and destination')
        copied.add(path)
    require(seed['old_tmpdir'] is None or type(seed['old_tmpdir']) is str,
            'explicit old temporary-write extent required')
    old_baseline = validate_baseline(raw['baseline'])
    validate_current_environment(baseline['environment'], raw['environment'])
    old_writes = _recovery_write_roots(old_baseline['native']['snapshot'], seed['old_tmpdir'])
    pins = [reference, *[seed[key] for key in REFERENCE_FIELDS['recovery-seed'].split()],
            raw['command'], command['release'], old_release['plan'], old_plan['scope'],
            old_plan['contract'], raw['baseline'],
            baseline['command'], baseline['scope'], baseline['source_set'], zero['policy'],
            zero['native_binding'], capture['state_before'], capture['state_after'],
            *capture['files'].values(), *sources['files'], *sources['official_sources']]
    if historical_sources is not None:
        pins = [historical_sources.resolve(pin) for pin in pins]
        pins += list(historical_sources.pins.values())
    for pin in pins:
        path = frozen.absolute(pin['path'])
        require(not any(path.resolve(strict=False).is_relative_to(write) for write in old_writes),
                'recovery evidence remains under old native writable scope')
        read_ref(pin, executable='size' in pin)
    require(not any(root.resolve(strict=False).is_relative_to(write) or write.is_relative_to(root)
                    for write in old_writes), 'clone overlaps old native writable scope including temporary roots')
    review = frozen.decode(read_ref(seed['review']))
    frozen.fields(review, 'decision actor materialization state_sha256 artifacts git_state_sha256 preserved_failures inherited_failures judgment')
    require(review['decision'] == 'ROOT_REVIEW_CURRENT_RECOVERED_CONTENT' and review['actor'] == 'Root' and
            review['state_sha256'] == canonical_hash(state) and
            review['materialization'] == seed['materialization'] and
            review['preserved_failures'] == FAILURES and review['inherited_failures'] == RECOVERY_FAILURES,
            'actual Root current-content review required')
    frozen.nonempty(review['judgment'])
    roles = frozen.read_record(old_plan['contract'], 'contract')['roles']
    required = {roles['spec'], roles['tasks'], *roles['application'], *roles['tests']}
    required |= {path for path in content if path.startswith('.git/')}
    require(type(review['artifacts']) is dict and set(review['artifacts']) == required and
            all(review['artifacts'][path] == capture['files'][path] for path in required) and
            review['git_state_sha256'] == canonical_hash({path: item for path, item in state.items()
                                                         if path == '.git' or path.startswith('.git/')}),
            'review must bind approved documents/current code/tests and exact Git state')
    require(content[roles['spec']].startswith(b'---\nstatus: approved\n---') and
            content[roles['tasks']].startswith(b'---\nstatus: approved\n---') and
            content[roles['tasks']].count(b'- [ ] T7:') == 1,
            'actual approvals and unfinished T7 must be preserved')
    planning = frozen.decode(read_ref(seed['planning']))
    frozen.fields(planning, 'decision actor campaign failed_adoption accounting remaining_rows claim_root preserved_failures inherited_failures no_retry no_extra_capacity')
    remaining = dict(list(ROWS.items())[2:])
    require(planning['decision'] == 'PLAN_FRESH_POST_TDD_COMPONENT_EVIDENCE' and planning['actor'] == 'Root' and
            planning['campaign'] == seed['campaign'] and planning['failed_adoption'] == seed['failure_adoption'] and
            planning['accounting'] == RECOVERY_ACCOUNTING and
            all(type(value) is int for value in planning['accounting'].values()) and
            planning['remaining_rows'] == remaining and planning['claim_root'] == str(CLAIM_ROOT) and
            planning['preserved_failures'] == FAILURES and planning['inherited_failures'] == RECOVERY_FAILURES and
            planning['no_retry'] is True and planning['no_extra_capacity'] is True,
            'separate Root83/24/107 plan and exact six unspent donors required')
    decision = read_record(seed['decision'], 'decision')
    require(decision['stage'] == RECOVERY_STAGE and decision['authority_kind'] == 'content_decision' and
            all(seed[key] in decision['prerequisite_evidence'] for key in ('review', 'planning', 'failure_adoption')) and
            all({'path': str(root / path), 'sha256': state[path]['sha256']} in decision['reviewed_artifacts']
                for path in required), 'separate proactive owner content decision required')
    if release is not None:
        require(release['stage'] == RECOVERY_STAGE and release['predecessor'] == reference and
                release['baseline'] == seed['baseline'] and release['decision'] == seed['decision'] and
                release['campaign'] == seed['campaign'] and release['source_set'] == baseline['source_set'],
                'recovery seed is only the exact first P5 release predecessor')
    if graph is not None:
        require(release is not None and graph['state'] == state and
                graph['scope'] == scope and graph['source_set'] == baseline['source_set'],
                'current first release must retain the new physical ZERO snapshot')
        require(seed['old_tmpdir'] == os.environ.get('TMPDIR'), 'current temporary-write binding differs')
        validate_current_environment(environment_identity(dict(os.environ)), baseline['environment'])
        for stage, donor in remaining.items():
            check_unspent_donor(stage)
            require(not os.path.lexists(donor_claim_path(donor)), 'recovery donor already spent')
    return {'seed': seed, 'baseline': baseline, 'state': state,
            'pins': {pin['path']: pin for pin in pins}}


def stage_policy_relation(release, baseline):
    """ZERO never grants Git writes; only the exact later turn overlay may differ."""
    observe = read_record(baseline['command'], 'observe-command')
    zero = frozen.read_record(observe['policy'], 'process-policy')
    business = frozen.read_record(release['policy'], 'process-policy')
    require(zero['turn_permission'] is None, 'ZERO policy must remain permissionless')
    if release['stage'] == 'D2-tail/Git-AC9':
        require(business['turn_permission'] is not None and
                dict(business, turn_permission=None) == zero,
                'only exact Git turn permission may differ from ZERO policy')
    else:
        require(business == zero, 'non-Git stage cannot change reviewed ZERO policy')
    return release['policy']


def predecessor_state_relation(release, prior, graph):
    """Only captured reviewer delivery and report return cross workspace identities."""
    stage = release['stage']
    crossing = stage in ('D2-tail/independent-review', 'D2-tail/local-ship')
    require((release['handoff'] is not None) == crossing,
            'explicit review projection or return required only at review boundaries')
    if crossing:
        import remaining_evidence_handoff as handoff
        _controlled(release['handoff'])
        validate = (handoff.validate_projection if stage == 'D2-tail/independent-review'
                    else handoff.validate_return)
        proof = validate(release['handoff'], release['predecessor'], graph)
        graph['graph_pins'].update(proof['pins'])
    else:
        require(prior['state_after'] == graph['state'], 'next baseline must retain actual predecessor state')


def validate_release(reference, expected_sha256):
    require(reference.get('sha256') == frozen.hash_value(expected_sha256), 'external exact stage command digest required')
    _controlled(reference)
    command = read_record(reference, 'command')
    _controlled(command['release'])
    release = read_record(command['release'], 'stage-release')
    require(release['donor'] == ROWS[release['stage']], 'wrong or consumed remaining donor')
    baseline = validate_baseline(release['baseline'])
    require(release['campaign'] == baseline['campaign'] and release['source_set'] == baseline['source_set'],
            'stage/campaign/baseline/source edges')
    validate_current_environment(release['environment'], baseline['environment'])
    _controlled(release['policy'])
    policy_ref = stage_policy_relation(release, baseline)
    _controlled(release['decision']); _controlled(release['plan'])
    decision = read_record(release['decision'], 'decision')
    plan = frozen.read_record(release['plan'], 'row-plan')
    require(decision['stage'] == plan['row_id'] == release['stage'] and plan['branch_id'] == BRANCH_ID and
            plan['donor_slot'] == release['donor'] and plan['input'] == release['decision'] and
            plan['scope'] == baseline['scope'] and plan['source_set'] == release['source_set'] and
            plan['output'] == command['output'] and plan['limits'] == frozen.LIMITS,
            'acyclic exact stage/plan/decision relation')
    graph = _base_graph(reference, command, release['campaign'], baseline['scope'],
        policy_ref,
        read_record(baseline['command'], 'observe-command')['native_binding'], baseline['manifest'],
        release['source_set'], baseline['state'], release['environment'], command['output'])
    require(graph['policy']['row_plan'] == release['plan'], 'current policy must bind actual stage plan')
    _controlled(plan['contract'])
    contract = frozen.read_record(plan['contract'], 'contract')
    _profile_pins(graph, plan, contract)
    reviewer = release['stage'] == 'D2-tail/independent-review'
    require(graph['scope'].get('topology') == ('reviewer-no-git' if reviewer else 'author-git'),
            'exact author or separate reviewer topology required')
    require(not any(path == '.git' or path.startswith('.git/') for path in graph['state'])
            if reviewer else (Path(graph['scope']['root']) / '.git').is_dir(),
            'reviewer must lack Git; author must retain its actual Git repository')
    graph.update(stage=release['stage'], plan=plan, contract=contract)
    crossing = release['stage'] in ('D2-tail/independent-review', 'D2-tail/local-ship')
    require((release['handoff'] is not None) == crossing, 'explicit review projection or return required only at review boundaries')
    for pin in decision['reviewed_artifacts'] + decision['prerequisite_evidence']:
        _retain_proof_pin(graph, pin, contract)
    frozen.validate_prerequisites(plan, contract, graph['scope'], baseline['state'])
    first = release['stage'] == next(iter(ROWS))
    if first:
        require(release['predecessor'] is None and decision['authority_kind'] == 'proactive_plan_approval',
                'first stage requires proactive Root approval, never a fabricated question')
        tasks = contract['roles']['tasks']
        require(baseline['state'][tasks]['sha256'] == DRAFT_TASKS_SHA and
                {'path': str(Path(graph['scope']['root']) / tasks), 'sha256': DRAFT_TASKS_SHA}
                in decision['reviewed_artifacts'], 'review exact actual draft before proactive approval')
    else:
        require(release['predecessor'] is not None, 'actual assessed predecessor required')
        predecessor = read_record(release['predecessor'])
        if predecessor['schema'] == 'remaining-recovery-seed-v1':
            proof = validate_recovery_seed(release['predecessor'], release=release, graph=graph)
            graph['graph_pins'].update(proof['pins'])
        elif predecessor['schema'] == 'remaining-replay-bridge-v1':
            from remaining_evidence_replay import validate_bridge
            require(release['stage'] == 'D2-tail/unavailable-review',
                    'saved replay bridge supplies only the direct P7 successor')
            proof = validate_bridge(release['predecessor'], release=release, graph=graph)
            predecessor_state_relation(release, proof.entry['raw'], graph)
            graph['graph_pins'].update(proof.pins)
        elif predecessor['schema'] == 'remaining-p7-replay-bridge-v1':
            from remaining_evidence_p7_replay import validate_p7_bridge
            require(release['stage'] == 'D2-tail/independent-review',
                    'saved P7 replay bridge supplies only the direct P8 successor')
            proof = validate_p7_bridge(release['predecessor'], release=release, graph=graph)
            graph['graph_pins'].update(proof.pins)
            predecessor_state_relation(release, proof.entry['raw'], graph)
        else:
            assessment = validate_assessment(release['predecessor'])
            require(assessment['campaign'] == release['campaign'] and
                    release['stage'] in assessment['admissible_for'] and assessment['integrity'] == 'PASS',
                    'quality failure supplies no authority; unsafe/unproven continuation blocked')
            prior = read_record(assessment['observation'], 'observation')
            predecessor_state_relation(release, prior, graph)
        allowed = {'D2-tail/Git-AC9': 'exact_git_grant',
                   'D2-tail/content-to-operation-question': 'content_decision',
                   'D2-tail/scope-invalidation': 'scope_change'}
        require(decision['authority_kind'] == allowed.get(release['stage'], 'stage_instruction'),
                'separate stage-specific Root authority required')
    overlay = frozen.validate_turn_permission(graph['policy'], plan, graph['scope'], release['plan'])
    require(plan['claim'] == str(donor_claim_path(release['donor'])), 'stable donor claim path required')
    check_unspent_donor(release['stage'])
    require(not os.path.lexists(plan['claim']), 'remaining donor already claimed')
    pins = [command['release'], release['baseline'], release['policy'], release['decision'], release['plan'], plan['contract']]
    if graph['policy']['turn_permission'] is not None:
        permission_ref = graph['policy']['turn_permission']
        _controlled(permission_ref)
        permission = frozen.read_record(permission_ref, 'turn-permission')
        pins += [permission_ref, permission['managed_probe']] + permission['primary_sources']
    if release['predecessor'] is not None:
        pins.append(release['predecessor'])
    for pin in pins:
        read_ref(pin)
        graph['graph_pins'][pin['path']] = pin
    graph.update(release=release, release_ref=command['release'], baseline=baseline,
        baseline_ref=release['baseline'], plan=plan, contract=contract,
        decision=dict(decision, request=decision['input']), input=decision['input'], turn_overlay=overlay,
        stage=release['stage'], donor=release['donor'])
    return graph


def donor_claim_path(donor):
    require(donor in ROWS.values(), 'unfunded donor claim')
    return CLAIM_ROOT / (frozen.digest(donor.encode()) + '.json')


def check_unspent_donor(stage):
    require(stage in ROWS, 'unfunded donor stage')
    old_root = CONTINUATION / 'postclosure-claims'
    for branch, directory in (('D2tail-resume20261027-j56k2v96', old_root),
                              (frozen.BRANCH_ID, frozen.CLAIM_ROOT)):
        require(not os.path.lexists(frozen.claim_path(branch, stage, directory)),
                'historical donor already claimed')


def acquire_donor_claim(graph):
    release = graph['release']
    require(release['stage'] in ROWS and release['donor'] == ROWS[release['stage']], 'exact stage/donor claim required')
    check_unspent_donor(release['stage'])
    directory = CLAIM_ROOT
    require(directory.resolve(strict=True) == directory and directory.is_dir() and
            directory.stat().st_uid == os.getuid() and not directory.stat().st_mode & 0o077,
            'protected owned donor store required')
    path = donor_claim_path(release['donor'])
    value = {'branch_id': BRANCH_ID, 'stage': release['stage'], 'donor': release['donor'],
             'command': graph['command_ref'], 'delivery': 'UNKNOWN', 'refund': False}
    data = (json.dumps(value, sort_keys=True) + '\n').encode()
    parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(parent)
        require((opened.st_dev, opened.st_ino) == (directory.stat().st_dev, directory.stat().st_ino),
                'donor store changed during acquisition')
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.fsync(parent)
    finally:
        os.close(parent)
    return path


def validate_assessment(reference):
    _controlled(reference)
    assessment = read_record(reference, 'assessment')
    require(assessment['preserved_failures'] == FAILURES and assessment['goal_complete'] is False,
            'historical question FAIL cannot be waived or goal claimed complete')
    require(assessment['integrity'] in ('PASS', 'FAIL', 'UNPROVEN') and
            type(assessment['admissible_for']) is list, 'explicit integrity and dependency assessment required')
    observation = read_record(assessment['observation'], 'observation')
    for pin in (assessment['observation'], assessment['campaign'], observation['command']):
        _controlled(pin)
    require(observation['campaign'] == assessment['campaign'] and observation['stage'] == assessment['stage'] and
            observation['donor'] == ROWS[assessment['stage']], 'assessment/actual stage provenance')
    command = read_record(observation['command'], 'command')
    _controlled(command['release'])
    release = read_record(command['release'], 'stage-release')
    for pin in (release['decision'], release['plan']):
        _controlled(pin)
    decision = read_record(release['decision'], 'decision')
    plan = frozen.read_record(release['plan'], 'row-plan')
    contract = frozen.read_record(plan['contract'], 'contract')
    require(release['campaign'] == assessment['campaign'] and release['stage'] == assessment['stage'] and
            release['donor'] == observation['donor'] and release['baseline'] == observation['baseline'] and
            decision['stage'] == plan['row_id'] == release['stage'] and plan['input'] == release['decision'] and
            plan['branch_id'] == BRANCH_ID and contract['row_id'] == release['stage'] and
            contract['obligations'] == OBLIGATIONS[release['stage']] and
            plan['output'] == command['output'] and plan['claim'] == str(donor_claim_path(release['donor'])) and
            assessment['observation']['path'] == str(Path(command['output']) / 'observation.json'),
            'actual observation must bind its independently released command')
    charge = frozen.validate_wire(observation['wire'], observation['thread_id'], observation['turn_id'])
    require(charge == observation['accounting'], 'assessment wire/accounting mismatch')
    healthy = observation['failure'] is None and _closed(observation['close']) and charge == {
        'actual': 1, 'attempted': 1, 'charged': 1, 'status': 'ACTUAL', 'accepted': 1}
    if healthy:
        starts = [frame['payload'] for frame in observation['wire'] if frame['direction'] == 'request'
                  and frame['payload'].get('method') == 'turn/start']
        require(len(starts) == 1 and starts[0].get('params', {}).get('input') ==
                [{'type': 'text', 'text': decision['input']}] and observation['input_delivery'] ==
                {'request_sha256': frozen.digest(decision['input'].encode()), 'USER': 1},
                'actual stage USER must be the separate Root instruction')
        frozen.ref_shape(observation['capture'])
        scope = frozen.read_record(plan['scope'], 'scope')
        frozen.validate_review_capture(observation['capture'],
            dict(observation, realroot=scope['realroot']), plan)
    if assessment['integrity'] == 'PASS':
        require(healthy, 'unhealthy or unknown observation cannot claim integrity PASS')
    stages = list(ROWS); index = stages.index(assessment['stage'])
    next_stage = stages[index + 1:index + 2]
    require(assessment['admissible_for'] in ([], next_stage), 'only direct funded successor may be assessed')
    if assessment['admissible_for']:
        require(healthy and assessment['integrity'] == 'PASS', 'unsafe or unknown delivery blocks dependencies')
        if assessment['stage'] in ('D2-tail/unavailable-review', 'D2-tail/independent-review'):
            import remaining_evidence_handoff as handoff
            baseline = read_record(release['baseline'], 'baseline')
            handoff.validate_review_consumption(assessment, dict(
                campaign=assessment['campaign'], stage=assessment['stage'], scope=scope,
                state=observation['state_before'], manifest=baseline['manifest'], contract=contract,
                plan=plan, output=command['output']))
    require(type(assessment['verdicts']) is dict and
            set(assessment['verdicts']) == set(contract['obligations']),
            'exact independent obligation verdicts required')
    for name, finding in assessment['verdicts'].items():
        frozen.nonempty(name)
        frozen.fields(finding, 'verdict sources judgment')
        require(finding['verdict'] in ('PASS', 'FAIL', 'UNPROVEN') and
                type(finding['sources']) is list and finding['sources'], 'actual obligation evidence required')
        frozen.nonempty(finding['judgment'])
        for pin in finding['sources']:
            read_ref(pin)
    if assessment['stage'] == 'D2-tail/plan-approval':
        require(assessment['verdicts'].get('actual_plan_question', {}).get('verdict') == 'FAIL',
                'proactive approval cannot manufacture prior question')
    return assessment
