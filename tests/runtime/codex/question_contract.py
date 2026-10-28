"""Finite N7-C source contract. Structural validation never grants runtime authority.

No archived producers or mutable postclosure helpers are imported. All supplied
receipts are evidence to be independently authenticated, not caller attestations.
"""
import hashlib
import json
import math
import posixpath


class Hold(ValueError):
    """Stop UNVERIFIED; reservations and observed attempts are never refunded."""


CONTEXTS = ('default', 'copy')
SECONDS = 180
CONTINUATION = '.omx/continuations/resume-20261027-j56k2v96'
DONORS = {
    'N7-C/default/first': 'R7/tasks/5',
    'N7-C/default/answer': 'R7/tasks/6',
    'N7-C/copy/first': 'R7/AC9-handoff/1',
    'N7-C/copy/answer': 'R7/AC9-handoff/2',
}
# These are separate evidence boundaries, never interchangeable labels.
DEPENDENCIES = {
    'source': (), 'review': ('source',), 'funding': (),
    'materialization': ('source',), 'process': ('source', 'materialization'),
    'profile': ('source', 'process'),
    'decision': ('review', 'funding', 'materialization', 'process', 'profile'),
}
MAX_RECORD = 1048576


def require(ok, reason):
    if not ok:
        raise Hold(reason)


def closed(value, fields, label):
    require(type(value) is dict and set(value) == set(fields), label + ' fields')
    return value


def canonical(value):
    try:
        data = json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise Hold('invalid JSON record') from exc
    require(len(data) <= MAX_RECORD, 'record size limit')
    return data


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(value):
    require(type(value) is str and len(value) == 64 and
            all(c in '0123456789abcdef' for c in value), 'invalid sha256')
    return value


def path(value):
    require(type(value) is str and value.startswith('/') and not value.startswith('//') and
            value == posixpath.normpath(value) and 1 < len(value) <= 4096 and
            all(ord(c) >= 32 and ord(c) != 127 for c in value), 'invalid absolute path')
    return value


def beneath(value, root):
    return value == root or value.startswith(root + '/')


def ref(value):
    closed(value, ('path', 'sha256'), 'reference')
    path(value['path']); sha(value['sha256'])
    return value


def loads(raw):
    require(type(raw) is bytes and len(raw) <= MAX_RECORD, 'record size/type')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate field')
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(Hold('nonfinite JSON')))
        canonical(value)
        return value
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise Hold('invalid JSON: ' + type(exc).__name__) from exc


def equal(actual, expected, label):
    require(canonical(actual) == canonical(expected), label + ' mismatch')


def typed_id(value):
    require(type(value) in (int, str) and (type(value) is int or 0 < len(value) <= 256),
            'invalid native ID')
    return type(value).__name__, value


class Deadline:
    """Created before any startup; equality expires, including cleanup."""
    def __init__(self, clock):
        self.clock = clock
        self.started = self.last = self._finite(clock())
        self.end = self.started + SECONDS

    @staticmethod
    def _finite(value):
        require(type(value) in (int, float) and math.isfinite(value), 'invalid clock')
        return value

    def check(self):
        now = self._finite(self.clock())
        require(now >= self.last, 'clock moved backwards')
        self.last = now
        require(now < self.end, 'context deadline reached')
        return now


def validate_header(command, command_sha256, root):
    """Reject foreign references before any DAG file is opened."""
    sha(command_sha256)
    require(digest(command) == command_sha256, 'external command digest mismatch')
    closed(command, ('kind', 'continuation', 'control_root', 'output_root', 'contexts',
                     'donors', 'history', 'records', 'limits', 'business_PASS'), 'command')
    path(root)
    require(command['kind'] == 'N7-C-launch-v1' and command['business_PASS'] is False,
            'not a raw N7-C command')
    equal(command['contexts'], list(CONTEXTS), 'two fixed contexts')
    equal(command['donors'], DONORS, 'fixed donor map')
    equal(command['limits'], {'contexts': 2, 'inputs_per_context': 2, 'seconds': 180}, 'limits')
    expected_c = root + '/' + CONTINUATION
    require(command['continuation'] == expected_c, 'wrong exact continuation')
    control, output = path(command['control_root']), path(command['output_root'])
    require(beneath(control, root + '/.omx') and control != root + '/.omx' and
            beneath(output, expected_c) and output != expected_c and
            not beneath(control, expected_c), 'control/output scope')
    require(not any(beneath(root, tmp) for tmp in ('/tmp', '/private/tmp', '/var/tmp', '/private/var/tmp')),
            'unprotected temporary Root')
    closed(command['history'], ('complete_history', 'aliases', 'donors'), 'history')
    history = command['history']
    require(history['complete_history'] is True and type(history['aliases']) is list,
            'missing complete history')
    require(all(type(x) is str and x for x in history['aliases']) and
            len(history['aliases']) == len(set(history['aliases'])), 'invalid history aliases')
    equal(history['donors'], {v: 'unused' for v in DONORS.values()}, 'spent/unknown donor')
    closed(command['records'], DEPENDENCIES, 'DAG refs')
    seen = set()
    for kind, deps in DEPENDENCIES.items():
        reference = ref(command['records'][kind])
        require(beneath(reference['path'], control) and reference['path'] not in seen,
                'foreign/aliased record')
        seen.add(reference['path'])


def validate_command(command, command_sha256, root, records):
    """Validate a closed acyclic DAG of already-read immutable record bytes.

    Does not open files, resolve aliases or authenticate Root. A live adapter
    must additionally bind exact file identities, ownership and protected grants.
    """
    validate_header(command, command_sha256, root)
    require(type(records) is dict and set(records) == set(DEPENDENCIES), 'missing DAG records')
    for kind, deps in DEPENDENCIES.items():
        reference = command['records'][kind]
        raw = records[kind]
        require(type(raw) is bytes and hashlib.sha256(raw).hexdigest() == reference['sha256'],
                'DAG record hash mismatch')
        record = loads(raw)
        closed(record, ('kind', 'dependencies', 'payload'), kind)
        require(record['kind'] == 'N7-C-' + kind + '-v1', 'DAG kind')
        equal(record['dependencies'], {k: command['records'][k] for k in deps}, 'DAG edges')
        # Payload semantics require exact independent review; syntax alone is
        # deliberately insufficient for execute(). No executable records loaded.
        require(type(record['payload']) is dict and bool(record['payload']), 'empty evidence payload')
    return {'status': 'STRUCTURAL_ONLY', 'runtime_admitted': False, 'N7': 'UNVERIFIED'}


def validate_paths(root, control, output, fixture, writable, sockets):
    """Lexical precheck only; no mode bit proves capability protection."""
    for value in (root, control, output, fixture, *writable, *sockets):
        path(value)
    require(type(writable) is list and type(sockets) is list and len(sockets) == 2 and
            len(set(sockets)) == 2, 'two distinct owned sockets required')
    require(beneath(control, root + '/.omx') and control != root + '/.omx', 'control placement')
    require(beneath(output, root + '/' + CONTINUATION) and not beneath(output, fixture), 'output placement')
    for protected in (control, output):
        require(not any(beneath(protected, scope) for scope in (*writable, fixture, '/tmp', '/private/tmp')),
                'protected scope is writable')
    for value in sockets:
        require(beneath(value, control) and len(value.encode()) < 104, 'socket scope/path length')


class Claims:
    """Fixed lifetime keys; the store must implement atomic durable no-follow create.

    No filesystem store is supplied in this source-only stage. A fresh store or
    history boolean cannot authenticate complete history or protected ownership.
    """
    def __init__(self, store, history):
        equal(history, {v: 'unused' for v in DONORS.values()}, 'donor history')
        self.store = store

    def context(self, mode):
        require(mode in CONTEXTS, 'unknown context')
        self.store.create_once('N7-C/' + mode, {'kind': 'context-reservation', 'mode': mode})

    def input(self, mode, which):
        key = 'N7-C/' + mode + '/' + which
        require(key in DONORS, 'unknown input claim')
        self.store.create_once(key, {'kind': 'input-reservation', 'donor': DONORS[key]})


class RawRetention:
    """Exact preclassified nonsecret startup profile, never a secret-name scanner.

    review_refs must be authenticated by the future live adapter. This validator
    only permits previously schema/profile-bound complete payload digests. Raw
    chunks remain bounded memory until complete-message classification succeeds;
    mixed safe/unknown chunks cannot be durably written as an aggregate.
    """
    def __init__(self, profile):
        closed(profile, ('schema', 'review', 'config_sha256', 'messages'), 'retention profile')
        ref(profile['schema']); ref(profile['review']); sha(profile['config_sha256'])
        require(type(profile['messages']) is list and 0 < len(profile['messages']) <= 64,
                'retention routes')
        self.routes = {}
        for row in profile['messages']:
            closed(row, ('method', 'request', 'response_sha256'), 'retention route')
            require(row['method'] in ('initialize', 'model/list', 'config/read',
                                     'configRequirements/read', 'account/read',
                                     'collaborationMode/list'), 'unsafe startup route')
            if row['method'] == 'account/read':
                equal(row['request'], {'refreshToken': False}, 'account refresh')
            key = (row['method'], canonical(row['request']))
            require(key not in self.routes, 'duplicate retention route')
            self.routes[key] = sha(row['response_sha256'])
        self.profile = loads(canonical(profile))

    def classify(self, method, request, response, config_sha256):
        sha(config_sha256)
        require(config_sha256 == self.profile['config_sha256'], 'effective config drift')
        require(self.routes.get((method, canonical(request))) == digest(response),
                'unclassified startup payload; raw persistence forbidden')
        return True
