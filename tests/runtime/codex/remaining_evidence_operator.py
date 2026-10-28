#!/usr/bin/env python3
"""Current component evidence; import and no-argument CLI are inert.

Only an exact externally supplied command digest reaches observe/run_stage.
Historical quality failures are never converted into execution authority or PASS.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
import remaining_evidence as contract
import postclosure_recovery as core
import cache_payload_replay as cache_payload
import remaining_evidence_p7_replay as packet_replay
from postclosure_recovery_operator import (RecordingRPC,
    record_failure, capture_review_target, _save_bytes)
from owned_transport import ProcessTransport, require_healthy_close, diagnostic_receipt
from postclosure_deadline import await_terminal


SECONDS = 180
CLOSE_RESERVE = 2


def save_record(path, value):
    """Keep finite hash-only environment receipts; redact everything else normally."""
    contract.validate_record(value)
    core.require(value['schema'] in ('remaining-observation-v1', 'remaining-baseline-v1'),
                 'only producer-owned observation receipts may use typed retention')
    identity = value['environment']
    contract.validate_current_environment(identity, identity)
    legacy = core.load_legacy()
    safe = legacy.finite_receipt(value)
    safe['environment'] = copy.deepcopy(identity)
    if value['schema'] == 'remaining-baseline-v1':
        environment = core.fields(value['invariant']['environment'], 'facts sha256')
        core.hash_value(environment['sha256'])
        facts = legacy.finite_receipt({'environment': environment['facts']})['environment']
        core.require(type(facts) is dict and set(facts) == {
            'selector_names', 'identity_sha256', 'default_home', 'default_codex_home',
            'selected_environment_file', 'legacy_selection'}, 'finite environment facts required')
        safe['invariant']['environment'] = dict(facts=facts, sha256=environment['sha256'])
    return _save_bytes(path, (json.dumps(safe, ensure_ascii=False, indent=2,
                                      allow_nan=False) + '\n').encode())


def check_grants(native, root):
    """An actual reconciled response must confine persistent writes to this root."""
    root = Path(root)
    snapshot = native['snapshot']
    core.require(snapshot['runtimeWorkspaceRoots'] == [str(root)], 'unexpected native workspace roots')
    sandbox = snapshot['sandbox']
    core.require(sandbox.get('type') == 'workspaceWrite' and sandbox.get('writableRoots') == []
                 and sandbox.get('networkAccess') is False
                 and snapshot.get('activePermissionProfile') is None,
                 'native persistent grants exceed reviewed root')
    controls = core.OLD_CONTROL_ROOT
    core.require(not controls.is_relative_to(root) and not root.is_relative_to(controls),
                 'native writable root exposes Root controls')


def same_invariant(actual, expected):
    # The original full environment hashes remain in their actual records.
    # Only the new campaign's declared environment comparator handles the nonce.
    core.require(set(actual) == set(expected), 'invariant shape drift')
    core.require({k: v for k, v in actual.items() if k != 'environment'} ==
                 {k: v for k, v in expected.items() if k != 'environment'} and
                 actual['environment']['facts'] == expected['environment']['facts'],
                 'current product/native/config/catalog/contributor drift')


def close_owned(transport, rpc, raw):
    result = transport.close()
    raw['close'] = result
    require_healthy_close(result)
    for frame in result.pop('tail_frames', []):
        core.require(rpc is not None, 'close frame without owned RPC')
        rpc.receive(raw=frame)
    core.require(result.get('reaped') is True and result.get('returncode') == 0 and
                 result.get('stderr_bytes') == 0 and
                 result.get('partial_stdout_bytes') == 0 and
                 not result.get('watchdog_fired') and result.get('watchdog_error') is None,
                 'owned process failed to close healthily')
    core.require(rpc is not None and not rpc.active_items and not rpc.command_items and not rpc.pending,
                 'owned process closed with pending lifecycle')
    return result


def baseline_configuration(baseline):
    calls = {frame['payload']['id'] for frame in baseline['wire']
             if frame['direction'] == 'request' and frame['payload'].get('method') == 'config/read'}
    replies = [frame['payload']['result'] for frame in baseline['wire']
               if frame['direction'] == 'response' and frame['payload'].get('id') in calls
               and 'result' in frame['payload']]
    core.require(replies, 'zero observation lacks actual configuration replies')
    return replies[-1]


class Session:
    """Current-only native/config/source sampling, never historical graph replay."""
    def __init__(self, graph, rpc, environment, helpers, raw):
        self.graph, self.rpc, self.environment = graph, rpc, environment
        self.helpers, self.raw = helpers, raw
        self.root = Path(graph['scope']['realroot'])
        self.legacy = core.load_legacy()
        self.installed = helpers['activation_r3'].inventory(self.root)
        self.identity = contract.environment_identity(environment)
        contract.validate_current_environment(self.identity, graph['expected_environment'])
        self.legacy.require_environment(self.legacy.environment_facts(environment), graph['native'])
        self.native = None
        self.candidate = None

    def metadata(self):
        return core.sample_metadata({**self.graph['policy']['metadata_paths'],
                                     **self.graph['graph_pins']})

    def check_environment(self):
        core.require(contract.environment_identity(dict(os.environ)) == self.identity,
                     'environment changed within owned context')
        core.require(contract.environment_identity(self.environment) == self.identity,
                     'child environment mapping changed')

    def bundle(self, phase):
        graph, root = self.graph, self.root
        self.check_environment()
        metadata_before = self.metadata()
        before = core.inventory(root)
        core.require(not any(self.helpers['activation_r3'].mdm_forced().values()), 'managed state outside premise')
        self.legacy.released_source(graph['manifest']['path'])
        start = len(self.rpc.wire)
        first = self.rpc.call('config/read', {'includeLayers': True, 'cwd': str(root)})
        catalog = self.rpc.call('skills/list', {'cwds': [str(root)], 'forceReload': True})
        second = self.rpc.call('config/read', {'includeLayers': True, 'cwd': str(root)})
        after = core.inventory(root)
        metadata_after = self.metadata()
        policy = dict(graph['policy'], metadata_paths={**graph['policy']['metadata_paths'], **graph['graph_pins']})
        def catalog_validator(value, configuration):
            return self.legacy.validate_catalog(value, self.installed,
                self.legacy.config_facts(configuration, self.helpers['activation_closure_probe'].structural), 'live')
        frame = core.validate_bundle(first, catalog, second, before, after, metadata_before,
                                    metadata_after, policy, graph['scope'], catalog_validator)
        core.require(self.helpers['activation_r3'].inventory(root) == self.installed and
                     not any(self.helpers['activation_r3'].mdm_forced().values()), 'installed/managed state drift')
        self.check_environment()
        if self.native is not None:
            candidate = core.invariant_projection(graph['scope'], graph['manifest'], second,
                                                  catalog, self.native, self.environment, metadata_after)
            if self.candidate is not None:
                core.require(candidate == self.candidate, 'current context invariant reset')
            self.candidate = candidate
            if graph['baseline'] is not None:
                same_invariant(candidate, graph['baseline']['invariant'])
            frame['invariant_sha256'] = core.canonical_hash(candidate)
        else:
            frame['invariant_sha256'] = None
        self.raw['samples'].append(dict(phase=phase, wire_start=start, wire_end=len(self.rpc.wire),
                                       before=before, after=after, metadata=metadata_after, frame=frame))
        return frame, second

    def start_thread(self, config):
        expected = self.graph['native']['forward_thread_expectation']
        request = dict(cwd=str(self.root), model=expected['model'], approvalPolicy='never',
                       sandbox='workspace-write', ephemeral=True)
        actual = self.rpc.call('thread/start', request)
        self.native = self.legacy.reconcile_thread(actual, request, expected, config['config'])
        core.require(self.native['thread_id'] == self.rpc.thread_id, 'native actual thread mismatch')
        check_grants(self.native, self.root)


class ProfileCapture:
    """Finite actual cache/OFF observations; proof objects come from frozen guards."""
    def __init__(self, graph, rpc, output, environment):
        self.graph, self.rpc, self.output, self.environment = graph, rpc, output, environment
        profile = graph['contract']
        self.cache = core.read_record(profile['cache_profile'], 'cache-profile') if profile['cache_profile'] else None
        self.git = core.read_record(profile['git_profile'], 'git-profile') if profile['git_profile'] else None
        self.capability = core.read_record(profile['capability_profile'], 'capability-profile') if profile['capability_profile'] else None
        self.versions, self.off_samples, self.samples = [], [], []
        self.root = Path(graph['scope']['root'])
        self.before_bytes = self.git_bytes(graph['state']) if self.git else {}

    def git_bytes(self, state):
        roles = self.graph['contract']['roles']
        paths = [name for name, value in state.items() if value.get('kind') == 'file' and name.startswith('.git/')]
        paths += roles['application'] + roles['tests'] + [roles['off']]
        return {name: (self.root / name).read_bytes() for name in paths
                if name is not None and (self.root / name).is_file()}

    def observe(self, event, index):
        item = event.get('params', {}).get('item', {})
        if event.get('method') != 'item/completed' or item.get('type') != 'commandExecution':
            return
        if self.cache and any(core.command_matches(item.get('command'), command)
                              for command in core.allowed_cache_commands(self.cache)):
            core.require(not self.rpc.command_items, 'overlapping cache command observation')
            captured = core.capture_cache_versions(self.cache, self.root, index)
            retained = []
            for number, version in enumerate(captured):
                reference = _save_bytes(self.output / ('cache-source-%05d-%03d.bin' % (index, number)), version['bytes'])
                retained.append({**{k: v for k, v in version.items() if k != 'bytes'}, 'capture': reference})
            self.versions.extend(captured)
            self.samples.append(dict(phase='post-command-source-equivalence', event_index=index, versions=retained))
        if self.git and (core.git_command_kind(self.git, item.get('command')) in ('add', 'commit', 'revert') or
                         any(core.command_matches(item.get('command'), command) for command in
                             ['python3 -m unittest discover -v'] + self.git['verification_commands'])):
            core.require(not self.rpc.command_items and item.get('status') == 'completed' and
                         type(item.get('exitCode')) is int and item['exitCode'] == 0 and
                         item.get('cwd') == str(self.root), 'successful local OFF observation required')
            path = self.git['off_path']
            data, info = core.file_bytes(self.root / path)
            observation = dict(event_index=index, command=item['command'], path=path,
                capture=_save_bytes(self.output / ('off-observed-%05d.bin' % index), data),
                identity=[info.st_dev, info.st_ino], mode=oct(info.st_mode & 0o777),
                relation='actual post-command observation; no pre-execution timing claim')
            self.off_samples.append(observation)
            self.samples.append(dict(phase='P6-off-observation', observation=observation))

    def capability_proof(self, configuration):
        return core.validate_capability(self.capability, configuration, supplied_dynamic_tools=[],
            authorized_methods=RecordingRPC.METHODS) if self.capability else None

    def validate_transition(self, after, before_artifacts, after_artifacts, events, capability):
        cache_proof = cache_payload.validate_derived_caches_replay(self.cache, self.graph['state'], after,
            self.versions, events, self.root, self.environment) if self.cache else None
        git_proof = core.validate_git_rollback(self.git, self.graph['state'], after,
            self.before_bytes, self.git_bytes(after), events, self.graph['contract']['roles'],
            cache_proof, self.off_samples) if self.git else None
        copy_proof = None
        roles = self.graph['contract']['roles']
        if self.graph['plan']['row_id'] == 'D2-tail/unavailable-review' and roles['off']:
            copies = [path for path in roles['packet']
                      if path.endswith('/payload/current/' + roles['off'])]
            if len(copies) == 1 and copies[0] in after and roles['off'] in after:
                captured = {path: (self.root / path).read_bytes() for path in (roles['off'], copies[0])}
                copy_proof = packet_replay.copied_off_proof(self.graph['plan'], self.graph['state'],
                                                          after, captured)
        return packet_replay.validate_transition(self.graph['plan'], self.graph['state'], after,
            self.graph['contract']['evidence'], contents_before=before_artifacts,
            contents_after=after_artifacts, cache_proof=cache_proof, git_proof=git_proof,
            capability_proof=capability, copy_proof=copy_proof)


def _artifacts(graph):
    root = Path(graph['scope']['root'])
    return {name: (root / name).read_bytes() for name in
            (graph['contract']['roles']['spec'], graph['contract']['roles']['tasks'])
            if name is not None and (root / name).is_file()}


def _retain_artifacts(raw, output, values, phase):
    captures = {name: _save_bytes(output / ('artifact-%s-%03d.bin' % (phase, index)), data)
                for index, (name, data) in enumerate(values.items())}
    raw['samples'].append(dict(phase='artifact-byte-captures-' + phase, captures=captures))


def _account(raw, rpc):
    if rpc is not None:
        raw.update(wire=rpc.wire, thread_id=rpc.thread_id, turn_id=rpc.turn_id)
    try:
        raw['accounting'] = core.validate_wire(raw['wire'], raw['thread_id'], raw['turn_id'])
    except BaseException as error:
        attempted = sum(frame['direction'] == 'request' and frame['payload'].get('method') == 'turn/start'
                        for frame in raw['wire'])
        raw['accounting'] = dict(actual=None, attempted=attempted, charged=attempted, status='UNKNOWN', accepted=0)
        record_failure(raw, error, 'wire-accounting')


def _execute(graph, command_ref, business, transport_factory, clock, monotonic_ns):
    deadline = clock() + SECONDS
    work_deadline = deadline - CLOSE_RESERVE
    output, root = Path(graph['output']), Path(graph['scope']['root'])
    environment = dict(os.environ)
    identity = contract.environment_identity(environment)
    contract.validate_current_environment(identity, graph['expected_environment'])
    before = core.inventory(root)
    core.require(before == graph['state'], 'current complete prestate differs from release')
    if business:
        core.validate_prerequisites(graph['plan'], graph['contract'], graph['scope'], before)
    output.mkdir(mode=0o700)
    raw = dict(schema='remaining-observation-v1', command=command_ref, campaign=graph['campaign'],
        baseline=graph['baseline_ref'], stage=graph['release']['stage'] if business else None,
        donor=graph['release']['donor'] if business else None, root=str(root), process_id=None,
        thread_id=None, turn_id=None, wire=[], samples=[], environment=identity,
        state_before=before, state_after=None, capture=None, input_delivery=None,
        close=None, failure=None, accounting=None, business_PASS=False)
    transport = rpc = session = profiles = None
    stage = 'prelaunch'
    artifacts_before = _artifacts(graph) if business else {}
    try:
        if business:
            stage = 'donor-claim'
            contract.acquire_donor_claim(graph)
            _retain_artifacts(raw, output, artifacts_before, 'before')
        transport = transport_factory(graph['policy']['argv'], root, environment, work_deadline)
        raw['process_id'] = transport.pid
        rpc = RecordingRPC(transport, work_deadline, clock=clock, monotonic_ns=monotonic_ns,
                           turn_overlay=graph['turn_overlay'])
        if business:
            profiles = ProfileCapture(graph, rpc, output, environment)
            rpc.on_event = profiles.observe
        stage = 'initialize'
        rpc.call('initialize', dict(clientInfo=dict(name='ains-remaining-evidence-v1', version='1')))
        rpc.send('initialized', notification=True)
        with core.bound_helpers(output / 'helper-output') as (_, (helpers, _)):
            session = Session(graph, rpc, environment, helpers, raw)
            stage = 'preflight'
            preflight, configuration = session.bundle(stage)
            if business:
                core.require(preflight['config'] == baseline_configuration(graph['baseline']),
                             'current config differs from actual zero observation')
            stage = 'thread-start'
            session.start_thread(configuration)
            first, _ = session.bundle('post-start-1')
            second, configuration = session.bundle('post-start-2')
            gate = core.Baselines(first, second)
            if business:
                stage = 'predispatch'
                immediate, configuration = session.bundle(stage)
                gate.check(immediate)
                core.require(core.inventory(root) == before, 'predispatch state mutation')
                capability = profiles.capability_proof(configuration)
                raw['input_delivery'] = dict(request_sha256=core.digest(graph['input'].encode()), USER=1)
                stage = 'turn-start'
                rpc.call('turn/start', dict(threadId=rpc.thread_id,
                    input=[dict(type='text', text=graph['input'])], **(graph['turn_overlay'] or {})))
                stage = 'turn-in-flight'
                await_terminal(rpc, work_deadline, clock)
                rpc.drain()
                core.require(core.load_legacy().healthy_terminal(rpc.events, 'live'), 'unhealthy terminal')
                stage = 'postterminal'
                final, _ = session.bundle(stage)
                core.require(final['config'] == immediate['config'] and
                             final['metadata_sha256'] == immediate['metadata_sha256'], 'terminal immutable drift')
                raw['state_after'] = core.inventory(root)
                artifacts_after = _artifacts(graph)
                _retain_artifacts(raw, output, artifacts_after, 'after')
                stage = 'transition'
                profiles.validate_transition(raw['state_after'], artifacts_before, artifacts_after,
                                             rpc.events, capability)
            rpc.drain()
    except BaseException as error:
        if transport is None:
            raw['close'] = diagnostic_receipt(getattr(error, 'cleanup_receipt', None))
        record_failure(raw, error, stage)
    finally:
        if transport is not None:
            try:
                close_owned(transport, rpc, raw)
            except BaseException as error:
                record_failure(raw, error, 'owned-close')
        try:
            after = core.inventory(root)
            core.require(raw['state_after'] is None or raw['state_after'] == after, 'shutdown state mutation')
            raw['state_after'] = after
            if not business:
                core.require(after == before, 'zero observation changed fixture')
            if session is not None:
                session.metadata()
                session.check_environment()
            if profiles is not None:
                raw['samples'].extend(profiles.samples)
            # The legacy capture utility needs its actual physical-root field;
            # this view shares the owned sample list, without changing its schema.
            capture_view = dict(raw, realroot=graph['scope']['realroot'])
            raw['capture'] = capture_review_target(
                dict(plan=graph['plan'] or {'scope': graph['scope_ref']}), capture_view, output)
        except BaseException as error:
            record_failure(raw, error, 'post-close-state-metadata-capture')
        _account(raw, rpc)
        if clock() > deadline:
            record_failure(raw, TimeoutError(), 'absolute-context-deadline')
        raw['samples'].append(dict(phase='elapsed', seconds=SECONDS - (deadline - clock())))
        contract.validate_record(raw, 'observation')
        save_record(output / 'observation.json', raw)
    if business or raw['failure'] is not None:
        return raw
    baseline = dict(schema='remaining-baseline-v1', command=command_ref,
        campaign=graph['campaign'], scope=graph['scope_ref'], source_set=graph['source_set'],
        manifest=graph['manifest'], state=raw['state_after'], environment=identity,
        invariant=session.candidate, native=session.native, wire=raw['wire'],
        close=raw['close'], failure=raw['failure'], accounting=raw['accounting'])
    # Bundle samples are retained by the referenced observation, not reconstructed.
    contract.validate_record(baseline, 'baseline')
    save_record(output / 'baseline.json', baseline)
    return baseline


def observe(command_ref, expected_sha256, *, transport_factory=ProcessTransport,
            clock=time.monotonic, monotonic_ns=time.monotonic_ns):
    graph = contract.validate_observation_command(command_ref, expected_sha256)
    return _execute(graph, command_ref, False, transport_factory, clock, monotonic_ns)


def run_stage(command_ref, expected_sha256, *, transport_factory=ProcessTransport,
              clock=time.monotonic, monotonic_ns=time.monotonic_ns):
    graph = contract.validate_release(command_ref, expected_sha256)
    return _execute(graph, command_ref, True, transport_factory, clock, monotonic_ns)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--observe', action='store_true')
    mode.add_argument('--run-stage', action='store_true')
    parser.add_argument('--command')
    parser.add_argument('--command-sha256')
    args = parser.parse_args(argv)
    if not args.observe and not args.run_stage:
        parser.print_help()
        return 0
    core.require(args.command and args.command_sha256, 'external exact command reference required')
    function = observe if args.observe else run_stage
    result = function(dict(path=args.command, sha256=args.command_sha256), args.command_sha256)
    failed = result['failure'] is not None
    print(json.dumps(dict(status='FAILED' if failed else 'RECORDED',
                          accounting=result['accounting'], business_PASS=False)))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
