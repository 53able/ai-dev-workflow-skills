"""L1 cases for skills/ains-review-gate/scripts/route-review.sh (contracts R-C*, invariants R-INV*; see contracts.md).

Each case builds a throwaway git repository: base `main` (or `trunk`), the change on `feat`, then the git
state, the uncommitted layer and the target-mode helpers. Expected exits are hand-decided from the
contracts (R-INV2 order: any exit-3 condition, then base-absent rules / gitlink, then rule matches);
where the contract has no conclusion the case accepts exit 3 or the otherwise expected exit.
"""
import functools
import subprocess

import pairwise
from l1lib import REPO, Case, Expect, Invocation, case_id, existing_rows, script_env

NAME = 'route-review'
SCRIPT = 'skills/ains-review-gate/scripts/route-review.sh'
RULES = 'docs/ains/human-review-rules'
AXES = {
    'mode': ['wt1', 'wt2', 'target'],      # wt1/wt2: worktree mode with 1/2 args; target: 3 args (committed-target)
    'git': ['normal', 'empty', 'no-main', 'detached', 'shallow', 'no-merge-base', 'multi-merge-base', 'subdir',
            'linked-worktree'],
    'change': ['modify', 'rename', 'binary', 'nul', 'newline-path', 'non-ascii', 'upper-case', 'symlink',
               'mode-only', 'delete', 'nested-repo', 'gitlink'],
    'where': ['lib', 'auth'],              # auth: under the base path rule src/auth/*
    'content': ['benign', 'hit'],          # hit: the changed lines contain isAdmin (base content rule isAdm[i]n)
    'layer': ['committed', 'staged', 'unstaged', 'untracked'],
    'rules': ['normal', 'empty', 'comments', 'missing-bar', 'bar-in-pattern', 'bad-regex', 'crlf', 'absent-base',
              'loosened-head'],
    'ref': ['branch', 'tag', 'short-sha', 'tree', 'blob', 'dash', 'ambiguous'],
    'rpath': ['plain', 'dot', 'dotdot', 'dslash', 'symlink-out'],
}
NEEDS_HISTORY = ('rename', 'mode-only', 'delete', 'gitlink')
EXCLUDE = (
    [(('git', 'empty'), ('change', c)) for c in NEEDS_HISTORY]
    + [(('git', 'empty'), ('layer', 'committed')), (('git', 'empty'), ('rules', 'loosened-head'))]
    + [(('change', 'nested-repo'), ('layer', v)) for v in ('committed', 'staged', 'unstaged')]
    + [(('mode', 'target'), ('change', 'nested-repo'))]
    + [(('change', c), ('layer', 'untracked')) for c in NEEDS_HISTORY]
    + [(('change', c), ('content', 'hit')) for c in ('mode-only', 'gitlink', 'upper-case')]   # upper-case tests the path rule alone
)
WHEN = {'layer': ('mode', ('wt1', 'wt2')), 'ref': ('mode', ('target',)), 'rpath': ('mode', ('target',))}

PATH_RULE = 'path | src/auth/* | 認証'
CONTENT_RULE = 'content | isAdm[i]n | 権限'      # [i] keeps the rule's own text from matching itself
BASE_RULES = {
    'normal': f'{PATH_RULE}\n{CONTENT_RULE}\n',
    'empty': '',
    'comments': '# only comments\n\n   \n  # indented\n',
    'missing-bar': f'{PATH_RULE}\n{CONTENT_RULE}\npath | src/x\n',
    'bar-in-pattern': f'{PATH_RULE}\ncontent | NEVER_X|isAdm[i]n | 権限\n',
    'bad-regex': f'{PATH_RULE}\n{CONTENT_RULE}\ncontent | ([ | 壊れた正規表現\n',
    'crlf': f'# comment\n\n{PATH_RULE}\n{CONTENT_RULE}\n'.replace('\n', '\r\n'),
    'loosened-head': f'{PATH_RULE}\n{CONTENT_RULE}\n',
}
LOOSE = 'content | NEVER_MA[T]CH | 緩めた\n'   # [T]: must not match its own added line
# Base path globs per rules variant (for R-INV1). absent-base has no base version.
BASE_GLOBS = {k: (['src/auth/*'] if PATH_RULE in v else []) for k, v in BASE_RULES.items()}
BASE_GLOBS['absent-base'] = []
RULES_WITH_MATCHING = ('normal', 'bar-in-pattern', 'crlf', 'loosened-head')
BENIGN, HIT = 'const v = 2;\n', 'if (isAdmin(user)) { grant(); }\n'
GIT_C = ['-c', 'user.name=l1', '-c', 'user.email=l1@example.com', '-c', 'protocol.file.allow=always',
         '-c', 'advice.addEmbeddedRepo=false', '-c', 'advice.detachedHead=false', '-c', 'init.defaultBranch=main',
         '-c', 'core.fileMode=true']
GIT_ENV = script_env()


def git(cwd, *args):
    return subprocess.run(['git', *GIT_C, *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True,
                          text=True).stdout.strip()


def commit(cwd, msg):
    git(cwd, 'add', '-A')
    git(cwd, 'commit', '-q', '--allow-empty', '-m', msg)


def change_dir(row):
    if row['change'] == 'upper-case':
        return 'src/AUTH' if row['where'] == 'auth' else 'src/Other'
    return 'src/auth' if row['where'] == 'auth' else 'src/lib'


def line(row):
    return HIT if row['content'] == 'hit' else BENIGN


def base_files(row, repo, subsrc):
    """Files that must already exist in base for the change to be a rename/delete/mode/gitlink edit."""
    (repo / 'README.md').write_text('# readme\n')
    (repo / 'src/lib').mkdir(parents=True)
    (repo / 'src/lib/util.ts').write_text('export const x = 1;\n')
    if row['rules'] != 'absent-base':
        (repo / RULES).parent.mkdir(parents=True)
        (repo / RULES).write_bytes(BASE_RULES[row['rules']].encode())
    d, c, history = repo / change_dir(row), row['change'], row['git'] != 'empty'
    d.mkdir(parents=True, exist_ok=True)
    if c == 'rename':
        (repo / 'src/lib/r.ts').write_text('export const r = 1;\n' + line(row))
    elif c == 'mode-only':
        (d / 'm.sh').write_text('echo m\n')
    elif c == 'delete':
        (d / 'd.ts').write_text('export const d = 1;\n' + line(row))
    elif c == 'modify' and history and row.get('layer') != 'untracked':
        (d / 'mod.ts').write_text('export const m = 1;\n')
    elif c == 'gitlink' and row.get('layer') == 'unstaged':
        return [('gitlink', f'{change_dir(row)}/sub', git(subsrc, 'rev-parse', 'HEAD'))]
    return []


def change_paths(row):
    """Repository paths the change touches (all of them are in scope for the case's mode)."""
    d, c = change_dir(row), row['change']
    return {'modify': [f'{d}/mod.ts' if row['git'] != 'empty' and row.get('layer') != 'untracked' else f'{d}/new.ts'],
            'rename': ['src/lib/r.ts', f'{d}/r.ts' if row['where'] == 'auth' else 'src/lib/r2.ts'],
            'binary': [f'{d}/image.bin'], 'nul': [f'{d}/nul.txt'], 'newline-path': [f'{d}/a\nb.ts'],
            'non-ascii': [f'{d}/認証.ts'], 'upper-case': [f'{d}/Upper.ts'], 'symlink': [f'{d}/link'],
            'mode-only': [f'{d}/m.sh'], 'delete': [f'{d}/d.ts'], 'nested-repo': [f'{d}/nested/'],
            'gitlink': [f'{d}/sub']}[c]


def apply_change(row, repo, layer, subsrc, base_sha):
    """Make the change in repo's worktree and stage/commit it as `layer`."""
    d, c = repo / change_dir(row), row['change']
    d.mkdir(parents=True, exist_ok=True)
    paths = change_paths(row)
    new_files = []
    if c == 'modify':
        p = repo / paths[0]
        if p.exists():
            with p.open('a') as f:
                f.write(line(row))
        else:
            p.write_text(line(row))
            new_files.append(paths[0])
    elif c == 'rename':
        (repo / paths[0]).rename(repo / paths[1])
        new_files.append(paths[1])
    elif c in ('binary', 'nul', 'newline-path', 'non-ascii', 'upper-case'):
        data = {'binary': b'\x89PNG\r\n\x1a\n\x00\x00' + (b'isAdmin' if row['content'] == 'hit' else b'pixels') + b'\x00\xff\n',
                'nul': b'x\x00' + line(row).encode()}.get(c, line(row).encode())
        (repo / paths[0]).write_bytes(data)
        new_files.append(paths[0])
    elif c == 'symlink':
        (repo / paths[0]).symlink_to('../../isAdmin.md' if row['content'] == 'hit' else '../../README.md')
        new_files.append(paths[0])
    elif c == 'mode-only':
        (repo / paths[0]).chmod(0o755)
    elif c == 'delete':
        (repo / paths[0]).unlink()
    elif c == 'nested-repo':
        nested = repo / paths[0]
        nested.mkdir()
        git(nested, 'init', '-q')
        (nested / 'y.txt').write_text(line(row))
        commit(nested, 'nested')
    elif c == 'gitlink':
        sub = repo / paths[0]
        if layer == 'unstaged':                 # base has the gitlink at subsrc HEAD; check out HEAD~1 here
            if sub.exists():
                sub.rmdir()
            git(repo, 'clone', '-q', str(subsrc), paths[0])
            git(sub, 'checkout', '-q', 'HEAD~1')
            return
        sub.mkdir(exist_ok=True)                # unpopulated submodule directory
        git(repo, 'update-index', '--add', '--cacheinfo', f'160000,{base_sha},{paths[0]}')
        if layer == 'committed':
            git(repo, 'commit', '-q', '-m', 'gitlink')
        return
    if layer == 'committed':
        commit(repo, 'change')
    elif layer == 'staged':
        git(repo, 'add', '-A')
    elif layer == 'unstaged':
        if c in ('rename', 'mode-only', 'delete', 'modify') and not new_files:
            return
        if c != 'rename':                       # a worktree rename is a deletion plus an untracked file
            git(repo, 'add', '-N', '--', *new_files)


def make_subsrc(tmp):
    sub = tmp / 'subsrc'
    sub.mkdir()
    git(sub, 'init', '-q')
    for i in (1, 2):
        (sub / 'f').write_text(f'{i}\n')
        commit(sub, f's{i}')
    return sub


def builder(row):
    mode, state, rules = row['mode'], row['git'], row['rules']
    layer = row.get('layer', 'committed')

    def build(tmp):
        src = tmp / 'repo'
        src.mkdir()
        subsrc = make_subsrc(tmp)
        git(src, 'init', '-q', '-b', 'main')
        extra = base_files(row, src, subsrc)
        ctx = {'globs': BASE_GLOBS[rules], 'paths': change_paths(row)}
        if state == 'empty':                     # no commits: the change stays staged or untracked
            apply_change(row, src, 'untracked' if mode == 'target' else layer, subsrc, None)
            return finish(row, tmp, src, ctx, base='main')
        for _, path, sha in extra:
            (src / path).mkdir(parents=True, exist_ok=True)
            git(src, 'update-index', '--add', '--cacheinfo', f'160000,{sha},{path}')
        commit(src, 'init')
        base_sha = git(src, 'rev-parse', 'HEAD')
        git(src, 'checkout', '-q', '-b', 'feat')
        if state == 'multi-merge-base':          # criss-cross: merge-base --all main feat = {A, B}
            git(src, 'checkout', '-q', 'main')
            (src / 'cc-a.txt').write_text('a\n')
            commit(src, 'A')
            a = git(src, 'rev-parse', 'HEAD')
            git(src, 'checkout', '-q', 'feat')
            (src / 'cc-b.txt').write_text('b\n')
            commit(src, 'B')
            b = git(src, 'rev-parse', 'HEAD')
            git(src, 'merge', '-q', '--no-ff', '-m', 'Y', a)
            git(src, 'checkout', '-q', 'main')
            git(src, 'merge', '-q', '--no-ff', '-m', 'X', b)
            git(src, 'checkout', '-q', 'feat')
        if rules == 'absent-base':               # the rules file arrives with the change branch
            (src / RULES).parent.mkdir(parents=True, exist_ok=True)
            (src / RULES).write_text(BASE_RULES['normal'])
            commit(src, 'add rules')
        if mode == 'target' or layer == 'committed':
            apply_change(row, src, 'committed', subsrc, base_sha)
        if state == 'shallow':                   # feat must have its own commit for depth 1 to cut the history
            (src / 'feat-start.txt').write_text('start\n')
            commit(src, 'feat start')
        git(src, 'branch', 'feat-strict')
        if rules == 'loosened-head':
            (src / RULES).write_text(LOOSE)
            commit(src, 'loosen rules')
        base = 'main'
        if mode == 'target':
            git(src, 'tag', 'v1', 'feat')
            git(src, 'branch', 'amb-extra', 'feat')
            git(src, 'checkout', '-q', 'amb-extra')
            (src / 'extra.txt').write_text('extra\n')
            commit(src, 'extra')
            git(src, 'checkout', '-q', 'feat')
            git(src, 'tag', 'amb', 'feat')
            git(src, 'branch', 'amb', 'amb-extra')
            ctx['feat_sha'] = git(src, 'rev-parse', 'feat')
        if state == 'no-main':
            git(src, 'branch', '-m', 'main', 'trunk')
            base = 'trunk'
        elif state == 'no-merge-base':
            orphan = git(src, 'commit-tree', 'main^{tree}', '-m', 'orphan')
            git(src, 'branch', '-f', 'main', orphan)
        work = src
        if state == 'detached':
            git(src, 'checkout', '-q', '--detach', 'feat')
        elif state == 'shallow':
            git(src, 'checkout', '-q', 'main')
            work = tmp / 'clone'
            git(tmp, 'clone', '-q', '--depth', '1', '--no-single-branch', f'file://{src}', str(work))
            git(work, 'checkout', '-q', 'feat')
        elif state == 'linked-worktree':
            git(src, 'checkout', '-q', 'main')
            work = tmp / 'linked'
            git(src, 'worktree', 'add', '-q', str(work), 'feat')
        if row['change'] == 'gitlink' and layer == 'unstaged' and not (work / ctx['paths'][0]).exists():
            (work / ctx['paths'][0]).mkdir(parents=True)
        if mode != 'target' and layer != 'committed':
            apply_change(row, work, layer, subsrc, base_sha)
        return finish(row, tmp, work, ctx, base)
    return build


def finish(row, tmp, work, ctx, base):
    """Arguments, cwd and the facts the checks need."""
    mode, state = row['mode'], row['git']
    cwd = work / 'src' if state == 'subdir' else work
    ctx.update(work=work, cwd=cwd)
    if mode != 'target':
        rules_arg = f'../{RULES}' if state == 'subdir' else RULES
        args = [rules_arg] + ([base] if mode == 'wt2' else [])
        return Invocation(args, cwd, ctx)
    # An uncommitted matching file is outside the committed-target scope (R-C3).
    (work / 'src/auth').mkdir(parents=True, exist_ok=True)
    (work / 'src/auth/dirty.ts').write_text(HIT)
    outside = tmp / 'outside'
    outside.mkdir()
    (outside / 'human-review-rules').write_text(BASE_RULES['normal'])
    if row['rpath'] == 'symlink-out':
        (work / 'docs').mkdir(exist_ok=True)
        (work / 'docs/out').symlink_to(outside)
    rel = {'plain': RULES, 'dot': f'./{RULES}', 'dotdot': f'docs/../{RULES}', 'dslash': RULES.replace('/', '//', 1),
           'symlink-out': 'docs/out/human-review-rules'}[row['rpath']]
    rules_arg = f'{work}/{rel}' if state == 'subdir' else rel     # a relative ../ path is not normalized
    feat = ctx.get('feat_sha', '')
    head = {'branch': 'feat', 'tag': 'v1', 'short-sha': feat[:12], 'tree': 'feat^{tree}', 'blob': 'feat:README.md',
            'dash': '--all', 'ambiguous': 'amb'}[row['ref']]
    ctx['strict_args'] = [rules_arg, base, 'feat-strict']
    return Invocation([rules_arg, base, head], cwd, ctx)


# ---- expectations (hand-decided from contracts.md; no re-implementation of the script) ----

def exit3_reasons(row):
    mode, state, out = row['mode'], row['git'], []
    if state == 'empty':
        out.append(('R-C6', 'コミットが無く base/merge-base を解決できない'))
    if state == 'shallow':
        out.append(('R-INV2', 'shallow clone で merge-base が無い'))
    if state == 'no-merge-base':
        out.append(('R-INV2', 'merge-base が無い'))
    if state == 'no-main' and mode == 'wt1':
        out.append(('R-C2', 'base 省略で origin/main も main も無い'))
    if mode == 'target':
        if row['ref'] in ('tree', 'blob', 'dash'):
            out.append(('R-C3', f'head（{row["ref"]}）をコミットに固定できない'))
        if row['rpath'] == 'symlink-out':
            out.append(('R-C3', '規則パスがリポジトリ外'))
    if row['change'] == 'nested-repo':
        out.append(('R-C6', '未追跡の入れ子リポジトリは差分にできない'))
    if row['rules'] in ('empty', 'comments'):
        out.append(('R-C6', '有効な規則が 0 件'))
    if row['rules'] in ('missing-bar', 'bad-regex'):
        out.append(('R-C6', '規則の書式が不正'))
    return out


def undecided(row):
    """Inputs whose handling the contract does not conclude: exit 3 or the otherwise expected exit."""
    out = []
    if row['git'] == 'multi-merge-base':
        out.append('merge-base が複数')
    if row['mode'] == 'target':
        if row['ref'] == 'ambiguous':
            out.append('曖昧な ref（どちらの候補でも同じ判定になる）')
        if row['rpath'] in ('dot', 'dotdot', 'dslash'):
            out.append(f'正規化していない規則パス（{row["rpath"]}）')
    if row['rules'] == 'crlf':
        out.append('CRLF の規則ファイル')
    return out


def exit10_reasons(row):
    out = []
    if row['rules'] == 'absent-base':
        out.append(('R-C6', '規則ファイルが base に無い'))
    if row['change'] == 'gitlink':
        out.append(('R-C6', 'gitlink の変更'))
    matching = row['rules'] in RULES_WITH_MATCHING or (row['rules'] == 'absent-base' and row['mode'] != 'target')
    if matching and row['where'] == 'auth':
        out.append(('R-C4', 'path 規則 src/auth/* に一致（大文字小文字を区別しない）'))
    if matching and row['content'] == 'hit':
        out.append(('R-C4', 'content 規則に一致（追加・削除行）'))
    return out


def expect_exit(want, contract, text):
    allowed = want if isinstance(want, tuple) else (want,)
    return Expect(contract, text, lambda r: None if r.exit in allowed else f'exit {r.exit}, want {"/".join(map(str, allowed))}')


def glob_hits(run):
    """Base path globs that a scope path matches, using bash `[[ == ]]` with nocasematch (never fnmatch)."""
    hits = []
    for p in run.inv.ctx['paths']:
        for g in run.inv.ctx['globs']:
            rc = subprocess.run([run.bash, '-c', 'shopt -s nocasematch; [[ $1 == $2 ]]', '_', p, g]).returncode
            if rc == 0:
                hits.append((p, g))
    return hits


def check_inv1(run):
    hits = glob_hits(run)
    return f'exit 0 although {hits} match base path rules' if hits and run.exit == 0 else None


def check_inv3(run):
    ctx = run.inv.ctx
    proc = subprocess.run([run.bash, str(REPO / SCRIPT), *ctx['strict_args']], cwd=ctx['cwd'],
                          env=script_env(), capture_output=True, timeout=60)
    if proc.returncode != 0 and run.exit == 0:
        return f'loosened head exit 0, same change without loosening exit {proc.returncode}'
    return None


def expects(row):
    out = [Expect('R-C6', 'exit は 0 / 3 / 10 のどれか', lambda r: None if r.exit in (0, 3, 10) else f'exit {r.exit}'),
           Expect('R-INV1', '対象範囲の変更が base 版の path 規則に一致すれば exit ≠ 0（bash の [[ == ]] で判定）', check_inv1)]
    r3, r10, und = exit3_reasons(row), exit10_reasons(row), undecided(row)
    if r3:
        ids = sorted({c for c, _ in r3})
        if r10:
            # The 3-before-10 order is read from the implementation, not the contract: allow both.
            out.append(expect_exit((3, 10), 'R-INV2', '仕様未定（優先順位）: exit 3 の条件（' + '、'.join(t for _, t in r3)
                                   + '）と exit 10 の条件（' + '、'.join(t for _, t in r10) + '）が重なる。exit 3 / 10 のどちらも許す'))
        else:
            out.append(expect_exit(3, ids[0], 'exit 3: ' + '、'.join(t for _, t in r3)))
    else:
        want = 10 if r10 else 0
        contract = r10[0][0] if r10 else 'R-C6'
        text = f'exit {want}: ' + ('、'.join(t for _, t in r10) if r10 else '規則に一致する変更が無い')
        if und:
            out.append(expect_exit((3, want), contract, f'{text}。ただし {"、".join(und)} は契約に結論が無いので exit 3 も許す'))
        else:
            out.append(expect_exit(want, contract, text))
    if row['mode'] == 'target' and row['rules'] == 'loosened-head':
        out.append(Expect('R-INV3', 'head 側で規則を緩めても、緩めない head より判定が下がらない', check_inv3))
    return tuple(out)


def make(row):
    return Case(case_id('rr', row), SCRIPT, row, expects(row), builder(row))


# Values that make the script stop with exit 3 (or an undecided exit) mask the other values of the row.
# Pass 1 covers every pair of the remaining values in rows free of them; pass 2 adds the masking values.
MASKING = {'git': ('empty', 'shallow', 'no-merge-base', 'multi-merge-base'), 'change': ('nested-repo',),
           'rules': ('empty', 'comments', 'missing-bar', 'bad-regex'),
           'ref': ('tree', 'blob', 'dash', 'ambiguous'), 'rpath': ('dot', 'dotdot', 'dslash', 'symlink-out')}
CLEAN_AXES = {a: [v for v in vs if v not in MASKING.get(a, ())] for a, vs in AXES.items()}
CLEAN_EXCLUDE = [p for p in EXCLUDE if all(v in CLEAN_AXES[a] for a, v in p)] + [(('mode', 'wt1'), ('git', 'no-main'))]


# Pairwise covers pairs only, so pin the triples a pair can hide behind another match: R-INV3 needs a
# loosened target row whose base rules match, and each content-carrying kind needs a content-only match
# (where=lib) so that e.g. a rename or a deletion is checked line by line (R-C5).
TARGET = {'ref': 'branch', 'rpath': 'plain'}
PINNED = ([{'mode': 'target', 'git': 'normal', 'change': 'modify', 'where': 'auth', 'content': 'benign',
            'rules': 'loosened-head', **TARGET},
           {'mode': 'target', 'git': 'detached', 'change': 'nul', 'where': 'lib', 'content': 'hit',
            'rules': 'loosened-head', 'ref': 'tag', 'rpath': 'plain'}]
          + [{'mode': mode, 'git': 'normal', 'change': c, 'where': 'lib', 'content': 'hit',
              **({'layer': 'committed'} if mode == 'wt1' else {}), 'rules': 'normal', **({} if mode == 'wt1' else TARGET)}
             for c in ('rename', 'binary', 'nul', 'symlink', 'delete') for mode in ('wt1', 'target')])


@functools.cache
def rows():
    """Generated once per process (about 6 s): pairwise over these axes is slow."""
    existing = existing_rows(NAME) + PINNED
    clean = pairwise.generate(CLEAN_AXES, CLEAN_EXCLUDE, WHEN, covered=existing)
    return tuple(PINNED + clean + pairwise.generate(AXES, EXCLUDE, WHEN, covered=existing + clean))


def cases():
    return [make(dict(row)) for row in rows()]
