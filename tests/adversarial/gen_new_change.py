"""L1 cases for skills/ains-spec/scripts/new-change.sh (contracts N-C*, invariants N-INV*; see contracts.md)."""
import os
from pathlib import Path

import pairwise
from l1lib import REPO, Case, Expect, Invocation, UNSPECIFIED, case_id, existing_rows, snapshot, today

NAME = 'new-change'
SCRIPT = 'skills/ains-spec/scripts/new-change.sh'
TEMPLATE = REPO / 'skills/ains-spec/assets/spec.md'
SLUGS = {'valid': 'valid-slug', 'trailing-dash': 'trail-', 'double-dash': 'a--b', 'digits': '123',
         'long256': 'a' * 256, 'unicode': 'café', 'dotdot': '../escape', 'upper': 'Bad', 'leading-dash': '-bad'}
VALID = ('valid', 'trailing-dash', 'double-dash', 'digits')      # match ^[a-z0-9][a-z0-9-]*$ (new-change.sh:24)
INVALID = ('unicode', 'dotdot', 'upper', 'leading-dash')
CREATABLE = ('default', 'absolute', 'space', 'missing-parent')
AXES = {
    'slug': list(SLUGS),
    'root': ['default', 'absolute', 'space', 'missing-parent', 'existing-file', 'dash-lead', 'unwritable'],
    'existing': ['none', 'spec', 'spec-link', 'broken-link'],
    'order': ['slug-first', 'root-first', 'multi-slug'],
}
EXCLUDE = [(('root', 'default'), ('order', 'root-first'))] + [
    (('root', r), ('existing', e)) for r in ('existing-file', 'missing-parent') for e in ('spec', 'spec-link', 'broken-link')]
WHEN = {}


def root_arg(row, work):
    return {'default': None, 'absolute': str(work / 'changes'), 'space': str(work / 'with space/changes'),
            'missing-parent': str(work / 'a/b/changes'), 'existing-file': str(work / 'afile'),
            'dash-lead': '-r', 'unwritable': str(work / 'ro')}[row['root']]


def builder(row):
    def build(tmp):
        work = tmp / 'work'
        work.mkdir()
        arg = root_arg(row, work)
        rootdir = work / (arg or 'docs/changes')
        if row['root'] == 'existing-file':
            rootdir.write_text('not a directory\n')
        target = rootdir / f'{today()}-{SLUGS[row["slug"]] if row["slug"] in VALID else "keep"}'
        ctx = {'root': arg or 'docs/changes', 'target': target, 'outside': work / 'outside.md', 'missing': work / 'missing.md'}
        if row['existing'] != 'none':
            target.mkdir(parents=True)
            spec = target / 'spec.md'
            if row['existing'] == 'spec':
                spec.write_text('human content\n')
            elif row['existing'] == 'spec-link':
                ctx['outside'].write_text('outside content\n')
                spec.symlink_to(ctx['outside'])
            else:
                spec.symlink_to(ctx['missing'])
        if row['root'] == 'unwritable':
            rootdir.mkdir(exist_ok=True)
            rootdir.chmod(0o555)
        slug, root = SLUGS[row['slug']], ([] if arg is None else ['--root', arg])
        args = {'slug-first': [slug, *root], 'root-first': [*root, slug],
                'multi-slug': ['first-slug', slug, *root]}[row['order']]
        ctx['before'] = snapshot(work)
        return Invocation(args, work, ctx)
    return build


def unchanged(run):
    after = snapshot(run.inv.cwd)
    diff = sorted(k for k in after.keys() | run.inv.ctx['before'].keys() if after.get(k) != run.inv.ctx['before'].get(k))
    return f'changed: {diff[:5]}' if diff else None


def existing_kept(row):
    def test(run):
        spec, ctx = run.inv.ctx['target'] / 'spec.md', run.inv.ctx
        if row['existing'] == 'spec':
            return None if spec.read_text() == 'human content\n' else 'existing spec.md changed'
        if not spec.is_symlink() or os.readlink(spec) != str(ctx['outside' if row['existing'] == 'spec-link' else 'missing']):
            return 'spec.md symlink replaced'
        if row['existing'] == 'spec-link':
            return None if ctx['outside'].read_text() == 'outside content\n' else 'symlink target changed'
        return 'broken symlink target was created' if ctx['missing'].exists() else None
    return test


def printed_dir(run):
    """N-C5: on exit 0 the last stdout line is a directory (relative to cwd) holding spec.md."""
    if run.exit != 0:
        return None
    d = run.inv.cwd / run.stdout.rstrip('\n').split('\n')[-1]
    spec = d / 'spec.md'
    return None if d.is_dir() and (spec.is_symlink() or spec.is_file()) else f'printed {run.stdout!r} is not a change dir'


def created(row):
    slug = SLUGS[row['slug']]

    def test(run):
        if run.exit != 0:
            return f'exit {run.exit}: {run.stderr.strip()}'
        wants = {f'{run.inv.ctx["root"]}/{d}-{slug}\n' for d in run.dates}
        return None if run.stdout in wants else f'stdout {run.stdout!r} not in {sorted(wants)}'
    return test


def template_placed(row):
    def test(run):
        d = Path(run.stdout.strip())
        spec = run.inv.cwd / d / 'spec.md'
        want = TEMPLATE.read_text().replace('{{CHANGE_ID}}', d.name)
        return None if spec.is_file() and spec.read_text() == want else 'spec.md is not the filled template'
    return test


def expects(row):
    slug, root, order, existing = row['slug'], row['root'], row['order'], row['existing']
    out = [Expect('N-C5', 'exit 0 なら stdout の最終行は spec.md を持つディレクトリ', printed_dir)]
    if existing != 'none':
        out.append(Expect('N-INV1', '既存の spec.md と symlink の参照先は変わらない（壊れた symlink の参照先も作らない）', existing_kept(row)))
    if root == 'dash-lead':
        out.append(Expect('N-C3', '--root の値が - で始まると exit 2', lambda r: None if r.exit == 2 else f'exit {r.exit}'))
        out.append(Expect('N-C3', '何も作らない', unchanged))
        return tuple(out)
    if order == 'multi-slug':
        out.append(Expect(UNSPECIFIED, 'N-INV2: slug を複数渡した場合（最後の slug が採られる）は記録する'))
        return tuple(out)
    if slug in INVALID:
        out.append(Expect('N-INV2', '不正な slug 1つは exit 2', lambda r: None if r.exit == 2 else f'exit {r.exit}'))
        out.append(Expect('N-INV2', '不正な slug 1つは何も作らない', unchanged))
    elif slug == 'long256':
        out.append(Expect(UNSPECIFIED, 'N-INV2: 正規表現は通るが mkdir に失敗する長さは記録する'))
    elif root in CREATABLE or existing != 'none':
        out.append(Expect('N-C1', 'exit 0、stdout は <root>/<実行の直前か直後の日付>-<slug>', created(row)))
        if existing == 'none':
            out.append(Expect('N-C2', 'spec.md は CHANGE_ID を埋めた雛形', template_placed(row)))
        else:
            out.append(Expect('N-C4', '既存の spec.md は上書きせず stderr に skip (exists)',
                              lambda r: None if 'skip (exists): ' in r.stderr else f'stderr {r.stderr!r}'))
    else:
        out.append(Expect('N-C6', '作成先を作れなければ exit ≠ 0', lambda r: f'exit 0: {r.stdout!r}' if r.exit == 0 else None))
        out.append(Expect('N-C6', '何も作らない', unchanged))
    return tuple(out)


def make(row):
    return Case(case_id('nc', row), SCRIPT, row, expects(row), builder(row))


def cases():
    return [make(row) for row in pairwise.generate(AXES, EXCLUDE, WHEN, covered=existing_rows(NAME))]
