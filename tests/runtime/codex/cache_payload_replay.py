"""Supplemental saved-evidence replay; never admits a runtime or an assessment.

The original source epoch and failed observations remain unchanged. The finite
inventory validator below is copied from postclosure_recovery, with only its
payload verifier substituted. Candidate bytecode is never decoded or executed.
"""
import importlib.util
import marshal
from pathlib import Path
import shutil
import struct

import postclosure_recovery as frozen
from postclosure_recovery import (Hold, PYTHON_ENVIRONMENT, _CacheProof,
    allowed_cache_commands, canonical_hash, command_matches, digest, fields,
    file_bytes, read_ref, relative, require, validate_record)


def validate_cache_replay(candidate, source, **profile):
    # Validate every original header, interpreter, source and path guard using
    # freshly compiled trusted-source bytes; then compare the original payload.
    require(type(candidate) is bytes and type(source) is bytes,
            'cache/source byte capture')
    require(16 <= len(candidate) <= 8 * 1024 * 1024 and len(source) <= 4 * 1024 * 1024,
            'cache/source capture size bound')
    code = compile(source, profile['source_path'], 'exec', flags=0,
                   dont_inherit=True, optimize=0)
    single_owned = marshal.dumps(code, marshal.version)
    loader_owner = [code]
    loader_owned = marshal.dumps(loader_owner[0], marshal.version)
    proof = frozen.validate_cache(candidate[:16] + single_owned, source, **profile)
    require(candidate[16:] in (single_owned, loader_owned),
            'cache full code/source/filename/content relation')
    return dict(proof, cache_sha256=digest(candidate))


def validate_derived_caches_replay(profile, before, after, versions, events, root, environment, captured_files=None):
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
                proof = validate_cache_replay(candidate, version['bytes'], source_path=str(root / version['source']),
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
