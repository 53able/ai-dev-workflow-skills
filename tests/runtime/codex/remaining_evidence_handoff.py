"""Pure captured-evidence bridges between author and independent reviewer.

No history admission, host fixture replay, process execution, or source rewiring.
"""
import os
from pathlib import Path

import postclosure_recovery as f

REVIEW = ('.agents/skills/ains-review/SKILL.md',
          '.agents/skills/ains-review/review-prompt.md')
P7, P8 = 'D2-tail/unavailable-review', 'D2-tail/independent-review'


def _core():
    import remaining_evidence
    return remaining_evidence


def _entry(reference, replay_proof=None):
    if replay_proof is not None:
        from remaining_evidence_replay import _ReplayedPredecessor
        f.require(type(replay_proof) is _ReplayedPredecessor and
                  replay_proof.entry['reference'] == reference,
                  'replay proof must bind this exact captured predecessor')
        return replay_proof.entry
    c = _core()
    raw = c.read_record(reference, 'observation')
    command = c.read_record(raw['command'], 'command')
    release = c.read_record(command['release'], 'stage-release')
    plan = f.read_record(release['plan'], 'row-plan')
    scope = f.read_record(plan['scope'], 'scope')
    f.require(raw['stage'] == release['stage'] == plan['row_id'] and
              raw['baseline'] == release['baseline'] and raw['campaign'] == release['campaign'] and
              raw['donor'] == release['donor'] == c.ROWS[raw['stage']] and
              reference['path'] == str(Path(command['output']) / 'observation.json') and
              command['output'] == plan['output'] and plan['branch_id'] == c.BRANCH_ID and
              plan['input'] == release['decision'] and
              raw['root'] == scope['root'] == scope['realroot'] and raw['failure'] is None and
              c._closed(raw['close']), 'closed actual remaining stage required')
    charge = f.validate_wire(raw['wire'], raw['thread_id'], raw['turn_id'])
    f.require(charge == raw['accounting'] == {'actual': 1, 'attempted': 1, 'charged': 1,
              'status': 'ACTUAL', 'accepted': 1}, 'actual single USER capture required')
    decision = c.read_record(release['decision'], 'decision')
    starts = [v['payload'] for v in raw['wire'] if v['direction'] == 'request' and
              v['payload'].get('method') == 'turn/start']
    f.require(len(starts) == 1 and starts[0].get('params', {}).get('input') ==
              [{'type': 'text', 'text': decision['input']}] and decision['stage'] == raw['stage'] and
              raw['input_delivery'] == {'request_sha256': f.digest(decision['input'].encode()), 'USER': 1},
              'actual released input required')
    view = dict(raw, realroot=scope['realroot'])
    capture, state, content = f.validate_review_capture(raw['capture'], view, plan)
    return dict(reference=reference, command_ref=raw['command'], release_ref=command['release'],
                raw=view, plan=plan, capture_ref=raw['capture'],
                capture=capture, state=state, content=content, release=release)


def _chain(predecessor):
    c = _core()
    contexts, captures, entries, seen = {}, {}, [], set()
    seeded = False
    historical_sources = None
    while predecessor is not None:
        key = f.canonical_hash(predecessor)
        f.require(key not in seen and len(entries) < 8, 'remaining predecessor cycle/bound')
        seen.add(key)
        predecessor_record = c.read_record(predecessor)
        if predecessor_record['schema'] == 'remaining-p7-replay-bridge-v1':
            from remaining_evidence_p7_replay import validate_p7_bridge
            f.require(not entries or (entries[-1]['raw']['stage'] == P8 and
                      entries[-1]['raw']['campaign'] == predecessor_record['campaign']),
                      'only the direct P8 edge may cross a P7 replay bridge')
            proof = validate_p7_bridge(predecessor)
            proof.entry['p7_replay_proof'] = proof
            for entry in proof.entries:
                context_key = f.canonical_hash(entry['reference'])
                capture_key = f.canonical_hash(entry['capture_ref'])
                f.require(context_key not in contexts and capture_key not in captures,
                          'duplicate replayed P7 chain context/capture')
                entries.append(entry)
                contexts[context_key] = entry
                captures[capture_key] = entry
            seeded = True
            break
        if predecessor_record['schema'] == 'remaining-replay-bridge-v1':
            from remaining_evidence_replay import validate_bridge
            f.require(entries and entries[-1]['raw']['stage'] == P7 and
                      entries[-1]['raw']['campaign'] == predecessor_record['campaign'] and
                      historical_sources is None, 'only the direct P7 edge may cross a replay bridge')
            proof = validate_bridge(predecessor)
            entry = _entry(predecessor_record['observation'], proof)
            entry['replay_bridge_ref'] = predecessor
            entry['replay_pins'] = proof.pins
            entries.append(entry)
            contexts[f.canonical_hash(entry['reference'])] = entry
            captures[f.canonical_hash(entry['capture_ref'])] = entry
            historical_sources = proof.historical_sources
            predecessor = entry['release']['predecessor']
            continue
        if predecessor_record['schema'] == 'remaining-recovery-seed-v1':
            f.require(entries and entries[-1]['raw']['stage'] == c.RECOVERY_STAGE,
                      'recovery seed can terminate only a healthy P5 chain')
            options = {} if historical_sources is None else dict(historical_sources=historical_sources)
            proof = c.validate_recovery_seed(predecessor, release=entries[-1]['release'], **options)
            entries[-1]['recovery_seed_pins'] = proof['pins']
            seeded = True
            break
        assessment = c.validate_record(predecessor_record, 'assessment')
        entry = _entry(assessment['observation'])
        f.require(assessment['integrity'] == 'PASS' and assessment['stage'] == entry['raw']['stage'] and
                  assessment['campaign'] == entry['raw']['campaign'] and
                  assessment['preserved_failures'] == c.FAILURES and assessment['goal_complete'] is False,
                  'unsafe predecessor assessment')
        if entries:
            f.require(entries[-1]['raw']['stage'] in assessment['admissible_for'] and
                      entries[-1]['raw']['campaign'] == assessment['campaign'] and
                      list(c.ROWS).index(entries[-1]['raw']['stage']) ==
                      list(c.ROWS).index(assessment['stage']) + 1, 'predecessor dependency/campaign')
        entry['assessment_ref'] = predecessor
        entry['assessment'] = assessment
        entries.append(entry)
        contexts[f.canonical_hash(entry['reference'])] = entry
        captures[f.canonical_hash(entry['capture_ref'])] = entry
        predecessor = entry['release']['predecessor']
    f.require(entries and (seeded or entries[-1]['raw']['stage'] == next(iter(c.ROWS))),
              'complete bounded remaining predecessor chain required')
    return entries, contexts, captures


def _captured_reads(entry, references):
    """Same complete cat semantics as frozen _actual_reads, without live paths."""
    root = Path(entry['raw']['root'])
    bodies = {str(root / path): data for path, data in entry['content'].items()}
    events = [v['payload'] for v in entry['raw']['wire'] if v['direction'] == 'response' and
              'method' in v['payload']]
    results = []
    for pin in references:
        f.ref_shape(pin)
        f.require(pin['path'] in bodies and f.digest(bodies[pin['path']]) == pin['sha256'],
                  'resource must bind actual captured bytes')
        found = None
        for index, event in enumerate(events):
            item = event.get('params', {}).get('item', {})
            if not (event.get('method') == 'item/completed' and item.get('type') == 'commandExecution' and
                    item.get('status') == 'completed' and type(item.get('exitCode')) is int and
                    item['exitCode'] == 0 and not item.get('outputTruncated', False)):
                continue
            try:
                argv = f.decode_command(item.get('command'))
            except (f.Hold, TypeError):
                continue
            if not argv or argv[0] not in ('cat', '/bin/cat', '/usr/bin/cat'):
                continue
            args = argv[1:]
            if args and args[0] == '--':
                args = args[1:]
            cwd = Path(item.get('cwd', str(root)))
            paths = [os.path.normpath(str(cwd / path)) for path in args]
            if pin['path'] not in paths or not all(path in bodies for path in paths):
                continue
            try:
                output = b''.join(bodies[path] for path in paths).decode('utf-8')
            except UnicodeError:
                continue
            if item.get('aggregatedOutput') == output:
                found = dict(resource=pin, command=item['command'], event_index=index)
                break
        f.require(found is not None, 'actual complete artifact consumption missing')
        results.append(found)
    return results


def _resources(entry, graph):
    manifest = f.decode(f.read_ref(graph['manifest']))
    refs = []
    for path in REVIEW:
        expected = manifest['suite_files'][path.replace('.agents/skills/', 'skills/', 1)]
        f.require(path in entry['content'] and f.digest(entry['content'][path]) == expected['sha256'] and
                  entry['state'][path]['mode'] == expected['mode'], 'captured source42 review resources')
        refs.append(dict(path=str(Path(entry['raw']['root']) / path), sha256=expected['sha256']))
    return _captured_reads(entry, refs)


def _packet(reference, author, entries, contexts, captures, graph):
    git = [entry for entry in entries if entry['raw']['stage'] == 'D2-tail/Git-AC9']
    f.require(len(git) == 1, 'unique actual P6 required')
    contract = f.read_record(git[0]['plan']['contract'], 'contract')
    profile = f.read_record(contract['git_profile'], 'git-profile')
    expected = f.derive_review_target(author, profile, git[0])
    packet = f.read_record(reference, 'review-packet')
    f.require(packet['scope'] == expected['scope'] and packet['capture'] == author['capture_ref'] and
              all(packet[key] == expected[key] for key in ('base', 'head', 'merge_base', 'target', 'callers')),
              'packet trusted actual scope/OIDs/target')
    for layer, changes in expected['layers'].items():
        f.require(type(packet[layer]) is dict and set(packet[layer]) == set(changes), 'exact actual layer paths')
        for path, (before, after) in changes.items():
            endpoints = f.fields(packet[layer][path], 'before after')
            f._endpoint_equal(endpoints['before'], before)
            f._endpoint_equal(endpoints['after'], after,
                author['state'][path]['mode'] if path == expected['roles']['off'] and after is not None else None)
    for role in ('spec', 'tasks'):
        path = expected['roles'][role]
        f.require(path in author['content'] and f.read_ref(packet[role]) == author['content'][path] and
                  author['content'][path].startswith(b'---\nstatus: approved\n---'), 'actual approved documents')
    f.require(packet['resources'] == _resources(author, graph), 'actual P7 resource consumption')
    _origins(packet, expected, author, contexts, captures)
    for index, check in enumerate(packet['checks']):
        context = contexts.get(f.canonical_hash(check['context']))
        if context is not None and context.get('old_checks_scope') == 'CAPTURED_P6_CONTEXT_ONLY':
            text = b'\n'.join(f.model_handoff_slice(source, contexts, captures, author['reference'])
                              for source in packet['origins']['/checks/' + str(index)])
            f.require(b'CAPTURED_P6_CONTEXT_ONLY' in text,
                      'model handoff must retain the historical P6 environment boundary')
    if any('recovery_seed_pins' in entry for entry in entries):
        for check in packet['checks']:
            key = f.canonical_hash(check['context'])
            f.require(key in contexts and contexts[key]['raw']['stage'] in
                      ('D2-tail/Git-AC9', P7), 'recovered packet requires healthy current P6/P7 checks')
    f.validate_packet_checks(packet, author, contexts, captures)
    return packet


def _proof(reference, record, required, entries, extra=()):
    pins = [reference, record['destination_state'], *extra]
    pins += [item['source'] for item in record.get('files', [])]
    if 'source' in record:
        pins.append(record['source'])
    if 'source_packet' in record:
        pins.append(record['source_packet'])
    for entry in entries:
        pins += [entry[key] for key in ('assessment_ref', 'reference', 'command_ref', 'release_ref', 'capture_ref')
                 if key in entry]
        pins += [entry['release'][key] for key in ('plan', 'decision', 'baseline') if 'release' in entry]
        if 'capture' in entry:
            pins += [entry['capture'][key] for key in ('scope', 'state_before', 'state_after')]
            pins += list(entry['capture']['files'].values())
        pins.append(entry['plan']['contract'])
        pins += list(entry.get('recovery_seed_pins', {}).values())
        pins += list(entry.get('replay_pins', {}).values())
        if 'p7_replay_proof' in entry:
            pins += list(entry['p7_replay_proof'].pins.values())
    return {'pins': {pin['path']: pin for pin in pins}, 'delivered': {
        path: {'sha256': f.digest(data), 'mode': mode} for path, (data, mode, _) in required.items()}}


def validate_projection(handoff_ref, predecessor_assessment_ref, graph):
    bridge = f.read_record(handoff_ref, 'review-projection')
    entries, contexts, captures = _chain(predecessor_assessment_ref)
    author = entries[0]
    replay = author.get('p7_replay_proof')
    if replay is None:
        campaign = author['raw']['campaign']
        admissible = author['assessment']['admissible_for']
    else:
        from remaining_evidence_p7_replay import _ReplayedP7
        f.require(type(replay) is _ReplayedP7 and replay.entry is author and
                  replay.bridge['observation'] == author['reference'] and
                  replay.bridge_ref == predecessor_assessment_ref,
                  'projection requires the exact typed saved P7 predecessor')
        campaign = replay.bridge['campaign']
        admissible = replay.bridge['admissible_for']
        f.require(bridge['source_packet'] == replay.bridge['packet'],
                  'projection must retain the exact replayed P7 packet')
    f.require(graph['stage'] == P8 and author['raw']['stage'] == P7 and
              campaign == graph['campaign'] and P8 in admissible and
              bridge['source_result'] == predecessor_assessment_ref and bridge['source_capture'] == author['capture_ref'],
              'exact P7 to P8 projection')
    packet = _packet(bridge['source_packet'], author, entries, contexts, captures, graph)
    root = graph['scope']['root']
    f.require(root == graph['scope']['realroot'] == bridge['destination_root'] and
              not Path(root).is_relative_to(Path(author['raw']['root'])) and
              not Path(author['raw']['root']).is_relative_to(Path(root)) and graph['scope']['topology'] == 'reviewer-no-git' and
              not Path(root).is_relative_to(_core().CONTINUATION) and
              not _core().CONTINUATION.is_relative_to(Path(root)) and
              f.decode(f.read_ref(bridge['destination_state'])) == graph['state'] and
              not any(path == '.git' or path.startswith('.git/') for path in graph['state']) and
              all(v.get('kind') in ('file', 'directory') and v.get('link_text') is None
                  for v in graph['state'].values()),
              'distinct protected no-Git reviewer baseline')
    required = {}
    def add(path, data, mode, role):
        f.relative(path)
        f.require(mode in ('0o644', '0o755') or mode == '0o600' and role == 'endpoint', 'delivery mode')
        if path in required:
            f.require(required[path][:2] == (data, mode), 'projection collision')
            required[path][2].add(role)
        else:
            required[path] = (data, mode, {role})
    for path in packet['target'] + packet['callers']:
        if path in author['content']:
            add(path, author['content'][path], author['state'][path]['mode'],
                'caller' if path in packet['callers'] else 'endpoint')
    roles = f.read_record(author['plan']['contract'], 'contract')['roles']
    for role in ('spec', 'tasks'):
        path = roles[role]
        add(path, author['content'][path], author['state'][path]['mode'], role)
    for layer in ('commit', 'index', 'worktree', 'untracked'):
        for path, sides in packet[layer].items():
            for side, endpoint in sides.items():
                if endpoint is not None:
                    add('review-material/' + layer + '/' + side + '/' + path,
                        f.read_ref(endpoint['content']), endpoint['mode'], 'endpoint')
    for sources in packet['origins'].values():
        for source in sources:
            _, origin = f.validate_source_slice(source, contexts, captures)
            f.model_handoff_slice(source, contexts, captures, author['reference'])
            if origin['kind'] == 'artifact':
                path = origin['path']
                add(path, author['content'][path], author['state'][path]['mode'], 'handoff')
            else:
                add('review-material/handoff-final-%05d.md' % origin['wire_index'],
                    origin['item']['text'].encode(), '0o644', 'handoff')
    for index, check in enumerate(packet['checks']):
        item = contexts[f.canonical_hash(check['context'])]['raw']['wire'][check['wire_index']]['payload']['params']['item']
        add('review-material/check-%03d.txt' % index, item['aggregatedOutput'].encode(), '0o644', 'check')
    files = bridge['files']
    f.require(type(files) is list and [item.get('destination') for item in files] == sorted(required),
              'exact finite delivered payload')
    for item in files:
        f.fields(item, 'source destination mode role')
        data, mode, roles = required[item['destination']]
        actual = graph['state'].get(item['destination'], {})
        f.require(f.read_ref(item['source']) == data and item['mode'] == mode and item['role'] in roles and
                  actual.get('kind') == 'file' and actual.get('sha256') == f.digest(data) and
                  actual.get('mode') == mode, 'delivered actual bytes/modes')
    allowed = set(required)
    manifest = f.decode(f.read_ref(graph['manifest']))
    for path, expected in manifest['suite_files'].items():
        if path.startswith('skills/'):
            installed = path.replace('skills/', '.agents/skills/', 1)
            actual = graph['state'].get(installed, {})
            f.require(actual.get('kind') == 'file' and all(actual.get(k) == expected[k]
                      for k in ('sha256', 'mode')), 'complete source42 install bytes/modes')
            allowed.add(installed)
    f.require(set(REVIEW) <= allowed, 'review body/template required')
    for pin in graph['scope']['instruction_sources'] + graph['scope']['install']:
        path = Path(pin['path'])
        if path.is_relative_to(Path(root)):
            relative = str(path.relative_to(root))
            f.require(graph['state'].get(relative, {}).get('sha256') == pin['sha256'], 'instruction/install identity')
            allowed.add(relative)
        else:
            f.read_ref(pin)  # Current global instruction/install controls, never historical host replay.
    f.require({p for p, v in graph['state'].items() if v.get('kind') == 'file'} == allowed,
              'extra author history/chat or missing reviewer payload')
    extra = [packet['spec'], packet['tasks']]
    for layer in ('commit', 'index', 'worktree', 'untracked'):
        extra += [endpoint['content'] for sides in packet[layer].values() for endpoint in sides.values()
                  if endpoint is not None]
    extra += [pin for pin in graph['scope']['instruction_sources'] + graph['scope']['install']
              if not Path(pin['path']).is_relative_to(Path(root))]
    return _proof(handoff_ref, bridge, required, entries, extra)


def validate_return(handoff_ref, predecessor_assessment_ref, graph):
    bridge = f.read_record(handoff_ref, 'review-return')
    entries, _, _ = _chain(predecessor_assessment_ref)
    f.require(len(entries) >= 2, 'reviewer and author required')
    reviewer, author = entries[:2]
    f.require(graph['stage'] == 'D2-tail/local-ship' and reviewer['raw']['stage'] == P8 and
              reviewer['raw']['campaign'] == graph['campaign'] and
              graph['stage'] in reviewer['assessment']['admissible_for'] and
              author['raw']['stage'] == P7 and bridge['source_result'] == predecessor_assessment_ref and
              bridge['source_capture'] == reviewer['capture_ref'] and bridge['destination_root'] ==
              graph['scope']['root'] == graph['scope']['realroot'] == author['raw']['root'] and
              f.decode(f.read_ref(bridge['destination_state'])) == graph['state'], 'actual reviewer return relation')
    path = bridge['report']; f.relative(path)
    f.require(path == graph['contract']['roles']['review'] and path not in author['state'], 'new exact report path')
    data = f.read_ref(bridge['source'])
    final = [frame['payload'].get('params', {}).get('item', {}) for frame in reviewer['raw']['wire']
             if frame['direction'] == 'response' and frame['payload'].get('method') == 'item/completed']
    review_path = f.read_record(reviewer['plan']['contract'], 'contract')['roles']['review']
    texts = [item.get('text', '').encode() for item in final if item.get('type') == 'agentMessage' and
             item.get('phase') == 'final_answer']
    file_origin = review_path is not None and any(review_path.encode() in text for text in texts)
    file_origin |= review_path is not None and any(item.get('type') == 'fileChange' and
        item.get('status') == 'completed' and any(change.get('path') in
        (review_path, str(Path(reviewer['raw']['root']) / review_path)) for change in item.get('changes', [])
        if type(change) is dict) for item in final)
    f.require(data and (data in texts or (file_origin and reviewer['content'].get(review_path) == data and
              reviewer['raw']['state_before'].get(review_path) != reviewer['state'].get(review_path))),
              'returned bytes require actual completed model report')
    state = graph['state']
    f.require(state.get(path, {}).get('kind') == 'file' and state[path].get('mode') == '0o644' and
              state[path].get('sha256') == f.digest(data), 'returned report bytes/mode')
    allowed = {path}
    for parent in Path(path).parents:
        name = str(parent)
        if name != '.' and name not in author['state']:
            f.require(state.get(name, {}).get('kind') == 'directory' and state[name].get('mode') == '0o755',
                      'necessary report parent')
            allowed.add(name)
    f._same_except(author['state'], state, allowed)
    return _proof(handoff_ref, bridge, {path: (data, '0o644', {'review'})}, entries)


def validate_review_consumption(assessment_or_observation, graph):
    c = _core()
    value = assessment_or_observation
    if type(value) is dict and 'schema' not in value:
        value = c.read_record(value)
    if value['schema'] == 'remaining-assessment-v1':
        reference = value['observation']
    else:
        f.require(value['schema'] == 'remaining-observation-v1', 'typed review observation required')
        reference = c.ref(Path(graph['output']) / 'observation.json')
        f.require(c.read_record(reference, 'observation') == value, 'actual observation reference')
    entry = _entry(reference)
    f.require(entry['raw']['stage'] == graph['stage'] and entry['plan'] == graph['plan'], 'current review stage relation')
    _resources(entry, graph)
    if graph['stage'] == P8:
        release = entry['release']
        proof = validate_projection(release['handoff'], release['predecessor'], graph)
        refs = [dict(path=str(Path(entry['raw']['root']) / path), sha256=value['sha256'])
                for path, value in proof['delivered'].items()]
        _captured_reads(entry, refs)
        return proof
    f.require(graph['stage'] == P7, 'review consumption only P7/P8')
    return {'pins': {}, 'delivered': {}}


def _origins(packet, expected, author, contexts, captures):
    origins = packet['origins']
    f.require(type(origins) is dict, 'model handoff origins mapping')
    required = {'/scope', '/base', '/head', '/merge_base', '/spec', '/tasks', '/commit', '/index', '/worktree', '/untracked'}
    required |= {'/target/' + str(i) for i in range(len(expected['target']))}
    required |= {'/callers/' + str(i) for i in range(len(expected['callers']))}
    required |= {'/checks/' + str(i) for i in range(len(packet['checks']))}
    for layer in ('commit', 'index', 'worktree', 'untracked'):
        required |= {'/' + layer + '/' + path.replace('~', '~0').replace('/', '~1') for path in packet[layer]}
    f.require(set(origins) == required, 'complete exact semantic handoff origin coverage')
    literals = {'/base': expected['base'], '/head': expected['head'], '/merge_base': expected['merge_base'],
                '/spec': expected['roles']['spec'], '/tasks': expected['roles']['tasks']}
    literals.update({'/target/' + str(i): path for i, path in enumerate(expected['target'])})
    literals.update({'/callers/' + str(i): path for i, path in enumerate(expected['callers'])})
    for pointer, sources in origins.items():
        f.require(type(sources) is list and sources, 'missing actual model handoff origin')
        text = b'\n'.join(f.model_handoff_slice(source, contexts, captures, author['reference']) for source in sources)
        if pointer in literals:
            f.require(type(literals[pointer]) is str and literals[pointer].encode() in text, 'model handoff missing actual literal/path/OID')
        lower = text.lower()
        absent = any(word in lower for word in (b'absent', b'none', b'empty', b'clean', b'no ', b'null', b'/dev/null',
                                                'なし'.encode(), '不存在'.encode(), '削除'.encode()))
        if pointer == '/scope':
            f.require(expected['scope']['root'].encode() in text or expected['head'].encode() in text,
                    'model handoff must identify actual repository/commit scope')
        if pointer in ('/commit', '/index', '/worktree', '/untracked'):
            layer = pointer[1:]
            names = {'commit': (b'commit', 'コミット'.encode()), 'index': (b'index', b'staged', 'ステージ'.encode()),
                     'worktree': (b'worktree', b'working tree', b'unstaged', '作業ツリー'.encode()),
                     'untracked': (b'untracked', '未追跡'.encode())}[layer]
            f.require(any(name in lower for name in names), 'model handoff must identify actual comparison layer')
            if not packet[layer]:
                f.require(absent, 'empty comparison layer needs actual sourced absence statement')
            elif layer == 'commit':
                f.require(expected['merge_base'].encode() in text and expected['head'].encode() in text,
                        'committed comparison needs actual immutable endpoints')
        pieces = pointer.split('/')
        if len(pieces) == 3 and pieces[1] in ('commit', 'index', 'worktree', 'untracked'):
            path = pieces[2].replace('~1', '/').replace('~0', '~')
            f.require(path.encode() in text, 'endpoint origin must identify its actual path')
            for side, endpoint in packet[pieces[1]][path].items():
                if endpoint is None:
                    f.require(absent, 'absent endpoint needs actual sourced absence')
                    continue
                data = f.read_ref(endpoint['content'])
                mode = endpoint['mode'].encode()
                git_mode = b'100755' if endpoint['mode'] == '0o755' else b'100644'
                oid = endpoint['oid'].encode()
                typed = (mode in text or git_mode in text) and (oid in text or f.digest(data).encode() in text)
                if typed:
                    continue
                referenced = False
                for artifact_path, content in author['content'].items():
                    if not content or content != data or artifact_path.encode() not in text or author['state'][artifact_path]['mode'] != endpoint['mode']:
                        continue
                    if artifact_path in expected['roles']['packet']:
                        f.model_handoff_slice({'kind': 'artifact', 'capture': author['capture_ref'], 'path': artifact_path,
                            'start': 0, 'end': len(content), 'sha256': f.digest(content)}, contexts, captures, author['reference'])
                        referenced = True
                    elif artifact_path == path and side == 'after':
                        _captured_reads(author, [{'path': str(Path(author['raw']['root']) / path), 'sha256': f.digest(content)}])
                        referenced = True
                f.require(typed or referenced, 'model handoff omitted endpoint content/mode identity or explicit actual payload')
        if pointer.startswith('/checks/'):
            check = packet['checks'][int(pieces[2])]
            command = ' '.join(f.decode_command(check['command'])).encode()
            f.require(command in text and any(word in lower for word in (b'passed', b'ok', b'exit 0', '成功'.encode(), '合格'.encode())),
                    'model handoff omitted actual check command/result reference')
    return True

