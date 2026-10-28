#!/usr/bin/env python3
"""Closed, source-only D2 successor contracts. Importing this module is inert.

Authority enters ONLY through a caller-supplied exact operator-command digest. Records
are data, never executable Python. Legacy producers and their runners are not
executed. Raw observations deliberately cannot adjudicate business success.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import marshal
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import struct
import sys
import time
import zlib

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[2]
CONTROL_ROOT = SOURCE / '.omx/continuations/resume-20261027-j56k2v96/postclosure-recovery-r1'
CLAIM_ROOT = CONTROL_ROOT / 'claims'
BRANCH_ID = 'D2tail-deadline-recovery1-resume20261027-j56k2v96'
BASE_ACTUAL = 76
WHOLE = 107
OLD_CONTROL_ROOT = CONTROL_ROOT.parent
OLD_SOURCE_SET = {'path': str(OLD_CONTROL_ROOT / 'postclosure-controller-preparation-r2/source-set-DATA.json'), 'sha256': 'c210598f13561d56fe8ca28f37a3f08684927a82777353534c7abd52f6d34be3'}
CLOSED_HISTORY = {'path': str(OLD_CONTROL_ROOT / 'postclosure-closed-history.json'), 'sha256': '98bf732397101130a6cdb1f2f889343e822e3a051718aa23fdbd9da26c5b97ca'}
OLD_CORE_SHA = 'd65a6707a197e379cca4aace4d451288f54a2c8494d1d8c2ae1855cf24ec5cdf'
LEGACY_SHA = 'c02009d36ae11ed3968dde4b32c69f0c591d362a586c49ea1ee99378cd4c7f53'
LEGACY_PREFIX_SHA = 'a94ccb082b08d3f59ef6b6dca0a14d1dc7cab7f3ab33bf66894299158ff3ea24'
D2_RAW_SHA = 'e66b0c4bb9b6d1fcd4709a9ac0a76fd4e328ad114797a781bdb27b54a5df426d'
D2_STATE_SHA = '6280b5070a5b3d5c7fdbbd2cd63437455ce97f97b1ce32354e1615a1838a2538'
D2_DRAFT_SHA = '7292c6547345cd86a554e749f3d4d2c23102b3aa2788d25a183a3af923ecf2b8'
COMPOSITE_SHA = 'f8765de9b11207e54332c57dd3ceab9beaf147921bfe77a7d8b41f439b0b6514'
D2_ACTUAL_ADOPTION_SHA = 'e45562be84f6a921b966c2827d73483edabbb96dc77a5c4dc5192136dd4ddd8c'
D2_MATERIAL_ADOPTION_SHA = '616d08c0ca35339a25ee4316cd6bcef4c3b13caac982dbfdff898e73606b3b23'
HELPERS = {
    'runtime': 'b4ad4e9dc029d19fe62228f547534f69ade69759a51e64b5341af65fdeaf28dc',
    'activation_recheck': '1bc197305203015c466ce8f53ad5c6af7dc4aed1bdd963e7a6c2df172c224dfd',
    'activation_closure_probe': '291d9efbca6313c93db8bd018d9cc3e1cd1358ae9a7e5437392692acc86a9e67',
    'activation_r3': '7556473ee8f6134553292226e30d2ac2ef49968fd873becfdb6629e1ff2b6fea',
}
ROWS = dict(zip((
    'D2-tail/tasks-initial', 'D2-tail/plan-approval',
    'D2-tail/TDD-build', 'D2-tail/content-to-operation-question', 'D2-tail/Git-AC9',
    'D2-tail/unavailable-review', 'D2-tail/independent-review', 'D2-tail/local-ship',
    'D2-tail/scope-invalidation'), (
    'deadline-repair/tasks-initial/1', 'R7/spec/6', 'R7/spec/7', 'R7/spec/8',
    'R7/spec/9', 'unavailable-review/1', 'independent-review/1', 'R7/spec/10', 'R7/tasks/3')))
FEATURES = ('hooks', 'plugins', 'remote_plugin', 'apps', 'memories',
            'external_agent_memory_import', 'token_budget', 'goals',
            'agent_message_board', 'multi_agent_v2', 'guardian_approval',
            'executor_capability_discovery', 'executor_capability_discovery_v2',
            'skip_host_skill_discovery')
MCP = ('agent-browser', 'computer-use', 'node_repl')
LIMITS = {'contexts': 1, 'USER': 1, 'seconds': 180}
_CURRENT_LEGACY = None


class Hold(RuntimeError):
    """A missing or contradictory premise; never an implicit approval."""


def require(condition, reason):
    if not condition:
        raise Hold(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical_hash(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode())


def fields(value, names):
    require(type(value) is dict and set(value) == set(names.split()),
            'closed fields: ' + names)
    return value


def hash_value(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None,
            'invalid sha256')
    return value


def nonempty(value):
    require(type(value) is str and bool(value.strip()), 'nonempty string required')
    return value


def decode_command(command):
    """Finite native shell wrapper; return a single argv, never evaluate shell."""
    nonempty(command)
    try:
        outer = shlex.split(command)
        if outer and outer[0] in ('/bin/zsh', '/bin/bash', '/bin/sh'):
            require(len(outer) == 3 and outer[1] == '-lc', 'unsupported native shell wrapper')
            inner = outer[2]
        else:
            inner = command
        require('$' not in inner and '`' not in inner and '\n' not in inner and '\r' not in inner,
                'shell substitutions/multiline command not admitted')
        lexer = shlex.shlex(inner, posix=True, punctuation_chars=';&|<>()')
        lexer.whitespace_split = True
        lexer.commenters = ''
        argv = list(lexer)
        require(argv and not any(token and all(character in ';&|<>()' for character in token) for token in argv),
                'compound/redirection command not admitted')
        require(argv == shlex.split(inner), 'noncanonical simple command parse')
        return argv
    except ValueError as error:
        raise Hold('malformed shell command') from error


def command_matches(actual, expected):
    try:
        return decode_command(actual) == decode_command(expected)
    except Hold:
        return False


def absolute(value):
    nonempty(value)
    p = Path(value)
    require(p.is_absolute() and str(p) == value and '..' not in p.parts and
            '.' not in p.parts, 'noncanonical absolute path')
    return p


def relative(value):
    nonempty(value)
    p = Path(value)
    require(not p.is_absolute() and str(p) == value and
            all(x not in ('.', '..') for x in p.parts), 'noncanonical relative path')
    return p


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def decode(data):
    try:
        return json.loads(data, object_pairs_hook=_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(Hold('nonfinite JSON')))
    except (ValueError, UnicodeError) as error:
        raise Hold('invalid JSON') from error


def file_bytes(path, exclusive=True):
    """No symlink/hardlink references, including symlinked parent components."""
    p = absolute(str(path))
    require(p.resolve(strict=True) == p, 'reference path alias')
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and (not exclusive or before.st_nlink == 1),
                'reference must be an exclusive regular file')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            data = stream.read()
        after = os.fstat(fd)
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                 before.st_mode) == (after.st_dev, after.st_ino, after.st_size,
                                      after.st_mtime_ns, after.st_mode) and
                p.lstat().st_ino == before.st_ino, 'reference changed during read')
        return data, after
    finally:
        os.close(fd)


def ref(path, executable=False):
    data, info = file_bytes(path, exclusive=not executable)
    result = {'path': str(path), 'sha256': digest(data)}
    if executable:
        result.update(size=len(data), mode=oct(stat.S_IMODE(info.st_mode)), nlink=info.st_nlink)
    return result


def read_ref(reference, executable=False):
    fields(reference, 'path sha256 size mode nlink' if executable else 'path sha256')
    hash_value(reference['sha256'])
    data, info = file_bytes(reference['path'], exclusive=not executable)
    require(digest(data) == reference['sha256'], 'reference byte drift')
    if executable:
        require(type(reference['size']) is int and reference['size'] == len(data) and
                reference['mode'] == oct(stat.S_IMODE(info.st_mode)) and
                type(reference['nlink']) is int and reference['nlink'] == info.st_nlink > 0, 'size/mode/link-count drift')
    return data


def ref_shape(reference, executable=False):
    fields(reference, 'path sha256 size mode nlink' if executable else 'path sha256')
    absolute(reference['path'])
    hash_value(reference['sha256'])
    if executable:
        require(type(reference['size']) is int and reference['size'] >= 0 and
                type(reference['mode']) is str and re.fullmatch(r'0o[0-7]{3,4}', reference['mode']) and
                type(reference['nlink']) is int and reference['nlink'] > 0, 'executable pin literal types')


SCHEMAS = {
    'source-set': 'files official_sources',
    'legacy-prefix': 'refs prefix_sha256 audit expected_actual expected_held whole reserve',
    'recovery-admission': 'branch_id funding_selection funding_adoption recovery_prefix composite_manifest materialization scopes rows source_review invariant_anchor',
    'scope': 'scope_id root realroot topology materialization instruction_sources install process_choice',
    'row-plan': 'branch_id row_id donor_slot scope predecessor predecessor_review contract input source_set admission output claim limits feasibility',
    'process-policy': 'row_plan scope argv session session_sha256 metadata_paths native_expectation official_sources turn_permission',
    'common': 'row_plan policy lookup native_binding source_set product_manifest predecessor_state_sha256 history_sha256 input_sha256',
    'implementation-review': 'source_set findings decision',
    'source-context-review': 'common implementation_review findings decision',
    'root-review': 'common source_context_review admission row_plan policy lookup release_id decision',
    'release': 'root_review common release_id',
    'command': 'release row_plan native_binding source_set operator output claim history',
    'context': 'branch_id row_id donor_slot common release prior_history_sha256 root realroot process_id thread_id turn_id wire samples input_delivery state_before state_after close failure accounting business_PASS',
    'independent-result': 'context review adjudication decision business_PASS',
    'decision': 'predecessor question request reviewed_artifacts actor',
    'predecessor': 'context independent_result state question',
    'contract': 'row_id roles authored derived immutable_paths expected_before expected_after obligations evidence git_profile cache_profile capability_profile tasks_progress',
    'lookup': 'policy wire state_before state_after native_facts USER',
    'materialization': 'predecessor source_state destination_state relocation composite_manifest topology',
    'funding-adoption': 'selection legacy_prefix branch_id mapping retired reserve decision',
    'process-choice': 'scope_id root realroot topology executable invoked_path invoked_link_text invoked_mode argv environment native_binding decision',
    'review-packet': 'scope capture base head merge_base commit index worktree untracked target callers spec tasks checks resources origins',
    'git-profile': 'branch main_ref off_path off_initial off_data off_mode verification_commands command_prefix env_executable object_format command_cwd executable invoked_path version auto_merge official_sources overrides environment_proof',
    'capability-profile': 'route process_only agents_enabled multi_agent_v2 dynamic_tools client_review_rpc external_review_cli wording official_sources',
    'cache-profile': 'row_id command extra_commands cwd interpreter outputs official_sources environment command_interpreter_proof',
    'question': 'context wire_index item_sha256 text',
    'lookup-review': 'policy scope source_set native_binding implementation_review decision',
    'lookup-command': 'review policy scope source_set native_binding operator output mode',
    'review-capture': 'scope state_before state_after files',
    'adjudication': 'context row_contract poststate observations packet capture projection',
    'review-projection': 'source_result source_packet source_capture destination_root destination_state files',
    'feasibility': 'tasks scope limits AC9_concurrency decision review',
    'turn-permission': 'row_plan input scope native_binding overlay primary_sources managed_probe',
    'review-return': 'source_result source_capture destination_root destination_state report source',
    'observation-plan': 'scope source_set native_binding product_manifest metadata_paths output',
    'invariant-anchor': 'product_manifest environment native persistent_config catalog external_metadata fixture_metadata',
}


SCHEMAS.update({
    'recovery-prefix': 'branch_id legacy_prefix closed_history old_source_set new_source_set planning_decision funding_selection expected_actual expected_held whole reserve prefix_sha256',
    'recovery-funding-adoption': 'selection recovery_prefix branch_id mapping new_capacity transferred retained_other retired reserve decision',
    'final-message': 'context wire_index item_sha256 text',
    'recovery-predecessor': 'context independent_result state final_message recovery_prefix',
    'recovery-decision': 'predecessor final_message request reviewed_artifacts actor',
})


def validate_record(value, kind=None):
    require(type(value) is dict and type(value.get('schema')) is str, 'record schema missing')
    match = re.fullmatch(r'postclosure-(.+)-v1', value['schema'])
    require(match is not None and match[1] in SCHEMAS, 'unknown successor schema')
    actual = match[1]
    require(kind is None or actual == kind, 'wrong record kind')
    fields(value, 'schema ' + SCHEMAS[actual])
    reference_fields = {
        'recovery-prefix': 'legacy_prefix closed_history old_source_set new_source_set planning_decision funding_selection',
        'recovery-funding-adoption': 'selection recovery_prefix',
        'final-message': 'context',
        'recovery-predecessor': 'context independent_result state final_message recovery_prefix',
        'recovery-decision': 'predecessor final_message',
        'legacy-prefix': 'audit',
        'recovery-admission': 'funding_selection funding_adoption recovery_prefix composite_manifest materialization source_review invariant_anchor',
        'scope': 'materialization process_choice',
        'row-plan': 'scope predecessor predecessor_review contract input source_set admission',
        'process-policy': 'row_plan scope native_expectation',
        'common': 'row_plan policy lookup native_binding source_set product_manifest',
        'implementation-review': 'source_set',
        'source-context-review': 'common implementation_review',
        'root-review': 'common source_context_review admission row_plan policy lookup',
        'release': 'root_review common',
        'command': 'release row_plan native_binding source_set',
        'context': 'common release', 'independent-result': 'context review adjudication',
        'decision': 'predecessor question', 'predecessor': 'context independent_result state question',
        'lookup': 'policy', 'materialization': 'predecessor source_state destination_state composite_manifest',
        'funding-adoption': 'selection legacy_prefix', 'process-choice': 'native_binding',
        'question': 'context',
        'lookup-review': 'policy scope source_set native_binding implementation_review',
        'lookup-command': 'review policy scope source_set native_binding',
        'review-capture': 'scope state_before state_after',
        'adjudication': 'context row_contract poststate',
        'review-projection': 'source_result source_packet source_capture destination_state',
        'feasibility': 'tasks scope AC9_concurrency review',
        'turn-permission': 'row_plan input scope native_binding managed_probe',
        'review-return': 'source_result source_capture destination_state source',
        'observation-plan': 'scope source_set native_binding product_manifest',
        'invariant-anchor': 'product_manifest',
    }.get(actual, '').split()
    for key in reference_fields:
        ref_shape(value[key])
    for key in ('branch_id', 'row_id', 'donor_slot', 'scope_id', 'release_id', 'decision', 'actor', 'request'):
        if key in value and not (actual == 'independent-result' and key == 'decision'):
            nonempty(value[key])
    for key in ('prefix_sha256', 'session_sha256', 'predecessor_state_sha256', 'history_sha256',
                'input_sha256', 'prior_history_sha256', 'expected_before'):
        if key in value:
            hash_value(value[key])
    for key in ('root', 'realroot', 'output', 'claim'):
        if key in value:
            absolute(value[key])
    if actual in ('source-set', 'legacy-prefix', 'scope', 'command', 'decision', 'process-policy'):
        lists = {'source-set': ('files', 'official_sources'), 'legacy-prefix': ('refs',),
                 'scope': ('instruction_sources', 'install'), 'command': ('history',),
                 'decision': ('reviewed_artifacts',), 'process-policy': ('official_sources',)}[actual]
        for key in lists:
            require(type(value[key]) is list, 'reference list type')
            for reference in value[key]:
                ref_shape(reference, actual == 'source-set' and key == 'files')
    if actual == 'recovery-funding-adoption':
        require(all(type(value[k]) is int for k in ('new_capacity', 'retained_other', 'reserve')) and
                all(type(value[k]) is list for k in ('mapping', 'transferred', 'retired')), 'recovery funding literal types')
    if actual == 'recovery-decision':
        require(type(value['reviewed_artifacts']) is list and value['reviewed_artifacts'], 'recovery reviewed artifacts')
        for pin in value['reviewed_artifacts']:
            ref_shape(pin)
    if actual == 'recovery-admission':
        require(type(value['scopes']) is list and value['scopes'] and value['rows'] == ROWS, 'recovery scopes/rows')
        for pin in value['scopes']:
            ref_shape(pin)
    if actual in ('command', 'lookup-command'):
        ref_shape(value['operator'], executable=True)
    if actual == 'process-choice':
        ref_shape(value['executable'], executable=True)
    if actual == 'row-plan':
        require(value['row_id'] in ROWS and value['donor_slot'] == ROWS[value['row_id']], 'unfunded row')
        require(value['limits'] == LIMITS and all(type(x) is int for x in value['limits'].values()), 'row limits')
        nonempty(value['branch_id'])
        for name in ('output', 'claim'):
            absolute(value[name])
    if actual == 'context':
        require(value['business_PASS'] is False, 'raw context cannot assert business PASS')
        for key in ('wire', 'samples'):
            require(type(value[key]) is list, 'raw list type')
        require(all(type(sample) is dict for sample in value['samples']), 'raw sample object type')
        require(value['process_id'] is None or type(value['process_id']) is int and value['process_id'] > 0,
                'raw process ID type')
        for key in ('thread_id', 'turn_id'):
            require(value[key] is None or type(value[key]) is str and value[key], 'raw thread/turn ID type')
        if value['failure'] is not None:
            failure = fields(value['failure'], 'primary secondary')
            require(type(failure['secondary']) is list, 'secondary failure list')
            for entry in [failure['primary']] + failure['secondary']:
                fields(entry, 'exception_type stage reason_code')
                require(all(type(item) is str and item for item in entry.values()) and
                        entry['reason_code'] in ('CONTRACT_HOLD', 'STAGE_EXCEPTION'), 'safe failure record')
    if actual == 'independent-result':
        require(type(value['business_PASS']) is bool and type(value['decision']) is str and value['decision'], 'independent result literal types')
    return value


def read_record(reference, kind=None):
    return validate_record(decode(read_ref(reference)), kind)


def load_legacy():
    """Import only the pinned CURRENT collector; never archive/main or globals mutation."""
    global _CURRENT_LEGACY
    path = HERE / 'native_delta.py'
    require(ref(path)['sha256'] == LEGACY_SHA, 'current collector drift')
    for name, expected in HELPERS.items():
        require(ref(HERE / (name + '.py'))['sha256'] == expected, 'helper drift')
    if _CURRENT_LEGACY is not None:
        require(_CURRENT_LEGACY.SOURCE == SOURCE and _CURRENT_LEGACY.__file__ == str(path),
                'cached current collector identity drift')
        return _CURRENT_LEGACY
    spec = importlib.util.spec_from_file_location('_postclosure_current_c020', path)
    module = importlib.util.module_from_spec(spec)
    # Exact CURRENT source, without bytecode writes beside protected helpers.
    # Its guarded main is never invoked.
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    require(module.SOURCE == SOURCE, 'collector SOURCE substitution')
    _CURRENT_LEGACY = module
    return module


@contextlib.contextmanager
def bound_helpers(sink):
    legacy = load_legacy()
    with legacy.bound_helpers(sink) as result:
        yield legacy, result


def inventory(root):
    """Reuse current complete namespace semantics, including identities/Git/cache."""
    return load_legacy().current_author_inventory(absolute(str(root)))


def old_source_set():
    original = read_record(OLD_SOURCE_SET, 'source-set')
    require(len(original['files']) == 11 and len(original['official_sources']) == 97, 'original frozen source counts')
    for pin in original['files']:
        read_ref(pin, executable=True)
    for pin in original['official_sources']:
        read_ref(pin)
    return original


def load_old_core():
    """Pinned current f4 is used exclusively for historical replay."""
    path = HERE / 'postclosure.py'
    require(ref(path)['sha256'] == OLD_CORE_SHA, 'historical core source drift')
    old_source_set()
    spec = importlib.util.spec_from_file_location('_postclosure_closed_f4', path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(read_ref(ref(path)), str(path), 'exec'), module.__dict__)
    require(module.__file__ == str(path) and module.SOURCE == SOURCE, 'historical core identity drift')
    return module


def validate_source_set(source_set):
    validate_record(source_set, 'source-set')
    original = old_source_set()
    require(type(source_set['files']) is list and len(source_set['files']) == 18, 'exact recovery source count')
    required = {pin['path']: pin for pin in original['files']}
    for name in ('postclosure_recovery.py', 'postclosure_recovery_operator.py',
                 'postclosure_recovery_controller.py', 'postclosure_recovery_test.py',
                 'postclosure_recovery_operator_test.py', 'postclosure_deadline.py',
                 'postclosure_deadline_test.py'):
        pin = ref(HERE / name, executable=True)
        required[pin['path']] = pin
    require(type(source_set['files']) is list and len(source_set['files']) == len(required), 'exact recovery source count')
    seen = set()
    for pin in source_set['files']:
        read_ref(pin, executable=True)
        require(pin['nlink'] == 1 and pin['path'] not in seen and required.get(pin['path']) == pin, 'recovery source identity/alias')
        seen.add(pin['path'])
    require(seen == set(required) and source_set['official_sources'] == original['official_sources'], 'exact original and recovery source pins')
    return source_set


def validate_legacy(prefix):
    validate_record(prefix, 'legacy-prefix')
    require(type(prefix['refs']) is list and len(prefix['refs']) == 47, 'exact legacy47 required')
    require(prefix['prefix_sha256'] == canonical_hash(prefix['refs']) == LEGACY_PREFIX_SHA, 'legacy prefix order/hash')
    require((prefix['expected_actual'], prefix['expected_held'], prefix['whole'], prefix['reserve']) == (74, 32, 106, 1)
            and all(type(prefix[k]) is int for k in ('expected_actual', 'expected_held', 'whole', 'reserve')), 'legacy accounting constants')
    require(len({r['path'] for r in prefix['refs']}) == 47, 'duplicate legacy context')
    # This is the only use of the old accounting schema. Successor contexts
    # must never be passed to workflow_usage.
    used = load_legacy().workflow_usage(prefix['refs'])
    require(sum(used.values()) == 53, 'legacy postanchor count')
    audit = decode(read_ref(prefix['audit']))
    require(type(audit) is dict and audit.get('schema') == 'INDEPENDENT_POST_FH_LEGACY47_USAGE_REPLAY_V1' and
            audit.get('verdict') == 'PASS' and audit.get('collector', {}).get('sha256') == LEGACY_SHA and
            audit.get('exact_reference_count') == 47 and audit.get('actual_postanchor') == 53 and
            audit.get('actual_global') == 74 and audit.get('held') == 32 and audit.get('whole') == 106 and
            audit.get('record_hashes_all_match') is True and audit.get('guard_violations') == [], 'legacy independent audit relation')
    return used


def read_predecessor(plan):
    kind = 'recovery-predecessor' if plan['row_id'] == 'D2-tail/tasks-initial' else 'predecessor'
    return read_record(plan['predecessor'], kind)


def read_input_decision(plan):
    kind = 'recovery-decision' if plan['row_id'] == 'D2-tail/tasks-initial' else 'decision'
    return read_record(plan['input'], kind)


def validate_recovery_prefix(reference):
    require(Path(reference['path']).is_relative_to(CONTROL_ROOT), 'recovery prefix outside current control root')
    prefix = read_record(reference, 'recovery-prefix')
    for key in ('new_source_set', 'funding_selection'):
        require(Path(prefix[key]['path']).is_relative_to(CONTROL_ROOT), 'new recovery prefix controls outside current root')
    require(prefix['branch_id'] == BRANCH_ID and prefix['closed_history'] == CLOSED_HISTORY and
            prefix['old_source_set'] == OLD_SOURCE_SET, 'exact closed recovery lineage')
    require(all(type(prefix[k]) is int for k in ('expected_actual', 'expected_held', 'whole', 'reserve')) and
            (prefix['expected_actual'], prefix['expected_held'], prefix['whole'], prefix['reserve']) == (76, 31, 107, 1),
            'recovery accounting cannot refund closed charges')
    require(prefix['prefix_sha256'] == canonical_hash({k: v for k, v in prefix.items() if k != 'prefix_sha256'}), 'complete recovery prefix hash')
    old = load_old_core()
    legacy_prefix = old.read_record(prefix['legacy_prefix'], 'legacy-prefix')
    old.validate_legacy(legacy_prefix)
    closed = decode(read_ref(CLOSED_HISTORY))
    require(closed['source_set'] == OLD_SOURCE_SET and closed['legacy_prefix'] == LEGACY_PREFIX_SHA and
            [pin['sha256'] for pin in closed['closed_results']] == [
                '71e4272abb0effd2ae019838648746aa710614dfa58d8588a3ab7bf8186b2778',
                'f2b6ec75c076582f68795d03b19c85e3c649a6ef6fbcdcda2b6fb750ff8de85b'] and
            closed['accepted_results_only'] == closed['closed_results'][:1], 'closed accepted/incident order')
    replay = old.validate_history(LEGACY_PREFIX_SHA, closed['closed_results'], closed['branch'],
                                  OLD_SOURCE_SET, closed['invariant_anchor'])
    require(replay == closed['accounting'] and replay == {
        'actual': 76, 'held': 30, 'actual_range': [76, 76], 'held_range': [30, 30], 'whole': 106,
        'unknown': False, 'blocked': True, 'history_sha256': '449849b94be12ef1a44db4d8182e913e740d32dc2e560a784997161d11d35366', 'contexts': 2},
        'old closed history remains blocked with both charges')
    decision = decode(read_ref(prefix['planning_decision']))
    require(prefix['planning_decision']['path'] == str(OLD_CONTROL_ROOT / 'recovery-planning-r1/ROOT-PLANNING-DECISION.json') and
            decision['status'] == 'PLANNING_ONLY_NO_MODEL_RELEASE' and decision['model_USER_released'] == 0 and
            decision['actual_closed_charges'] == 76 and decision['proposed_new_planning_whole'] == 107 and
            decision['one_additional_capacity'] == 1, 'Root planning revision is not a runtime release')
    validate_source_set(read_record(prefix['new_source_set'], 'source-set'))
    selection = decode(read_ref(prefix['funding_selection']))
    require(type(selection) is dict and 'recovery_prefix' not in selection, 'funding selection cannot point back to prefix')
    return prefix



def validate_recovery_anchor(reference, candidate):
    require(Path(reference['path']).is_relative_to(CONTROL_ROOT), 'new epoch requires new owned observed anchor')
    anchor = validate_anchor(reference, candidate)
    closed = decode(read_ref(CLOSED_HISTORY))
    old_anchor = read_record(closed['invariant_anchor'], 'invariant-anchor')
    require(all(anchor[key] == old_anchor[key] for key in (
        'product_manifest', 'native', 'persistent_config', 'catalog', 'external_metadata', 'fixture_metadata')),
        'recovery epoch product/native/config/catalog/instruction baseline drift')
    # Environment is freshly observed in this epoch, including its actual nonce.
    # Lifetime equality remains strict within this epoch through validate_anchor.
    return anchor


def validate_final_message(reference, context_ref, record):
    message = read_record(reference, 'final-message')
    require(message['context'] == context_ref and type(message['wire_index']) is int and
            message['wire_index'] == 150 and len(record['wire']) > 150, 'actual P1 final wire origin')
    frame = record['wire'][150]
    event = frame.get('payload', {})
    params = event.get('params', {})
    item = params.get('item', {})
    require(frame.get('direction') == 'response' and event.get('method') == 'item/completed' and
            params.get('threadId') == record['thread_id'] and params.get('turnId') == record['turn_id'] and
            item.get('type') == 'agentMessage' and item.get('phase') == 'final_answer' and
            item.get('id') == 'msg_05c44178baad168c016ae02b78db5c819199be4b63727e5a2b' and
            message['item_sha256'] == canonical_hash(item) and message['text'] == item.get('text'),
            'P1 completed ACK provenance; ACK grants no new authority')
    return message


def validate_recovery_bootstrap(plan, predecessor, decision, prefix, scope, state, contract):
    require(plan['row_id'] == 'D2-tail/tasks-initial' and plan['donor_slot'] == ROWS[plan['row_id']], 'recovery bootstrap only new tasks donor')
    closed = decode(read_ref(prefix['closed_history']))
    accepted_ref, incident_ref = closed['closed_results']
    accepted = read_record(accepted_ref, 'independent-result')
    incident = read_record(incident_ref, 'independent-result')
    previous = read_record(accepted['context'], 'context')
    failed = read_record(incident['context'], 'context')
    require(accepted['business_PASS'] is True and accepted['decision'] == 'ACCEPT_EXACT_D2_ROW' and
            incident['business_PASS'] is False and predecessor['independent_result'] == accepted_ref and
            predecessor['context'] == accepted['context'] and predecessor['recovery_prefix'] == plan_prefix(plan),
            'accepted P1 only; failed P2 is charge and incident only')
    require(previous['state_after'] == failed['state_before'] == failed['state_after'] == state and len(state) == 151 and
            decode(read_ref(predecessor['state'])) == state and scope['root'] == scope['realroot'] == previous['root'] == failed['root'],
            'approved P1/failed P2/fresh current physical state relation')
    roles = contract['roles']
    require(roles['tasks'] not in state and state[roles['spec']]['sha256'] ==
            '4cacd0c98d2fc05d409ded3dfafdcb8988679eb01e13e5bfb45e1b3111804677', 'approved spec and absent tasks required')
    validate_final_message(predecessor['final_message'], accepted['context'], previous)
    require(decision['predecessor'] == plan['predecessor'] and decision['final_message'] == predecessor['final_message'] and
            decision['actor'] == 'Root' and decision['reviewed_artifacts'] == [
                {'path': str(Path(scope['root']) / roles['spec']), 'sha256': state[roles['spec']]['sha256']}] and
            decision['request'] != read_record(predecessor['final_message'], 'final-message')['text'], 'separate genuine Root tasks instruction')


def plan_prefix(plan):
    return read_record(plan['admission'], 'recovery-admission')['recovery_prefix']


def validate_unspent_transfers():
    old = load_old_core()
    for row in list(ROWS)[1:]:
        require(not os.path.lexists(old.claim_path(old.BRANCH_ID, row, old.CLAIM_ROOT)), 'transferred donor already claimed')


def validate_funding(admission, prefix):
    for key in ('funding_selection', 'funding_adoption', 'recovery_prefix'):
        require(Path(admission[key]['path']).is_relative_to(CONTROL_ROOT), 'new funding controls outside current recovery root')
    selection = decode(read_ref(admission['funding_selection']))
    fields(selection, 'schema branch_id new_slot_mapping new_capacity transferred retained_other retired_nonspendable reserve source_activation runtime_release')
    mapping = [{'from': donor, 'to': row} for row, donor in ROWS.items()]
    require(selection['schema'] == 'postclosure-recovery-funding-selection-v1' and
            selection['branch_id'] == BRANCH_ID and selection['source_activation'] is False and
            selection['runtime_release'] is False, 'funding selection is data only')
    require(selection['new_slot_mapping'] == mapping and selection['transferred'] == list(ROWS.values())[1:] and
            type(selection['new_capacity']) is int and selection['new_capacity'] == 1 and
            type(selection['retained_other']) is int and selection['retained_other'] == 13 and
            type(selection['reserve']) is int and selection['reserve'] == 1, 'exact recovery donor capacity')
    retired = selection['retired_nonspendable']
    require(type(retired) is list and len(retired) == len(set(retired)) == 8 and
            all(type(x) is str and x for x in retired) and not set(retired) & set(ROWS.values()), 'retired donors remain nonspendable')
    closed = decode(read_ref(CLOSED_HISTORY))
    first = read_record(closed['closed_results'][0], 'independent-result')
    previous = read_record(first['context'], 'context')
    old_common = read_record(previous['common'], 'common')
    old_plan = decode(read_ref(old_common['row_plan']))
    old_admission = load_old_core().read_record(old_plan['admission'], 'D2-admission')
    old_selection = decode(read_ref(old_admission['funding_selection']))
    require(retired == old_selection['retired_nonspendable'], 'retired donor identities immutable')
    adopted = read_record(admission['funding_adoption'], 'recovery-funding-adoption')
    require(adopted['selection'] == admission['funding_selection'] == prefix['funding_selection'] and
            adopted['recovery_prefix'] == admission['recovery_prefix'] and
            adopted['branch_id'] == admission['branch_id'] == BRANCH_ID and adopted['mapping'] == mapping and
            all(adopted[k] == selection[k] for k in ('new_capacity', 'transferred', 'retained_other', 'reserve')) and
            adopted['retired'] == retired and adopted['decision'] == 'ADOPT_EXACT_RECOVERY_NINE_ONLY', 'recovery adoption relation')
    validate_unspent_transfers()


def metadata_receipt(path):
    """Hash-only source metadata, including explicit absence; never copy bodies."""
    path = absolute(str(path))
    realpath = str(path.resolve(strict=False))
    if not path.exists() and not path.is_symlink():
        return {'exists': False, 'realpath': realpath, 'kind': None, 'mode': None, 'identity': None, 'sha256': None}
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode), 'metadata leaf alias')
    require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), 'unsupported metadata source type')
    sha256 = None
    if stat.S_ISREG(info.st_mode):
        data, checked = file_bytes(Path(realpath))
        require((info.st_dev, info.st_ino, info.st_mode) == (checked.st_dev, checked.st_ino, checked.st_mode), 'metadata read identity changed')
        sha256 = digest(data)
    return {'exists': True, 'realpath': realpath, 'kind': 'file' if stat.S_ISREG(info.st_mode) else 'directory',
            'mode': oct(stat.S_IMODE(info.st_mode)), 'identity': [info.st_dev, info.st_ino], 'sha256': sha256}


def mandatory_metadata_paths(scope):
    root = Path(scope['realroot']); home = Path.home() / '.codex'
    paths = {Path('/etc/codex/config.toml'), Path('/etc/codex/requirements.toml'), Path('/etc/codex/managed_config.toml')}
    paths |= {home / name for name in ('config.toml', 'auth.json', 'hooks.json', 'environments.toml', 'managed_config.toml', 'AGENTS.md', 'AGENTS.override.md')}
    for ancestor in {root, *root.parents}:
        paths |= {ancestor / '.codex/config.toml', ancestor / '.codex/hooks.json', ancestor / 'AGENTS.md', ancestor / 'AGENTS.override.md', ancestor / 'CLAUDE.md'}
    paths.add(root / '.codex')
    paths |= {Path(pin['path']) for pin in scope['instruction_sources']}
    return sorted(map(str, paths))


def required_metadata(scope):
    return {path: metadata_receipt(path) for path in mandatory_metadata_paths(scope)}


def validate_required_metadata(policy, scope):
    expected = required_metadata(scope)
    require(type(policy['metadata_paths']) is dict and set(expected) <= set(policy['metadata_paths']), 'mandatory config/auth/instruction metadata closure missing')
    require(all(policy['metadata_paths'][path] == entry for path, entry in expected.items()), 'mandatory source metadata drift/appearance')
    home = Path.home() / '.codex'
    permitted = {str(home / name) for name in ('config.toml', 'auth.json', 'hooks.json', 'environments.toml', 'AGENTS.md', 'AGENTS.override.md')}
    for path, entry in expected.items():
        if path.endswith(('/.codex/config.toml', '/.codex/hooks.json')) or path in ('/etc/codex/config.toml', '/etc/codex/requirements.toml', '/etc/codex/managed_config.toml', str(home / 'managed_config.toml'), str(Path(scope['realroot']) / '.codex')):
            require(path in permitted or entry['exists'] is False, 'unreviewed system/managed/project contributor')
    return expected


def sample_metadata(expected):
    actual = {}
    for path, pin in expected.items():
        if type(pin) is dict and set(pin) == {'exists', 'realpath', 'kind', 'mode', 'identity', 'sha256'}:
            actual[path] = metadata_receipt(path)
        else:
            require(type(pin) is dict, 'metadata pin object')
            ref_shape(pin, executable='size' in pin)
            actual[path] = ref(Path(path), executable='size' in pin)
    require(actual == expected, 'immutable metadata drift/absence appearance')
    return actual


def _scope_normalize(value, root):
    if type(value) is str:
        return '$FIXTURE' + value[len(root):] if value == root or value.startswith(root + '/') else value
    if type(value) is list:
        return [_scope_normalize(item, root) for item in value]
    if type(value) is dict:
        return {_scope_normalize(key, root): _scope_normalize(item, root) for key, item in value.items()}
    return value


def invariant_projection(scope, manifest_ref, config, catalog, native13, environment, metadata):
    """Derive the finite shared baseline from actual zero-USER observations."""
    require(manifest_ref['sha256'] == COMPOSITE_SHA, 'all D2 rows require exact adopted composite')
    manifest = decode(read_ref(manifest_ref)); root = Path(scope['realroot'])
    require(str(root) == scope['root'] and set(mandatory_metadata_paths(scope)) <= set(metadata), 'invariant actual scope/metadata closure')
    external = {path: metadata_receipt(path) for path in mandatory_metadata_paths(scope) if not Path(path).is_relative_to(root)}
    # Fixture-ancestor sources are independently checked absent/current per
    # scope. Only shared external host sources belong to the lifetime anchor.
    ancestor_paths = {str(a / name) for a in root.parents for name in ('AGENTS.md', 'AGENTS.override.md', 'CLAUDE.md', '.codex/config.toml', '.codex/hooks.json')}
    external = {path: entry for path, entry in external.items() if path not in ancestor_paths or entry['exists']}
    fixture = {}
    for path, value in manifest['suite_files'].items():
        require(path.startswith('skills/'), 'unexpected composite source path')
        destination = path.replace('skills/', '.agents/skills/', 1)
        observed = metadata_receipt(root / destination)
        require(observed['kind'] == 'file' and observed['sha256'] == value['sha256'] and observed['mode'] == value['mode'], 'actual complete installed source42')
        fixture[destination] = {'sha256': observed['sha256'], 'mode': observed['mode']}
    for name in ('AGENTS.md', 'AGENTS.override.md', 'CLAUDE.md', 'docs/ains/human-review-rules'):
        observed = metadata_receipt(root / name)
        fixture[name] = {'sha256': observed['sha256'], 'mode': observed['mode'], 'exists': observed['exists']}
    for pin in scope['instruction_sources']:
        path = Path(pin['path'])
        if path.is_relative_to(root):
            observed = metadata_receipt(path)
            fixture[str(path.relative_to(root))] = {'sha256': observed['sha256'], 'mode': observed['mode'], 'exists': observed['exists']}
    for layer in config['layers']:
        source = layer.get('name', layer.get('source', {}))
        if source.get('type') in ('user', 'system'):
            expected_path = str(Path.home() / '.codex/config.toml') if source['type'] == 'user' else '/etc/codex/config.toml'
            require(source.get('file') == expected_path and expected_path in metadata, 'actual config layer source outside mandatory coverage')
    for key in ('model_instructions_file', 'instructions_file', 'developer_instructions_file'):
        value = config['config'].get(key)
        if value is not None:
            require(type(value) is str and value in metadata and type(metadata[value]) is dict and metadata[value].get('exists') is True, 'configured instruction contributor missing from metadata')
            require(value in mandatory_metadata_paths(scope), 'configured instruction contributor outside pinned closure')
    cfg = json.loads(json.dumps(config))
    # Only the process-controlled current trust leaf and its session metadata
    # vary with the author/reviewer cwd. All persistent layers remain exact.
    cfg['config'].get('projects', {}).pop(str(root), None)
    cfg['layers'] = [layer for layer in cfg['layers'] if layer.get('name', layer.get('source', {})).get('type') != 'sessionFlags']
    cfg['origins'] = {key: value for key, value in cfg['origins'].items() if value.get('name', {}).get('type') != 'sessionFlags'}
    facts = load_legacy().environment_facts(environment)
    return {'schema': 'postclosure-invariant-anchor-v1', 'product_manifest': manifest_ref,
        'environment': {'facts': facts, 'sha256': canonical_hash(dict(environment))},
        'native': _scope_normalize({key: value for key, value in native13.items() if key != 'thread_id'}, str(root)),
        'persistent_config': load_legacy().safe_config_identity(_scope_normalize(cfg, str(root))),
        'catalog': load_legacy().safe_config_identity(_scope_normalize(catalog, str(root))),
        'external_metadata': external, 'fixture_metadata': fixture}


def validate_anchor(reference, candidate):
    anchor = read_record(reference, 'invariant-anchor')
    require(anchor == candidate, 'lifetime native/config/catalog/source/instruction/environment baseline drift')
    return anchor


def session_for(realroot, controlled_negative=False):
    absolute(realroot)
    result = {'features': {key: False for key in FEATURES},
            'mcp_servers': {key: {'enabled': False, 'command': '/usr/bin/false'} for key in MCP},
            'projects': {realroot: {'trust_level': 'trusted'}}}
    # Root-approved source design: no nested model contexts in any D2 row.
    # P7 additionally adjudicates unavailability in its declared route.
    result['agents'] = {'enabled': False}
    return result


def argv_for(executable, realroot, controlled_negative=False):
    absolute(executable)
    values = ['features.' + key + '=false' for key in FEATURES]
    for name in MCP:
        values += ['mcp_servers.' + name + '.enabled=false',
                   'mcp_servers.' + name + '.command="/usr/bin/false"']
    values += ['agents.enabled=false']
    values += ['projects={' + json.dumps(realroot, ensure_ascii=False) + '={trust_level="trusted"}}']
    return [executable, '--no-daemon', '-a', 'never', 'app-server', '--strict-config', '--stdio'] + [x for v in values for x in ('-c', v)]


def process_policy(scope_reference, row_reference, metadata_paths, native_expectation, official_sources, turn_permission=None):
    scope = read_record(scope_reference, 'scope')
    choice = read_record(scope['process_choice'], 'process-choice')
    plan = read_record(row_reference, 'row-plan')
    contract = read_record(plan['contract'], 'contract')
    negative = plan['row_id'] == 'D2-tail/unavailable-review' and contract['capability_profile'] is not None
    session = session_for(scope['realroot'], negative)
    return {'schema': 'postclosure-process-policy-v1', 'row_plan': row_reference,
            'scope': scope_reference, 'argv': argv_for(choice['invoked_path'], scope['realroot'], negative),
            'session': session, 'session_sha256': canonical_hash(session),
            'metadata_paths': metadata_paths, 'native_expectation': native_expectation,
            'official_sources': official_sources, 'turn_permission': turn_permission}


def p6_turn_overlay(realroot):
    absolute(realroot)
    return {'sandboxPolicy': {'type': 'workspaceWrite', 'writableRoots': [str(Path(realroot) / '.git')],
                             'networkAccess': False, 'excludeTmpdirEnvVar': False, 'excludeSlashTmp': False},
            'approvalPolicy': 'never', 'cwd': realroot}


def validate_turn_permission(policy, plan, scope, row_reference):
    if plan['row_id'] != 'D2-tail/Git-AC9':
        require(policy['turn_permission'] is None, 'extra Git permission is P6-only')
        return None
    permission = read_record(policy['turn_permission'], 'turn-permission')
    require(permission['row_plan'] == row_reference and permission['input'] == plan['input'] and
            permission['scope'] == plan['scope'] and permission['native_binding'] == policy['native_expectation'] and
            permission['overlay'] == p6_turn_overlay(scope['realroot']), 'finite actual P6 grant/permission edge')
    require(type(permission['primary_sources']) is list and permission['primary_sources'] and
            all(pin in policy['official_sources'] for pin in permission['primary_sources']), 'P6 API primary-source pins')
    for pin in permission['primary_sources']:
        read_ref(pin)
    read_ref(permission['managed_probe'])
    return permission['overlay']


def disabled_mcp_servers(value):
    return (type(value) is dict and set(value) == set(MCP) and
            all(type(server) is dict and server.get('enabled') is False and
                server.get('command') == '/usr/bin/false' for server in value.values()))


def policy_projection(data, policy, scope):
    """Successor policy, without calling the legacy three-root validator."""
    validate_record(policy, 'process-policy')
    expected = session_for(scope['realroot'])
    require(policy['session'] == expected and policy['session_sha256'] == canonical_hash(expected), 'policy session drift')
    require(type(data) is dict and type(data.get('config')) is dict and
            type(data.get('layers')) is list and type(data.get('origins')) is dict, 'config/layers/origins required')
    kinds = []
    names = set()
    for layer in data['layers']:
        require(type(layer) is dict, 'invalid layer')
        source = layer.get('name', layer.get('source'))
        raw = layer.get('config')
        require(type(source) is dict and source.get('type') in ('sessionFlags', 'user', 'system') and
                type(raw) is dict and layer.get('version') == 'sha256:' + canonical_hash(raw) and
                layer.get('disabledReason') is None, 'layer identity/version/disabled')
        kind = source['type']
        kinds.append(kind)
        require(type(raw.get('mcp_servers', {})) is dict, 'layer MCP structure')
        names.update(raw.get('mcp_servers', {}))
        if kind == 'sessionFlags':
            require(source == {'type': 'sessionFlags'} and raw == expected, 'sessionFlags exact content')
        else:
            require(type(raw.get('projects', {})) is dict and not any(
                p in raw.get('projects', {}) for p in (scope['root'], scope['realroot'])), 'persistent project trust candidate')
            require(kind != 'system' or raw == {}, 'nonempty system policy')
    require(kinds in (['sessionFlags', 'user'], ['sessionFlags', 'user', 'system']), 'layer order/cardinality')
    key = 'projects.' + scope['realroot'] + '.trust_level'
    origin = {'name': {'type': 'sessionFlags'}, 'version': 'sha256:' + canonical_hash(expected)}
    require(data['origins'].get(key) == origin, 'project trust origin')
    require(data['origins'].get('agents.enabled') == origin and
            type(data['config'].get('agents')) is dict and data['config']['agents'].get('enabled') is False,
            'actual agents.enabled=false origin/effective value required on every D2 row')
    cfg = data['config']
    require(type(cfg.get('features')) is dict and all(cfg['features'].get(k) is False for k in FEATURES), 'effective feature flags')
    require(names == set(MCP) and disabled_mcp_servers(cfg.get('mcp_servers')) and
            type(cfg.get('projects')) is dict and cfg['projects'].get(scope['realroot']) == {'trust_level': 'trusted'},
            'effective MCP/project scope')
    skills = cfg.get('skills')
    require(skills is None or type(skills) is dict, 'skills type')
    require((skills or {}).get('include_instructions') in (None, True) and
            type((skills or {}).get('include_instructions')) in (type(None), bool), 'instructions disabled')
    # Pinned native default-source proof checks are retained for absence/null.
    load_legacy().native_premises(data, MCP)
    return load_legacy().safe_config_identity(data)


def validate_capability(profile, config, *, supplied_dynamic_tools, authorized_methods):
    """P7 declared route only; never a claim that baseline Codex cannot review."""
    validate_record(profile, 'capability-profile')
    require(profile['route'] == 'model-native-independent-agent' and profile['process_only'] is True and
            profile['agents_enabled'] is False and profile['multi_agent_v2'] is False and
            profile['dynamic_tools'] == [] and profile['client_review_rpc'] is False and
            profile['external_review_cli'] is False and
            profile['wording'] == 'independent-agent review unavailable in this declared P7 route',
            'unsupported capability-negative route')
    require(type(profile['official_sources']) is list and profile['official_sources'], 'registry source proof missing')
    for reference in profile['official_sources']:
        read_ref(reference)
    cfg = config.get('config', {})
    require(type(cfg.get('agents')) is dict and cfg['agents'].get('enabled') is False and
            type(cfg.get('features')) is dict and cfg['features'].get('multi_agent_v2') is False,
            'actual native independent-agent disabled predicate absent')
    require(supplied_dynamic_tools == [] and 'review/start' not in authorized_methods and
            disabled_mcp_servers(cfg.get('mcp_servers')) and
            cfg['features'].get('plugins') is False and cfg['features'].get('remote_plugin') is False,
            'alternative review route/dynamic supply not excluded')
    return {'route': profile['route'], 'agents_enabled': False, 'multi_agent_v2': False,
            'dynamic_tools': [], 'client_review_rpc': False, 'external_review_cli': False,
            'wording': profile['wording'], 'business_PASS': False}


def validate_bundle(config_a, catalog, config_b, before, after, metadata_before,
                    metadata_after, policy, scope, catalog_validator):
    require(config_a == config_b, 'raw config A/B inequality')
    require(before == after and metadata_before == metadata_after and
            metadata_before == policy['metadata_paths'], 'paired fullstate/metadata drift')
    identity = policy_projection(config_a, policy, scope)
    proof = catalog_validator(catalog, config_a)
    require(type(proof) is dict and proof.get('enabled_unique_targets') == 16 and
            proof.get('load_errors') == 0, 'native catalog proof')
    return {'config': identity, 'catalog': load_legacy().redacted_config(catalog),
            'catalog_proof': proof, 'state_sha256': canonical_hash(after),
            'metadata_sha256': canonical_hash(metadata_after)}


class Baselines:
    def __init__(self, first, second):
        self.first = canonical_hash(first)
        self.failed = False
        self.check(second)

    def check(self, value):
        if self.failed or canonical_hash(value) != self.first:
            self.failed = True
            raise Hold('B1/predispatch baseline drift (gate permanently closed)')


def claim_path(branch, row, directory):
    nonempty(branch)
    require(row in ROWS, 'claim row')
    directory = absolute(str(directory))
    return directory / (canonical_hash({'branch_id': branch, 'row_id': row}) + '.claim.json')


def acquire_claim(branch, row, directory, release):
    """Stable lifetime claim, retained even on failure. No refunds or retries."""
    require(branch == BRANCH_ID and Path(directory) == CLAIM_ROOT, 'recovery claim scope')
    validate_unspent_transfers()
    path = claim_path(branch, row, directory)
    require(path.parent.resolve(strict=True) == path.parent, 'claim directory alias')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        data = json.dumps({'branch_id': branch, 'row_id': row, 'release': release},
                          sort_keys=True).encode() + b'\n'
        with os.fdopen(os.dup(fd), 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    return path


def validate_history(prefix_hash, contexts, branch_id=None, source_set=None, invariant_anchor=None):
    hash_value(prefix_hash)
    previous = prefix_hash
    seen = {key: set() for key in ('row_id', 'donor_slot', 'release', 'common')}
    actual = BASE_ACTUAL
    actual_upper = BASE_ACTUAL
    unknown_transport = False
    blocked = False
    prior_results = []
    for reference in contexts:
        require(not blocked, 'failed/unknown predecessor blocks successor release')
        result = read_record(reference, 'independent-result')
        record = read_record(result['context'], 'context')
        read_ref(result['review'])
        if branch_id is None:
            branch_id = record['branch_id']
        expected_row = list(ROWS)[len(seen['row_id'])] if len(seen['row_id']) < len(ROWS) else None
        require(record['branch_id'] == branch_id and record['row_id'] == expected_row, 'history branch/row order')
        release = read_record(record['release'], 'release')
        reviewed = read_record(release['root_review'], 'root-review')
        common = read_record(record['common'], 'common')
        if source_set is None:
            source_set = common['source_set']
        require(common['source_set'] == source_set, 'D2 history source set must remain frozen')
        plan = read_record(common['row_plan'], 'row-plan')
        admission = read_record(plan['admission'], 'recovery-admission')
        if invariant_anchor is None:
            invariant_anchor = admission['invariant_anchor']
        require(admission['invariant_anchor'] == invariant_anchor, 'D2 lifetime invariant anchor cannot reset')
        require(common['product_manifest']['sha256'] == COMPOSITE_SHA, 'D2 product manifest changed')
        lookup = read_record(common['lookup'], 'lookup')
        validate_lookup(lookup, common['policy'], common['source_set'], common['native_binding'])
        require(read_record(lookup['native_facts']['invariant_candidate'], 'invariant-anchor') == read_record(invariant_anchor, 'invariant-anchor'), 'history actual lifetime baseline drift')
        require(plan['claim'] == str(claim_path(BRANCH_ID, record['row_id'], CLAIM_ROOT)) and
                result['context']['path'] == str(Path(plan['output']) / 'context.json'), 'actual stable claim/output provenance')
        claimed = decode(read_ref(ref(Path(plan['claim']))))
        fields(claimed, 'branch_id row_id release')
        require(claimed == {'branch_id': BRANCH_ID, 'row_id': record['row_id'], 'release': record['release']},
                'actual exclusive claim lineage')
        require(release['common'] == record['common'] == reviewed['common'] and
                reviewed['row_plan'] == common['row_plan'] and plan['branch_id'] == branch_id and
                plan['row_id'] == record['row_id'] and plan['donor_slot'] == record['donor_slot'], 'history release/common/plan relation')
        require(record['row_id'] in ROWS and record['donor_slot'] == ROWS[record['row_id']] and
                record['prior_history_sha256'] == previous, 'successor chronology/donor')
        for key, values in seen.items():
            identity = canonical_hash(record[key])
            require(identity not in values, 'duplicate successor ' + key)
            values.add(identity)
        charge = validate_wire(record['wire'], record['thread_id'], record['turn_id'])
        require(record['accounting'] == charge, 'wire/accounting disagreement')
        if charge['actual'] is None:
            unknown_transport = True
            actual_upper += charge['attempted']
        else:
            actual += charge['actual']
            actual_upper += charge['actual']
        close = record['close']
        healthy = (type(close) is dict and close.get('reaped') is True and
                   close.get('partial_stdout_bytes') == 0 and record['failure'] is None and
                   charge == {'actual': 1, 'attempted': 1, 'charged': 1, 'status': 'ACTUAL', 'accepted': 1})
        if healthy:
            validate_sample_replay(record)
            if result['business_PASS'] is True and result['decision'] == 'ACCEPT_EXACT_D2_ROW':
                validate_adjudication(result, record, plan, prior_results)
        blocked = not healthy or result['business_PASS'] is not True or result['decision'] != 'ACCEPT_EXACT_D2_ROW'
        previous = canonical_hash({'previous': previous, 'context': reference})
        prior_results.append(reference)
    return {'actual': None if unknown_transport else actual, 'held': None if unknown_transport else WHOLE - actual,
            'actual_range': [actual, actual_upper], 'held_range': [WHOLE - actual_upper, WHOLE - actual], 'whole': WHOLE,
            'unknown': unknown_transport, 'blocked': blocked, 'history_sha256': previous, 'contexts': len(contexts)}


def validate_sample_replay(record):
    common = read_record(record['common'], 'common')
    plan = read_record(common['row_plan'], 'row-plan')
    admission = read_record(plan['admission'], 'recovery-admission')
    anchor_hash = canonical_hash(read_record(admission['invariant_anchor'], 'invariant-anchor'))
    phases = ('preflight', 'post-start-1', 'post-start-2', 'predispatch', 'postterminal')
    samples = [sample for sample in record['samples'] if sample.get('phase') in phases]
    require([sample['phase'] for sample in samples] == list(phases), 'complete ordered paired samples required')
    previous_end = 0
    for index, sample in enumerate(samples):
        fields(sample, 'phase wire_start wire_end before after metadata frame')
        require(sample['frame'].get('invariant_sha256') == anchor_hash, 'business sample lifetime baseline relation')
        start, end = sample['wire_start'], sample['wire_end']
        require(type(start) is int and type(end) is int and previous_end <= start < end <= len(record['wire']) and
                sample['before'] == sample['after'], 'sample interval/state pair')
        previous_end = end
        requests = [entry['payload'] for entry in record['wire'][start:end] if entry['direction'] == 'request']
        require([request.get('method') for request in requests] == ['config/read', 'skills/list', 'config/read'], 'sample exact config/catalog/config methods')
        replies = {entry['payload'].get('id'): entry['payload'] for entry in record['wire'][start:end]
                   if entry['direction'] == 'response' and 'id' in entry['payload']}
        require(all(request['id'] in replies and 'result' in replies[request['id']] for request in requests), 'sample actual complete replies')
        require(replies[requests[0]['id']]['result'] == replies[requests[2]['id']]['result'] == sample['frame']['config'] and
                sample['frame']['state_sha256'] == canonical_hash(sample['after']) and
                sample['frame']['metadata_sha256'] == canonical_hash(sample['metadata']), 'sample actual config/state/metadata frame relation')
        require(sample['after'] == (record['state_after'] if index == 4 else record['state_before']), 'sample business endpoint relation')
    require(samples[1]['frame'] == samples[2]['frame'] == samples[3]['frame'] and
            all(sample['metadata'] == samples[0]['metadata'] for sample in samples), 'B1/immediate/metadata replay relation')
    starts = [index for index, entry in enumerate(record['wire']) if entry['direction'] == 'request' and entry['payload'].get('method') == 'turn/start']
    require(len(starts) == 1 and samples[3]['wire_end'] == starts[0], 'immediate predispatch sample boundary')
    events = [entry['payload'] for entry in record['wire'] if entry['direction'] == 'response' and 'method' in entry['payload']]
    require(load_legacy().healthy_terminal(events, 'live'), 'healthy actual successor terminal required')
    return True


def validate_successor_predecessor(predecessor, history, scope, state, material, plan=None):
    require(history, 'successor predecessor requires accepted history')
    accepted = read_record(history[-1], 'independent-result')
    previous_context = read_record(accepted['context'], 'context')
    require(predecessor['context'] == accepted['context'] and predecessor['independent_result'] == history[-1] and
            accepted['business_PASS'] is True and accepted['decision'] == 'ACCEPT_EXACT_D2_ROW', 'actual accepted successor predecessor')
    if previous_context['root'] == scope['root']:
        require(previous_context['state_after'] == state, 'actual predecessor poststate relation')
    else:
        require(material['predecessor'] == predecessor['context'] and
                decode(read_ref(material['source_state'])) == previous_context['state_after'] and
                decode(read_ref(material['destination_state'])) == state and
                material['relocation'].get('independent_projection_review') is not None,
                'cross-root accepted materialization projection required')
        require(plan is not None, 'cross-root route requires actual current plan')
        contexts, captures = evidence_contexts(accepted['context'], previous_context,
            read_record(read_record(previous_context['common'], 'common')['row_plan'], 'row-plan'), history[:-1])
        previous = contexts[canonical_hash(accepted['context'])]
        if plan['row_id'] == 'D2-tail/independent-review':
            require(previous['plan']['row_id'] == 'D2-tail/unavailable-review', 'P8 must follow actual P7')
            adjudication = read_record(accepted['adjudication'], 'adjudication')
            packet = read_record(adjudication['packet'], 'review-packet')
            content = {name: file_bytes(Path(scope['root']) / name)[0] for name, value in state.items() if value.get('kind') == 'file'}
            current = {'plan': plan, 'raw': {'root': scope['root'], 'realroot': scope['realroot'], 'state_before': state}, 'content': content}
            validate_review_projection(material['relocation']['independent_projection_review'], history[-1], accepted,
                packet, previous, current, contexts, captures, require_consumption=False)
        elif plan['row_id'] == 'D2-tail/local-ship':
            validate_review_return(material['relocation']['independent_projection_review'], history, accepted, previous, scope, state, plan, contexts)
        else:
            raise Hold('unadmitted cross-root route')
    if plan is not None and plan['row_id'] != 'D2-tail/independent-review':
        first = read_record(read_record(history[0], 'independent-result')['context'], 'context')
        require(scope['root'] == scope['realroot'] == first['root'], 'all author rows retain actual adopted P1 root')
    validate_question(predecessor['question'], predecessor['context'], previous_context['wire'])
    return previous_context


def validate_review_return(reference, history, accepted, reviewer, scope, state, plan, contexts):
    """Faithful report delivery back to the unchanged actual P7 author root."""
    bridge = read_record(reference, 'review-return')
    require(reviewer['plan']['row_id'] == 'D2-tail/independent-review' and len(history) >= 2,
            'author return requires actual accepted P8')
    p7result = read_record(history[-2], 'independent-result')
    author = contexts[canonical_hash(p7result['context'])]
    require(author['plan']['row_id'] == 'D2-tail/unavailable-review' and
            bridge['source_result'] == history[-1] and bridge['source_capture'] == reviewer['capture_ref'] and
            bridge['destination_root'] == scope['root'] == scope['realroot'] == author['raw']['root'] and
            decode(read_ref(bridge['destination_state'])) == state, 'actual reviewer-to-author return relation')
    report = bridge['report']; relative(report)
    roles = read_record(plan['contract'], 'contract')['roles']
    require(report == roles['review'] and report not in author['state'], 'new exact returned review artifact')
    data = read_ref(bridge['source'])
    reviewer_roles = read_record(reviewer['plan']['contract'], 'contract')['roles']
    review_path = reviewer_roles['review']
    final_texts = [frame['payload'].get('params', {}).get('item', {}).get('text', '').encode()
        for frame in reviewer['raw']['wire'] if frame['direction'] == 'response' and
        frame['payload'].get('method') == 'item/completed' and
        frame['payload'].get('params', {}).get('item', {}).get('type') == 'agentMessage' and
        frame['payload'].get('params', {}).get('item', {}).get('phase') == 'final_answer']
    file_origin = False
    if review_path is not None:
        file_origin = any(review_path.encode() in text for text in final_texts)
        for frame in reviewer['raw']['wire']:
            event = frame.get('payload', {}); item = event.get('params', {}).get('item', {})
            if frame.get('direction') == 'response' and event.get('method') == 'item/completed' and item.get('type') == 'fileChange' and item.get('status') == 'completed':
                file_origin |= any(change.get('path') in (review_path, str(Path(reviewer['raw']['root']) / review_path))
                                   for change in item.get('changes', []) if type(change) is dict)
    require(data and (data in final_texts or (review_path is not None and file_origin and
        reviewer['content'].get(review_path) == data and
        reviewer['raw']['state_before'].get(review_path) != reviewer['state'].get(review_path))),
        'returned report must be actual completed reviewer output')
    require(file_bytes(Path(scope['root']) / report)[0] == data and state.get(report, {}).get('mode') == '0o644',
            'returned review exact bytes/mode')
    allowed = {report}
    for parent in Path(report).parents:
        name = str(parent)
        if name != '.' and name not in author['state']:
            require(state.get(name, {}).get('kind') == 'directory' and state[name].get('mode') == '0o755', 'review return necessary parent')
            allowed.add(name)
    _same_except(author['state'], state, allowed)
    return True


def validate_question(reference, context_ref, wire):
    question = read_record(reference, 'question')
    require(question['context'] == context_ref and type(question['wire_index']) is int and
            0 <= question['wire_index'] < len(wire), 'actual predecessor question origin')
    entry = wire[question['wire_index']]
    event = entry.get('payload', {})
    item = event.get('params', {}).get('item', {})
    require(event.get('method') == 'item/completed' and item.get('type') == 'agentMessage' and
            item.get('phase') == 'final_answer' and question['item_sha256'] == canonical_hash(item) and
            question['text'] == item.get('text') and type(question['text']) is str and question['text'],
            'question must be actual completed predecessor final message')
    return question


def validate_initial_materialization(material, scope, predecessor, prefix, spec_path):
    """Exact accepted D2 bootstrap, never a healthy-checkpoint cast or v65 copy."""
    require(material['predecessor'] == predecessor['context'] == prefix['refs'][-1] and
            material['predecessor']['sha256'] == D2_RAW_SHA and
            material['source_state']['sha256'] == D2_STATE_SHA and
            material['composite_manifest']['sha256'] == COMPOSITE_SHA, 'exact accepted D2 bootstrap pins')
    raw = decode(read_ref(predecessor['context']))
    require(raw.get('healthy') is True and raw.get('closed') is True and raw.get('failure') is None and
            raw.get('business_PASS') is False and raw.get('collector_sha256') == LEGACY_SHA,
            'actual D2 closed healthy context required')
    source_frame = decode(read_ref(material['source_state']))
    source = source_frame['state']
    require(len(source) == 151 and raw['state'] == source, 'actual D2 poststate151 relation')
    post = decode(read_ref(raw['scope_facts']['workflow-closure-postimage.json']))
    require(post.get('after') == source and post.get('postimage', {}).get('sha256') == D2_DRAFT_SHA and
            post.get('draft') == spec_path, 'actual D2 draft/postimage relation')
    read_ref(post['postimage'])
    relocation = fields(material['relocation'], 'source_root destination_root actual_adoption materialization_adoption exceptions')
    require(relocation['actual_adoption']['sha256'] == D2_ACTUAL_ADOPTION_SHA and
            relocation['materialization_adoption']['sha256'] == D2_MATERIAL_ADOPTION_SHA, 'pinned DATA adoptions required')
    adopted = decode(read_ref(relocation['actual_adoption']))
    relocated = decode(read_ref(relocation['materialization_adoption']))
    require(adopted.get('actual_context') == predecessor['context'] and adopted.get('poststate151') == material['source_state'] and
            adopted.get('draft_postimage', {}).get('sha256') == D2_DRAFT_SHA and
            adopted.get('actual_held_whole') == [74, 32, 106], 'actual D2 Root adoption relation')
    require(relocated.get('reference151') == material['source_state'] and
            relocated.get('author_root') == scope['root'] and relocated.get('canonical_root') == scope['realroot'] and
            relocated.get('current_composite_manifest') == material['composite_manifest'] and
            relocated.get('admission_or_process_or_runtime_grant') is False,
            'separate DATA materialization adoption relation')
    require(predecessor['independent_result'] == relocation['actual_adoption'], 'initial independent acceptance binding')
    for key in ('independent_audit', 'actual_report', 'business', 'N4', 'N5', 'exact_original5'):
        read_ref(adopted[key])
    read_ref(relocated['independent_verifier'])
    read_ref(relocated['independent_index'])
    installed_index = decode(read_ref(relocated['materializer_index']))
    destination = decode(read_ref(material['destination_state']))
    require(destination == inventory(scope['root']) and set(destination) == set(source), 'faithful materialized namespace')
    exceptions = {'.agents/skills/ains-review/review-prompt.md',
                  '.agents/skills/ains-spec/scripts/new-change.sh', 'skills-lock.json'}
    require(relocation['exceptions'] == sorted(exceptions) and
            relocation['source_root'] == source_frame['realroot'] and relocation['destination_root'] == scope['realroot'],
            'finite composite-only relocation exceptions')
    manifest = decode(read_ref(material['composite_manifest']))
    old_ids = {tuple(value['identity']) for value in source.values()}
    new_ids = set()
    for path, old in source.items():
        new = destination[path]
        require(new.get('kind') == old.get('kind') and new.get('mode') == old.get('mode') and
                new.get('link_text') == old.get('link_text') is None and
                new.get('realpath') == str(Path(scope['realroot']) / path) and
                tuple(new.get('identity', [])) not in old_ids and tuple(new.get('identity', [])) not in new_ids,
                'materialized mode/kind/identity/physical relocation')
        new_ids.add(tuple(new['identity']))
        if path not in exceptions:
            require(new.get('sha256') == old.get('sha256'), 'undeclared materialization content change')
        elif path.startswith('.agents/'):
            expected = manifest['suite_files'][path.replace('.agents/skills/', 'skills/', 1)]
            require(new['sha256'] == expected['sha256'] and new['mode'] == expected['mode'], 'F1/H composite payload relation')
        else:
            require(new['sha256'] == installed_index[Path(scope['root']).name + '/' + path]['sha256'], 'adopted installed lock bytes')
    require(destination[spec_path]['sha256'] == D2_DRAFT_SHA and
            not any(path.endswith('/tasks.md') and not path.startswith('.agents/') for path in destination) and
            'tests/test_notifier.py' not in destination, 'fresh draft/no historical tasks/test transplantation')
    wire = decode(read_ref(raw['wire']))
    validate_question(predecessor['question'], predecessor['context'], wire)
    return destination


LOOKUP_METHODS = ('initialize', 'initialized', 'config/read', 'skills/list', 'config/read',
                  'thread/start', 'config/read', 'skills/list', 'config/read',
                  'config/read', 'skills/list', 'config/read')


def lookup_policy_relation(lookup_reference, expected_reference):
    expected_policy = read_record(expected_reference, 'process-policy')
    lookup_policy = read_record(lookup_reference, 'process-policy')
    if lookup_reference != expected_reference:
        plan = read_record(expected_policy['row_plan'], 'row-plan')
        require(plan['row_id'] == 'D2-tail/Git-AC9' and expected_policy['turn_permission'] is not None and
                lookup_policy == dict(expected_policy, turn_permission=None), 'only exact P6 zero/business turn-permission difference')
    return lookup_policy


def validate_lookup(lookup, policy_reference, source_reference, native_reference):
    validate_record(lookup, 'lookup')
    lookup_policy = lookup_policy_relation(lookup['policy'], policy_reference)
    require(lookup_policy['turn_permission'] is None and type(lookup['USER']) is int and lookup['USER'] == 0 and
            lookup['state_before'] == lookup['state_after'], 'zero lookup exact policy/paired state')
    wire = lookup['wire']
    facts = fields(lookup['native_facts'], 'configuration_identity config_facts native13 catalog_proof capability supplied_dynamic_tools bundles process_id close failure source_set native_binding invariant_candidate')
    require(facts['source_set'] == source_reference and facts['native_binding'] == native_reference and
            facts['failure'] is None and facts['supplied_dynamic_tools'] == [] and
            type(facts['process_id']) is int and facts['process_id'] > 0 and
            type(facts['close']) is dict and facts['close'].get('reaped') is True and
            facts['close'].get('partial_stdout_bytes') == 0 and not facts['close'].get('watchdog_fired') and
            facts['close'].get('watchdog_error') is None, 'lookup source/native/owned process closure')
    requests = [entry['payload'] for entry in wire if entry['direction'] == 'request']
    require([request.get('method') for request in requests] == list(LOOKUP_METHODS), 'lookup exact zero-USER method profile')
    require(validate_wire(wire, facts['native13']['thread_id'], None) == {'actual': 0, 'attempted': 0, 'charged': 0, 'status': 'ZERO', 'accepted': 0}, 'lookup USER dispatch')
    replies = {entry['payload'].get('id'): entry['payload'] for entry in wire if entry['direction'] == 'response' and 'id' in entry['payload']}
    calls = [request for request in requests if 'id' in request]
    require(all(request['id'] in replies and 'result' in replies[request['id']] for request in calls), 'lookup missing/error RPC reply')
    native = decode(read_ref(native_reference))
    thread_request = next(request for request in requests if request['method'] == 'thread/start')
    actual = replies[thread_request['id']]['result']
    snapshot = load_legacy().reconcile_thread(actual, thread_request['params'], native['forward_thread_expectation'])
    require(snapshot == facts['native13'], 'lookup actual native13 snapshot')
    bundles = facts['bundles']
    require(type(bundles) is list and len(bundles) == 3 and bundles[1] == bundles[2] and
            facts['configuration_identity'] == bundles[2]['config'] and
            facts['catalog_proof'] == bundles[2]['catalog_proof'] and
            facts['catalog_proof'].get('enabled_unique_targets') == 16 and facts['catalog_proof'].get('load_errors') == 0,
            'lookup catalog/two-equal-B1 binding')
    policy = read_record(policy_reference, 'process-policy')
    scope = read_record(policy['scope'], 'scope')
    installed = [{'name': name, 'path': str(Path(scope['root']) / '.agents/skills' / name / 'SKILL.md'),
                  'realpath': str((Path(scope['root']) / '.agents/skills' / name / 'SKILL.md').resolve())}
                 for name in sorted(load_legacy().MANUAL | load_legacy().AUTO)]
    require(facts['config_facts'].get('response_identity') == facts['configuration_identity'], 'lookup source-computed config facts identity')
    for frame, offset in zip(bundles, (2, 6, 9)):
        pair = requests[offset:offset + 3]
        require(replies[pair[0]['id']]['result'] == replies[pair[2]['id']]['result'] == frame['config'] and
                replies[pair[1]['id']]['result'] == frame['catalog'] and
                frame['state_sha256'] == canonical_hash(lookup['state_before']) and
                load_legacy().validate_catalog(frame['catalog'], installed, facts['config_facts'], 'live') == frame['catalog_proof'],
                'lookup actual config/catalog/fullstate pair')
    candidate = read_record(facts['invariant_candidate'], 'invariant-anchor')
    require(candidate['product_manifest']['sha256'] == COMPOSITE_SHA and
            bundles[2].get('invariant_sha256') == canonical_hash(candidate) and
            candidate['native'] == _scope_normalize({key: value for key, value in facts['native13'].items() if key != 'thread_id'}, scope['realroot']),
            'observed invariant candidate actual native/source relation')
    validate_required_metadata(lookup_policy, scope)
    plan_record = read_record(lookup_policy['row_plan'])
    if plan_record['schema'] == 'postclosure-row-plan-v1':
        admission = read_record(plan_record['admission'], 'recovery-admission')
        validate_recovery_anchor(admission['invariant_anchor'], candidate)
    else:
        require(plan_record['schema'] == 'postclosure-observation-plan-v1', 'unknown zero observation plan')
    return facts


def validate_lookup_command(command_ref, expected_sha256):
    require(command_ref.get('sha256') == hash_value(expected_sha256), 'caller exact lookup command binding')
    command = read_record(command_ref, 'lookup-command')
    require(command['mode'] in ('business', 'anchor-observation'), 'explicit zero lookup mode')
    review = read_record(command['review'], 'lookup-review')
    decision = 'RELEASE_EXACT_ZERO_USER_ANCHOR_OBSERVATION_ONLY' if command['mode'] == 'anchor-observation' else 'RELEASE_EXACT_ZERO_USER_LOOKUP_ONLY'
    require(review['decision'] == decision and
            all(review[key] == command[key] for key in ('policy', 'scope', 'source_set', 'native_binding')), 'lookup Root authority edges')
    sources = validate_source_set(read_record(command['source_set'], 'source-set'))
    implementation = read_record(review['implementation_review'], 'implementation-review')
    require(implementation['source_set'] == command['source_set'] and implementation['decision'] == 'APPROVE_EXACT_SOURCE' and
            implementation['findings'] == [], 'lookup exact independent source review')
    scope = read_record(command['scope'], 'scope')
    choice = read_record(scope['process_choice'], 'process-choice')
    require(all(scope[key] == choice[key] for key in ('scope_id', 'root', 'realroot', 'topology')) and
            str(Path(scope['root']).resolve(strict=True)) == scope['realroot'] and
            choice['native_binding'] == command['native_binding'] and choice['decision'] == 'SELECT_EXACT_PROCESS_ONLY_SCOPE', 'lookup actual scope choice')
    read_ref(choice['executable'], executable=True)
    invoked = absolute(choice['invoked_path'])
    require(str(invoked) == '/opt/homebrew/bin/codex' and invoked.is_symlink() and
            str(invoked.resolve(strict=True)) == choice['executable']['path'] and
            os.readlink(invoked) == choice['invoked_link_text'] and
            oct(stat.S_IMODE(invoked.lstat().st_mode)) == choice['invoked_mode'], 'lookup executable invocation identity')
    native = decode(read_ref(command['native_binding']))
    legacy = load_legacy()
    require(native.get('official_commit') == legacy.SEMANTIC_COMMIT and
            native.get('codex_version') == 'codex-cli 0.164.0' and
            native.get('executable_identity', {}).get('sha256') == choice['executable']['sha256'] ==
            'd8990e3ee7acfbc26f91265b12a1a83f0fee40d0e0f8f1f40a37d4ec21f499cf', 'lookup native executable/source version')
    policy = read_record(command['policy'], 'process-policy')
    anchor_ref = None
    if command['mode'] == 'anchor-observation':
        plan = read_record(policy['row_plan'], 'observation-plan')
        require(all(plan[key] == command[key] for key in ('scope', 'source_set', 'native_binding', 'output')) and
                plan['metadata_paths'] == policy['metadata_paths'], 'closed zero observation plan relation')
        contract = {'capability_profile': None}
        manifest_ref = plan['product_manifest']
        negative = False
    else:
        plan = read_record(policy['row_plan'], 'row-plan')
        contract = read_record(plan['contract'], 'contract')
        admission = read_record(plan['admission'], 'recovery-admission')
        anchor_ref = admission['invariant_anchor']
        read_record(anchor_ref, 'invariant-anchor')
        manifest_ref = admission['composite_manifest']
        negative = plan['row_id'] == 'D2-tail/unavailable-review' and contract['capability_profile'] is not None
    require(manifest_ref['sha256'] == COMPOSITE_SHA, 'zero lookup exact source42 composite')
    read_ref(manifest_ref)
    require(policy['turn_permission'] is None, 'zero lookup cannot apply any turn overlay')
    validate_required_metadata(policy, scope)
    require(policy['scope'] == command['scope'] and policy['native_expectation'] == command['native_binding'] and
            policy['session'] == session_for(scope['realroot'], negative) and
            policy['argv'] == choice['argv'] == argv_for(choice['invoked_path'], scope['realroot'], negative) and
            policy['official_sources'] == sources['official_sources'], 'lookup policy exact scope/session/argv')
    read_ref(command['operator'], executable=True)
    require(command['operator']['path'] == str(HERE / 'postclosure_recovery_operator.py') and
            Path(command['output']).is_relative_to(CONTROL_ROOT) and not Path(command['output']).exists(), 'lookup operator/output')
    pins = [command_ref, command['review'], command['policy'], command['scope'], command['source_set'],
            command['native_binding'], review['implementation_review'], scope['process_choice'], choice['executable']]
    pins += sources['files'] + sources['official_sources'] + [manifest_ref] + scope['instruction_sources'] + scope['install']
    for path_key, hash_key in (('proof_path', 'proof_sha256'), ('source_index_path', 'source_index_sha256')):
        pin = {'path': native[path_key], 'sha256': native[hash_key]}
        read_ref(pin)
        pins.append(pin)
    if anchor_ref is not None:
        pins.append(anchor_ref)
    controls = [command_ref, command['review'], command['policy'], command['scope'], command['source_set'],
                command['native_binding'], review['implementation_review'], scope['process_choice'], policy['row_plan']]
    for pin in controls:
        require(Path(pin['path']).is_relative_to(CONTROL_ROOT), 'recovery lookup controls outside current control root')
    return {'command': command, 'scope': scope, 'choice': choice, 'policy': policy,
            'contract': contract, 'native': native, 'manifest': manifest_ref, 'anchor': anchor_ref,
            'pins': {reference['path']: reference for reference in pins}, 'controls': controls}


def validate_wire(wire, thread_id, turn_id):
    require(type(wire) is list, 'wire list required')
    pending = {}
    seen_ids = set()
    starts = 0
    accepted = 0
    replies = 0
    uncertain = False
    last = -1
    active_items = {}
    terminal = False
    for index, entry in enumerate(wire):
        fields(entry, 'index monotonic_ns direction payload bytes_sha256 bytes_length')
        require(type(entry['index']) is int and entry['index'] == index and
                type(entry['monotonic_ns']) is int and entry['monotonic_ns'] > last,
                'wire index/time ordering')
        last = entry['monotonic_ns']
        hash_value(entry['bytes_sha256'])
        require(type(entry['bytes_length']) is int and entry['bytes_length'] > 0, 'wire original byte length')
        obj = entry['payload']
        require(type(obj) is dict, 'wire payload')
        params = obj.get('params', {})
        require(type(params) is dict, 'wire params object')
        if entry['direction'] == 'request':
            method = obj.get('method')
            require(method in ('initialize', 'initialized', 'config/read', 'skills/list', 'thread/start', 'turn/start'),
                    'forbidden RPC method/server answer')
            if 'id' in obj:
                require(type(obj['id']) is int and obj['id'] not in seen_ids and
                        obj['id'] == len(seen_ids) + 1, 'duplicate/nonmonotonic request id')
                seen_ids.add(obj['id'])
                pending[obj['id']] = method
            if method == 'turn/start':
                starts += 1
                require(starts == 1 and params.get('threadId') == thread_id,
                        'second USER or foreign thread')
        elif entry['direction'] == 'response':
            item = obj.get('params', {}).get('item', {})
            method = obj.get('method', '')
            if type(method) is str and method.startswith(('item/', 'turn/')):
                require(not terminal and starts == 1 and thread_id is not None and turn_id is not None and
                        params.get('threadId') == thread_id, 'owned retained lifecycle thread identity/order')
                if method.startswith('item/'):
                    require(params.get('turnId') == turn_id, 'owned retained item turn identity')
                elif method in ('turn/started', 'turn/completed'):
                    require(type(params.get('turn')) is dict and params['turn'].get('id') == turn_id,
                            'owned retained turn identity')
                else:
                    require(params.get('turnId') == turn_id, 'owned retained turn delta identity')
                if method in ('item/started', 'item/completed'):
                    require(type(item) is dict, 'retained item object')
                    identity = nonempty(item.get('id'))
                    binding = (nonempty(item.get('type')), item.get('command'), item.get('cwd'))
                    if method == 'item/started':
                        require(identity not in active_items, 'retained duplicate item start')
                        active_items[identity] = binding
                    else:
                        require(identity in active_items and active_items.pop(identity) == binding, 'retained foreign item completion')
                if method == 'turn/completed':
                    require(not active_items and params['turn'].get('status') == 'completed', 'retained terminal active items/status')
                    terminal = True
            require(not (type(item) is dict and type(item.get('type')) is str and
                         item['type'].lower().startswith(('collabagent', 'subagent'))) and
                    not str(obj.get('method', '')).lower().startswith(('agent/', 'collab/', 'subagent/')),
                    'unaccounted nested agent context in retained wire')
            if 'id' in obj:
                require(type(obj['id']) is int and 'method' not in obj and obj['id'] in pending, 'server request/foreign response')
                method = pending.pop(obj['id'])
                if method == 'turn/start':
                    replies += 1
                    if 'result' in obj:
                        require(type(obj['result']) is dict and type(obj['result'].get('turn')) is dict and
                                obj['result']['turn'].get('id') == turn_id, 'malformed/foreign turn response')
                        accepted += 1
            if params.get('threadId') is not None:
                require(params['threadId'] == thread_id, 'foreign event thread')
            if params.get('turnId') is not None:
                require(params['turnId'] == turn_id, 'foreign event turn')
        elif entry['direction'] == 'transport_error':
            uncertain = uncertain or starts > replies
        else:
            raise Hold('unknown wire direction')
    uncertain = uncertain or starts > replies
    return {'actual': None if uncertain else starts, 'attempted': starts, 'charged': starts,
            'status': 'UNKNOWN' if uncertain else ('ACTUAL' if starts else 'ZERO'), 'accepted': accepted}


def _same_except(before, after, paths):
    require({k: v for k, v in before.items() if k not in paths} ==
            {k: v for k, v in after.items() if k not in paths}, 'undeclared state mutation')


def validate_cache(candidate, source, *, source_path, cache_path, mtime_ns, source_size,
                   interpreter, expected_interpreter):
    """Attribute one finite CPython cache without decoding candidate code.

    Caller captures source bytes and stat together. Cache namespace/mode/alias
    classification remains a separate full-inventory contract. This verifier
    does not admit a runtime profile, ignore unchanged caches, or execute pyc.
    """
    require(type(candidate) is bytes and type(source) is bytes, 'cache/source byte capture')
    require(len(candidate) <= 8 * 1024 * 1024 and len(source) <= 4 * 1024 * 1024, 'cache/source capture size bound')
    fields(interpreter, 'executable version cache_tag magic marshal_version')
    require(interpreter == expected_interpreter, 'interpreter source profile drift')
    read_ref(interpreter['executable'], executable=True)
    require(sys.implementation.name == 'cpython' and sys.version_info[:3] == (3, 14, 6) and
            interpreter['version'] == '3.14.6' and interpreter['cache_tag'] == sys.implementation.cache_tag == 'cpython-314' and
            interpreter['magic'] == importlib.util.MAGIC_NUMBER.hex() == '2b0e0d0a' and
            interpreter['marshal_version'] == marshal.version == 5, 'unreviewed interpreter profile')
    absolute(source_path)
    absolute(cache_path)
    require(cache_path == importlib.util.cache_from_source(source_path, optimization=''), 'cache source/path/tag relation')
    require(type(mtime_ns) is int and mtime_ns >= 0 and type(source_size) is int and
            source_size == len(source), 'captured source stat')
    require(len(candidate) >= 16 and candidate[:4] == importlib.util.MAGIC_NUMBER, 'cache magic/header')
    flags = struct.unpack('<I', candidate[4:8])[0]
    require(flags in (0, 1, 3), 'unsupported pyc flags')
    if flags == 0:
        require(candidate[8:16] == struct.pack('<II', (mtime_ns // 1_000_000_000) & 0xffffffff,
                                               source_size & 0xffffffff), 'cache timestamp/source-size relation')
    else:
        require(candidate[8:16] == importlib.util.source_hash(source), 'cache source-hash relation')
    expected = compile(source, source_path, 'exec', flags=0, dont_inherit=True, optimize=0)
    require(candidate[16:] == marshal.dumps(expected, marshal.version), 'cache full code/source/filename/content relation')
    return {'cache_sha256': digest(candidate), 'source_sha256': digest(source),
            'source_path': source_path, 'cache_path': cache_path, 'flags': flags,
            'business_PASS': False}


def capture_cache_versions(profile, root, event_index):
    """Honest post-observation capture, never labeled pre-execution provenance."""
    validate_record(profile, 'cache-profile')
    versions = []
    for output in profile['outputs']:
        fields(output, 'source cache mode flags')
        relative(output['source'])
        relative(output['cache'])
        path = absolute(str(root)) / output['source']
        if not path.exists():
            continue
        data, info = file_bytes(path)
        require(len(data) <= 4 * 1024 * 1024, 'source capture bound')
        versions.append({'source': output['source'], 'bytes': data, 'mtime_ns': info.st_mtime_ns,
                         'size': info.st_size, 'event_index': event_index,
                         'relation': 'post-observation source equivalence; no write-causality claim'})
    return versions


def allowed_cache_commands(profile):
    require(profile['command'] == 'python3 -m unittest discover -v' and type(profile['extra_commands']) is list and
            all(type(command) is str for command in profile['extra_commands']) and len(profile['extra_commands']) <= 8,
            'finite actual D2 interpreter commands')
    require(profile['row_id'] == 'D2-tail/Git-AC9' or profile['extra_commands'] == [], 'extra verification commands are P6-only')
    for command in profile['extra_commands']:
        argv = decode_command(command)
        require(len(argv) == 3 and argv[:2] == ['python3', '-c'], 'bounded approved Python verification command')
    return [profile['command']] + profile['extra_commands']


class _CacheProof(dict):
    pass


PYTHON_ENVIRONMENT = ('PATH', 'PYTHONPATH', 'PYTHONHOME', 'PYTHONOPTIMIZE',
                      'PYTHONPYCACHEPREFIX', 'PYTHONDONTWRITEBYTECODE', 'PYTHONHASHSEED',
                      'PYTHONNODEBUGRANGES', 'PYTHONSAFEPATH')


def validate_derived_caches(profile, before, after, versions, events, root, environment, captured_files=None):
    validate_record(profile, 'cache-profile')
    require(profile['row_id'] in ('D2-tail/TDD-build', 'D2-tail/Git-AC9',
                                  'D2-tail/independent-review', 'D2-tail/local-ship'), 'cache row not admitted')
    require(profile['command'] == 'python3 -m unittest discover -v' and profile['cwd'] == str(root),
            'authentic D2 test command/cwd')
    require(profile['environment'] == {key: environment.get(key) for key in PYTHON_ENVIRONMENT} and
            all(environment.get(key) is None for key in PYTHON_ENVIRONMENT if key != 'PATH'),
            'test interpreter environment drift/unsupported flags')
    interpreter = profile['interpreter']
    commands = allowed_cache_commands(profile)
    require(str(Path(shutil.which('python3', path=environment.get('PATH')) or '').resolve()) == interpreter['executable']['path'],
            'actual python3 resolution differs from pinned interpreter')
    read_ref(profile['command_interpreter_proof'])
    require(type(profile['official_sources']) is list and profile['official_sources'], 'CPython official-source proof')
    for reference in profile['official_sources']:
        read_ref(reference)
    require(type(profile['outputs']) is list and profile['outputs'], 'finite source/cache mapping required')
    mapping = {}
    for output in profile['outputs']:
        fields(output, 'source cache mode flags')
        relative(output['source']); relative(output['cache'])
        require(output['cache'] not in mapping and output['mode'] == '0o644' and
                type(output['flags']) is list and output['flags'] and
                all(type(flag) is int and flag in (0, 1, 3) for flag in output['flags']) and
                str(root / output['cache']) == importlib.util.cache_from_source(str(root / output['source']), optimization=''),
                'finite canonical cache mapping/mode/header profile')
        mapping[output['cache']] = output
    changed = {path for path in set(before) | set(after) if before.get(path) != after.get(path) and
               (path in mapping or '__pycache__' in Path(path).parts)}
    matches = {}
    for path in changed:
        if after.get(path, {}).get('kind') == 'directory':
            require(path not in before and any(str(Path(cache).parent) == path for cache in mapping), 'undeclared cache directory')
            continue
        require(path in mapping and path in after and after[path].get('kind') == 'file' and
                after[path].get('link_text') is None and after[path].get('mode') == mapping[path]['mode'],
                'undeclared/deleted/aliased cache output')
        candidate = captured_files[path] if captured_files is not None else file_bytes(root / path)[0]
        require(digest(candidate) == after[path].get('sha256'), 'cache inventory/read drift')
        flags = struct.unpack('<I', candidate[4:8])[0] if len(candidate) >= 8 else None
        require(flags in mapping[path]['flags'], 'cache header-mode transition not admitted')
        matched = []
        for version in versions:
            if version['source'] != mapping[path]['source']:
                continue
            index = version['event_index']
            require(type(index) is int and 0 <= index < len(events), 'source version command index')
            event = events[index]
            item = event.get('params', {}).get('item', {})
            require(event.get('method') == 'item/completed' and item.get('type') == 'commandExecution' and
                    any(command_matches(item.get('command'), command) for command in commands) and item.get('cwd') == str(root) and
                    item.get('status') == 'completed' and type(item.get('exitCode')) is int,
                    'actual completed authorized test command')
            try:
                proof = validate_cache(candidate, version['bytes'], source_path=str(root / version['source']),
                                       cache_path=str(root / path), mtime_ns=version['mtime_ns'], source_size=version['size'],
                                       interpreter=interpreter, expected_interpreter=profile['interpreter'])
            except Hold:
                continue
            matched.append(dict(proof, event_index=index, relation=version['relation']))
        require(matched, 'cache has no observed authorized source version')
        matches[path] = matched
    return _CacheProof({'profile': canonical_hash(profile), 'before': canonical_hash(before),
                        'after': canonical_hash(after), 'paths': sorted(changed), 'matches': matches,
                        'business_PASS': False})


def validate_resource_consumption(resources, events, captured_files=None):
    """Complete successful command output, bound to an installed resource Ref.

    Text mentions, failed compound reads and partial/subsequence outputs cannot
    establish consumption. This is ordinary body consumption, not injection.
    """
    require(type(resources) is list and len(resources) >= 2, 'review body/template required')
    bodies = {}
    for resource in resources:
        fields(resource, 'resource command event_index')
        bodies[resource['resource']['path']] = read_ref(resource['resource']).decode('utf-8')
    if captured_files is not None:
        require(type(captured_files) is dict, 'trusted companion capture map')
        for path, data in captured_files.items():
            absolute(path)
            require(type(data) is bytes, 'trusted companion bytes')
            try:
                text = data.decode('utf-8')
            except UnicodeError:
                continue
            require(path not in bodies or bodies[path] == text, 'resource/capture content disagreement')
            bodies[path] = text
    consumed = set()
    for resource in resources:
        fields(resource, 'resource command event_index')
        body = read_ref(resource['resource']).decode('utf-8')
        nonempty(body)
        require(type(resource['event_index']) is int and 0 <= resource['event_index'] < len(events), 'resource event index')
        event = events[resource['event_index']]
        require(type(event) is dict and event.get('method') == 'item/completed', 'resource completed command event required')
        item = event.get('params', {}).get('item', {})
        require(type(item) is dict and item.get('type') == 'commandExecution' and
                item.get('status') == 'completed' and type(item.get('exitCode')) is int and
                item['exitCode'] == 0 and item.get('command') == resource['command'] and
                not item.get('outputTruncated', False),
                'missing successful complete installed resource consumption')
        argv = decode_command(resource['command'])
        require(argv and argv[0] in ('cat', '/bin/cat', '/usr/bin/cat'), 'unsupported resource read command')
        paths = argv[1:]
        if paths and paths[0] == '--':
            paths = paths[1:]
        resolved = [str((Path(item.get('cwd', '/')) / path).resolve()) if not Path(path).is_absolute() else path for path in paths]
        require(resolved and all(path in bodies for path in resolved) and resource['resource']['path'] in resolved and
                item.get('aggregatedOutput') == ''.join(bodies[path] for path in resolved),
                'resource read must contain complete exact output for actual finite files')
        require(resource['resource']['path'] not in consumed, 'duplicate resource consumption')
        consumed.add(resource['resource']['path'])
    return sorted(consumed)


MAX_CAPTURE_FILES = 512
MAX_CAPTURE_FILE_BYTES = 8 * 1024 * 1024
MAX_CAPTURE_BYTES = 64 * 1024 * 1024


def validate_review_capture(reference, record, plan):
    capture = read_record(reference, 'review-capture')
    owned = [sample for sample in record['samples'] if sample.get('phase') == 'review-target-capture']
    require(len(owned) == 1 and fields(owned[0], 'phase capture')['capture'] == reference and
            capture['scope'] == plan['scope'], 'review capture must be owned by actual raw context')
    scope = read_record(capture['scope'], 'scope')
    require(scope['root'] == record['root'] and scope['realroot'] == record['realroot'], 'capture actual scope')
    before, after = (decode(read_ref(capture[key])) for key in ('state_before', 'state_after'))
    require(before == after == record['state_after'], 'capture paired complete post-close state')
    expected = {path for path, value in after.items() if value.get('kind') == 'file'}
    require(type(capture['files']) is dict and set(capture['files']) == expected and
            len(expected) <= MAX_CAPTURE_FILES and
            all(value.get('kind') in ('file', 'directory') and value.get('link_text') is None for value in after.values()),
            'complete finite regular-file capture only')
    total = 0
    content = {}
    for path, pin in capture['files'].items():
        relative(path)
        data = read_ref(pin)
        total += len(data)
        require(len(data) <= MAX_CAPTURE_FILE_BYTES and total <= MAX_CAPTURE_BYTES and
                digest(data) == after[path]['sha256'], 'capture bytes/inventory/hash/size relation')
        require(not Path(pin['path']).is_relative_to(Path(scope['realroot'])), 'capture bytes must be immutable outside fixture')
        content[path] = data
    return capture, after, content


def evidence_contexts(context_reference, record, plan, prior_results):
    entries = [(context_reference, record, plan)]
    for result_reference in prior_results:
        result = read_record(result_reference, 'independent-result')
        previous = read_record(result['context'], 'context')
        common = read_record(previous['common'], 'common')
        entries.append((result['context'], previous, read_record(common['row_plan'], 'row-plan')))
    contexts, captures = {}, {}
    for reference, raw, row in entries:
        key = canonical_hash(reference)
        require(key not in contexts, 'duplicate evidence context')
        owned = [sample for sample in raw['samples'] if sample.get('phase') == 'review-target-capture']
        require(len(owned) == 1, 'actual raw-owned final capture required')
        capture_reference = owned[0]['capture']
        capture, state, content = validate_review_capture(capture_reference, raw, row)
        entry = {'reference': reference, 'raw': raw, 'plan': row, 'capture_ref': capture_reference,
                 'capture': capture, 'state': state, 'content': content}
        contexts[key] = entry
        captures[canonical_hash(capture_reference)] = entry
    if plan['row_id'] == 'D2-tail/spec-approval':
        predecessor = read_record(plan['predecessor'], 'predecessor')
        require(predecessor['context']['sha256'] == D2_RAW_SHA, 'finite bootstrap question context only')
        old = decode(read_ref(predecessor['context']))
        require(old.get('healthy') is True and old.get('closed') is True and old.get('failure') is None,
                'actual accepted legacy D2 question required')
        wire = decode(read_ref(old['wire']))
        question = validate_question(predecessor['question'], predecessor['context'], wire)
        event = wire[question['wire_index']]['payload']
        require(wire[question['wire_index']]['direction'] == 'response_or_event', 'exact legacy question event direction')
        adapted_wire = list(wire)
        adapted_wire[question['wire_index']] = dict(wire[question['wire_index']], direction='response')
        adapted = dict(old, wire=adapted_wire, turn_id=event['params']['turnId'], state_after=old['state'])
        contexts[canonical_hash(predecessor['context'])] = {
            'reference': predecessor['context'], 'raw': adapted, 'plan': None,
            'capture_ref': None, 'capture': None, 'state': old['state'], 'content': {},
            'legacy_question_index': question['wire_index']}
    return contexts, captures


def validate_source_slice(source, contexts, captures, purpose=None):
    require(type(source) is dict, 'source slice object')
    if source.get('kind') == 'wire':
        fields(source, 'kind context wire_index item_sha256 field start end sha256')
        key = canonical_hash(source['context'])
        require(key in contexts, 'source slice context outside accepted evidence')
        entry = contexts[key]
        wire = entry['raw']['wire']
        index = source['wire_index']
        require(type(index) is int and 0 <= index < len(wire), 'source slice wire index')
        if entry['plan'] is None:
            require(entry['reference']['sha256'] == D2_RAW_SHA and index == entry['legacy_question_index'], 'finite legacy bootstrap question slice only')
        frame = wire[index]
        event = frame.get('payload', {})
        params = event.get('params', {})
        item = params.get('item', {})
        require(frame.get('direction') == 'response' and event.get('method') == 'item/completed' and
                type(item) is dict and canonical_hash(item) == source['item_sha256'] and
                params.get('threadId') == entry['raw']['thread_id'] and params.get('turnId') == entry['raw']['turn_id'],
                'source slice actual completed item/lifecycle identity')
        field = source['field']
        accepted_exit = item.get('exitCode') == 0 and type(item.get('exitCode')) is int
        row = entry['plan']['row_id'] if entry['plan'] is not None else None
        if purpose == 'red_before_production' and row == 'D2-tail/TDD-build':
            accepted_exit |= type(item.get('exitCode')) is int and item['exitCode'] == 1 and command_matches(
                item.get('command'), 'python3 -m unittest discover -v')
        if purpose == 'installed_HUMAN_REQUIRED_10' and row == 'D2-tail/local-ship':
            try:
                argv = decode_command(item.get('command'))
            except Hold:
                argv = []
            if argv and argv[0] in ('sh', 'bash', '/bin/sh', '/bin/bash'):
                argv = argv[1:]
            helper = '.agents/skills/ains-review-gate/scripts/route-review.sh'
            target = str(Path(entry['raw']['root']) / helper)
            accepted_exit |= bool(argv and str((Path(entry['raw']['root']) / argv[0]).resolve()) == target and
                                  type(item.get('exitCode')) is int and item['exitCode'] == 10 and
                                  'HUMAN_REQUIRED' in item.get('aggregatedOutput', '') and helper in entry['content'])
        require((item.get('type') == 'agentMessage' and field == 'text') or
                (item.get('type') == 'commandExecution' and field == 'aggregatedOutput' and
                 item.get('status') == 'completed' and accepted_exit and
                 not item.get('outputTruncated', False)), 'source slice successful model output required')
        require(type(item.get(field)) is str, 'source slice textual item field')
        body = item[field].encode('utf-8')
        origin = {'entry': entry, 'item': item, 'kind': 'wire', 'wire_index': index}
    elif source.get('kind') == 'input':
        fields(source, 'kind context start end sha256')
        key = canonical_hash(source['context'])
        require(key in contexts and contexts[key]['plan'] is not None, 'input slice must be successor actual USER')
        entry = contexts[key]
        decision = read_input_decision(entry['plan'])
        starts = [frame['payload'] for frame in entry['raw']['wire'] if frame['direction'] == 'request' and frame['payload'].get('method') == 'turn/start']
        require(len(starts) == 1 and starts[0].get('params', {}).get('input') == [{'type': 'text', 'text': decision['request']}],
                'input slice actual signed USER delivery')
        body = decision['request'].encode('utf-8')
        origin = {'entry': entry, 'kind': 'input'}
    elif source.get('kind') == 'artifact':
        fields(source, 'kind capture path start end sha256')
        key = canonical_hash(source['capture'])
        require(key in captures, 'artifact slice is not raw-owned capture')
        entry = captures[key]
        relative(source['path'])
        require(source['path'] in entry['content'], 'artifact slice path absent from actual capture')
        body = entry['content'][source['path']]
        origin = {'entry': entry, 'kind': 'artifact', 'path': source['path']}
    else:
        raise Hold('unknown source slice kind')
    start, end = source['start'], source['end']
    require(type(start) is int and type(end) is int and 0 <= start < end <= len(body) and
            digest(body[start:end]) == hash_value(source['sha256']), 'source slice UTF8-byte range/digest')
    return body[start:end], origin


def model_handoff_slice(source, contexts, captures, author_reference):
    data, origin = validate_source_slice(source, contexts, captures)
    entry = origin['entry']
    require(entry['reference'] == author_reference, 'handoff origin must be actual P7 author context')
    require(origin['kind'] in ('wire', 'artifact'), 'input decisions are not model handoff')
    if origin['kind'] == 'wire':
        require(origin['item'].get('type') == 'agentMessage' and origin['item'].get('phase') == 'final_answer',
                'handoff origin must be actual completed final answer')
    else:
        path = origin['path']
        roles = read_record(entry['plan']['contract'], 'contract')['roles']
        require(path in roles['packet'] and entry['raw']['state_before'].get(path, {}).get('sha256') !=
                entry['raw']['state_after'][path]['sha256'], 'handoff must be actual model-authored packet path')
        provenance = False
        for frame in entry['raw']['wire']:
            event = frame.get('payload', {})
            item = event.get('params', {}).get('item', {})
            if frame.get('direction') != 'response' or event.get('method') != 'item/completed':
                continue
            if item.get('type') == 'agentMessage' and item.get('phase') == 'final_answer':
                provenance |= path in item.get('text', '') or str(Path(entry['raw']['root']) / path) in item.get('text', '')
            if item.get('type') == 'fileChange' and item.get('status') == 'completed':
                provenance |= any(change.get('path') in (path, str(Path(entry['raw']['root']) / path))
                                  for change in item.get('changes', []) if type(change) is dict)
        require(provenance, 'supervisor capture cannot supply missing model handoff')
    return data


def validate_adjudication(result, record, plan, prior_results):
    adjudication = read_record(result['adjudication'], 'adjudication')
    require(adjudication['context'] == result['context'] and adjudication['row_contract'] == plan['contract'] and
            decode(read_ref(adjudication['poststate'])) == record['state_after'], 'adjudication actual context/contract/poststate')
    contract = read_record(plan['contract'], 'contract')
    require(contract['expected_after'] is None and contract['evidence'] == {}, 'released contract must remain prospective and unchanged')
    contexts, captures = evidence_contexts(result['context'], record, plan, prior_results)
    current = contexts[canonical_hash(result['context'])]
    require(adjudication['capture'] == current['capture_ref'], 'adjudication capture must be actual own raw capture')
    observations = adjudication['observations']
    require(type(observations) is dict and set(observations) == set(contract['obligations']), 'exact actual obligation observation set')
    for obligation, observation in observations.items():
        fields(observation, 'sources judgment')
        require(type(observation['sources']) is list and observation['sources'] and
                type(observation['judgment']) is str and observation['judgment'].strip(), 'actual source slices and independent judgment required')
        for source in observation['sources']:
            validate_source_slice(source, contexts, captures, purpose=obligation)
    input_obligations = {'D2-tail/spec-approval': 'separate_spec_decision',
                         'D2-tail/plan-approval': 'separate_plan_decision',
                         'D2-tail/content-to-operation-question': 'actual_content_decision',
                         'D2-tail/Git-AC9': 'separate_exact_git_grant',
                         'D2-tail/scope-invalidation': 'actual_scope_change'}
    if plan['row_id'] in input_obligations:
        require(any(source.get('kind') == 'input' and source.get('context') == result['context']
                    for source in observations[input_obligations[plan['row_id']]]['sources']),
                'owner decision requires actual input slice, not model prose')
    if plan['row_id'] == 'D2-tail/spec-approval':
        predecessor = read_record(plan['predecessor'], 'predecessor')
        question = read_record(predecessor['question'], 'question')
        require(any(source.get('kind') == 'wire' and source.get('context') == predecessor['context'] and
                    source.get('wire_index') == question['wire_index'] for source in observations['actual_question']['sources']),
                'P1 actual question must be exact accepted D2 final item')
    common = read_record(record['common'], 'common')
    decision = read_input_decision(plan)
    starts = [frame['payload'] for frame in record['wire'] if frame['direction'] == 'request' and frame['payload'].get('method') == 'turn/start']
    require(len(starts) == 1 and starts[0].get('params', {}).get('input') == [{'type': 'text', 'text': decision['request']}] and
            common['input_sha256'] == canonical_hash(decision), 'actual authorized USER delivery binding')
    policy = read_record(common['policy'], 'process-policy')
    overlay = validate_turn_permission(policy, plan, read_record(plan['scope'], 'scope'), common['row_plan']) or {}
    require(set(starts[0]['params']) == {'threadId', 'input'} | set(overlay) and
            all(starts[0]['params'].get(key) == value for key, value in overlay.items()), 'actual finite turn permission delivery')
    def captured_before():
        samples = [sample for sample in record['samples'] if sample.get('phase') == 'artifact-byte-captures-before']
        require(len(samples) == 1, 'actual before-artifact capture required')
        fields(samples[0], 'phase captures')
        require(type(samples[0]['captures']) is dict, 'before capture mapping')
        content = {}
        for path, reference in samples[0]['captures'].items():
            relative(path)
            data = read_ref(reference)
            require(Path(reference['path']).is_relative_to(Path(plan['output'])) and
                    digest(data) == record['state_before'].get(path, {}).get('sha256'), 'actual owned before-byte capture')
            content[path] = data
        return content
    before_content = captured_before()
    events = [frame['payload'] for frame in record['wire'] if frame['direction'] == 'response' and 'method' in frame['payload']]
    cache_proof = None
    if contract['cache_profile'] is not None:
        versions = []
        for sample in record['samples']:
            if sample.get('phase') != 'post-command-source-equivalence':
                continue
            fields(sample, 'phase event_index versions')
            require(type(sample['versions']) is list, 'actual captured source versions')
            for version in sample['versions']:
                fields(version, 'source mtime_ns size event_index relation capture')
                require(version['event_index'] == sample['event_index'] and
                        Path(version['capture']['path']).is_relative_to(Path(plan['output'])), 'owned source version/event')
                versions.append({**{key: value for key, value in version.items() if key != 'capture'},
                                 'bytes': read_ref(version['capture'])})
        cache_proof = validate_derived_caches(read_record(contract['cache_profile'], 'cache-profile'),
            record['state_before'], record['state_after'], versions, events, Path(record['root']),
            dict(os.environ), captured_files=current['content'])
    git_proof = None
    if contract['git_profile'] is not None:
        require(prior_results, 'Git journey needs actual accepted predecessor capture')
        prior_result = read_record(prior_results[-1], 'independent-result')
        previous = contexts[canonical_hash(prior_result['context'])]
        require(previous['state'] == record['state_before'], 'Git actual predecessor capture relation')
        git_proof = validate_git_rollback(read_record(contract['git_profile'], 'git-profile'),
            record['state_before'], record['state_after'], previous['content'], current['content'], events,
            contract['roles'], cache_proof, [sample['observation'] for sample in record['samples']
                if sample.get('phase') == 'P6-off-observation'])
    capability_proof = None
    if contract['capability_profile'] is not None:
        lookup = read_record(common['lookup'], 'lookup')
        validate_lookup(lookup, common['policy'], common['source_set'], common['native_binding'])
        capability_proof = lookup['native_facts']['capability']
        require(capability_proof is not None, 'actual declared-route zero-USER capability evidence required')
    validate_transition(plan, record['state_before'], record['state_after'], {},
                        contents_before=before_content, contents_after=current['content'],
                        git_proof=git_proof, cache_proof=cache_proof, capability_proof=capability_proof)
    if plan['row_id'] == 'D2-tail/local-ship':
        validate_local_ship_adjudication(adjudication, current, contexts, captures)
    if plan['row_id'] in ('D2-tail/unavailable-review', 'D2-tail/independent-review'):
        validate_f1_adjudication(adjudication, current, contexts, captures, prior_results)
    else:
        require(adjudication['packet'] is None and adjudication['projection'] is None, 'F1 packet/projection only admitted review rows')
    return adjudication


def model_artifact_provenance(entry, path):
    require(path in entry['content'] and entry['state'].get(path, {}).get('kind') == 'file' and
            entry['raw']['state_before'].get(path) != entry['state'][path], 'actual new/changed model artifact required')
    for frame in entry['raw']['wire']:
        event = frame.get('payload', {}); item = event.get('params', {}).get('item', {})
        if frame.get('direction') != 'response' or event.get('method') != 'item/completed':
            continue
        if item.get('type') == 'agentMessage' and item.get('phase') == 'final_answer' and path in item.get('text', ''):
            return True
        if item.get('type') == 'fileChange' and item.get('status') == 'completed' and any(
                change.get('path') in (path, str(Path(entry['raw']['root']) / path))
                for change in item.get('changes', []) if type(change) is dict):
            return True
    raise Hold('missing actual model artifact provenance')


def validate_local_ship_adjudication(adjudication, current, contexts, captures):
    """Objective P9 facts; report quality and business judgment stay independent."""
    contract = read_record(current['plan']['contract'], 'contract')
    helper = '.agents/skills/ains-review-gate/scripts/route-review.sh'
    root = Path(current['raw']['root'])
    common = read_record(current['raw']['common'], 'common')
    manifest = decode(read_ref(common['product_manifest']))
    expected = manifest['suite_files']['skills/ains-review-gate/scripts/route-review.sh']
    require(helper in current['content'] and digest(current['content'][helper]) == expected['sha256'] and
            current['state'][helper]['mode'] == expected['mode'], 'actual current installed H helper')
    valid = set()
    for index, frame in enumerate(current['raw']['wire']):
        event = frame.get('payload', {}); params = event.get('params', {}); item = params.get('item', {})
        if frame.get('direction') != 'response' or event.get('method') != 'item/completed' or item.get('type') != 'commandExecution':
            continue
        try:
            argv = decode_command(item.get('command'))
        except Hold:
            continue
        if argv and argv[0] in ('sh', 'bash', '/bin/sh', '/bin/bash'):
            argv = argv[1:]
        if not argv or argv[0] not in (helper, str(root / helper)):
            continue
        require(2 <= len(argv) <= 4 and argv[1] in ('docs/ains/human-review-rules', str(root / 'docs/ains/human-review-rules')) and
                params.get('threadId') == current['raw']['thread_id'] and params.get('turnId') == current['raw']['turn_id'] and
                item.get('cwd') == str(root) and item.get('status') == 'completed' and
                type(item.get('exitCode')) is int and item['exitCode'] == 10 and not item.get('outputTruncated', False) and
                type(item.get('aggregatedOutput')) is str and 'HUMAN_REQUIRED' in item['aggregatedOutput'],
                'actual installed H complete exit10/current cwd required')
        valid.add(index)
    require(valid, 'P9 actual installed HUMAN_REQUIRED command missing')
    sources = adjudication['observations']['installed_HUMAN_REQUIRED_10']['sources']
    require(any(source.get('kind') == 'wire' and source.get('context') == current['reference'] and
                source.get('wire_index') in valid and source.get('field') == 'aggregatedOutput' and
                b'HUMAN_REQUIRED' in validate_source_slice(source, contexts, captures, purpose='installed_HUMAN_REQUIRED_10')[0]
                for source in sources), 'P9 H obligation must cite actual complete command result')
    path = contract['roles']['local_pr']
    require(type(path) is str and path in contract['authored'] and path in current['content'] and current['content'][path],
            'P9 captured local PR artifact required')
    model_artifact_provenance(current, path)
    require(any(source.get('kind') == 'artifact' and source.get('capture') == current['capture_ref'] and source.get('path') == path
                for source in adjudication['observations']['local_pr_complete']['sources']), 'P9 PR obligation must cite actual captured PR')
    return True


class CapturedGit:
    """Read-only bounded SHA1 object view; no executable Git dependency."""
    def __init__(self, content):
        self.content = content
        self.cache = {}
        require(not any(path.startswith('.git/objects/pack/') or path == '.git/objects/info/alternates'
                        for path in content), 'unsupported packed/alternate review object store')

    def object(self, object_id):
        require(type(object_id) is str and re.fullmatch('[0-9a-f]{40}', object_id), 'captured Git OID')
        if object_id in self.cache:
            return self.cache[object_id]
        require(len(self.cache) < 10000, 'captured Git traversal bound')
        path = '.git/objects/' + object_id[:2] + '/' + object_id[2:]
        raw = self.content.get(path)
        require(type(raw) is bytes and len(raw) <= MAX_CAPTURE_FILE_BYTES, 'captured loose object missing/oversize')
        decoder = zlib.decompressobj()
        data = decoder.decompress(raw, 16 * 1024 * 1024 + 1)
        require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail and
                len(data) <= 16 * 1024 * 1024 and hashlib.sha1(data).hexdigest() == object_id, 'captured Git object/hash/header')
        header, zero, body = data.partition(b'\0')
        kind, space, size = header.partition(b' ')
        require(zero and space and kind in (b'commit', b'tree', b'blob') and
                size == str(len(body)).encode(), 'captured Git object type/size')
        self.cache[object_id] = kind, body
        return kind, body

    def commit(self, object_id):
        kind, body = self.object(object_id)
        require(kind == b'commit', 'captured commit required')
        headers = body.split(b'\n\n', 1)[0].splitlines()
        trees = [line[5:].decode() for line in headers if line.startswith(b'tree ')]
        parents = [line[7:].decode() for line in headers if line.startswith(b'parent ')]
        require(len(trees) == 1 and len(parents) <= 1 and
                all(re.fullmatch('[0-9a-f]{40}', oid) for oid in trees + parents), 'unsupported review commit ancestry')
        return trees[0], parents[0] if parents else None

    def ancestry(self, object_id):
        result = []
        while object_id is not None:
            require(object_id not in result and len(result) < 128, 'review ancestry cycle/bound')
            result.append(object_id)
            _, object_id = self.commit(object_id)
        return result

    def tree(self, object_id, prefix=''):
        require(prefix.count('/') < 64, 'captured tree depth')
        kind, body = self.object(object_id)
        require(kind == b'tree', 'captured tree required')
        result, names = {}, set()
        while body:
            entry, zero, rest = body.partition(b'\0')
            mode, space, name = entry.partition(b' ')
            require(zero and space and len(rest) >= 20 and name and b'/' not in name and
                    name not in (b'.', b'..') and name not in names and
                    mode in (b'40000', b'100644', b'100755'), 'captured tree mode/path')
            names.add(name)
            path = prefix + name.decode('utf-8')
            oid = rest[:20].hex()
            body = rest[20:]
            if mode == b'40000':
                nested = self.tree(oid, path + '/')
                require(not set(nested) & set(result), 'captured tree duplicate')
                result.update(nested)
            else:
                kind, value = self.object(oid)
                require(kind == b'blob', 'captured tree blob')
                result[path] = (mode.decode(), oid, value)
        return result


def _file_endpoint(state, content, path, off_path=None):
    if path not in content:
        require(path not in state, 'target absence must be actual namespace absence')
        return None
    require(state[path].get('kind') == 'file' and (state[path].get('mode') in ('0o644', '0o755') or (path == off_path and state[path].get('mode') == '0o600')), 'review endpoint file mode')
    data = content[path]
    oid = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    return ('100755' if state[path]['mode'] == '0o755' else '100644', oid, data)


def _endpoint_equal(endpoint, expected, actual_mode=None):
    if expected is None:
        require(endpoint is None, 'false endpoint presence')
        return
    fields(endpoint, 'content mode oid')
    require(endpoint['mode'] == (actual_mode or ('0o644' if expected[0] == '100644' else '0o755')) and
            endpoint['oid'] == expected[1] and read_ref(endpoint['content']) == expected[2], 'endpoint actual bytes/mode/blob identity')


def derive_review_target(entry, git_profile, accepted_git_entry):
    state, content = entry['state'], entry['content']
    accepted_state = accepted_git_entry['state']
    require({path: value for path, value in state.items() if path == '.git' or path.startswith('.git/')} ==
            {path: value for path, value in accepted_state.items() if path == '.git' or path.startswith('.git/')},
            'P7 Git state differs from accepted actual P6')
    branch = git_profile['branch']
    require(content.get('.git/HEAD') == b'ref: ' + branch.encode() + b'\n', 'review feature HEAD')
    def ref_oid(path):
        value = content.get('.git/' + path)
        require(type(value) is bytes and re.fullmatch(b'[0-9a-f]{40}\n', value), 'captured review loose ref')
        return value.strip().decode()
    base, head = ref_oid(git_profile['main_ref']), ref_oid(branch)
    store = CapturedGit(content)
    base_chain, head_chain = store.ancestry(base), store.ancestry(head)
    merge_base = next((oid for oid in head_chain if oid in base_chain), None)
    require(merge_base is not None, 'review merge base not proven')
    baseline = store.tree(store.commit(merge_base)[0])
    committed = store.tree(store.commit(head)[0])
    validate_index(content.get('.git/index'), committed)
    roles = read_record(entry['plan']['contract'], 'contract')['roles']
    target = sorted(set(roles['application'] + roles['tests'] + roles['progress'] +
                        [path for path in (roles['spec'], roles['tasks'], roles['off']) if path is not None]))
    callers = sorted(roles['callers'])
    require(target and not set(target) & set(callers), 'independently bound target/caller roles')
    layers = {'commit': {}, 'index': {}, 'worktree': {}, 'untracked': {}}
    for path in target:
        relative(path)
        if baseline.get(path) != committed.get(path):
            layers['commit'][path] = (baseline.get(path), committed.get(path))
        actual = _file_endpoint(state, content, path, roles['off'])
        if path in committed:
            if committed[path] != actual:
                layers['worktree'][path] = (committed[path], actual)
        elif actual is not None:
            require(path not in baseline, 'untracked target was tracked in baseline')
            layers['untracked'][path] = (None, actual)
    for path in callers:
        require(path in content and path in committed and committed[path] == _file_endpoint(state, content, path),
                'caller must be actual unchanged committed content')
    return {'scope': {'root': entry['raw']['root'], 'realroot': entry['raw']['realroot']},
            'base': base, 'head': head, 'merge_base': merge_base, 'target': target, 'callers': callers,
            'layers': layers, 'roles': roles}


def _actual_reads(entry, references):
    events = [frame['payload'] for frame in entry['raw']['wire'] if frame['direction'] == 'response' and 'method' in frame['payload']]
    bodies = {pin['path']: read_ref(pin).decode('utf-8') for pin in references}
    for path, data in entry['content'].items():
        try:
            bodies[str(Path(entry['raw']['root']) / path)] = data.decode('utf-8')
        except UnicodeError:
            pass
    resources = []
    for pin in references:
        found = None
        for index, event in enumerate(events):
            item = event.get('params', {}).get('item', {})
            if (event.get('method') != 'item/completed' or item.get('type') != 'commandExecution' or
                    item.get('status') != 'completed' or type(item.get('exitCode')) is not int or item['exitCode'] != 0 or
                    item.get('outputTruncated', False) or type(item.get('command')) is not str):
                continue
            try:
                argv = decode_command(item['command'])
            except Hold:
                continue
            if not argv or argv[0] not in ('cat', '/bin/cat', '/usr/bin/cat'):
                continue
            args = argv[1:]
            if args and args[0] == '--':
                args = args[1:]
            paths = [str((Path(item.get('cwd', entry['raw']['root'])) / path).resolve()) if not Path(path).is_absolute() else path for path in args]
            if paths and pin['path'] in paths and all(path in bodies for path in paths) and item.get('aggregatedOutput') == ''.join(bodies[path] for path in paths):
                found = {'resource': pin, 'command': item['command'], 'event_index': index}
                break
        require(found is not None, 'actual complete artifact consumption missing')
        resources.append(found)
    return resources, events


def installed_review_reads(entry):
    admission = read_record(entry['plan']['admission'], 'recovery-admission')
    manifest = decode(read_ref(admission['composite_manifest']))
    references = []
    for relative_path in ('.agents/skills/ains-review/SKILL.md', '.agents/skills/ains-review/review-prompt.md'):
        expected = manifest['suite_files'][relative_path.replace('.agents/skills/', 'skills/', 1)]
        require(relative_path in entry['content'] and digest(entry['content'][relative_path]) == expected['sha256'] and
                entry['state'][relative_path]['mode'] == expected['mode'], 'actual installed F1 body/template manifest')
        references.append({'path': str(Path(entry['raw']['root']) / relative_path), 'sha256': expected['sha256']})
    resources, events = _actual_reads(entry, references)
    validate_resource_consumption(resources, events,
        captured_files={str(Path(entry['raw']['root']) / path): data for path, data in entry['content'].items()})
    return resources


def validate_packet_origins(packet, expected, author, contexts, captures):
    origins = packet['origins']
    require(type(origins) is dict, 'model handoff origins mapping')
    required = {'/scope', '/base', '/head', '/merge_base', '/spec', '/tasks', '/commit', '/index', '/worktree', '/untracked'}
    required |= {'/target/' + str(i) for i in range(len(expected['target']))}
    required |= {'/callers/' + str(i) for i in range(len(expected['callers']))}
    required |= {'/checks/' + str(i) for i in range(len(packet['checks']))}
    for layer in ('commit', 'index', 'worktree', 'untracked'):
        required |= {'/' + layer + '/' + path.replace('~', '~0').replace('/', '~1') for path in packet[layer]}
    require(set(origins) == required, 'complete exact semantic handoff origin coverage')
    literals = {'/base': expected['base'], '/head': expected['head'], '/merge_base': expected['merge_base'],
                '/spec': expected['roles']['spec'], '/tasks': expected['roles']['tasks']}
    literals.update({'/target/' + str(i): path for i, path in enumerate(expected['target'])})
    literals.update({'/callers/' + str(i): path for i, path in enumerate(expected['callers'])})
    for pointer, sources in origins.items():
        require(type(sources) is list and sources, 'missing actual model handoff origin')
        text = b'\n'.join(model_handoff_slice(source, contexts, captures, author['reference']) for source in sources)
        if pointer in literals:
            require(type(literals[pointer]) is str and literals[pointer].encode() in text, 'model handoff missing actual literal/path/OID')
        lower = text.lower()
        absent = any(word in lower for word in (b'absent', b'none', b'empty', b'clean', b'no ', b'null', b'/dev/null',
                                                'なし'.encode(), '不存在'.encode(), '削除'.encode()))
        if pointer == '/scope':
            require(expected['scope']['root'].encode() in text or expected['head'].encode() in text,
                    'model handoff must identify actual repository/commit scope')
        if pointer in ('/commit', '/index', '/worktree', '/untracked'):
            layer = pointer[1:]
            names = {'commit': (b'commit', 'コミット'.encode()), 'index': (b'index', b'staged', 'ステージ'.encode()),
                     'worktree': (b'worktree', b'working tree', b'unstaged', '作業ツリー'.encode()),
                     'untracked': (b'untracked', '未追跡'.encode())}[layer]
            require(any(name in lower for name in names), 'model handoff must identify actual comparison layer')
            if not packet[layer]:
                require(absent, 'empty comparison layer needs actual sourced absence statement')
            elif layer == 'commit':
                require(expected['merge_base'].encode() in text and expected['head'].encode() in text,
                        'committed comparison needs actual immutable endpoints')
        pieces = pointer.split('/')
        if len(pieces) == 3 and pieces[1] in ('commit', 'index', 'worktree', 'untracked'):
            path = pieces[2].replace('~1', '/').replace('~0', '~')
            require(path.encode() in text, 'endpoint origin must identify its actual path')
            for side, endpoint in packet[pieces[1]][path].items():
                if endpoint is None:
                    require(absent, 'absent endpoint needs actual sourced absence')
                    continue
                data = read_ref(endpoint['content'])
                mode = endpoint['mode'].encode()
                git_mode = b'100755' if endpoint['mode'] == '0o755' else b'100644'
                oid = endpoint['oid'].encode()
                typed = (mode in text or git_mode in text) and (oid in text or digest(data).encode() in text)
                if typed:
                    continue
                referenced = False
                for artifact_path, content in author['content'].items():
                    if not content or content != data or artifact_path.encode() not in text or author['state'][artifact_path]['mode'] != endpoint['mode']:
                        continue
                    if artifact_path in expected['roles']['packet']:
                        model_handoff_slice({'kind': 'artifact', 'capture': author['capture_ref'], 'path': artifact_path,
                            'start': 0, 'end': len(content), 'sha256': digest(content)}, contexts, captures, author['reference'])
                        referenced = True
                    elif artifact_path == path and side == 'after':
                        _actual_reads(author, [{'path': str(Path(author['raw']['root']) / path), 'sha256': digest(content)}])
                        referenced = True
                require(typed or referenced, 'model handoff omitted endpoint content/mode identity or explicit actual payload')
        if pointer.startswith('/checks/'):
            check = packet['checks'][int(pieces[2])]
            command = ' '.join(decode_command(check['command'])).encode()
            require(command in text and any(word in lower for word in (b'passed', b'ok', b'exit 0', '成功'.encode(), '合格'.encode())),
                    'model handoff omitted actual check command/result reference')
    return True


def validate_packet_checks(packet, author, contexts, captures):
    require(type(packet['checks']) is list and packet['checks'], 'actual current check artifact required')
    roles = read_record(author['plan']['contract'], 'contract')['roles']
    source_paths = set(roles['application']) | set(roles['tests'])
    require(source_paths, 'actual app/test check target required')
    for check in packet['checks']:
        fields(check, 'context wire_index item_sha256 command cwd source_capture result')
        key = canonical_hash(check['context'])
        require(key in contexts and contexts[key]['plan'] is not None, 'check must originate in actual accepted context')
        entry = contexts[key]
        require(check['source_capture'] == entry['capture_ref'] and command_matches(check['command'], 'python3 -m unittest discover -v') and
                check['cwd'] == entry['raw']['root'] == author['raw']['root'], 'actual configured D2 check/source capture')
        index = check['wire_index']
        require(type(index) is int and 0 <= index < len(entry['raw']['wire']), 'actual check wire index')
        frame = entry['raw']['wire'][index]
        event = frame['payload']; item = event.get('params', {}).get('item', {})
        require(frame['direction'] == 'response' and event.get('method') == 'item/completed' and
                canonical_hash(item) == check['item_sha256'] and item.get('type') == 'commandExecution' and
                item.get('command') == check['command'] and item.get('cwd') == check['cwd'] and
                item.get('status') == 'completed' and type(item.get('exitCode')) is int and item['exitCode'] == 0,
                'actual successful completed current check')
        require(check['result'].get('kind') == 'wire' and check['result'].get('context') == check['context'] and
                check['result'].get('wire_index') == index, 'check result must cite its actual command')
        validate_source_slice(check['result'], contexts, captures)
        require(all(path in entry['content'] and entry['content'][path] == author['content'][path] and
                    entry['state'][path]['mode'] == author['state'][path]['mode'] for path in source_paths), 'stale check target source bytes/modes')
        event_index = sum(1 for value in entry['raw']['wire'][:index] if value['direction'] == 'response' and 'method' in value['payload'])
        versions = {}
        for sample in entry['raw']['samples']:
            if sample.get('phase') == 'post-command-source-equivalence' and sample.get('event_index') == event_index:
                for version in sample['versions']:
                    versions[version['source']] = read_ref(version['capture'])
        require(source_paths <= set(versions) and all(versions[path] == author['content'][path] for path in source_paths),
                'check lacks actual post-command source equivalence for complete target')
    return True


def validate_f1_adjudication(adjudication, current, contexts, captures, prior_results):
    require(adjudication['packet'] is not None, 'actual natural handoff packet required')
    row = current['plan']['row_id']
    source_result = None
    if row == 'D2-tail/independent-review':
        require(prior_results, 'separate reviewer needs accepted P7 predecessor')
        source_result = read_record(prior_results[-1], 'independent-result')
        author = contexts[canonical_hash(source_result['context'])]
        require(author['plan']['row_id'] == 'D2-tail/unavailable-review', 'reviewer immediate predecessor must be P7')
        source_adjudication = read_record(source_result['adjudication'], 'adjudication')
        require(adjudication['packet'] == source_adjudication['packet'], 'reviewer must consume exact accepted P7 packet')
    else:
        author = current
        require(adjudication['projection'] is None, 'P7 may not claim independent reviewer projection')
    git_entries = [entry for entry in contexts.values() if entry['plan'] is not None and entry['plan']['row_id'] == 'D2-tail/Git-AC9']
    require(len(git_entries) == 1, 'actual accepted P6 Git journey required for review')
    git_entry = git_entries[0]
    profile = read_record(read_record(git_entry['plan']['contract'], 'contract')['git_profile'], 'git-profile')
    expected = derive_review_target(author, profile, git_entry)
    packet = read_record(adjudication['packet'], 'review-packet')
    require(packet['scope'] == expected['scope'] and packet['capture'] == author['capture_ref'] and
            all(packet[key] == expected[key] for key in ('base', 'head', 'merge_base', 'target', 'callers')), 'packet trusted actual scope/OIDs/target')
    for layer, changes in expected['layers'].items():
        require(type(packet[layer]) is dict and set(packet[layer]) == set(changes), 'packet omitted/extra actual layer path')
        for path, (before, after) in changes.items():
            endpoints = fields(packet[layer][path], 'before after')
            _endpoint_equal(endpoints['before'], before)
            _endpoint_equal(endpoints['after'], after, author['state'][path]['mode'] if path == expected['roles']['off'] and after is not None else None)
    for role in ('spec', 'tasks'):
        path = expected['roles'][role]
        require(path in author['content'] and read_ref(packet[role]) == author['content'][path] and
                author['content'][path].startswith(b'---\nstatus: approved\n---'), 'actual current approved feature documents')
    require(packet['resources'] == installed_review_reads(author), 'actual installed P7 resource consumption')
    validate_packet_origins(packet, expected, author, contexts, captures)
    validate_packet_checks(packet, author, contexts, captures)
    if row == 'D2-tail/independent-review':
        validate_review_projection(adjudication['projection'], prior_results[-1], source_result, packet,
                                   author, current, contexts, captures)
        installed_review_reads(current)
    else:
        lookup = read_record(read_record(current['raw']['common'], 'common')['lookup'], 'lookup')
        require(lookup['native_facts']['capability'] is not None, 'actual declared-route unavailable proof required')
    # Both the unavailable stop and final independent verdict must be actual
    # completed model final output; captured supervisor prose cannot replace it.
    verdict_obligation = 'completed_review' if row == 'D2-tail/independent-review' else 'independent_review_incomplete'
    observation = adjudication['observations'][verdict_obligation]
    require(any(source.get('kind') == 'wire' and source.get('context') == current['reference'] and
                validate_source_slice(source, contexts, captures)[1].get('item', {}).get('phase') == 'final_answer'
                for source in observation['sources']), 'actual completed model stop/verdict required')
    return True


def validate_review_projection(reference, source_result_ref, source_result, packet, author, current, contexts, captures, require_consumption=True):
    require(reference is not None, 'reviewer projection is mandatory')
    projection = read_record(reference, 'review-projection')
    source_adjudication = read_record(source_result['adjudication'], 'adjudication')
    require(projection['source_result'] == source_result_ref and projection['source_packet'] == source_adjudication['packet'] and
            projection['source_capture'] == author['capture_ref'] and
            projection['destination_root'] == current['raw']['root'] == current['raw']['realroot'] and
            decode(read_ref(projection['destination_state'])) == current['raw']['state_before'], 'actual accepted P7 delivery projection')
    scope = read_record(current['plan']['scope'], 'scope')
    material = read_record(scope['materialization'], 'materialization')
    require(scope['topology'] == 'reviewer-no-git' and material['destination_state'] == projection['destination_state'] and
            material['relocation'].get('independent_projection_review') == reference and
            not any(path == '.git' or path.startswith('.git/') for path in current['raw']['state_before']),
            'distinct no-Git reviewer materialization relation')
    required = {}
    source_roles = read_record(author['plan']['contract'], 'contract')['roles']
    off_path = source_roles['off']
    off_destinations = {off_path} | {'review-material/' + layer + '/after/' + off_path for layer in ('commit', 'index', 'worktree', 'untracked')} if off_path is not None else set()
    def add(destination, data, mode, role):
        relative(destination)
        require(mode in ('0o644', '0o755') or (mode == '0o600' and destination in off_destinations and role == 'endpoint'), 'projection content mode')
        if destination in required:
            require(required[destination]['data'] == data and required[destination]['mode'] == mode, 'projection destination collision')
            required[destination]['roles'].add(role)
        else:
            required[destination] = {'data': data, 'mode': mode, 'roles': {role}}
    for path in packet['target'] + packet['callers']:
        if path in author['content']:
            role = 'caller' if path in packet['callers'] else 'endpoint'
            add(path, author['content'][path], author['state'][path]['mode'], role)
    roles = read_record(author['plan']['contract'], 'contract')['roles']
    for role in ('spec', 'tasks'):
        path = roles[role]
        add(path, author['content'][path], author['state'][path]['mode'], role)
    for layer in ('commit', 'index', 'worktree', 'untracked'):
        for path, endpoints in packet[layer].items():
            for side in ('before', 'after'):
                endpoint = endpoints[side]
                if endpoint is not None:
                    add('review-material/' + layer + '/' + side + '/' + path,
                        read_ref(endpoint['content']), endpoint['mode'], 'endpoint')
    for sources in packet['origins'].values():
        for source in sources:
            _, origin = validate_source_slice(source, contexts, captures)
            model_handoff_slice(source, contexts, captures, author['reference'])
            if origin['kind'] == 'artifact':
                path = origin['path']
                add(path, author['content'][path], author['state'][path]['mode'], 'handoff')
            else:
                add('review-material/handoff-final-%05d.md' % origin['wire_index'],
                    origin['item']['text'].encode(), '0o644', 'handoff')
    for index, check in enumerate(packet['checks']):
        key = canonical_hash(check['context'])
        event = contexts[key]['raw']['wire'][check['wire_index']]['payload']
        output = event['params']['item']['aggregatedOutput'].encode()
        add('review-material/check-%03d.txt' % index, output, '0o644', 'check')
    files = projection['files']
    require(type(files) is list and [item.get('destination') for item in files] == sorted(required) and
            len(files) == len(required), 'complete exact finite projection content closure')
    delivered = []
    prestate = current['raw']['state_before']
    for item in files:
        fields(item, 'source destination mode role')
        path = item['destination']
        expected = required[path]
        require(item['mode'] == expected['mode'] and item['role'] in expected['roles'] and
                read_ref(item['source']) == expected['data'] and path in current['content'] and
                current['content'][path] == expected['data'] and prestate.get(path, {}).get('kind') == 'file' and
                prestate[path].get('mode') == expected['mode'], 'projection actual bytes/modes/membership')
        delivered.append({'path': str(Path(current['raw']['root']) / path), 'sha256': digest(expected['data'])})
    # Delivery does not prove use. Every actual payload file must be consumed
    # through a complete successful read, independently from resource loading.
    if require_consumption:
        _actual_reads(current, delivered)
    admission = read_record(current['plan']['admission'], 'recovery-admission')
    manifest = decode(read_ref(admission['composite_manifest']))
    allowed = set(required)
    for path, value in manifest['suite_files'].items():
        if path.startswith('skills/'):
            installed = path.replace('skills/', '.agents/skills/', 1)
            if installed in prestate:
                require(prestate[installed].get('sha256') == value['sha256'] and prestate[installed].get('mode') == value['mode'],
                        'reviewer exact installed resource mode/hash')
                allowed.add(installed)
    for pin in scope['instruction_sources'] + scope['install']:
        path = Path(pin['path'])
        if path.is_relative_to(Path(current['raw']['root'])):
            relative_path = str(path.relative_to(Path(current['raw']['root'])))
            require(relative_path in prestate and prestate[relative_path].get('sha256') == pin['sha256'], 'reviewer instruction/install pin')
            allowed.add(relative_path)
    actual_files = {path for path, value in prestate.items() if value.get('kind') == 'file'}
    require(actual_files == allowed, 'reviewer payload contains missing/extra author history or unrelated files')
    return True


def validate_review_packet(packet, *, expected_scope, expected_capture, target_paths,
                           implementation_paths, expected_resources, events):
    validate_record(packet, 'review-packet')
    require(packet['scope'] == expected_scope and packet['capture'] == expected_capture,
            'stale/unrelated packet capture')
    for key in ('base', 'head', 'merge_base'):
        require(type(packet[key]) is str and re.fullmatch('[0-9a-f]{40}', packet[key]), 'packet object identity')
    require(type(packet['target']) is list and packet['target'] == target_paths and
            len(set(target_paths)) == len(target_paths) and target_paths and
            set(implementation_paths) <= set(target_paths), 'packet target scope')
    require(type(packet['callers']) is list and not set(packet['callers']) & set(target_paths), 'packet callers scope')
    allowed = set(target_paths) | set(packet['callers'])
    identity = {}
    for layer in ('commit', 'index', 'worktree', 'untracked'):
        entries = packet[layer]
        require(type(entries) is dict and not set(entries) - allowed, 'unrelated packet layer target')
        identity[layer] = {}
        for path, endpoints in entries.items():
            relative(path)
            fields(endpoints, 'before after')
            require(endpoints['before'] is not None or endpoints['after'] is not None, 'empty layer endpoint')
            for endpoint in endpoints.values():
                if endpoint is not None:
                    read_ref(endpoint)
            identity[layer][path] = endpoints
    require(set(implementation_paths) <= set(packet['commit']) and implementation_paths,
            'committed implementation required; staged-only packet insufficient')
    for key in ('spec', 'tasks'):
        read_ref(packet[key])
    require(packet['resources'] == expected_resources, 'installed review resource drift')
    validate_resource_consumption(packet['resources'], events)
    target_identity = canonical_hash(identity)
    require(type(packet['checks']) is list and packet['checks'], 'current review checks required')
    for check in packet['checks']:
        fields(check, 'command cwd target_sha256 event_index')
        require(check['cwd'] == expected_scope['root'] and check['target_sha256'] == target_identity and
                type(check['event_index']) is int and 0 <= check['event_index'] < len(events), 'check target identity')
        item = events[check['event_index']].get('params', {}).get('item', {})
        require(events[check['event_index']].get('method') == 'item/completed' and
                item.get('type') == 'commandExecution' and item.get('command') == check['command'] and
                item.get('status') == 'completed' and type(item.get('exitCode')) is int and item['exitCode'] == 0,
                'actual successful current check required')
    return {'target_sha256': target_identity, 'business_PASS': False}


class _GitProof(dict):
    pass


GIT_ENV_PREFIX = ['/usr/bin/env', '-i', 'PATH=/usr/bin:/bin', 'GIT_CONFIG_NOSYSTEM=1',
                  'GIT_CONFIG_GLOBAL=/dev/null', 'GIT_CONFIG_SYSTEM=/dev/null', 'GIT_ATTR_NOSYSTEM=1',
                  'GIT_OPTIONAL_LOCKS=0', 'GIT_NO_REPLACE_OBJECTS=1']


def git_argv(profile, command):
    argv = decode_command(command)
    prefix = profile['command_prefix']
    require(prefix in ([], GIT_ENV_PREFIX), 'finite Git environment prefix')
    if prefix:
        require(argv[:len(prefix)] == prefix, 'Git isolated command environment missing')
        argv = argv[len(prefix):]
    return argv


GIT_OVERRIDES = ('maintenance.auto=false', 'gc.auto=0', 'core.hooksPath=/dev/null',
                 'commit.gpgSign=false', 'tag.gpgSign=false', 'rerere.enabled=false', 'core.fsmonitor=false')


def git_command_kind(profile, command):
    try:
        argv = git_argv(profile, command)
    except Hold:
        return None
    overrides = [value for option in profile['overrides'] for value in ('-c', option)]
    if argv and argv[0] == profile['invoked_path'] and argv[1:1 + len(overrides)] == overrides:
        remaining = argv[1 + len(overrides):]
        return remaining[0] if remaining else None
    return None


def validate_index(data, expected_tree):
    """Bounded full SHA1 v2 index; never let Git read/freshen a shared index."""
    require(type(data) is bytes and 32 <= len(data) <= 8 * 1024 * 1024 and
            data[:4] == b'DIRC' and hashlib.sha1(data[:-20]).digest() == data[-20:], 'index checksum/header')
    version, count = struct.unpack('>II', data[4:12])
    require(version == 2 and count <= 10000, 'unsupported/split/oversize index version')
    position = 12
    entries = {}
    def tree_oid(prefix=''):
        groups = {}
        for name, value in expected_tree.items():
            if not name.startswith(prefix):
                continue
            suffix = name[len(prefix):]
            first, separator, _ = suffix.partition('/')
            groups[first] = None if separator else value
        encoded = []
        for name, value in groups.items():
            if value is None:
                mode, object_id, sort_name = '40000', tree_oid(prefix + name + '/'), name + '/'
            else:
                mode, object_id, sort_name = value[0], value[1], name
            object_bytes = object_id if type(object_id) is bytes else bytes.fromhex(object_id)
            encoded.append((sort_name.encode(), mode.encode() + b' ' + name.encode() + b'\0' + object_bytes))
        body = b''.join(value for _, value in sorted(encoded))
        return hashlib.sha1(b'tree ' + str(len(body)).encode() + b'\0' + body).digest()
    for _ in range(count):
        start = position
        require(position + 62 <= len(data) - 20, 'truncated index entry')
        values = struct.unpack('>10I20sH', data[position:position + 62])
        mode, object_id, flags = values[6], values[10].hex(), values[11]
        position += 62
        zero = data.find(b'\0', position, len(data) - 20)
        require(zero >= 0 and not flags & 0xf000 and mode in (0o100644, 0o100755), 'index flags/stage/mode')
        name = data[position:zero].decode('utf-8')
        relative(name)
        require((flags & 0xfff) == min(len(name.encode()), 0xfff) and name not in entries, 'index name length/duplicate')
        position = zero + 1
        padding = (8 - (position - start) % 8) % 8
        require(data[position:position + padding] == b'\0' * padding, 'index entry padding')
        position += padding
        entries[name] = (format(mode, 'o'), object_id)
    while position < len(data) - 20:
        require(position + 8 <= len(data) - 20, 'index extension header')
        name = data[position:position + 4]
        size = struct.unpack('>I', data[position + 4:position + 8])[0]
        position += 8
        require(name == b'TREE' and position + size <= len(data) - 20, 'unsupported index extension/shared index')
        extension = data[position:position + size]
        # Cache-tree is an optional accelerator; bind its entire bytes through
        # index checksum, reject malformed records and noncanonical paths. The
        # authoritative staged mapping is independently checked below.
        offset = 0
        cache_paths = set()
        def cache_tree(prefix=''):
            nonlocal offset
            end = extension.find(b'\0', offset)
            require(end >= offset, 'cache-tree path')
            component = extension[offset:end].decode('utf-8')
            require('/' not in component and component not in ('.', '..'), 'cache-tree component')
            path = prefix + component
            require(path not in cache_paths and len(cache_paths) < 10000 and path.count('/') < 64,
                    'cache-tree duplicate/depth')
            cache_paths.add(path)
            offset = end + 1
            end = extension.find(b'\n', offset)
            require(end >= offset, 'cache-tree count')
            numbers = extension[offset:end].split(b' ')
            require(len(numbers) == 2 and re.fullmatch(b'-?[0-9]+', numbers[0]) and numbers[1].isdigit(), 'cache-tree counters')
            count, children = map(int, numbers)
            require(-1 <= count <= 10000 and children <= 10000, 'cache-tree bounds')
            offset = end + 1
            if count >= 0:
                require(offset + 20 <= len(extension), 'cache-tree object ID')
                require(extension[offset:offset + 20] == tree_oid(path + '/' if path else ''), 'cache-tree object/content relation')
                offset += 20
                expected_count = sum(name == path or name.startswith(path + '/') or path == '' for name in expected_tree)
                require(count == expected_count, 'cache-tree tracked count')
            for _ in range(children):
                cache_tree(path + '/' if path else '')
        cache_tree()
        require(offset == len(extension), 'cache-tree trailing bytes')
        position += size
    require(list(entries) == sorted(entries, key=lambda name: name.encode()) and
            position == len(data) - 20 and entries == {name: (value[0], value[1]) for name, value in expected_tree.items()},
            'index staged tree/content mismatch')
    return entries


def validate_git_rollback(profile, before, after, before_bytes, after_bytes, events, roles, cache_proof=None, off_samples=None):
    """Finite SHA1 loose-object commit -> revert -> restore, without invoking Git.

    Unsupported packs, alternate object stores, merge commits, commands or
    unattributed objects fail closed. Full before/after captures are trusted
    supervisor inputs, never model-provided hashes or printed source snippets.
    """
    validate_record(profile, 'git-profile')
    require(type(profile['verification_commands']) is list and len(profile['verification_commands']) <= 8, 'finite OFF verification commands')
    for command in profile['verification_commands']:
        argv = decode_command(command)
        require(len(argv) == 3 and argv[:2] == ['python3', '-c'], 'exact approved OFF Python verification')
    require(profile['command_prefix'] in ([], GIT_ENV_PREFIX), 'finite Git process environment')
    if profile['command_prefix']:
        require(profile['env_executable'] is not None and profile['env_executable']['path'] == '/usr/bin/env', 'exact Git env executable')
        read_ref(profile['env_executable'], executable=True)
    else:
        require(profile['env_executable'] is None, 'unused env executable pin')
    require(profile['object_format'] == 'sha1', 'unsupported Git object format')
    read_ref(profile['executable'], executable=True)
    require(profile['invoked_path'] in ('git', profile['executable']['path']), 'unreviewed Git invoked path')
    require(profile['version'] == '2.54.0', 'unreviewed Git version')
    require(type(profile['official_sources']) is list and profile['official_sources'], 'Git primary-source proof required')
    for reference in profile['official_sources']:
        read_ref(reference)
    read_ref(profile['environment_proof'])
    require(type(profile['overrides']) is list and all(type(value) is str for value in profile['overrides']) and
            profile['overrides'][:len(GIT_OVERRIDES)] == list(GIT_OVERRIDES), 'required Git process overrides')
    for value in profile['overrides'][len(GIT_OVERRIDES):]:
        require(value == 'core.untrackedCache=false' or re.fullmatch(r'user\.(name|email)=[^\n\r\0]+', value), 'unreviewed Git override key')
    branch, main = profile['branch'], profile['main_ref']
    require(type(branch) is str and re.fullmatch(r'refs/heads/[A-Za-z0-9][A-Za-z0-9/_-]*', branch) and
            type(main) is str and re.fullmatch(r'refs/heads/[A-Za-z0-9][A-Za-z0-9/_-]*', main) and
            branch != main and '..' not in branch and '..' not in main, 'finite feature/main refs')
    head = b'ref: ' + branch.encode() + b'\n'
    require(before_bytes.get('.git/HEAD') == after_bytes.get('.git/HEAD') == head, 'symbolic HEAD changed')
    branch_path, main_path = '.git/' + branch, '.git/' + main
    require(before_bytes.get(main_path) == after_bytes.get(main_path) and before_bytes.get(main_path), 'baseline MAIN changed')
    require(before_bytes.get('.git/config') == after_bytes.get('.git/config'), 'Git config changed')
    config = before_bytes.get('.git/config', b'')
    formats = re.findall(rb'(?im)^\s*objectformat\s*=([^\n]+)', config)
    require(all(value.strip().lower() == b'sha1' for value in formats) and
            not re.search(rb'(?i)alternates|worktreeconfig', config), 'unsupported Git config')
    for path in set(before) | set(after):
        require(not path.startswith('.git/objects/pack/') and path != '.git/objects/info/alternates', 'packed/alternate object store unsupported')
    app_tests = set(roles['application']) | set(roles['tests'])
    require(app_tests and profile['off_path'] not in app_tests and roles['off'] == profile['off_path'], 'finite app/test/OFF roles')
    relative(profile['off_path'])
    off = profile['off_path']
    expected_off = read_ref(profile['off_data'])
    require(profile['off_initial'] in ('preserve', 'create') and profile['off_mode'] in ('0o600', '0o644') and
            after.get(off, {}).get('kind') == 'file' and after[off].get('mode') == profile['off_mode'] and
            after_bytes.get(off) == expected_off, 'exact persistent OFF artifact')
    if profile['off_initial'] == 'preserve':
        require(off in before and before[off] == after[off] and before_bytes.get(off) == expected_off,
                'same preserved OFF artifact')
    else:
        require(off not in before and type(off_samples) is list and off_samples, 'P6 must actually initialize OFF during row')
        required_stages = []
        for index, event in enumerate(events):
            item = event.get('params', {}).get('item', {})
            if event.get('method') != 'item/completed' or item.get('type') != 'commandExecution':
                continue
            if any(command_matches(item.get('command'), command) for command in
                   ['python3 -m unittest discover -v'] + profile['verification_commands']):
                required_stages.append(index)
                continue
            if git_command_kind(profile, item.get('command')) in ('add', 'commit', 'revert'):
                required_stages.append(index)
        require([sample.get('event_index') for sample in off_samples] == required_stages and len(required_stages) >= 4,
                'complete actual Git/test OFF observation stages')
        for sample in off_samples:
            fields(sample, 'event_index command path capture identity mode relation')
            item = events[sample['event_index']]['params']['item']
            require(sample['command'] == item['command'] and sample['path'] == off and
                    sample['identity'] == after[off]['identity'] and sample['mode'] == profile['off_mode'] and
                    read_ref(sample['capture']) == expected_off and
                    sample['relation'] == 'actual post-command observation; no pre-execution timing claim',
                    'same actual OFF bytes/identity at each observed stage')
    for path in app_tests:
        relative(path)
        require({k: v for k, v in before.get(path, {}).items() if k != 'identity'} ==
                {k: v for k, v in after.get(path, {}).items() if k != 'identity'} and
                before_bytes.get(path) == after_bytes.get(path) and
                before_bytes.get(path) is not None, 'restored app/test worktree bytes/identity')
    # Worktree identities can legitimately change after Git checkout; the
    # contract instead requires exact bytes/kind/mode/path and no alias. Do not
    # use this as an exemption for any non-Git row.
    for path in app_tests:
        require(before[path].get('kind') == after[path].get('kind') == 'file', 'Git app/test kind')
    def oid(data):
        require(type(data) is bytes and re.fullmatch(b'[0-9a-f]{40}\n', data) is not None, 'loose ref object ID')
        return data.strip().decode()
    initial = oid(before_bytes.get(branch_path))
    final = oid(after_bytes.get(branch_path))
    transitions = None
    for logpath in ('.git/logs/HEAD', '.git/logs/' + branch):
        old, new = before_bytes.get(logpath, b''), after_bytes.get(logpath, b'')
        require(new.startswith(old), 'reflog prefix rewritten')
        lines = new[len(old):].splitlines()
        require(len(lines) == 3, 'exactly three feature/HEAD reflog transitions')
        pairs = []
        for line in lines:
            pair = line.split(b' ', 2)
            require(len(pair) == 3 and re.fullmatch(b'[0-9a-f]{40}', pair[0]) and
                    re.fullmatch(b'[0-9a-f]{40}', pair[1]) and b'\t' in pair[2], 'reflog entry')
            pairs.append((pair[0].decode(), pair[1].decode()))
        require(pairs[0][0] == initial and pairs[1][0] == pairs[0][1] and
                pairs[2][0] == pairs[1][1] and pairs[2][1] == final, 'reflog C/R/S chain')
        require(transitions is None or transitions == pairs, 'HEAD/feature reflog disagreement')
        transitions = pairs
    commit, revert, restore = (pair[1] for pair in transitions)
    parsed = {}

    def object_value(object_id):
        if object_id in parsed:
            return parsed[object_id]
        require(len(parsed) < 10000, 'Git object traversal bound')
        path = '.git/objects/' + object_id[:2] + '/' + object_id[2:]
        raw = after_bytes.get(path)
        require(type(raw) is bytes and len(raw) <= 8 * 1024 * 1024, 'missing/oversize loose object')
        decoder = zlib.decompressobj()
        expanded = decoder.decompress(raw, 16 * 1024 * 1024 + 1)
        require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail and
                len(expanded) <= 16 * 1024 * 1024 and hashlib.sha1(expanded).hexdigest() == object_id, 'loose object path/hash/compression')
        header, separator, body = expanded.partition(b'\0')
        kind, space, size = header.partition(b' ')
        require(separator and space and kind in (b'commit', b'tree', b'blob') and
                size.isdigit() and str(len(body)).encode() == size, 'Git object type/size')
        parsed[object_id] = kind, body
        return kind, body

    def commit_value(object_id, parent):
        kind, body = object_value(object_id)
        require(kind == b'commit', 'expected commit object')
        headers = body.split(b'\n\n', 1)[0].splitlines()
        trees = [line[5:].decode() for line in headers if line.startswith(b'tree ')]
        parents = [line[7:].decode() for line in headers if line.startswith(b'parent ')]
        require(len(trees) == 1 and re.fullmatch('[0-9a-f]{40}', trees[0]) and parents == [parent], 'commit tree/single-parent chain')
        return trees[0]

    def tree_value(object_id, prefix=''):
        require(prefix.count('/') < 64, 'Git tree depth bound')
        kind, body = object_value(object_id)
        require(kind == b'tree', 'expected tree object')
        result = {}
        names = set()
        while body:
            entry, zero, rest = body.partition(b'\0')
            require(zero and len(rest) >= 20, 'tree encoding')
            mode, space, name = entry.partition(b' ')
            require(space and name and b'/' not in name and name not in (b'.', b'..') and
                    mode in (b'40000', b'100644', b'100755'), 'tree mode/name')
            name = name.decode('utf-8')
            require(name not in names, 'duplicate Git tree entry')
            names.add(name)
            path = prefix + name
            child = rest[:20].hex()
            body = rest[20:]
            require(path not in result, 'duplicate tree path')
            if mode == b'40000':
                nested = tree_value(child, path + '/')
                require(not set(nested) & set(result), 'tree alias')
                result.update(nested)
            else:
                child_kind, content = object_value(child)
                require(child_kind == b'blob', 'tree blob kind')
                result[path] = (mode.decode(), child, content)
        return result

    initial_kind, initial_body = object_value(initial)
    require(initial_kind == b'commit', 'initial loose commit required')
    initial_tree = next((line[5:].decode() for line in initial_body.split(b'\n\n', 1)[0].splitlines() if line.startswith(b'tree ')), None)
    require(initial_tree is not None, 'initial tree missing')
    c_tree = commit_value(commit, initial)
    r_tree = commit_value(revert, commit)
    s_tree = commit_value(restore, revert)
    require(r_tree == initial_tree and s_tree == c_tree, 'revert/restore tree relation')
    baseline, changed = tree_value(initial_tree), tree_value(c_tree)
    validate_index(before_bytes.get('.git/index'), baseline)
    validate_index(after_bytes.get('.git/index'), changed)
    changes = {path for path in set(baseline) | set(changed) if baseline.get(path) != changed.get(path)}
    require(changes and changes <= app_tests, 'commit modifies unrelated/nonimplementation paths')
    for path in changes:
        require(path in changed and changed[path][2] == before_bytes[path], 'committed implementation/worktree relation')
    existing_objects = {path for path in before if re.fullmatch(r'\.git/objects/[0-9a-f]{2}/[0-9a-f]{38}', path)}
    final_objects = {path for path in after if re.fullmatch(r'\.git/objects/[0-9a-f]{2}/[0-9a-f]{38}', path)}
    require(existing_objects <= final_objects, 'existing Git object deleted')
    reachable_paths = {'.git/objects/' + value[:2] + '/' + value[2:] for value in parsed}
    require(final_objects - existing_objects == reachable_paths - existing_objects, 'unattributed new Git object')
    allowed = {branch_path, '.git/logs/HEAD', '.git/logs/' + branch, '.git/index', '.git/COMMIT_EDITMSG'}
    require(profile['auto_merge'] in ('absent', 'restore-tree'), 'AUTO_MERGE route must be explicit')
    if profile['auto_merge'] == 'restore-tree':
        require('.git/AUTO_MERGE' not in before and
                after_bytes.get('.git/AUTO_MERGE') == s_tree.encode() + b'\n' and
                after.get('.git/AUTO_MERGE', {}).get('mode') == '0o644', 'final AUTO_MERGE restore-tree relation')
        allowed.add('.git/AUTO_MERGE')
    else:
        require('.git/AUTO_MERGE' not in before and '.git/AUTO_MERGE' not in after, 'AUTO_MERGE final absence route')
    for path in set(before) | set(after):
        require(not (path.startswith('.git/') and path.endswith('.lock')) and path not in ('.git/MERGE_MSG', '.git/REVERT_HEAD', '.git/CHERRY_PICK_HEAD') and
                not path.startswith('.git/sequencer'), 'unfinished Git operation state')
    allowed |= final_objects - existing_objects
    for path in final_objects - existing_objects:
        allowed.add(str(Path(path).parent))
    cache_paths = set()
    if cache_proof is not None:
        require(type(cache_proof) is _CacheProof and cache_proof['before'] == canonical_hash(before) and
                cache_proof['after'] == canonical_hash(after), 'Git/derived proof endpoints')
        cache_paths = set(cache_proof['paths'])
    if profile['off_initial'] == 'create':
        allowed.add(off)
        for parent in Path(off).parents:
            path = str(parent)
            if path != '.' and path not in before:
                require(after.get(path, {}).get('kind') == 'directory' and after[path].get('mode') == '0o755', 'necessary OFF parent directory')
                allowed.add(path)
    _same_except(before, after, allowed | app_tests | cache_paths)
    for path in existing_objects:
        require(before[path] == after[path] and before_bytes[path] == after_bytes[path], 'existing object modified')
    for path in allowed:
        if path in after:
            require(after[path].get('kind') in ('file', 'directory') and after[path].get('link_text') is None,
                    'Git mutable alias/type')
    completed = []
    for event in events:
        item = event.get('params', {}).get('item', {})
        if event.get('method') != 'item/completed' or item.get('type') != 'commandExecution':
            continue
        command = item.get('command', '')
        raw_git = re.search(r'(?<![A-Za-z0-9_])(?:[^\s\"\']*/)?git(?:[\s\"\']|$)', command) is not None
        try:
            decoded = git_argv(profile, command)
        except Hold:
            require(not raw_git, 'unreviewed Git command wrapper/environment')
            decoded = []
        if raw_git:
            require(decoded and decoded[0] == profile['invoked_path'], 'unreviewed Git executable/command')
        if decoded and decoded[0] == profile['invoked_path']:
            require(item.get('status') == 'completed' and type(item.get('exitCode')) is int and
                    item['exitCode'] == 0 and item.get('cwd') == profile['command_cwd'], 'actual Git command failure/cwd')
            argv = decoded
            overrides = [value for option in profile['overrides'] for value in ('-c', option)]
            require(argv[1:1 + len(overrides)] == overrides, 'process-only Git safety overrides absent')
            completed.append(['git'] + argv[1 + len(overrides):])
    require(all(len(argv) > 1 and argv[1] in ('add', 'commit', 'revert', 'status', 'diff', 'show', 'log', 'rev-parse', 'ls-files')
                for argv in completed), 'ungranted extra Git operation')
    mutations = [argv for argv in completed if len(argv) > 1 and argv[1] in ('add', 'commit', 'revert')]
    if len(mutations) > 1 and mutations[1][1:3] == ['commit', '--quiet']:
        mutations[1] = ['git', 'commit'] + mutations[1][3:]
    require(len(mutations) == 4 and mutations[0][:3] == ['git', 'add', '--'] and
            set(mutations[0][3:]) == app_tests and mutations[1][:3] == ['git', 'commit', '-m'] and
            len(mutations[1]) == 4 and mutations[2] == ['git', 'revert', '--no-edit', commit] and
            mutations[3] == ['git', 'revert', '--no-edit', revert], 'actual authorized Git command sequence')
    proof = _GitProof({'commit': commit, 'revert': revert, 'restore': restore,
                       'before': canonical_hash(before), 'after': canonical_hash(after),
                       'profile': canonical_hash(profile), 'business_PASS': False})
    return proof


def validate_transition(plan, before, after, evidence, adjudicating=False,
                        contents_before=None, contents_after=None, git_proof=None,
                        capability_proof=None, cache_proof=None):
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
        expected_mode = before[path].get('mode') if path in before else ('0o755' if item['kind'] == 'directory' else '0o644')
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


def validate_tasks_progress(policy, path, before, after):
    fields(policy, 'path checkboxes memo_heading max_memo_bytes')
    require(policy['path'] == path and type(policy['checkboxes']) is list and
            all(type(index) is int and index >= 0 for index in policy['checkboxes']) and
            len(set(policy['checkboxes'])) == len(policy['checkboxes']) and
            type(policy['max_memo_bytes']) is int and 0 <= policy['max_memo_bytes'] <= 8192,
            'finite task progress policy')
    require(before.startswith(b'---\nstatus: approved\n---') and after.startswith(b'---\nstatus: approved\n---'),
            'task progress cannot change plan approval')
    old_lines, new_lines = before.splitlines(keepends=True), after.splitlines(keepends=True)
    heading = policy['memo_heading']
    limit = len(old_lines)
    if heading is not None:
        require(type(heading) is str and heading.startswith('## ') and '\n' not in heading, 'exact memo heading')
        matches = [i for i, line in enumerate(old_lines) if line.rstrip(b'\r\n') == heading.encode()]
        require(len(matches) == 1 and not any(line.startswith(b'## ') for line in old_lines[matches[0] + 1:]),
                'memo must be existing final section')
        limit = matches[0] + 1
        require(len(new_lines) >= limit and len(b''.join(new_lines[limit:])) <= policy['max_memo_bytes'], 'memo byte bound')
    else:
        require(len(new_lines) == len(old_lines), 'task progress may not add unrelated lines')
    require(len(new_lines) >= limit, 'task authoritative prefix removed')
    for index in range(limit):
        old, new = old_lines[index], new_lines[index]
        if index in policy['checkboxes']:
            require(re.match(rb'^\s*- \[ \]', old) is not None and
                    new in (old, old.replace(b'[ ]', b'[x]', 1)), 'allowed actual task checkbox only')
        else:
            require(old == new, 'task scope/Done/dependencies/grants/content changed')
    require(all(index < limit for index in policy['checkboxes']), 'checkbox outside authoritative task prefix')
    return True


def validate_prerequisites(plan, contract, scope, state):
    roles = fields(contract['roles'], 'spec tasks application tests callers progress packet review local_pr off')
    row = plan['row_id']
    required = ['spec'] + ([] if row == 'D2-tail/spec-approval' else ['tasks'])
    for role in required:
        path = roles[role]
        require(type(path) is str, 'actual specification/task path required')
        relative(path)
        if row == 'D2-tail/tasks-initial' and role == 'tasks':
            require(path not in state, 'new tasks must not already exist')
            continue
        require(path in state and state[path].get('kind') == 'file', 'required approved artifact absent')
        data, _ = file_bytes(Path(scope['root']) / path)
        require(digest(data) == state[path].get('sha256'), 'prerequisite artifact inventory drift')
        status = 'draft' if (row == 'D2-tail/spec-approval' or row == 'D2-tail/plan-approval' and role == 'tasks') else 'approved'
        require(data.startswith(('---\nstatus: ' + status + '\n---').encode()), 'actual approval prerequisite missing')
    if row == 'D2-tail/TDD-build':
        feasible = read_record(plan['feasibility'], 'feasibility')
        require(feasible['scope'] == plan['scope'] and feasible['limits'] == LIMITS and
                feasible['decision'] == 'SUFFICIENT_ACTUAL_TASKS_FOR_ONE_D2_USER' and
                feasible['tasks']['sha256'] == state[roles['tasks']]['sha256'], 'actual tasks/AC9 one-turn feasibility required')
        read_ref(feasible['tasks']); read_ref(feasible['AC9_concurrency']); read_ref(feasible['review'])
    else:
        require(plan['feasibility'] is None, 'feasibility record is P4-only')
    return True


def validate_graph(command_ref, expected_command_sha256):
    """Validate upstream DAG. An exact caller digest is necessary, never a label."""
    hash_value(expected_command_sha256)
    require(command_ref['sha256'] == expected_command_sha256, 'caller exact command binding')
    command = read_record(command_ref, 'command')
    release = read_record(command['release'], 'release')
    root_review_ref = release['root_review']
    root_review = read_record(root_review_ref, 'root-review')
    require(root_review['decision'] == 'RELEASE_EXACT_ONE_D2_CONTEXT', 'Root decision')
    common = read_record(root_review['common'], 'common')
    plan = read_record(root_review['row_plan'], 'row-plan')
    require(common['row_plan'] == root_review['row_plan'] and common['policy'] == root_review['policy'] and
            common['lookup'] == root_review['lookup'] and plan['admission'] == root_review['admission'], 'graph edge drift')
    require(release['common'] == root_review['common'] and release['release_id'] == root_review['release_id'] and
            command['row_plan'] == root_review['row_plan'] and command['source_set'] == common['source_set'] and
            command['native_binding'] == common['native_binding'] and command['output'] == plan['output'] and
            command['claim'] == plan['claim'], 'command/release exact edges')
    read_ref(command['operator'], executable=True)
    require(command['operator']['path'] == str(HERE / 'postclosure_recovery_operator.py'), 'operator substitution')
    source_set = validate_source_set(read_record(common['source_set'], 'source-set'))
    require(plan['source_set'] == common['source_set'], 'row source set drift')
    context_review = read_record(root_review['source_context_review'], 'source-context-review')
    impl_review = read_record(context_review['implementation_review'], 'implementation-review')
    require(context_review['common'] == root_review['common'] and context_review['decision'] == 'APPROVE_EXACT_CONTEXT' and
            context_review['findings'] == [] and impl_review['source_set'] == common['source_set'] and
            impl_review['findings'] == [] and impl_review['decision'] == 'APPROVE_EXACT_SOURCE', 'independent source/context review')
    admission = read_record(root_review['admission'], 'recovery-admission')
    require(admission['branch_id'] == plan['branch_id'] and admission['rows'] == ROWS and
            admission['source_review'] == context_review['implementation_review'], 'admission row/source relation')
    anchor_ref = admission['invariant_anchor']
    require(Path(anchor_ref['path']).is_relative_to(CONTROL_ROOT), 'new epoch anchor control scope')
    read_record(anchor_ref, 'invariant-anchor')
    prefix = validate_recovery_prefix(admission['recovery_prefix'])
    require(prefix['new_source_set'] == common['source_set'], 'recovery source binding')
    validate_funding(admission, prefix)
    require(type(command['history']) is list, 'successor history list')
    history = validate_history(prefix['prefix_sha256'], command['history'], plan['branch_id'], common['source_set'], admission['invariant_anchor'])
    require(not history['unknown'] and not history['blocked'] and common['history_sha256'] == history['history_sha256'], 'history blocked/drift')
    expected_row = list(ROWS)[len(command['history'])] if len(command['history']) < len(ROWS) else None
    require(plan['row_id'] == expected_row, 'row chronology')
    scope = read_record(plan['scope'], 'scope')
    require(plan['scope'] in admission['scopes'] and scope['root'] == str(absolute(scope['root'])) and
            str(Path(scope['root']).resolve(strict=True)) == scope['realroot'] and
            scope['topology'] in ('author-git', 'reviewer-no-git'), 'admitted exact scope')
    require((plan['row_id'] == 'D2-tail/independent-review') == (scope['topology'] == 'reviewer-no-git'), 'distinct author/reviewer topology')
    require((Path(scope['root']) / '.git').exists() == (scope['topology'] == 'author-git'), 'actual topology drift')
    choice = read_record(scope['process_choice'], 'process-choice')
    require(all(choice[k] == scope[k] for k in ('scope_id', 'root', 'realroot', 'topology')) and
            choice['decision'] == 'SELECT_EXACT_PROCESS_ONLY_SCOPE', 'process choice relation')
    read_ref(choice['executable'], executable=True)
    invoked = absolute(choice['invoked_path'])
    require(choice['invoked_path'] == '/opt/homebrew/bin/codex' and invoked.is_symlink() and
            os.readlink(invoked) == choice['invoked_link_text'] and
            oct(stat.S_IMODE(invoked.lstat().st_mode)) == choice['invoked_mode'] and
            str(invoked.resolve(strict=True)) == choice['executable']['path'], 'actual invoked executable symlink identity')
    policy = read_record(root_review['policy'], 'process-policy')
    contract = read_record(plan['contract'], 'contract')
    negative = plan['row_id'] == 'D2-tail/unavailable-review' and contract['capability_profile'] is not None
    require(policy['row_plan'] == root_review['row_plan'] and policy['scope'] == plan['scope'] and
            policy['session'] == session_for(scope['realroot'], negative) and
            policy['session_sha256'] == canonical_hash(policy['session']) and
            policy['argv'] == choice['argv'] == argv_for(choice['invoked_path'], scope['realroot'], negative) and
            policy['native_expectation'] == common['native_binding'], 'policy exact process scope')
    require(policy['official_sources'] == source_set['official_sources'], 'policy official-source drift')
    turn_overlay = validate_turn_permission(policy, plan, scope, root_review['row_plan'])
    validate_required_metadata(policy, scope)
    anchor_ref = admission['invariant_anchor']
    anchor = read_record(anchor_ref, 'invariant-anchor')
    require(anchor['product_manifest'] == admission['composite_manifest'] == common['product_manifest'] and
            common['product_manifest']['sha256'] == COMPOSITE_SHA, 'immutable exact adopted product baseline')
    metadata_required = [anchor_ref] + source_set['files'] + source_set['official_sources'] + [
        command_ref, command['release'], root_review_ref, root_review['common'],
        root_review['source_context_review'], context_review['implementation_review'],
        root_review['row_plan'], root_review['policy'], root_review['lookup'],
        root_review['admission'], plan['scope'], plan['input'], plan['predecessor'],
        plan['predecessor_review'], plan['contract'], common['native_binding'],
        admission['funding_selection'], admission['funding_adoption'],
        admission['recovery_prefix'], admission['composite_manifest'], admission['materialization'],
        scope['process_choice'], choice['executable']] + scope['instruction_sources'] + scope['install']
    # The policy cannot contain its own digest or downstream command/review
    # digests. Runtime protects the complete graph separately (below).
    for key in ('legacy_prefix', 'closed_history', 'old_source_set', 'new_source_set', 'planning_decision', 'funding_selection'):
        metadata_required.append(prefix[key])
    closed = decode(read_ref(prefix['closed_history']))
    for result_ref in closed['closed_results']:
        old_result = read_record(result_ref, 'independent-result')
        metadata_required.extend((result_ref, old_result['context']))
    graph_pins = {r['path']: r for r in metadata_required}
    if policy['turn_permission'] is not None:
        permission = read_record(policy['turn_permission'], 'turn-permission')
        for pin in [policy['turn_permission'], permission['managed_probe']] + permission['primary_sources']:
            read_ref(pin)
            graph_pins[pin['path']] = pin
    if plan['feasibility'] is not None:
        feasible = read_record(plan['feasibility'], 'feasibility')
        for pin in [plan['feasibility'], feasible['tasks'], feasible['AC9_concurrency'], feasible['review']]:
            read_ref(pin)
            graph_pins[pin['path']] = pin
    for profile_name, profile_kind, only_row in (
            ('git_profile', 'git-profile', 'D2-tail/Git-AC9'),
            ('capability_profile', 'capability-profile', 'D2-tail/unavailable-review')):
        reference = contract[profile_name]
        require((reference is not None) == (plan['row_id'] == only_row), 'required finite row profile')
        if reference is not None:
            profile = read_record(reference, profile_kind)
            graph_pins[reference['path']] = reference
            for pin in profile['official_sources']:
                read_ref(pin)
                graph_pins[pin['path']] = pin
            if profile_kind == 'git-profile':
                require(profile['command_prefix'] == GIT_ENV_PREFIX and profile['invoked_path'] == profile['executable']['path'] and
                        profile['off_initial'] == 'create' and profile['off_mode'] in ('0o600', '0o644'), 'actual P6 isolated environment and new OFF artifact')
                for pin in (profile['executable'], profile['environment_proof'], profile['off_data'], profile['env_executable']):
                    read_ref(pin, executable='size' in pin)
                    graph_pins[pin['path']] = pin
    if contract['cache_profile'] is not None:
        cache_profile = read_record(contract['cache_profile'], 'cache-profile')
        require(cache_profile['row_id'] == plan['row_id'], 'cache profile row binding')
        graph_pins[contract['cache_profile']['path']] = contract['cache_profile']
        for pin in cache_profile['official_sources'] + [cache_profile['command_interpreter_proof']]:
            read_ref(pin)
            graph_pins[pin['path']] = pin
        pin = cache_profile['interpreter']['executable']
        read_ref(pin, executable=True)
        graph_pins[pin['path']] = pin
    if contract['git_profile'] is not None:
        git_profile = read_record(contract['git_profile'], 'git-profile')
        require(contract['cache_profile'] is not None and cache_profile['extra_commands'] == git_profile['verification_commands'],
                'P6 exact Git/cache verification command relation')
    predecessor = read_predecessor(plan)
    decision = read_input_decision(plan)
    message_key = 'final_message' if not command['history'] else 'question'
    require(decision['predecessor'] == plan['predecessor'] and decision[message_key] == predecessor[message_key] and
            decision['reviewed_artifacts'] and type(decision['request']) is str and decision['request'].strip(), 'genuine predecessor decision relation')
    for reference in decision['reviewed_artifacts']:
        read_ref(reference)
    read_ref(predecessor[message_key])
    read_ref(plan['predecessor_review'])
    for key in ('state', message_key):
        graph_pins[predecessor[key]['path']] = predecessor[key]
    state = decode(read_ref(predecessor['state']))
    if contract['git_profile'] is not None:
        require(read_record(contract['git_profile'], 'git-profile')['off_path'] not in state, 'P6 OFF must be genuinely absent before initialization')
    require(common['predecessor_state_sha256'] == canonical_hash(state) and common['input_sha256'] == canonical_hash(decision), 'common input/state binding')
    lookup = read_record(root_review['lookup'], 'lookup')
    validate_lookup(lookup, root_review['policy'], common['source_set'], common['native_binding'])
    native = decode(read_ref(common['native_binding']))
    legacy = load_legacy()
    require(native.get('official_commit') == legacy.SEMANTIC_COMMIT and native.get('codex_version') == 'codex-cli 0.164.0' and
            native.get('executable_identity', {}).get('sha256') == choice['executable']['sha256'] ==
            'd8990e3ee7acfbc26f91265b12a1a83f0fee40d0e0f8f1f40a37d4ec21f499cf' and
            native['executable_identity'].get('symlink_target') == choice['executable']['path'] and
            type(native.get('forward_thread_expectation')) is dict and
            set(native['forward_thread_expectation']) == set(legacy.THREAD_FIELDS) and
            native['forward_thread_expectation']['cwd'] == scope['root'], 'official current executable/native13 binding')
    expected_native = native['forward_thread_expectation']
    require(expected_native['runtimeWorkspaceRoots'] == [scope['root']] and
            expected_native['sandbox'] == {'type': 'workspaceWrite', 'writableRoots': [], 'networkAccess': False,
                                           'excludeTmpdirEnvVar': False, 'excludeSlashTmp': False} and
            expected_native['approvalPolicy'] == 'never' and expected_native['activePermissionProfile'] is None,
            'finite initial native write scope/network/approval profile')
    require([pin['path'] for pin in scope['instruction_sources']] == expected_native['instructionSources'],
            'every actual instruction source must be pinned')
    for path_key, hash_key in (('proof_path', 'proof_sha256'), ('source_index_path', 'source_index_sha256')):
        pin = {'path': native[path_key], 'sha256': native[hash_key]}
        read_ref(pin)
        graph_pins[pin['path']] = pin
    require(common['native_binding'] == choice['native_binding'], 'native binding relation')
    require(common['product_manifest'] == admission['composite_manifest'], 'composite source relation')
    load_legacy().released_source(admission['composite_manifest']['path'])
    read_ref(admission['composite_manifest'])
    material = read_record(scope['materialization'], 'materialization')
    require((scope['topology'] == 'reviewer-no-git' or scope['materialization'] == admission['materialization']) and
            material['composite_manifest'] == admission['composite_manifest'] and
            material['topology'] == scope['topology'], 'materialization relation')
    current = inventory(scope['root'])
    require(current == state, 'actual predecessor inventory drift')
    require(contract['expected_before'] == canonical_hash(current) and contract['expected_after'] is None and
            contract['evidence'] == {}, 'contract predecessor/future evidence drift')
    validate_prerequisites(plan, contract, scope, current)
    if not command['history']:
        validate_recovery_bootstrap(plan, predecessor, decision, prefix, scope, state, contract)
    else:
        validate_successor_predecessor(predecessor, command['history'], scope, state, material, plan)
    for reference in scope['instruction_sources'] + scope['install']:
        read_ref(reference)
    require(plan['claim'] == str(claim_path(plan['branch_id'], plan['row_id'], CLAIM_ROOT)), 'stable source-owned lifetime row claim')
    require(Path(plan['output']).is_relative_to(CONTROL_ROOT) and not Path(plan['output']).exists(), 'recovery output scope/already exists')
    fixture_pins = {pin['path'] for pin in scope['instruction_sources'] + scope['install']}
    for path in graph_pins:
        require(path in fixture_pins or not Path(path).is_relative_to(Path(scope['realroot'])), 'Root controls must be outside writable fixture')
    controls = [command_ref, command['release'], root_review_ref, root_review['common'],
                root_review['source_context_review'], context_review['implementation_review'], common['source_set'],
                root_review['row_plan'], root_review['policy'], root_review['lookup'], root_review['admission'],
                plan['scope'], scope['process_choice'], plan['contract'], plan['input'], plan['predecessor'], plan['predecessor_review']]
    controls += [common['native_binding'], admission['funding_selection'], admission['funding_adoption'],
                 admission['recovery_prefix'], admission['invariant_anchor']]
    for pin in controls:
        require(Path(pin['path']).is_relative_to(CONTROL_ROOT), 'recovery controls outside current control root')
    return {'command_ref': command_ref, 'command': command, 'release': release,
            'root_review_ref': root_review_ref, 'root_review': root_review, 'common': common,
            'plan': plan, 'scope': scope, 'choice': choice, 'policy': policy,
            'state': state, 'contract': contract, 'decision': decision, 'graph_pins': graph_pins, 'controls': controls,
            'turn_overlay': turn_overlay, 'anchor': anchor_ref}
