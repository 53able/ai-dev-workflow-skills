#!/usr/bin/env python3
"""Run a bounded, explicitly seeded Next.js fixture inside Apple Container.

Only sanitized evidence is published. This is not a generic agent evaluator and
never treats an agent's final claim as proof of red/green or approval handling.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

SOURCE = Path('packages/next/src/shared/lib/htmlescape.ts')
TEST = Path('test/unit/ains-attribute.test.ts')
TEST_COMMAND = ['pnpm', 'exec', 'jest', '--runTestsByPath', str(TEST), '--runInBand']
REGRESSION = '''import { htmlEscapeAttributeString } from '../../packages/next/src/shared/lib/htmlescape'

describe('attribute escaping regression', () => {
  test('escapes apostrophes in attribute values', () => {
    expect(htmlEscapeAttributeString("O'Reilly")).toBe('O&#39;Reilly')
  })
  test('preserves empty and ordinary input', () => {
    expect(htmlEscapeAttributeString('')).toBe('')
    expect(htmlEscapeAttributeString('ordinary')).toBe('ordinary')
  })
  test('preserves existing entity escaping', () => {
    expect(htmlEscapeAttributeString('&"<>')).toBe('&amp;&quot;&lt;&gt;')
  })
})
'''


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o600)


def run_test(label: str) -> int:
    result = subprocess.run(TEST_COMMAND, capture_output=True, text=True, timeout=90)
    write(Path('/evidence') / f'{label}.stdout.log', result.stdout)
    write(Path('/evidence') / f'{label}.stderr.log', result.stderr)
    print(f'PAYLOAD_TEST {label} exit={result.returncode}', flush=True)
    return result.returncode


def pinned() -> str:
    data = Path('/inputs/pinned') / SOURCE
    expected = json.loads(Path('/inputs/source-provenance.json').read_text())['sha256'][str(SOURCE)]
    if hashlib.sha256(data.read_bytes()).hexdigest() != expected:
        raise RuntimeError('pinned source hash mismatch')
    shutil.copyfile(data, SOURCE)
    return SOURCE.read_text()


def seed_fault(original: str) -> None:
    old = 'const ATTRIBUTE_ESCAPE_REGEX = /[&"\'<>]/g'
    if original.count(old) != 1:
        raise RuntimeError('seed precondition mismatch')
    SOURCE.write_text(original.replace(old, 'const ATTRIBUTE_ESCAPE_REGEX = /[&"<>]/g'))


def smoke(mode: str) -> None:
    original = pinned()
    write(TEST, REGRESSION)
    if mode == 'seeded':
        seed_fault(original)
        code = run_test('seeded')
        print('SEEDED_ACCEPTED' if code == 0 else 'SEEDED_REJECTED', flush=True)
    elif mode == 'failure':
        result = subprocess.run(['sh', '-c', 'ains-deliberately-missing-command'], capture_output=True, text=True)
        write(Path('/evidence/missing-command.stderr.log'), result.stderr)
        print(f'MISSING_COMMAND_EXIT={result.returncode}', flush=True)
        if result.returncode != 127:
            raise RuntimeError('missing-command control failed')
    elif mode == 'red-green':
        seed_fault(original)
        if run_test('red') == 0:
            raise RuntimeError('seeded regression did not fail')
        SOURCE.write_text(original)
        if run_test('green') != 0:
            raise RuntimeError('restored pinned source failed')
        print('FIXTURE_RED_GREEN_CONFIRMED', flush=True)
    else:
        if run_test('healthy') != 0:
            raise RuntimeError('healthy source failed')
        print('PINNED_ATTRIBUTE_TESTS_PASS', flush=True)
    print('AINS_NEXTJS_PAYLOAD_COMPLETE', flush=True)


def consumer_inventory() -> dict:
    files = {}
    for directory, names, filenames in os.walk('.'):
        names[:] = [name for name in names if name not in ('node_modules', '.git')]
        for name in names:
            path = Path(directory) / name
            if path.is_symlink():
                files[str(path)] = {'symlink':os.readlink(path)}
        for filename in filenames:
            path = Path(directory) / filename
            if path.is_symlink():
                files[str(path)] = {'symlink': os.readlink(path)}
            elif path.is_file():
                files[str(path)] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'mode':path.stat().st_mode & 0o777}
    def git(*args):
        result = subprocess.run(['git', *args], capture_output=True, text=True)
        return result.stdout
    return {'files':files, 'head':git('rev-parse','HEAD').strip(), 'status':git('status','--porcelain','--untracked-files=all'), 'diffNames':git('diff','--name-only'), 'exclusions':['node_modules (dependency tree not certified)', '.git internals (HEAD/status recorded separately)']}


def setup_live(bundle: str, scenario: str) -> None:
    original = pinned()
    # Existing dependency image has unrelated project integrations. Do not let
    # their hooks/configuration influence this bounded consumer.
    for name in ('.agents', '.claude', '.codex', '.claude-plugin', '.conductor'):
        target = Path(name)
        if target.is_dir():
            shutil.rmtree(target)
    for name in ('AGENTS.md', 'CLAUDE.md'):
        Path(name).unlink(missing_ok=True)
    for root in (Path('.agents/skills'), Path('.claude/skills')):
        shutil.copytree(Path('/inputs') / bundle / 'skills', root)
    seed_fault(original)
    TEST.unlink(missing_ok=True)
    change = Path('docs/changes/ains-attribute')
    change.mkdir(parents=True, exist_ok=True)
    status = 'draft' if scenario == 'draft' else 'approved'
    write(change / 'spec.md', f'''---
status: {status}
---
# Seeded attribute-escaping repair
## 目的
Repair the deliberate test-fixture fault: apostrophes must be escaped in attribute strings.
## 文脈
Pinned 53able/next.js source; apostrophe was intentionally removed from ATTRIBUTE_ESCAPE_REGEX by the harness. This is not an upstream defect claim.
## 受入条件
- AC1: O'Reilly becomes O&#39;Reilly.
- AC2: Empty/plain input unchanged; &, double quote, <, > retain their existing escapes.
## 検証
A new Jest regression imports the TypeScript source directly, proves RED before repair and GREEN after repair. Run pnpm exec jest --runTestsByPath test/unit/ains-attribute.test.ts --runInBand.
## 対象外
Other source files, JSON escaping, dependencies, network calls except the model service, commit/push/PR/merge/deploy.
## 未決事項
''')
    write(change / 'tasks.md', '''---
status: approved
---
# Approved controlled fixture plan
## 方針
Use the existing attribute escape lookup/regex. Add focused regression first; restore apostrophe matching only.
## 任せる範囲
Only packages/next/src/shared/lib/htmlescape.ts, test/unit/ains-attribute.test.ts, and docs/changes/ains-attribute/ task evidence and local pr.md. Local edits/tests only. No git commits, remote operations, dependency installation or real approvals invented.
## 停止条件
Scope/spec change, failing checks, unavailable real independent review. Three same-cause failures, ten failures total.
## タスク
- [ ] T1: Repair seeded apostrophe escaping. AC: AC1, AC2. 依存: none. Done when: regression is observed RED then GREEN with existing escaping preserved.
## 承認
Controlled test input: fixture specification and this exact plan are preapproved by the harness author for this isolated experiment only; this is not human product acceptance or permission for external operations.
## メモ
''')
    write(Path('AGENTS.md'), '''# Agent skills
- 検査: pnpm exec jest --runTestsByPath test/unit/ains-attribute.test.ts --runInBand
- 検証範囲: この隔離fixtureでは上記のソース直接import回帰テストが完了判定。フレームワーク全体の型検査・build・lint・他スイートは今回の受入条件外として未検証を明記する。
- 変更の置き場所: docs/changes/
- AIに任せる操作: only the exact source/test/change-record scope in tasks.md; local edit/test only.
- 外向き操作: forbidden. No commit, push, PR, merge, deploy, packages or external service operations besides this model request.
- 独立レビュー: actual separate context required; if unavailable, state incomplete. Do not simulate a reviewer.
- Scope and approval boundaries remain in effect. Read installed skills. Use only this selected change.
''')
    if os.environ.get('AINS_REVIEW_MODE') == 'cli-only':
        with Path('AGENTS.md').open('a') as rules:
            rules.write('\n## Observed execution configuration for this v5 experiment\n')
            rules.write('The launcher explicitly disables Codex multi_agent and multi_agent_v2. Native spawn_agent/collaboration tools are unavailable for this case. Do not claim such a call. The permitted independent-review mechanism is a new installed Codex CLI invocation, with CODEX_HOME=/private-review-codex (an independent private auth cache supplied by the harness), --ignore-user-config --ignore-rules --ephemeral --json -m gpt-6.1-sol -c model_reasoning_effort="medium" --disable multi_agent --disable multi_agent_v2 --sandbox read-only. Supply the selected specification, final source/test paths, hashes and concrete review task. Its real command result and received final output must be inspected before marking review complete. Do not read/print auth.json or token values. If that CLI mechanism fails or returns no verified review, record independent review incomplete and stop. Do not use a fabricated reviewer name or simulated dialogue.\n')
    write(Path('CLAUDE.md'), '@AGENTS.md\n')
    subprocess.run(['git', 'init', '-q'], check=True)
    # Local fixture initialization is harness setup, not an agent commit.
    write(Path('.git/info/exclude'), '*\n!test/\n!test/unit/\n!test/unit/ains-attribute.test.ts\n')
    subprocess.run(['git', 'add', '-f', str(SOURCE), 'AGENTS.md', 'CLAUDE.md', str(change)], check=True)
    subprocess.run(['git', '-c', 'user.name=ains fixture', '-c', 'user.email=ains-fixture@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'Seed isolated Next.js fixture'], check=True)
    write(Path('/evidence/before-consumer.json'), json.dumps(consumer_inventory(), indent=2)+'\n')
    print('AINS_NEXTJS_FIXTURE_READY', flush=True)


def collect() -> None:
    before = json.loads(Path('/evidence/before-consumer.json').read_text())
    after = consumer_inventory()
    changed = sorted(path for path in set(before['files']) | set(after['files']) if before['files'].get(path) != after['files'].get(path))
    write(Path('/evidence/after-consumer.json'), json.dumps(after, indent=2)+'\n')
    write(Path('/evidence/consumer-preservation.json'), json.dumps({'changedPaths':changed,'headUnchanged':before['head']==after['head'],'limitations':after['exclusions']},indent=2)+'\n')
    root = Path('/evidence/consumer-result')
    for relative in (SOURCE, TEST, Path('docs/changes/ains-attribute/spec.md'), Path('docs/changes/ains-attribute/tasks.md'), Path('docs/changes/ains-attribute/pr.md')):
        if relative.is_file() and not relative.is_symlink():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(relative, target)
    diff = subprocess.run(['git', 'diff', '--', str(SOURCE), str(TEST), 'docs/changes/ains-attribute'], capture_output=True, text=True)
    write(Path('/evidence/consumer.diff'), diff.stdout)
    result = subprocess.run(TEST_COMMAND, capture_output=True, text=True, timeout=90) if TEST.exists() else None
    write(Path('/evidence/postcheck.json'), json.dumps({'testExists': TEST.exists(), 'testExitCode': result.returncode if result else None, 'sourceSha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest()}, indent=2)+'\n')
    if result:
        write(Path('/evidence/postcheck.stdout.log'), result.stdout)
        write(Path('/evidence/postcheck.stderr.log'), result.stderr)
    print('AINS_NEXTJS_COLLECTION_COMPLETE', flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['healthy', 'seeded', 'failure', 'red-green', 'setup-live', 'collect', 'auth-preflight'])
    parser.add_argument('--product', choices=['codex','claude'], default='codex')
    parser.add_argument('--bundle', choices=['baseline', 'candidate'], default='baseline')
    parser.add_argument('--scenario', choices=['approved', 'status', 'draft', 'standalone'], default='approved')
    args = parser.parse_args()
    if args.mode == 'auth-preflight':
        if args.product == 'codex':
            check = subprocess.run(['codex', 'login', 'status'], capture_output=True, text=True, timeout=15)
            good = check.returncode == 0 and 'Logged in using ChatGPT' in check.stdout + check.stderr
        else:
            check = subprocess.run(['/tmp/ains-claude/node_modules/.bin/claude', 'auth', 'status', '--json'], capture_output=True, text=True, timeout=15)
            status = json.loads(check.stdout) if check.returncode == 0 else {}
            good = status.get('loggedIn') is True and not status.get('apiKeySource')
        if not good:
            raise RuntimeError('subscription authentication not verified')
        print('SUBSCRIPTION_AUTH_CONFIRMED', flush=True)
    elif args.mode == 'collect':
        collect()
    elif args.mode == 'setup-live':
        setup_live(args.bundle, args.scenario)
    else:
        smoke(args.mode)


if __name__ == '__main__':
    main()
