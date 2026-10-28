"""Finite saved-P6 bridge: immutable failure, current launch epoch, no processes.

Historical source bytes are checked as data, never imported or executed. This
module produces a typed predecessor only after recomputing the complete saved
cache/Git/transition proof. Ordinary failed assessments remain inadmissible.
"""
import os
from pathlib import Path
import shutil

import cache_payload_replay as payload
import postclosure_recovery as f
from owned_transport import require_healthy_close

P6, P7 = 'D2-tail/Git-AC9', 'D2-tail/unavailable-review'
OBSERVATION_SHA = '42479303be84aff6afd4cfa7beb4821512ae971216b9c9f2762c495e44d53049'
SOURCE26_SHA = '0a50d0205f3c91f14e1eb9cd5ad9c0383dce19823a4747bd9b748a996dba13e2'
ARCHIVE_SHA = 'b1a95ab8024c6dda7f055d5353ef6833a387f1ae1e2eb956f9abded97720abc7'
RESULT_SHA = '7935c647f6ac31b1f3786c29219dbc7897ba22305e7657255ce57510a3da8a4c'
REVIEW_SHA = '77e8c008c359124b1ecf9035b73e408b440ce98d62ca197aa34c3fb00c5ea18f'
OLD_OWNED = ('remaining_evidence.py', 'remaining_evidence_operator.py',
    'remaining_evidence_test.py', 'remaining_evidence_operator_test.py',
    'remaining_evidence_handoff.py', 'remaining_evidence_handoff_test.py',
    'owned_transport.py', 'owned_transport_test.py')
ADOPTION_FIELDS = ('decision actor observation replay_result review current_source_set '
    'accounting preserved_failures inherited_failures raw_failure_preserved no_retry '
    'no_extra_capacity judgment')
ACCOUNTING = dict(charged=85, unspent=22, planning_whole=107)
FAILURE = dict(primary=dict(exception_type='Hold', stage='transition',
                           reason_code='CONTRACT_HOLD'), secondary=[])


def _core():
    import remaining_evidence
    return remaining_evidence


class _HistoricalSources:
    """Validated finite source resolver; not an execution-source substitute."""
    def __init__(self, sources, replacements, pins):
        self.sources, self._replacements, self.pins = sources, replacements, pins

    def resolve(self, pin):
        f.ref_shape(pin, executable='size' in pin)
        replacement = self._replacements.get(pin['path'])
        if replacement is None:
            return pin
        original, archived = replacement
        f.require(pin == original, 'historical source substitution')
        return archived


class _ReplayedPredecessor:
    """Producer-typed saved evidence. Raw failure is intentionally retained."""
    def __init__(self, entry, pins, historical_sources, evidence):
        self.entry, self.pins = entry, pins
        self.historical_sources, self.evidence = historical_sources, evidence


def validate_historical_source26(reference, archive):
    c = _core()
    expected_source = dict(path=str(c.CONTROL_ROOT / 'post-TDD-preparation-r2/source-set.json'),
                           sha256=SOURCE26_SHA)
    expected_archive = dict(path=str(c.CONTINUATION / 'remaining-evidence-source-freeze-r6/INDEX.json'),
                            sha256=ARCHIVE_SHA)
    f.require(reference == expected_source and archive == expected_archive,
              'exact historical source26/archive required')
    c._controlled(reference)
    sources = c.read_record(reference, 'source-set')
    index = f.decode(f.read_ref(archive))
    f.require(index['files'] == sources['files'] and
              index['official_sources'] == sources['official_sources'], 'historical source/archive index mismatch')
    original = f.read_record(dict(path=str(c.FROZEN_SOURCE_SET), sha256=c.FROZEN_SOURCE_SET_SHA), 'source-set')
    f.validate_source_set(original)
    expected = {pin['path']: pin for pin in original['files']}
    f.require(len(sources['files']) == 26 and sources['official_sources'] == original['official_sources'],
              'historical original18/97 source closure')
    replacements, pins = {}, [reference, archive, *original['files'], *original['official_sources']]
    indexed = {pin['path']: pin for pin in sources['files']}
    f.require(len(indexed) == 26, 'duplicate historical source path')
    for name in OLD_OWNED:
        path = str(c.HERE / name)
        f.require(path in indexed, 'missing historical owned source')
        logical = indexed[path]
        archived = f.ref(Path(archive['path']).parent / (name + '.bin'), executable=True)
        f.require(logical == dict(archived, path=path) and archived['nlink'] == 1 and
                  archived['mode'] == '0o644', 'historical archive bytes/mode/link mismatch')
        replacements[path] = logical, archived
        expected[path] = logical
        pins.append(archived)
    f.require(indexed == expected, 'historical source substitution')
    return _HistoricalSources(sources, replacements, {pin['path']: pin for pin in pins})


def _actual_p6(reference, historical_sources):
    """Validate exact old entry bindings, then recompute its saved transition."""
    c = _core()
    f.require(type(historical_sources) is _HistoricalSources, 'typed historical source proof required')
    f.require(reference == dict(path=str(c.CONTROL_ROOT / 'post-TDD-P6-actual-r1/observation.json'),
                               sha256=OBSERVATION_SHA), 'exact saved P6 observation required')
    raw = c.read_record(reference, 'observation')
    command = c.read_record(raw['command'], 'command')
    release = c.read_record(command['release'], 'stage-release')
    plan = f.read_record(release['plan'], 'row-plan')
    contract = f.read_record(plan['contract'], 'contract')
    scope = f.read_record(plan['scope'], 'scope')
    decision = c.read_record(release['decision'], 'decision')
    baseline = c.validate_baseline(release['baseline'])
    f.require(raw['stage'] == release['stage'] == plan['row_id'] == decision['stage'] == P6 and
              raw['baseline'] == release['baseline'] and raw['campaign'] == release['campaign'] == baseline['campaign'] and
              raw['donor'] == release['donor'] == plan['donor_slot'] == c.ROWS[P6] and
              raw['root'] == scope['root'] == scope['realroot'] and
              reference['path'] == str(Path(command['output']) / 'observation.json') and
              command['output'] == plan['output'] and plan['branch_id'] == c.BRANCH_ID and
              plan['claim'] == str(c.donor_claim_path(c.ROWS[P6])) and
              plan['input'] == release['decision'] and decision['authority_kind'] == 'exact_git_grant' and
              contract['row_id'] == P6 and contract['obligations'] == c.OBLIGATIONS[P6] and
              plan['source_set'] == release['source_set'] == baseline['source_set'] and
              f.decode(f.read_ref(plan['source_set'])) == historical_sources.sources and
              raw['state_before'] == baseline['state'] and raw['failure'] == FAILURE and
              raw['business_PASS'] is False, 'exact failed P6 release/plan/decision bindings')
    require_healthy_close(raw['close'])
    charge = f.validate_wire(raw['wire'], raw['thread_id'], raw['turn_id'])
    f.require(charge == raw['accounting'] == dict(actual=1, attempted=1, charged=1,
              status='ACTUAL', accepted=1), 'single actual P6 USER')
    c.validate_current_environment(raw['environment'], baseline['environment'])
    starts = [v['payload'] for v in raw['wire'] if v['direction'] == 'request' and
              v['payload'].get('method') == 'turn/start']
    policy = f.read_record(release['policy'], 'process-policy')
    overlay = f.validate_turn_permission(policy, plan, scope, release['plan'])
    f.require(len(starts) == 1 and starts[0].get('params') == dict(threadId=raw['thread_id'],
              input=[dict(type='text', text=decision['input'])], **overlay) and
              raw['input_delivery'] == dict(request_sha256=f.digest(decision['input'].encode()), USER=1),
              'actual exact P6 input and finite Git overlay')
    view = dict(raw, realroot=scope['realroot'])
    capture, after, after_bytes = f.validate_review_capture(raw['capture'], view, plan)
    previous_assessment = c.validate_assessment(release['predecessor'])
    f.require(previous_assessment['stage'] == 'D2-tail/content-to-operation-question' and
              previous_assessment['campaign'] == raw['campaign'] and previous_assessment['integrity'] == 'PASS' and
              previous_assessment['admissible_for'] == [P6], 'actual accepted P5 predecessor required')
    previous = c.read_record(previous_assessment['observation'], 'observation')
    previous_command = c.read_record(previous['command'], 'command')
    previous_release = c.read_record(previous_command['release'], 'stage-release')
    previous_plan = f.read_record(previous_release['plan'], 'row-plan')
    before_capture, before, before_bytes = f.validate_review_capture(previous['capture'],
        dict(previous, realroot=scope['realroot']), previous_plan)
    f.require(before == raw['state_before'], 'P5/P6 complete endpoint relation')
    seed = c.validate_recovery_seed(previous_release['predecessor'], release=previous_release,
                                    historical_sources=historical_sources)
    events = [v['payload'] for v in raw['wire'] if v['direction'] == 'response' and 'id' not in v['payload']]
    f.require(f.load_legacy().healthy_terminal(events, 'live'), 'actual healthy P6 terminal')
    versions, off, sample_pins = [], [], []
    for sample in raw['samples']:
        if sample['phase'] == 'post-command-source-equivalence':
            for version in sample['versions']:
                versions.append({**{k: v for k, v in version.items() if k != 'capture'},
                                 'bytes': f.read_ref(version['capture'])})
                sample_pins.append(version['capture'])
        if sample['phase'] == 'P6-off-observation':
            off.append(sample['observation'])
            sample_pins.append(sample['observation']['capture'])
    cache_profile = f.read_record(contract['cache_profile'], 'cache-profile')
    git_profile = f.read_record(contract['git_profile'], 'git-profile')
    cache = payload.validate_derived_caches_replay(cache_profile, before, after, versions, events,
        Path(raw['root']), cache_profile['environment'], captured_files=after_bytes)
    git = f.validate_git_rollback(git_profile, before, after, before_bytes, after_bytes,
        events, contract['roles'], cache, off)
    def artifacts(content):
        return {name: content[name] for name in (contract['roles']['spec'], contract['roles']['tasks'])}
    transition = f.validate_transition(plan, before, after, contract['evidence'],
        contents_before=artifacts(before_bytes), contents_after=artifacts(after_bytes),
        cache_proof=cache, git_proof=git)
    evidence = dict(cache=cache, git=git, transition=transition)
    pins = [reference, raw['command'], command['release'], release['plan'], release['decision'],
            release['baseline'], release['policy'], plan['scope'], plan['contract'],
            contract['cache_profile'], contract['git_profile'], raw['capture'],
            capture['state_before'], capture['state_after'], *capture['files'].values(),
            release['predecessor'], previous_assessment['observation'], previous['capture'],
            previous['command'], previous_command['release'], previous_release['plan'], previous_plan['contract'],
            before_capture['state_before'], before_capture['state_after'], *before_capture['files'].values(),
            cache_profile['interpreter']['executable'], cache_profile['command_interpreter_proof'],
            *cache_profile['official_sources'], git_profile['executable'], git_profile['environment_proof'],
            *git_profile['official_sources'], *sample_pins]
    if git_profile['env_executable'] is not None:
        pins.append(git_profile['env_executable'])
    permission = f.read_record(policy['turn_permission'], 'turn-permission')
    pins += [policy['turn_permission'], permission['managed_probe'], *permission['primary_sources']]
    pins += list(seed['pins'].values())
    entry = dict(reference=reference, command_ref=raw['command'], release_ref=command['release'],
        raw=view, plan=plan, capture_ref=raw['capture'], capture=capture,
        state=after, content=after_bytes, release=release)
    return entry, evidence, pins


def _reviewed_replay(bridge, evidence, entry):
    c = _core()
    f.require(bridge['replay_result'] == dict(path=str(c.CONTINUATION / 'saved-P6-payload-replay-r1/RESULT.json'),
              sha256=RESULT_SHA) and bridge['review'] == dict(
              path=str(c.CONTINUATION / 'saved-P6-payload-replay-r1/INDEPENDENT-REVIEW.json'), sha256=REVIEW_SHA),
              'exact saved supplemental result/review required')
    saved = f.decode(f.read_ref(bridge['replay_result']))
    f.require(saved['replay_status'] == 'TRANSITION_VALIDATED_SUPPLEMENT_ONLY' and
              all(saved[key] == evidence[key] for key in ('cache', 'git', 'transition')) and
              saved['original_observation'] == bridge['observation'] and saved['original_failure'] == FAILURE and
              saved['original_business_PASS'] is False and saved['frozen_source_set'] == bridge['historical_source_set'] and
              saved['new_model_USER'] == 0 and saved['accounting'] == ACCOUNTING and
              saved['candidate_decoded_or_executed'] is False and saved['runtime_admission_changed'] is False and
              saved['assessment_admission_changed'] is False and saved['goal_complete'] is False and
              saved['supplemental_verifier'] == f.ref(Path(payload.__file__)), 'saved supplemental proof must recompute exactly')
    review = f.decode(f.read_ref(bridge['review']))
    f.fields(review, 'verdict issues reviewer reviewed independent_recomputed_exact_result runtime_admission assessment_admission goal_complete')
    expected_reviewed = [f.ref(c.HERE / 'cache_payload_replay.py'), f.ref(c.HERE / 'cache_payload_replay_test.py'),
        f.ref(c.CONTINUATION / 'saved-P6-payload-replay-r1/replay.py'), bridge['replay_result']]
    f.require(review['verdict'] == 'APPROVE_SUPPLEMENTAL_ONLY' and type(review['issues']) is int and
              review['issues'] == 0 and review['reviewed'] == expected_reviewed and
              review['independent_recomputed_exact_result'] is True and review['runtime_admission'] is False and
              review['assessment_admission'] is False and review['goal_complete'] is False,
              'independent supplemental-only review required')
    f.nonempty(review['reviewer'])
    c._controlled(bridge['adoption'])
    adoption = f.decode(f.read_ref(bridge['adoption']))
    f.fields(adoption, ADOPTION_FIELDS)
    f.require(adoption['decision'] == 'ROOT_ADOPT_EXACT_SAVED_P6_REPLAY_FOR_P7' and adoption['actor'] == 'Root' and
              all(adoption[key] == bridge[key] for key in ('observation', 'replay_result', 'review', 'current_source_set')) and
              adoption['accounting'] == ACCOUNTING and adoption['preserved_failures'] == c.FAILURES and
              adoption['inherited_failures'] == c.RECOVERY_FAILURES and adoption['raw_failure_preserved'] is True and
              adoption['no_retry'] is True and adoption['no_extra_capacity'] is True,
              'separate exact Root replay adoption required')
    f.nonempty(adoption['judgment'])
    f.require(type(bridge['verdicts']) is dict and set(bridge['verdicts']) == set(c.OBLIGATIONS[P6]),
              'exact P6 obligation verdicts required')
    pins = list(expected_reviewed)
    for finding in bridge['verdicts'].values():
        f.fields(finding, 'verdict sources judgment')
        f.require(finding['verdict'] == 'PASS' and type(finding['sources']) is list and finding['sources'],
                  'all actual P6 obligations must pass')
        f.nonempty(finding['judgment'])
        for pin in finding['sources']:
            f.read_ref(pin, executable='size' in pin)
            pins.append(pin)
    return pins



DIAGNOSTIC_BASELINE_SHA = 'eac9dd3890e7c3247906642d7051813d81d6e55d07a51cbc9972071f424760a3'
DIAGNOSTIC_OBSERVATION_SHA = 'ce943dbad68bef5ec3955d5047cb575825edae6feb92c72ae95add331b69f920'
DIAGNOSTIC_ARCHIVE_SHA = 'a50bf5d2a244a4ecafcdc0a11c136fb5e32fa177eff77f072352f82ab907c048'
COMPARISON_SHA = 'ce14e52d452117eca85f49bb6a709d93c379ea17cc30fdc0aa5df924fdbdc2e5'
DIAGNOSTIC_OWNED = OLD_OWNED + ('cache_payload_replay.py', 'cache_payload_replay_test.py',
                               'remaining_evidence_replay.py', 'remaining_evidence_replay_test.py')
ZERO_CHARGE = dict(actual=0, attempted=0, charged=0, status='ZERO', accepted=0)


def _diagnostic_source30(reference, source_set):
    c = _core()
    f.require(reference == dict(path=str(c.CONTINUATION / 'remaining-evidence-source-freeze-r7/INDEX.json'),
              sha256=DIAGNOSTIC_ARCHIVE_SHA), 'exact diagnostic source30 archive required')
    index = f.decode(f.read_ref(reference))
    f.require(index['source_set'] == source_set, 'diagnostic source/archive edge')
    source = c.read_record(source_set, 'source-set')
    original = f.read_record(dict(path=str(c.FROZEN_SOURCE_SET), sha256=c.FROZEN_SOURCE_SET_SHA), 'source-set')
    f.validate_source_set(original)
    f.require(index['files'] == source['files'] and index['official_sources'] == source['official_sources'] ==
              original['official_sources'] and len(source['files']) == 30, 'exact diagnostic original18/97/12 closure')
    expected = {pin['path']: pin for pin in original['files']}
    indexed = {pin['path']: pin for pin in source['files']}
    pins = [reference, source_set, *original['files'], *original['official_sources']]
    for name in DIAGNOSTIC_OWNED:
        path = str(c.HERE / name)
        archived = f.ref(Path(reference['path']).parent / (name + '.bin'), executable=True)
        f.require(indexed.get(path) == dict(archived, path=path) and archived['mode'] == '0o644' and
                  archived['nlink'] == 1, 'diagnostic archived source bytes/mode/link mismatch')
        expected[path] = indexed[path]
        pins.append(archived)
    f.require(indexed == expected and len(indexed) == 30, 'diagnostic source substitution/duplicate')
    return pins


def _diagnostic_zero(transition, entry):
    c = _core()
    directory = c.CONTROL_ROOT / 'post-TDD-P7-current-environment-zero-diagnostic-r1'
    f.require(transition['diagnostic_baseline'] == dict(path=str(directory / 'baseline.json'),
              sha256=DIAGNOSTIC_BASELINE_SHA) and transition['diagnostic_observation'] == dict(
              path=str(directory / 'observation.json'), sha256=DIAGNOSTIC_OBSERVATION_SHA),
              'exact actual diagnostic ZERO required')
    baseline = c.validate_baseline(transition['diagnostic_baseline'])
    raw = c.read_record(transition['diagnostic_observation'], 'observation')
    scope = f.read_record(baseline['scope'], 'scope')
    f.require(raw['command'] == baseline['command'] and raw['campaign'] == baseline['campaign'] and
              raw['baseline'] is None and raw['stage'] is None and raw['donor'] is None and
              raw['turn_id'] is None and raw['input_delivery'] is None and raw['failure'] is None and
              raw['business_PASS'] is False and raw['accounting'] == baseline['accounting'] == ZERO_CHARGE and
              raw['state_before'] == raw['state_after'] == baseline['state'] == entry['state'] and
              raw['environment'] == baseline['environment'] and raw['wire'] == baseline['wire'] and
              raw['close'] == baseline['close'] and raw['thread_id'] == baseline['native']['thread_id'] and
              raw['root'] == scope['root'] == scope['realroot'] == entry['raw']['root'],
              'actual diagnostic ZERO raw/baseline/state/native binding')
    require_healthy_close(raw['close'])
    f.require(f.validate_wire(raw['wire'], raw['thread_id'], None) == ZERO_CHARGE,
              'diagnostic cannot send model USER')
    old_baseline = c.validate_baseline(entry['release']['baseline'])
    f.require(baseline['native']['snapshot'] == old_baseline['native']['snapshot'],
              'diagnostic native profile differs from captured P6')
    samples = [sample for sample in raw['samples'] if sample['phase'] in ('preflight', 'post-start-1', 'post-start-2')]
    f.require([sample['phase'] for sample in samples] == ['preflight', 'post-start-1', 'post-start-2'],
              'diagnostic actual three sampling phases')
    from remaining_evidence_operator import baseline_configuration
    configuration = baseline_configuration(baseline)
    previous_end = -1
    for sample in samples:
        frame = sample['frame']
        f.require(sample['before'] == sample['after'] == baseline['state'] and
                  frame['state_sha256'] == f.canonical_hash(baseline['state']) and
                  frame['metadata_sha256'] == f.canonical_hash(sample['metadata']) and
                  sample['metadata'] == samples[0]['metadata'] and
                  all(frame[key] == samples[0]['frame'][key] for key in ('config', 'catalog', 'catalog_proof')) and
                  frame['catalog_proof']['enabled_unique_targets'] == 16 and frame['catalog_proof']['load_errors'] == 0,
                  'diagnostic state/config/catalog/metadata sampling drift')
        start, end = sample['wire_start'], sample['wire_end']
        f.require(type(start) is int and type(end) is int and previous_end <= start < end <= len(raw['wire']),
                  'diagnostic finite sample wire interval')
        previous_end = end
        wire = raw['wire'][start:end]
        requests = [value['payload'] for value in wire if value['direction'] == 'request']
        f.require([value['method'] for value in requests] == ['config/read', 'skills/list', 'config/read'],
                  'diagnostic sample actual read sequence')
        calls = {value['id']: value['method'] for value in requests}
        configurations = [value['payload']['result'] for value in wire if value['direction'] == 'response' and
                          calls.get(value['payload'].get('id')) == 'config/read' and 'result' in value['payload']]
        catalogs = [value['payload']['result'] for value in wire if value['direction'] == 'response' and
                    calls.get(value['payload'].get('id')) == 'skills/list' and 'result' in value['payload']]
        f.require(configurations == [configuration, configuration] and len(catalogs) == 1 and
                  f.load_legacy().redacted_config(catalogs[0]) == frame['catalog'],
                  'diagnostic actual stable config/catalog replies')
    invariant_hash = f.canonical_hash(baseline['invariant'])
    f.require(samples[0]['frame']['invariant_sha256'] is None and
              samples[1]['frame']['invariant_sha256'] == samples[2]['frame']['invariant_sha256'] == invariant_hash,
              'diagnostic post-start invariant pair')
    command = c.read_record(baseline['command'], 'observe-command')
    pins = [transition['diagnostic_baseline'], transition['diagnostic_observation'], baseline['command'],
            baseline['scope'], baseline['source_set'], baseline['manifest'], raw['capture'],
            command['policy'], command['native_binding'], command['expected_state']]
    capture, _, _ = f.validate_review_capture(raw['capture'], dict(raw, realroot=scope['realroot']),
                                            dict(scope=baseline['scope']))
    pins += [capture['state_before'], capture['state_after'], *capture['files'].values()]
    return baseline, pins


def _environment_transition(reference, bridge, entry, release, graph):
    c = _core()
    c._controlled(reference)
    transition = c.read_record(reference, 'environment-transition')
    f.require(transition['decision'] == 'ROOT_CONTINUE_P7_IN_EXPLICIT_NEW_CONTEXT' and transition['actor'] == 'Root' and
              transition['previous_observation'] == bridge['observation'] and
              transition['current_source_set'] == bridge['current_source_set'] and
              transition['accounting'] == ACCOUNTING and transition['preserved_failures'] == c.FAILURES and
              transition['inherited_failures'] == c.RECOVERY_FAILURES and
              transition['old_environment_equivalence'] == transition['old_config_value_equivalence'] == 'UNPROVEN' and
              transition['old_checks_scope'] == 'CAPTURED_P6_CONTEXT_ONLY' and
              transition['no_retry'] is True and transition['no_extra_capacity'] is True and
              transition['goal_complete'] is False, 'explicit new P7 context cannot rehabilitate old equivalence')
    f.nonempty(transition['judgment'])
    diagnostic, pins = _diagnostic_zero(transition, entry)
    pins += _diagnostic_source30(transition['diagnostic_source_archive'], diagnostic['source_set'])
    expected_comparison = dict(path=str(c.CONTROL_ROOT / 'post-TDD-P7-preparation-r1/CURRENT-ENVIRONMENT-COMPARISON.json'),
                               sha256=COMPARISON_SHA)
    f.require(transition['comparison'] == expected_comparison, 'exact full unknown-environment comparison required')
    comparison = f.decode(f.read_ref(transition['comparison']))
    f.require(comparison['status'] == 'CURRENT_NATIVE_ZERO_HEALTHY_BUT_OLD_ENVIRONMENT_NOT_EQUIVALENT' and
              comparison['old_baseline'] == entry['release']['baseline'] and
              comparison['new_baseline'] == transition['diagnostic_baseline'] and
              comparison['current_full_state_equal_old_P6_after'] is True and
              comparison['configuration_differences'] and comparison['invariant_differences'] and
              comparison['native_snapshot_differences'] == [] and comparison['model_USER'] == 0 and
              comparison['permission_or_P7_release'] is False, 'old context/config equivalence must remain unproven')
    pins += [reference, transition['previous_observation'], transition['current_source_set'], transition['comparison']]
    if graph is not None:
        from remaining_evidence_operator import baseline_configuration, same_invariant
        f.require(release is not None and release['stage'] == P7, 'new context applies to exact P7 release only')
        fresh = c.validate_baseline(release['baseline'])
        f.require(fresh['state'] == graph['state'] == diagnostic['state'] and
                  fresh['scope'] == diagnostic['scope'] and fresh['manifest'] == graph['manifest'] == diagnostic['manifest'] and
                  fresh['source_set'] == bridge['current_source_set'] and
                  fresh['native']['snapshot'] == diagnostic['native']['snapshot'],
                  'new P7 ZERO state/scope/manifest/native drift')
        c.validate_current_environment(fresh['environment'], diagnostic['environment'])
        c.validate_current_environment(graph['expected_environment'], fresh['environment'])
        same_invariant(fresh['invariant'], diagnostic['invariant'])
        f.require(baseline_configuration(fresh) == baseline_configuration(diagnostic),
                  'new P7 ZERO effective config must equal diagnostic context')
        profile = f.read_record(f.read_record(entry['plan']['contract'], 'contract')['cache_profile'], 'cache-profile')
        current_python = {key: os.environ.get(key) for key in f.PYTHON_ENVIRONMENT}
        f.require({key: value for key, value in profile['environment'].items() if key != 'PATH'} ==
                  {key: value for key, value in current_python.items() if key != 'PATH'},
                  'captured P6 Python flags differ from actual P7 environment')
        selected = shutil.which('python3', path=current_python['PATH'])
        f.require(selected is not None and
                  f.ref(Path(selected).resolve(strict=True), executable=True) == profile['interpreter']['executable'],
                  'actual P7 Python selection differs from the captured P6 interpreter')
        pins += [release['baseline'], fresh['command']]
    entry['old_checks_scope'] = 'CAPTURED_P6_CONTEXT_ONLY'
    entry['environment_transition_ref'] = reference
    return pins


def validate_bridge(reference, *, release=None, graph=None):
    c = _core()
    c._controlled(reference)
    bridge = c.read_record(reference, 'replay-bridge')
    f.require(bridge['preserved_failures'] == c.FAILURES and bridge['inherited_failures'] == c.RECOVERY_FAILURES and
              bridge['admissible_for'] == [P7] and bridge['goal_complete'] is False,
              'replay bridge cannot erase failures or widen successor')
    historical = validate_historical_source26(bridge['historical_source_set'], bridge['archive'])
    current = c.validate_campaign(bridge['campaign'])
    c.validate_source_set(bridge['current_source_set'])
    old = c.read_record(bridge['historical_campaign'], 'campaign')
    f.require(current['source_set'] == bridge['current_source_set'] and
              old['source_set'] == bridge['historical_source_set'] and
              dict(current, source_set=None) == dict(old, source_set=None),
              'only reviewed source epoch may cross campaigns')
    entry, evidence, pins = _actual_p6(bridge['observation'], historical)
    f.require(entry['raw']['campaign'] == bridge['historical_campaign'], 'bridge exact historical campaign')
    pins += _reviewed_replay(bridge, evidence, entry)
    for key in ('campaign', 'historical_campaign', 'current_source_set', 'historical_source_set',
                'archive', 'observation', 'replay_result', 'review', 'adoption'):
        f.read_ref(bridge[key])
        pins.append(bridge[key])
    if release is not None:
        f.require(release['stage'] == P7 and release['predecessor'] == reference and
                  release['campaign'] == bridge['campaign'] and release['source_set'] == bridge['current_source_set'],
                  'replay bridge is P7-only in the exact current epoch')
    if graph is not None:
        f.require(release is not None and graph['state'] == entry['state'] and
                  graph['source_set'] == bridge['current_source_set'] and
                  graph['scope']['root'] == graph['scope']['realroot'] == entry['raw']['root'],
                  'fresh P7 ZERO must retain actual P6 full poststate/root')
        if bridge['environment_transition'] is None:
            c.validate_current_environment(graph['expected_environment'], entry['raw']['environment'])
    if bridge['environment_transition'] is not None:
        pins += _environment_transition(bridge['environment_transition'], bridge, entry, release, graph)
    for pin in pins:
        f.read_ref(pin, executable='size' in pin)
    actual_pins = dict(historical.pins)
    actual_pins.update({pin['path']: pin for pin in pins})
    actual_pins[reference['path']] = reference
    entry['replay_bridge_ref'] = reference
    entry['replay_pins'] = actual_pins
    return _ReplayedPredecessor(entry, actual_pins, historical, evidence)
