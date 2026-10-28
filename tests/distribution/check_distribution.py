"""Pinned project-install checks. No product model execution or third-party parser.

Only the owned metadata subset is supported: a first-line YAML frontmatter
with unquoted top-level name / boolean disable-model-invocation, and an
openai.yaml policy block with two-space allow_implicit_invocation boolean.
Other top-level Codex sections (e.g. interface) are outside this parser's scope.
Unsupported/duplicate policy fields fail clearly instead of guessing YAML.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1]
CONTRACT = json.loads((HERE / 'intended-skills.json').read_text())
EXPECTED = set(CONTRACT['manual'] + CONTRACT['automatic'])
FAILURES = []


def check(name, fn):
    try:
        fn()
    except (AssertionError, ValueError, OSError, subprocess.SubprocessError) as exc:
        FAILURES.append(name)
        print(f'FAIL {name}: {exc}', flush=True)
    else:
        print(f'PASS {name}', flush=True)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0] != '---' or '---' not in lines[1:]:
        raise ValueError('expected delimited frontmatter on first line')
    result = {}
    for line in lines[1:lines[1:].index('---') + 1]:
        match = re.fullmatch(r'(name|disable-model-invocation):\s*(.*?)\s*', line)
        if match:
            key, value = match.groups()
            if key in result:
                raise ValueError(f'duplicate {key}')
            if key == 'name' and not re.fullmatch(r'[a-z0-9-]+', value):
                raise ValueError('unsupported name scalar; expected plain slug')
            if key == 'disable-model-invocation' and value not in ('true', 'false'):
                raise ValueError('unsupported invocation boolean; expected true/false')
            result[key] = value
    return result


def implicit_policy(text):
    value = None
    policy_seen = False
    inside = False
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if not line.startswith((' ', '\t')):
            inside = False
            if re.match(r'policy\s*:', line):
                if policy_seen or line.strip() != 'policy:':
                    raise ValueError('unsupported/duplicate policy; use block policy:')
                policy_seen = inside = True
            continue
        if inside:
            match = re.fullmatch(r'  allow_implicit_invocation: (true|false)\s*(?:#.*)?', line)
            if not match or value is not None:
                raise ValueError('unsupported/duplicate policy field; expected two-space boolean')
            value = match.group(1) == 'true'
    if policy_seen and value is None:
        raise ValueError('policy block lacks allow_implicit_invocation')
    return True if value is None else value


def parser_checks():
    require(frontmatter('---\nname: ains\n---\ndisable-model-invocation: true')['name'] == 'ains', 'name parse')
    require('disable-model-invocation' not in frontmatter('---\nname: ains\n---\ndisable-model-invocation: true'), 'body leaked into frontmatter')
    require(implicit_policy('interface:\n  allow_implicit_invocation: false\n') is True, 'wrong scope disabled invocation')
    require(implicit_policy('policy:\n  allow_implicit_invocation: false\ninterface:\n  display_name: Example\n') is False, 'exact policy not found')
    require(implicit_policy('# policy:\n#  allow_implicit_invocation: false\n') is True, 'comment changed policy')
    for malformed in ['policy: {allow_implicit_invocation: false}', 'policy:\n  allow_implicit_invocation: "false"', 'policy:\n    allow_implicit_invocation: false', 'policy:\n  allow_implicit_invocation: false\n  allow_implicit_invocation: true', 'policy:\n  unrelated: false', 'policy:\npolicy:\n  allow_implicit_invocation: false']:
        try:
            implicit_policy(malformed)
        except ValueError:
            continue
        raise AssertionError(f'unsupported policy accepted: {malformed!r}')


def source_inventory():
    files = list((SOURCE / 'skills').rglob('SKILL.md'))
    names = [frontmatter(p.read_text()).get('name') for p in files]
    require(len(names) == len(set(names)), 'duplicate discovered names')
    require(set(names) == EXPECTED, f'intended inventory mismatch: {set(names) ^ EXPECTED}')
    require({p.parent.name for p in files} == EXPECTED, 'skill names must match directory names')


def metadata(root):
    claude_manual, codex_manual = set(), set()
    for name in sorted(EXPECTED):
        fm = frontmatter((root / name / 'SKILL.md').read_text())
        if fm.get('disable-model-invocation') == 'true':
            claude_manual.add(name)
        adapter = root / name / 'agents/openai.yaml'
        if adapter.exists() and not implicit_policy(adapter.read_text()):
            codex_manual.add(name)
    intended = set(CONTRACT['manual'])
    require(claude_manual == intended, f'Claude manual set differs: {claude_manual ^ intended}')
    require(codex_manual == intended, f'Codex manual set differs: {codex_manual ^ intended}')


def no_fixtures(root):
    bad = [str(p.relative_to(root)) for name in sorted(EXPECTED) for p in (root / name).rglob('*') if p.name in ('evals', 'graders', 'case.yaml', 'place-files.sh', 'setup.sh')]
    require(not bad, f'development fixtures shipped: {bad[:12]} (total {len(bad)})')


def resources(root):
    for name, paths in CONTRACT['required_resources'].items():
        for relative in paths:
            require((root / name / relative).is_file(), f'missing resource {name}/{relative}')
    for name in CONTRACT['manual']:
        require((root / name / 'agents/openai.yaml').is_file(), f'missing manual adapter {name}')


def installed_links(root):
    # Scan Markdown file links in runtime documents, excluding development evals.
    for name in EXPECTED:
        for md in (root / name).rglob('*.md'):
            if 'evals' in md.relative_to(root / name).parts:
                continue
            for target in re.findall(r'\[[^\]]*\]\(([^\s)]+)\)', md.read_text()):
                if re.match(r'[a-zA-Z][a-zA-Z0-9+.-]*:', target) or target.startswith(('#', '/')):
                    continue
                relative = target.split('#')[0]
                require((md.parent / relative).exists(), f'broken link {md.relative_to(root)} -> {target}')


def modes(root):
    for name, rel in [('ains', 'scripts/status.sh'), ('ains-spec', 'scripts/new-change.sh'), ('ains-review-gate', 'scripts/route-review.sh')]:
        p = root / name / rel
        require(p.stat().st_mode & stat.S_IXUSR, f'not executable: {name}/{rel}')


def execute_installed(root, consumer):
    new = root / 'ains-spec/scripts/new-change.sh'
    result = subprocess.run([str(new), 'installed-check', '--root', str(consumer / 'changes with spaces')], cwd=consumer, text=True, capture_output=True, timeout=30)
    require(result.returncode == 0, result.stderr)
    d = Path(result.stdout.strip())
    expected = (root / 'ains-spec/assets/spec.md').read_text().replace('{{CHANGE_ID}}', d.name)
    require((d / 'spec.md').read_text() == expected, 'installed template mismatch')
    result = subprocess.run([str(root / 'ains/scripts/status.sh'), str(d.parent)], cwd=consumer, text=True, capture_output=True, timeout=30)
    require(result.returncode == 0 and f'{d.name}  status=draft  plan=-' in result.stdout, f'installed status failed: rc={result.returncode} {result.stdout} {result.stderr}')


def fixture_inventory_check(path):
    inventory = json.loads(path.read_text())
    for item in inventory:
        moved = SOURCE / item['destination']
        require(moved.is_file(), f'missing migrated eval {item["destination"]}')
        require(hashlib.sha256(moved.read_bytes()).hexdigest() == item['sha256'], f'eval content changed: {moved}')
        require(oct(stat.S_IMODE(moved.stat().st_mode)) == item['mode'], f'eval mode changed: {moved}')
    expected_paths = {item['destination'] for item in inventory}
    actual = {str(p.relative_to(SOURCE)) for name in ('ains-spec', 'ains-build', 'ains-review-gate') for p in (SOURCE / 'tests/evals' / name).rglob('*') if p.is_file()}
    require(actual == expected_paths, f'migrated inventory differs: {actual ^ expected_paths}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--static-only', action='store_true', help='skip CLI discovery/install matrix')
    parser.add_argument('--log-dir', type=Path, help='retain pinned CLI command output')
    parser.add_argument('--eval-inventory', type=Path, help='verify original eval hashes after migration')
    args = parser.parse_args()
    check('scoped metadata parser positive/negative fixtures', parser_checks)
    check('source intended skill inventory', source_inventory)
    check('source exact invocation metadata parity', lambda: metadata(SOURCE / 'skills'))
    check('source runtime resources and adapters', lambda: resources(SOURCE / 'skills'))
    check('source fixture exclusion', lambda: no_fixtures(SOURCE / 'skills'))
    check('source Markdown links', lambda: installed_links(SOURCE / 'skills'))
    if args.eval_inventory:
        check('original eval paths and contents preserved after move', lambda: fixture_inventory_check(args.eval_inventory))
    if not args.static_only:
        with tempfile.TemporaryDirectory(prefix='ains-distribution-') as temp:
            work = Path(temp)
            env = dict(os.environ)
            # Child-only clean home/config. Reuse npm package cache, never auth files.
            env['npm_config_cache'] = str(Path.home() / '.npm')
            env['HOME'] = str(work / 'child home')
            env['XDG_CONFIG_HOME'] = str(work / 'child config')
            Path(env['HOME']).mkdir()
            def cli(label, cwd, arguments):
                command = ['npx', '--yes', 'skills@1.7.4', *arguments]
                result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=180)
                output = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', result.stdout + result.stderr)
                if args.log_dir:
                    args.log_dir.mkdir(parents=True, exist_ok=True)
                    (args.log_dir / f'{label}.log').write_text(f'command: {command!r}\ncwd: {cwd}\nexit: {result.returncode}\n{output}')
                require(result.returncode == 0, f'{label}: rc={result.returncode}\n{output[-3000:]}')
                return output
            def version():
                require(cli('version', work, ['--version']).strip() == '1.7.4', 'unexpected CLI version')
            check('skills CLI pinned version 1.7.4', version)
            def discovery():
                output = cli('discovery', work, ['add', str(SOURCE), '--list'])
                # CLI lists each skill as an indented slug line; inspect every candidate,
                # including unexpected skills, independently of the expected inventory.
                names = re.findall(r'^│    ([a-z][a-z0-9-]*)\s*$', output, re.M)
                require(len(names) == len(set(names)), f'duplicate listed skills: {names}')
                require(set(names) == EXPECTED, f'CLI inventory mismatch: {names}\n{output}')
            check('CLI exact intended discovery', discovery)
            for copy in (False, True):
                for products in [('claude-code',), ('codex',), ('claude-code', 'codex')]:
                    label = ('copy' if copy else 'symlink') + '-' + '-'.join(products)
                    consumer = work / (label + ' consumer with spaces')
                    consumer.mkdir()
                    try:
                        cli(label, consumer, ['add', str(SOURCE), '--skill', '*', '-a', *products, '-y', *(['--copy'] if copy else [])])
                    except (AssertionError, OSError, subprocess.SubprocessError) as exc:
                        FAILURES.append(label)
                        print(f'FAIL {label} install: {exc}', flush=True)
                        continue
                    for product in products:
                        root = consumer / ('.claude/skills' if product == 'claude-code' else '.agents/skills')
                        prefix = f'{label}/{product}'
                        def names_check(root=root):
                            require({p.name for p in root.iterdir() if (p / 'SKILL.md').is_file()} == EXPECTED, 'installed names differ')
                            for name in EXPECTED:
                                require((root / name / 'SKILL.md').read_bytes() == (SOURCE / 'skills' / name / 'SKILL.md').read_bytes(), f'wrong installed provenance: {name}')
                        check(prefix + ' names/provenance', names_check)
                        for title, fn in [('metadata parity', metadata), ('resources', resources), ('Markdown/sibling links', installed_links), ('executable modes', modes), ('fixture exclusion', no_fixtures)]:
                            check(prefix + ' ' + title, lambda fn=fn, root=root: fn(root))
                        # Both products in one consumer need distinct change roots.
                        run_cwd = consumer / product
                        run_cwd.mkdir()
                        check(prefix + ' installed scripts from consumer cwd', lambda root=root, run_cwd=run_cwd: execute_installed(root, run_cwd))
    print(f'failed={len(FAILURES)}')
    return bool(FAILURES)

if __name__ == '__main__':
    raise SystemExit(main())
