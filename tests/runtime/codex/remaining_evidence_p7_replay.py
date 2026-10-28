"""Exact saved-P7 replay and one confidentiality-preserving packet copy.

The copied transition validator differs only at its expected-mode selection.
Saved code archives are data, never imported or executed. No process is started.
"""
import hashlib
from pathlib import Path

import postclosure_recovery as f
from postclosure_recovery import (require, validate_record, read_record, canonical_hash,
    fields, relative, _same_except, _GitProof, _CacheProof, read_ref, digest,
    validate_tasks_progress)
from owned_transport import require_healthy_close

PREFIX = 'docs/review-handoff/notification-toggle/'
P7, P8 = 'D2-tail/unavailable-review', 'D2-tail/independent-review'
OBSERVATION_SHA = '81708921a851b667579de10d422901ddd3d2f730bce532e8c097a48f0cacc031'
ARCHIVE_SHA = 'f8bd53ba6f1e20f3551b96d345b15f18ff1e639eb0e1cae1d817f13ee0faa6f2'
SOURCE30_SHA = '884a5ff97924fc74e37899cd84b0ae766b3c9af3ea607dc2789ba7022787fabe'
PACKET_SHA = '5f429b71f8ba595a10ce93b529adef9e644bcc149bb6496d4d1871687b97532b'
CAPABILITY_SHA = '1080e23c74b91e317d8d3091c5637fc2aef44ce4d1b4c861ee340ceacae5eea9'
CAPABILITY_PRODUCER_SHA = '80a7e845d249b564aec8c7a50784f83bf21a45fd7af48eb87b3cb8487057e7c7'
ACCOUNTING = dict(charged=86, unspent=21, planning_whole=107)


def _core():
    import remaining_evidence
    return remaining_evidence


class _CopiedOffProof(dict):
    pass


class _ReplayedP7:
    def __init__(self, entry, entries, contexts, captures, pins, evidence, bridge=None):
        self.entry, self.entries, self.contexts, self.captures = entry, entries, contexts, captures
        self.pins, self.evidence, self.bridge = pins, evidence, bridge


def copied_off_proof(plan, before, after, captured_files):
    contract = read_record(plan['contract'], 'contract')
    off = contract['roles']['off']
    f.require(plan['row_id'] == contract['row_id'] == P7 and type(off) is str,
              'copied OFF proof is P7-only')
    relative(off)
    destination = PREFIX + 'payload/current/' + off
    f.require(destination in contract['roles']['packet'] and destination in contract['authored'] and
              destination not in before and off not in contract['authored'] and off not in contract['derived'] and
              before.get(off) == after.get(off) and after.get(off, {}).get('kind') == 'file' and
              after[off].get('mode') == '0o600' and after[off].get('link_text') is None and
              after.get(destination, {}).get('kind') == 'file' and after[destination].get('mode') == '0o600' and
              after[destination].get('link_text') is None and
              after[destination].get('identity') != after[off].get('identity'),
              'one new exact OFF copy must preserve source and confidentiality')
    source_identity, destination_identity = after[off].get('identity'), after[destination].get('identity')
    for identity in (source_identity, destination_identity):
        f.require(type(identity) is list and len(identity) == 2 and all(type(value) is int for value in identity) and
                  sum(item.get('kind') == 'file' and item.get('identity') == identity for item in after.values()) == 1,
                  'copied OFF source/destination cannot alias any captured file')
    root = f.absolute(after[off]['realpath'])
    for _ in Path(off).parts:
        root = root.parent
    f.require(str(root / off) == after[off]['realpath'] and str(root / destination) == after[destination]['realpath'],
              'copied OFF exact physical source/destination paths')
    f.require(type(captured_files) is dict and type(captured_files.get(off)) is bytes and
              type(captured_files.get(destination)) is bytes and captured_files[off] == captured_files[destination] and
              digest(captured_files[off]) == after[off]['sha256'] == after[destination]['sha256'],
              'copied OFF actual source/destination bytes')
    return _CopiedOffProof(dict(plan=canonical_hash(plan), before=canonical_hash(before),
        after=canonical_hash(after), source=off, destination=destination,
        sha256=digest(captured_files[off]), mode='0o600'))


def _copied_mode(proof, plan, before, after, path, item):
    original = before[path].get('mode') if path in before else ('0o755' if item['kind'] == 'directory' else '0o644')
    if proof is None:
        return original
    contract = read_record(plan['contract'], 'contract')
    off = contract['roles']['off']
    f.require(type(proof) is _CopiedOffProof and plan['row_id'] == P7 and
              proof['plan'] == canonical_hash(plan) and proof['before'] == canonical_hash(before) and
              proof['after'] == canonical_hash(after) and proof['source'] == off and
              proof['destination'] == PREFIX + 'payload/current/' + off and
              proof['destination'] in contract['roles']['packet'] and proof['mode'] == '0o600' and
              before.get(off) == after.get(off) and proof['sha256'] == after[off]['sha256'] ==
              after[proof['destination']]['sha256'], 'actual endpoint-bound copied OFF proof required')
    return proof['mode'] if path == proof['destination'] else original


def validate_transition(plan, before, after, evidence, adjudicating=False,
                        contents_before=None, contents_after=None, git_proof=None,
                        capability_proof=None, cache_proof=None, copy_proof=None):
    """Exact endpoints plus semantic per-row obligations. No generic metadata waiver."""
    validate_record(plan, 'row-plan')
    contract = read_record(plan['contract'], 'contract')
    require(contract['row_id'] == plan['row_id'] and contract['expected_before'] == canonical_hash(before), 'contract predecessor')
    if adjudicating:
        require(contract['expected_after'] == canonical_hash(after), 'independent postimage endpoint')
    else:
        require(contract['expected_after'] is None, 'runtime must not preload future postimage')
    require(type(contract['authored']) is list and type(contract['derived']) is list and
            type(contract['immutable_paths']) is list, 'contract path sets')
    authored = set(contract['authored'])
    derived = set(contract['derived'])
    immutable = set(contract['immutable_paths'])
    roles = fields(contract['roles'], 'spec tasks application tests callers progress packet review local_pr off')
    for role in ('spec', 'tasks', 'review', 'local_pr', 'off'):
        if roles[role] is not None:
            relative(roles[role])
    for role in ('application', 'tests', 'callers', 'progress', 'packet'):
        require(type(roles[role]) is list and len(set(roles[role])) == len(roles[role]), 'finite role paths')
        for path in roles[role]:
            relative(path)
    role_sets = {key: set(value if type(value) is list else ([value] if value else [])) for key, value in roles.items()}
    role_paths = [p for values in role_sets.values() for p in values]
    require(len(set(role_paths)) == len(role_paths), 'role path overlap')
    legal_roles = {
        'D2-tail/spec-approval': ('spec',), 'D2-tail/tasks-initial': ('tasks',),
        'D2-tail/plan-approval': ('tasks',),
        'D2-tail/TDD-build': ('application', 'tests', 'tasks', 'progress'),
        'D2-tail/content-to-operation-question': ('tasks', 'progress'),
        'D2-tail/Git-AC9': ('off',), 'D2-tail/unavailable-review': ('packet',),
        'D2-tail/independent-review': ('review',), 'D2-tail/local-ship': ('local_pr',),
        'D2-tail/scope-invalidation': ('spec', 'tasks'),
    }[plan['row_id']]
    legal = set().union(*(role_sets[name] for name in legal_roles))
    # Explicit parents are allowed only when genuinely new and needed for an
    # admitted artifact. Directory creation does not authorize arbitrary files.
    parents = {str(parent) for path in legal for parent in Path(path).parents if str(parent) != '.'}
    new_parents = {p for p in parents if p not in before and after.get(p, {}).get('kind') == 'directory'}
    require(authored <= legal | new_parents, 'per-row authored role violation')
    if plan['row_id'] in ('D2-tail/spec-approval', 'D2-tail/plan-approval'):
        expected_role = 'spec' if plan['row_id'] == 'D2-tail/spec-approval' else 'tasks'
        require(authored == role_sets[expected_role] and len(authored) == 1, 'approval exact artifact role')
    require(len(authored) == len(contract['authored']) and len(derived) == len(contract['derived']) and
            not authored & derived and not (authored | derived) & immutable, 'path classification overlap')
    for path in authored | derived | immutable:
        relative(path)
    for name in authored | derived:
        require(not any(part in ('.git', '.codex', '.agents') for part in Path(name).parts) and
                Path(name).name not in ('AGENTS.md', 'CLAUDE.md', 'config.toml'), 'protected mutable path')
    if plan['row_id'] == 'D2-tail/Git-AC9':
        profile = read_record(contract['git_profile'], 'git-profile')
        require(type(git_proof) is _GitProof and git_proof['before'] == canonical_hash(before) and
                git_proof['after'] == canonical_hash(after) and git_proof['profile'] == canonical_hash(profile),
                'actual relational Git proof required')
    else:
        require(contract['git_profile'] is None, 'Git profile is P6-only')
        _same_except(before, after, authored | derived)
    for state in (before, after):
        identities = {}
        for path, item in state.items():
            if item.get('kind') == 'file':
                identity = tuple(item.get('identity', []))
                require(len(identity) == 2 and identity not in identities, 'state hardlink/alias')
                identities[identity] = path
            if path in authored | derived:
                require(item.get('kind') in ('file', 'directory') and item.get('link_text') is None,
                        'mutable path alias')
    for path in authored:
        if path not in after:
            continue
        item = after[path]
        expected_mode = _copied_mode(copy_proof, plan, before, after, path, item)
        if plan['row_id'] == 'D2-tail/Git-AC9' and path == roles['off']:
            expected_mode = profile['off_mode']
        require(item.get('mode') == expected_mode and expected_mode in ('0o600', '0o644', '0o755') and (path not in before or item['kind'] == before[path]['kind']),
                'authored artifact mode/kind changed beyond exact contract')
    require(type(evidence) is dict and evidence == contract['evidence'], 'exact row evidence required')
    obligations = {
        'D2-tail/spec-approval': ('actual_question', 'separate_spec_decision', 'spec_content_identical', 'spec_approved'),
        'D2-tail/tasks-initial': ('approved_spec_consumed', 'all_AC_linked', 'new_tasks', 'plan_question', 'no_implementation'),
        'D2-tail/plan-approval': ('actual_plan_question', 'separate_plan_decision', 'tasks_content_identical', 'tasks_approved'),
        'D2-tail/TDD-build': ('actual_tasks_feasibility', 'red_before_production', 'configured_checks_green', 'AC9_concurrency', 'owner_review_stop'),
        'D2-tail/content-to-operation-question': ('actual_content_decision', 'operation_question', 'targets_effects_recovery', 'no_implementation'),
        'D2-tail/Git-AC9': ('separate_exact_git_grant', 'commit_revert_restore', 'same_persistent_OFF', 'baseline_MAIN_unchanged', 'feature_docs_unchanged', 'actual_AC11'),
        'D2-tail/unavailable-review': ('complete_current_packet', 'actual_supported_route_unavailable', 'independent_review_incomplete', 'no_root_packet_fill'),
        'D2-tail/independent-review': ('separate_context_no_author_conversation', 'installed_F1_body_consumed', 'installed_template_consumed', 'current_all_layers', 'completed_review'),
        'D2-tail/local-ship': ('current_checks', 'AC_evidence', 'installed_HUMAN_REQUIRED_10', 'local_pr_complete', 'owner_rollback', 'no_external_action'),
        'D2-tail/scope-invalidation': ('actual_scope_change', 'both_approvals_draft', 'no_implementation'),
    }[plan['row_id']]
    require(contract['obligations'] == list(obligations), 'per-row obligation set')
    if adjudicating:
        require(set(evidence) == set(obligations), 'complete independent obligation evidence')
        # References are inputs to independent content judgment, never automatic
        # business acceptance. This function returns business_PASS:false.
        for name, reference in evidence.items():
            require(type(reference) is dict, 'obligation is not proof: ' + name)
            read_ref(reference)
    else:
        require(evidence == {}, 'runtime must not preload future outcome evidence')
    row = plan['row_id']
    if row in ('D2-tail/TDD-build', 'D2-tail/content-to-operation-question') and roles['tasks'] in authored:
        require(type(contents_before) is dict and type(contents_after) is dict and
                roles['tasks'] in contents_before and roles['tasks'] in contents_after,
                'actual task progress byte captures required')
        require(digest(contents_before[roles['tasks']]) == before[roles['tasks']]['sha256'] and
                digest(contents_after[roles['tasks']]) == after[roles['tasks']]['sha256'], 'task progress capture/state relation')
        validate_tasks_progress(contract['tasks_progress'], roles['tasks'],
                                contents_before[roles['tasks']], contents_after[roles['tasks']])
    else:
        require(contract['tasks_progress'] is None, 'unused task progress policy')
    if row in ('D2-tail/spec-approval', 'D2-tail/plan-approval'):
        require(len(authored) == 1 and not derived, 'approval changes only one artifact')
        path = next(iter(authored))
        require(type(contents_before) is dict and type(contents_after) is dict and
                path in contents_before and path in contents_after, 'trusted approval byte captures required')
        old, new = contents_before[path], contents_after[path]
        require(digest(old) == before.get(path, {}).get('sha256') and
                digest(new) == after.get(path, {}).get('sha256'), 'approval capture/state relation')
        require(old.startswith(b'---\nstatus: draft\n---') and
                new == old.replace(b'---\nstatus: draft\n---', b'---\nstatus: approved\n---', 1),
                'approval must change status only, preserving exact business content')
    if row in ('D2-tail/content-to-operation-question', 'D2-tail/unavailable-review',
               'D2-tail/independent-review', 'D2-tail/scope-invalidation'):
        require(not derived, 'row does not admit derived outputs')
    if row == 'D2-tail/tasks-initial':
        require(not derived and all(path not in before for path in authored) and
                roles['tasks'] in authored and after.get(roles['tasks'], {}).get('kind') == 'file', 'tasks must be genuinely new and present')
    if row == 'D2-tail/scope-invalidation':
        require(authored == role_sets['spec'] | role_sets['tasks'] and len(authored) == 2,
                'both approval artifacts required')
        require(type(contents_before) is dict and type(contents_after) is dict, 'trusted invalidation byte captures required')
        for role in ('spec', 'tasks'):
            path = roles[role]
            require(path in contents_before and path in contents_after and
                    digest(contents_before[path]) == before.get(path, {}).get('sha256') and
                    digest(contents_after[path]) == after.get(path, {}).get('sha256') and
                    contents_before[path].startswith(b'---\nstatus: approved\n---') and
                    contents_after[path].startswith(b'---\nstatus: draft\n---'), 'both approval status transitions')
        path = roles['tasks']
        require(contents_after[path] == contents_before[path].replace(
            b'---\nstatus: approved\n---', b'---\nstatus: draft\n---', 1), 'invalidation tasks content changed')
    if derived:
        profile = read_record(contract['cache_profile'], 'cache-profile')
        require(profile['row_id'] == row and type(cache_proof) is _CacheProof and
                cache_proof['before'] == canonical_hash(before) and cache_proof['after'] == canonical_hash(after) and
                cache_proof['profile'] == canonical_hash(profile) and set(cache_proof['paths']) <= derived,
                'finite cache/source-equivalence proof required')
        finite_paths = {output['cache'] for output in profile['outputs']}
        finite_paths |= {str(Path(path).parent) for path in finite_paths}
        require(derived <= finite_paths and all(output['source'] in role_sets['application'] | role_sets['tests']
                                              for output in profile['outputs']), 'derived output not tied to approved app/test roles')
    else:
        require(contract['cache_profile'] is None, 'unused cache profile not admitted')
    if row == 'D2-tail/unavailable-review':
        profile = read_record(contract['capability_profile'], 'capability-profile')
        require(type(capability_proof) is dict and capability_proof.get('route') == profile['route'] and
                capability_proof.get('agents_enabled') is False and capability_proof.get('multi_agent_v2') is False and
                capability_proof.get('business_PASS') is False, 'actual supported-route capability proof missing')
    else:
        require(contract['capability_profile'] is None, 'capability profile is P7-only')
    return {'state_before_sha256': canonical_hash(before), 'state_after_sha256': canonical_hash(after),
            'business_PASS': False, 'obligations': list(obligations)}


def _historical_source30(source_ref, archive_ref):
    c = _core()
    import remaining_evidence_replay as old
    f.require(source_ref == dict(path=str(c.CONTROL_ROOT / 'post-TDD-P7-preparation-r3/source-set.json'),
              sha256=SOURCE30_SHA) and archive_ref == dict(
              path=str(c.CONTINUATION / 'remaining-evidence-source-freeze-r9/INDEX.json'), sha256=ARCHIVE_SHA),
              'exact saved P7 source30/archive required')
    index = f.decode(read_ref(archive_ref))
    source = c.read_record(source_ref, 'source-set')
    original = read_record(dict(path=str(c.FROZEN_SOURCE_SET), sha256=c.FROZEN_SOURCE_SET_SHA), 'source-set')
    f.validate_source_set(original)
    f.require(index['source_set'] == source_ref and index['files'] == source['files'] and
              index['official_sources'] == source['official_sources'] == original['official_sources'] and
              len(source['files']) == 30, 'exact P7 original18/97/12 source closure')
    indexed = {pin['path']: pin for pin in source['files']}
    expected = {pin['path']: pin for pin in original['files']}
    pins = [source_ref, archive_ref, *original['files'], *original['official_sources']]
    for name in old.DIAGNOSTIC_OWNED:
        path = str(c.HERE / name)
        archived = f.ref(Path(archive_ref['path']).parent / (name + '.bin'), executable=True)
        f.require(indexed.get(path) == dict(archived, path=path) and archived['mode'] == '0o644' and
                  archived['nlink'] == 1, 'P7 archived source bytes/mode/link mismatch')
        expected[path] = indexed[path]
        pins.append(archived)
    f.require(indexed == expected and len(indexed) == 30, 'P7 historical source substitution/duplicate')
    return pins


def _actual_entry(reference):
    c = _core()
    import remaining_evidence_replay as old
    f.require(reference == dict(path=str(c.CONTROL_ROOT / 'post-TDD-P7-actual-r1/observation.json'),
              sha256=OBSERVATION_SHA), 'exact saved P7 observation required')
    raw = c.read_record(reference, 'observation')
    command = c.read_record(raw['command'], 'command')
    release = c.read_record(command['release'], 'stage-release')
    plan = read_record(release['plan'], 'row-plan')
    scope = read_record(plan['scope'], 'scope')
    decision = c.read_record(release['decision'], 'decision')
    contract = read_record(plan['contract'], 'contract')
    baseline = c.validate_baseline(release['baseline'])
    f.require(raw['stage'] == release['stage'] == plan['row_id'] == decision['stage'] == P7 and
              raw['baseline'] == release['baseline'] and raw['campaign'] == release['campaign'] == baseline['campaign'] and
              raw['donor'] == release['donor'] == plan['donor_slot'] == c.ROWS[P7] and
              reference['path'] == str(Path(command['output']) / 'observation.json') and command['output'] == plan['output'] and
              plan['branch_id'] == c.BRANCH_ID and plan['claim'] == str(c.donor_claim_path(c.ROWS[P7])) and
              plan['input'] == release['decision'] and contract['row_id'] == P7 and
              contract['obligations'] == c.OBLIGATIONS[P7] and decision['authority_kind'] == 'stage_instruction' and
              plan['source_set'] == release['source_set'] == baseline['source_set'] and
              raw['root'] == scope['root'] == scope['realroot'] and
              raw['failure'] == old.FAILURE and raw['business_PASS'] is False and raw['state_before'] == baseline['state'],
              'exact retained P7 transition HOLD and release bindings')
    require_healthy_close(raw['close'])
    f.require(f.validate_wire(raw['wire'], raw['thread_id'], raw['turn_id']) == raw['accounting'] ==
              dict(actual=1, attempted=1, charged=1, status='ACTUAL', accepted=1), 'actual single P7 USER')
    c.validate_current_environment(raw['environment'], baseline['environment'])
    starts = [value['payload'] for value in raw['wire'] if value['direction'] == 'request' and
              value['payload'].get('method') == 'turn/start']
    f.require(len(starts) == 1 and starts[0]['params'] == dict(threadId=raw['thread_id'],
              input=[dict(type='text', text=decision['input'])]) and
              raw['input_delivery'] == dict(request_sha256=digest(decision['input'].encode()), USER=1),
              'actual exact Root P7 input without added overlay')
    events = [value['payload'] for value in raw['wire'] if value['direction'] == 'response' and
              'method' in value['payload']]
    f.require(f.load_legacy().healthy_terminal(events, 'live'), 'actual completed P7 terminal')
    view = dict(raw, realroot=scope['realroot'])
    capture, state, content = f.validate_review_capture(raw['capture'], view, plan)
    entry = dict(reference=reference, command_ref=raw['command'], release_ref=command['release'], raw=view,
        plan=plan, capture_ref=raw['capture'], capture=capture, state=state, content=content, release=release)
    archive_ref = dict(path=str(c.CONTINUATION / 'remaining-evidence-source-freeze-r9/INDEX.json'), sha256=ARCHIVE_SHA)
    pins = _historical_source30(release['source_set'], archive_ref)
    pins += [reference, raw['command'], command['release'], release['plan'], plan['scope'], plan['contract'],
             release['decision'], release['baseline'], release['policy'], raw['capture'],
             capture['state_before'], capture['state_after'], *capture['files'].values()]
    return entry, baseline, pins


def _old_chain(author, baseline):
    c = _core()
    import remaining_evidence_handoff as h
    import remaining_evidence_replay as old
    from remaining_evidence_operator import baseline_configuration, same_invariant
    reference = author['release']['predecessor']
    f.require(reference == dict(path=str(c.CONTROL_ROOT / 'post-TDD-P7-preparation-r3/replay-bridge.json'),
              sha256='85005d7b9746edb98a28817060cd374619410dfbc93a5e386e2f07589c4dee47'),
              'exact old P7 replay predecessor required')
    bridge = c.read_record(reference, 'replay-bridge')
    f.require(bridge['current_source_set'] == author['release']['source_set'] and
              bridge['campaign'] == author['raw']['campaign'] and bridge['preserved_failures'] == c.FAILURES and
              bridge['inherited_failures'] == c.RECOVERY_FAILURES and bridge['admissible_for'] == [P7] and
              bridge['goal_complete'] is False and bridge['environment_transition'] is not None,
              'old P7 bridge provenance/quality boundaries')
    historical = old.validate_historical_source26(bridge['historical_source_set'], bridge['archive'])
    git, evidence, pins = old._actual_p6(bridge['observation'], historical)
    pins += old._reviewed_replay(bridge, evidence, git)
    current_campaign = c.read_record(bridge['campaign'], 'campaign')
    old_campaign = c.read_record(bridge['historical_campaign'], 'campaign')
    f.require(git['raw']['campaign'] == bridge['historical_campaign'] and
              old_campaign['source_set'] == bridge['historical_source_set'] and
              current_campaign['source_set'] == bridge['current_source_set'] and
              dict(current_campaign, source_set=None) == dict(old_campaign, source_set=None),
              'only exact historical source epoch crosses old campaigns')
    pins += old._environment_transition(bridge['environment_transition'], bridge, git, None, None)
    transition = c.read_record(bridge['environment_transition'], 'environment-transition')
    diagnostic = c.validate_baseline(transition['diagnostic_baseline'])
    f.require(baseline['state'] == diagnostic['state'] == git['state'] and
              baseline['scope'] == diagnostic['scope'] and baseline['manifest'] == diagnostic['manifest'] and
              baseline['native']['snapshot'] == diagnostic['native']['snapshot'],
              'saved P7 baseline must match explicit diagnostic state/scope/manifest/native')
    c.validate_current_environment(baseline['environment'], diagnostic['environment'])
    same_invariant(baseline['invariant'], diagnostic['invariant'])
    f.require(baseline_configuration(baseline) == baseline_configuration(diagnostic),
              'saved P7 actual configuration differs from explicit new context')
    assessment_ref = git['release']['predecessor']
    assessment = c.validate_assessment(assessment_ref)
    previous = h._entry(assessment['observation'])
    previous['assessment_ref'], previous['assessment'] = assessment_ref, assessment
    seed = c.validate_recovery_seed(previous['release']['predecessor'], release=previous['release'],
                                    historical_sources=historical)
    previous['recovery_seed_pins'] = seed['pins']
    pins += list(historical.pins.values()) + list(seed['pins'].values()) + [reference]
    pins += [bridge[key] for key in ('campaign', 'historical_campaign', 'current_source_set',
                                    'historical_source_set', 'archive', 'observation', 'replay_result', 'review', 'adoption')]
    return [author, git, previous], pins


def _capability(reference, author):
    c = _core()
    import remaining_evidence_replay as old
    f.require(reference == dict(path=str(c.CONTINUATION / 'P7-capability-witness-r1/RESULT.json'),
              sha256=CAPABILITY_SHA), 'exact actual capability witness required')
    witness = f.decode(read_ref(reference))
    contract = read_record(author['plan']['contract'], 'contract')
    profile_ref = contract['capability_profile']
    profile = read_record(profile_ref, 'capability-profile')
    producer = dict(path=str(c.CONTINUATION / 'P7-capability-witness-r1/probe.py'), sha256=CAPABILITY_PRODUCER_SHA)
    f.require(witness['scope'] == 'ACTUAL_ZERO_USER_FULL_CONFIG_CAPABILITY_WITNESS' and
              witness['actual_P7'] == author['reference'] and witness['profile'] == profile_ref and
              witness['source_set'] == author['release']['source_set'] and witness['producer'] == producer and
              witness['failure'] is None and witness['configuration_body_saved'] is False and
              witness['model_USER'] == witness['thread_starts'] == 0 and
              witness['accounting'] == old.ZERO_CHARGE and witness['before_sha256'] == witness['after_sha256'] ==
              canonical_hash(author['state']), 'actual zero-USER unchanged-state capability witness')
    require_healthy_close(witness['close'])
    f.require(f.validate_wire(witness['wire'], None, None) == old.ZERO_CHARGE, 'capability probe cannot send USER')
    requests = [value['payload'] for value in witness['wire'] if value['direction'] == 'request']
    f.require([value['method'] for value in requests] == ['initialize', 'initialized', 'config/read', 'config/read'],
              'capability witness exact read-only RPC profile')
    config_calls = {value['id'] for value in requests if value['method'] == 'config/read'}
    replies = [value['payload']['result'] for value in witness['wire'] if value['direction'] == 'response' and
               value['payload'].get('id') in config_calls and 'result' in value['payload']]
    f.require(len(replies) == 2 and replies[0] == replies[1] == witness['config_receipt'],
              'capability actual configuration A/B receipt')
    phases = [sample for sample in author['raw']['samples'] if sample['phase'] in
              ('preflight', 'post-start-1', 'post-start-2', 'predispatch', 'postterminal')]
    names = ['preflight', 'post-start-1', 'post-start-2', 'predispatch', 'postterminal']
    f.require([sample['phase'] for sample in phases] == witness['P7_matched_phases'] == names and
              all(sample['frame']['config'] == witness['config_receipt'] for sample in phases),
              'actual capability receipt must match every P7 phase')
    for sample in phases:
        f.require(sample['before'] == sample['after'] and sample['frame']['state_sha256'] ==
                  canonical_hash(sample['after']) and sample['frame']['metadata_sha256'] == canonical_hash(sample['metadata']) and
                  sample['metadata'] == phases[0]['metadata'] and all(sample['frame'][key] == phases[0]['frame'][key]
                  for key in ('catalog', 'catalog_proof')), 'actual P7 within-context sample drift')
    c.validate_current_environment(witness['environment'], author['raw']['environment'])
    proof = witness['capability']
    fields(proof, 'route agents_enabled multi_agent_v2 dynamic_tools client_review_rpc external_review_cli wording business_PASS')
    f.require(profile['route'] == proof['route'] == 'model-native-independent-agent' and profile['process_only'] is True and
              profile['agents_enabled'] is proof['agents_enabled'] is False and
              profile['multi_agent_v2'] is proof['multi_agent_v2'] is False and
              profile['dynamic_tools'] == proof['dynamic_tools'] == [] and
              profile['client_review_rpc'] is proof['client_review_rpc'] is False and
              profile['external_review_cli'] is proof['external_review_cli'] is False and
              profile['wording'] == proof['wording'] == 'independent-agent review unavailable in this declared P7 route' and
              proof['business_PASS'] is False, 'actual frozen capability return shape/route')
    pins = [reference, producer, profile_ref, *profile['official_sources']]
    for pin in pins:
        read_ref(pin)
    return proof, pins


def _packet_endpoints(packet, author, git):
    """Check all36 model-declared endpoints, including unchanged/empty payloads."""
    contract = read_record(author['plan']['contract'], 'contract')
    content, state = author['content'], author['state']
    manifest = f.decode(content[PREFIX + 'manifest.json'])
    f.require(manifest['repository'] == author['raw']['root'] and
              manifest['authorized_scope'] == packet['target'] and
              manifest['context']['external_callers'] == packet['callers'] and
              all(manifest[key] == packet[key] for key in ('base', 'head', 'merge_base')) and
              len(manifest['write_allowlist']) == 18 and
              {PREFIX + path for path in manifest['write_allowlist']} == set(contract['roles']['packet']),
              'actual model manifest scope/OIDs/finite write set')
    store = f.CapturedGit(content)
    base = store.tree(store.commit(packet['base'])[0])
    head = store.tree(store.commit(packet['head'])[0])
    used = {}
    for path in packet['target']:
        for side in ('base', 'head', 'index', 'current'):
            model = manifest['endpoints'][path][side]
            f.require(type(model) is dict, 'actual model endpoint object')
            if model['exists'] is False:
                f.require(model['artifact'] is model['sha256'] is model['mode'] is None,
                          'actual model absent endpoint cannot invent payload')
                endpoint = None
            else:
                f.require(model['exists'] is True and type(model['artifact']) is str, 'actual model endpoint presence')
                artifact = PREFIX + model['artifact']
                f.require(artifact in contract['roles']['packet'] and artifact in content,
                          'model endpoint must be an actual finite packet copy')
                data = content[artifact]
                mode = {'100644': '0o644', '100755': '0o755'}.get(model['mode'], model['mode'])
                oid = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
                f.require(digest(data) == model['sha256'] and len(data) == model['bytes'] and
                          state[artifact]['mode'] == mode and model.get('git_blob_oid', oid) == oid,
                          'actual model endpoint content/mode/size/OID')
                endpoint = dict(content=author['capture']['files'][artifact], mode=mode, oid=oid)
                used[artifact] = dict(mode=mode, sha256=digest(data), bytes=len(data))
            if side == 'current':
                trusted = f._file_endpoint(state, content, path, contract['roles']['off'])
                actual_mode = state[path]['mode'] if path == contract['roles']['off'] else None
            else:
                trusted, actual_mode = (base if side == 'base' else head).get(path), None
            f._endpoint_equal(endpoint, trusted, actual_mode)
    for layer in ('commit', 'index', 'worktree', 'untracked'):
        f.require(manifest['layers'][layer]['present'] == bool(packet[layer]) and
                  set(manifest['layers'][layer]['paths']) == set(packet[layer]), 'actual model layer declaration')
    check = manifest['decisive_check']
    f.require(check['classification'] == 'CAPTURED_P6_CONTEXT_ONLY' and
              check['observation_sha256'] == git['reference']['sha256'] and len(packet['checks']) == 1 and
              packet['checks'][0]['context'] == git['reference'] and
              packet['checks'][0]['wire_index'] == check['wire_index'], 'actual model check retains captured P6 scope')
    item = git['raw']['wire'][check['wire_index']]['payload']['params']['item']
    f.require(item['command'] == check['actual_wire_command'] and item['cwd'] == check['cwd'] and
              item['exitCode'] == check['exitCode'] == 0 and item['aggregatedOutput'] == check['output'],
              'actual model check fields match exact saved P6 event')
    finals = [(index, value['payload']['params']['item']['text']) for index, value in enumerate(author['raw']['wire'])
              if value['direction'] == 'response' and value['payload'].get('method') == 'item/completed' and
              value['payload'].get('params', {}).get('item', {}).get('type') == 'agentMessage' and
              value['payload']['params']['item'].get('phase') == 'final_answer']
    f.require(len(finals) == 1 and all(word in finals[0][1] for word in
              ('CAPTURED_P6_CONTEXT_ONLY', '独立レビュー未完了', '利用不可')), 'actual unavailable/incomplete P7 stop')
    for path, value in used.items():
        f.require(value['bytes'] != 0 or path in finals[0][1], 'empty packet copy needs actual model provenance')
    changed = {path for path in set(author['raw']['state_before']) | set(state)
               if author['raw']['state_before'].get(path) != state.get(path)}
    f.require(len(packet['target']) == 9 and len(used) == 12 and len(contract['roles']['packet']) == 18 and
              changed == set(contract['authored']) and len(changed) == 35,
              'actual P7 finite9target/12payload/18file/35path footprint')
    return dict(targets=9, endpoints=36, payloads=used, packet_files=18, changed_paths=35,
                origins=len(packet['origins']), final_answer_wire_index=finals[0][0])


def replay_actual_p7(observation, packet, capability_witness):
    c = _core()
    import remaining_evidence_handoff as h
    author, baseline, pins = _actual_entry(observation)
    entries, old_pins = _old_chain(author, baseline)
    pins += old_pins
    contexts = {canonical_hash(entry['reference']): entry for entry in entries}
    captures = {canonical_hash(entry['capture_ref']): entry for entry in entries}
    _protected_reference(packet)
    capability, capability_pins = _capability(capability_witness, author)
    pins += capability_pins + [packet]
    validated = h._packet(packet, author, entries, contexts, captures, dict(manifest=baseline['manifest']))
    endpoints = _packet_endpoints(validated, author, entries[1])
    contract = read_record(author['plan']['contract'], 'contract')
    copied = copied_off_proof(author['plan'], author['raw']['state_before'], author['state'], author['content'])
    transition = validate_transition(author['plan'], author['raw']['state_before'], author['state'],
        contract['evidence'], contents_before={}, contents_after={}, capability_proof=capability, copy_proof=copied)
    for entry in entries:
        pins += [entry[key] for key in ('reference', 'command_ref', 'release_ref', 'capture_ref')]
        pins += [entry['plan']['contract'], entry['release']['plan'], entry['release']['decision'], entry['release']['baseline']]
        pins += [entry['capture']['state_before'], entry['capture']['state_after'], *entry['capture']['files'].values()]
    for pin in pins:
        read_ref(pin, executable='size' in pin)
    evidence = dict(schema='remaining-p7-saved-replay-v1', observation=observation, packet=packet,
        capability_witness=capability_witness, historical_source_set=author['release']['source_set'],
        archive=dict(path=str(c.CONTINUATION / 'remaining-evidence-source-freeze-r9/INDEX.json'), sha256=ARCHIVE_SHA),
        verifier=f.ref(Path(__file__)), original_failure=author['raw']['failure'], original_business_PASS=False,
        capability=capability, copied_off_proof=copied, transition=transition, packet_audit=endpoints,
        chain=[entry['reference'] for entry in entries], accounting=ACCOUNTING,
        status='EXACT_SAVED_P7_REPLAY_VALIDATED_SUPPLEMENT_ONLY', runtime_admission=False,
        assessment_admission=False, P8_authorized=False, new_model_USER=0, goal_complete=False)
    proof = _ReplayedP7(author, entries, contexts, captures, {pin['path']: pin for pin in pins}, evidence)
    proof.bridge_ref = None
    return proof



def _protected_reference(reference):
    f.ref_shape(reference)
    f.require(Path(reference['path']).is_relative_to(_core().CONTINUATION),
              'Root P7 replay evidence outside protected continuation')
    read_ref(reference)


def validate_p7_bridge(reference, *, release=None, graph=None):
    c = _core()
    c._controlled(reference)
    bridge = c.read_record(reference, 'p7-replay-bridge')
    f.require(bridge['preserved_failures'] == c.FAILURES and bridge['inherited_failures'] == c.RECOVERY_FAILURES and
              bridge['admissible_for'] == [P8] and bridge['goal_complete'] is False,
              'saved P7 bridge cannot erase failures or widen successor')
    current = c.validate_campaign(bridge['campaign'])
    c.validate_source_set(bridge['current_source_set'])
    old = c.read_record(bridge['historical_campaign'], 'campaign')
    f.require(current['source_set'] == bridge['current_source_set'] and
              old['source_set'] == bridge['historical_source_set'] and
              dict(current, source_set=None) == dict(old, source_set=None), 'only exact source32 epoch may cross P7 campaign')
    proof = replay_actual_p7(bridge['observation'], bridge['packet'], bridge['capability_witness'])
    f.require(proof.entry['raw']['campaign'] == bridge['historical_campaign'] and
              proof.evidence['historical_source_set'] == bridge['historical_source_set'] and
              proof.evidence['archive'] == bridge['archive'], 'bridge exact historical P7 epoch')
    for key in ('replay_result', 'review', 'adoption'):
        _protected_reference(bridge[key])
    f.require(f.decode(read_ref(bridge['replay_result'])) == proof.evidence, 'saved P7 replay result must recompute exactly')
    review = f.decode(read_ref(bridge['review']))
    fields(review, 'verdict issues reviewer reviewed independent_recomputed_exact_result runtime_admission assessment_admission goal_complete')
    reviewed = [f.ref(c.HERE / 'remaining_evidence_p7_replay.py'), f.ref(c.HERE / 'remaining_evidence_p7_replay_test.py'),
                bridge['replay_result'], bridge['packet'], bridge['capability_witness']]
    f.require(review['verdict'] == 'APPROVE' and type(review['issues']) is int and review['issues'] == 0 and
              review['reviewed'] == reviewed and review['independent_recomputed_exact_result'] is True and
              review['runtime_admission'] is False and review['assessment_admission'] is False and
              review['goal_complete'] is False, 'independent exact P7 supplemental review required')
    f.nonempty(review['reviewer'])
    c._controlled(bridge['adoption'])
    adoption = f.decode(read_ref(bridge['adoption']))
    fields(adoption, 'decision actor observation packet capability_witness replay_result review current_source_set accounting preserved_failures inherited_failures raw_failure_preserved no_retry no_extra_capacity judgment')
    f.require(adoption['decision'] == 'ROOT_ADOPT_EXACT_SAVED_P7_REPLAY_FOR_P8' and adoption['actor'] == 'Root' and
              all(adoption[key] == bridge[key] for key in ('observation', 'packet', 'capability_witness', 'replay_result',
                  'review', 'current_source_set')) and adoption['accounting'] == ACCOUNTING and
              adoption['preserved_failures'] == c.FAILURES and adoption['inherited_failures'] == c.RECOVERY_FAILURES and
              adoption['raw_failure_preserved'] is True and adoption['no_retry'] is True and
              adoption['no_extra_capacity'] is True, 'separate exact Root P7 replay adoption required')
    f.nonempty(adoption['judgment'])
    f.require(type(bridge['verdicts']) is dict and set(bridge['verdicts']) == set(c.OBLIGATIONS[P7]),
              'exact independent P7 obligation verdicts')
    pins = list(proof.pins.values()) + [reference] + reviewed
    for finding in bridge['verdicts'].values():
        fields(finding, 'verdict sources judgment')
        f.require(finding['verdict'] == 'PASS' and type(finding['sources']) is list and finding['sources'],
                  'all actual P7 obligations must pass')
        f.nonempty(finding['judgment'])
        pins += finding['sources']
    if release is not None:
        f.require(release['stage'] == P8 and release['predecessor'] == reference and
                  release['campaign'] == bridge['campaign'] and release['source_set'] == bridge['current_source_set'],
                  'P7 replay bridge is exact current P8-only predecessor')
    if graph is not None:
        f.require(release is not None and graph['campaign'] == bridge['campaign'] and
                  graph['source_set'] == bridge['current_source_set'], 'P8 current graph/source/campaign binding')
    for key in ('campaign', 'current_source_set', 'historical_campaign', 'historical_source_set', 'archive',
                'observation', 'packet', 'capability_witness', 'replay_result', 'review', 'adoption'):
        pins.append(bridge[key])
    for pin in pins:
        read_ref(pin, executable='size' in pin)
    proof.pins = {pin['path']: pin for pin in pins}
    proof.bridge, proof.bridge_ref = bridge, reference
    return proof
