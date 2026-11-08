#!/usr/bin/env python3
"""Prepare immutable public inputs/manifests; never loads authentication."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('workspace', type=Path)
    parser.add_argument('--image', default='nextjs-document-baseline:20261108')
    args = parser.parse_args()
    root = args.workspace.resolve()
    inputs = root / 'input'
    shutil.copyfile(Path(__file__).with_name('container_case.py'), inputs / 'container_case.py')
    manifest = {
        'version': 1, 'slug': 'ains-nextjs-fixture',
        'claim': 'The pinned Next.js seeded fixture distinguishes broken apostrophe matching from restored behavior.',
        'hypothesis': 'The focused regression passes on pinned source and fails when apostrophe regex matching is removed.',
        'falsificationCriteria': [{'id': 'seed-not-detected', 'description': 'Seeded apostrophe fault passes the regression.'}],
        'image': {'tag': args.image},
        'defaults': {'network': 'none', 'cpus': 1, 'memory': '2G', 'timeoutSeconds': 120, 'retries': 0, 'repeats': 1, 'maxConcurrency': 2, 'readOnlyRoot': False, 'allowWritableMounts': False},
        'mounts': [{'source': 'input', 'target': '/inputs', 'readonly': True}],
        'cases': [],
    }
    for mode, group, relation, marker in [
        ('healthy', 'target', 'support', 'PINNED_ATTRIBUTE_TESTS_PASS'),
        ('seeded', 'negative', 'falsify', 'SEEDED_ACCEPTED'),
        ('failure', 'failure', 'neutral', 'MISSING_COMMAND_EXIT=127'),
        ('red-green', 'boundary', 'support', 'FIXTURE_RED_GREEN_CONFIRMED'),
    ]:
        case = {'id': mode, 'group': group, 'description': mode, 'relation': relation, 'criterionIds': [],
                'command': ['python3', '/inputs/container_case.py', mode],
                'oracle': {'exitCode': 0, 'stdoutContains': ['AINS_NEXTJS_PAYLOAD_COMPLETE', marker]}}
        if relation == 'falsify': case['criterionIds'] = ['seed-not-detected']
        manifest['cases'].append(case)
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    smoke = dict(manifest, cases=manifest['cases'][:3])
    (root / 'smoke.json').write_text(json.dumps(smoke, indent=2) + '\n')
    print(json.dumps({'workspace': str(root), 'manifest': str(root / 'manifest.json'), 'inputScriptSha256': hashlib.sha256((inputs / 'container_case.py').read_bytes()).hexdigest()}))


if __name__ == '__main__': main()
