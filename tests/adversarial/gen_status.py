"""L1 cases for skills/ains/scripts/status.sh (contracts S-C*, invariants S-INV*; see contracts.md)."""
import re

import pairwise
from l1lib import Case, Expect, Invocation, UNSPECIFIED, case_id, existing_rows

NAME = 'status'
SCRIPT = 'skills/ains/scripts/status.sh'
HAS_ROOT = ('default', 'relative', 'absolute')
FM_TASKS = ('template', 'done-x', 'indent', 'no-tnum')
AXES = {
    'root': ['default', 'relative', 'absolute', 'absent'],
    'dir': ['date', 'nondate', 'space', 'newline', 'dash', 'symlink', 'broken-link', 'hidden', 'no-spec'],
    'fm': ['normal', 'nospace', 'tab', 'trail-ws', 'lead-ws', 'quoted', 'comment', 'crlf', 'body-cr',
           'bom', 'blank-first', 'upper-key', 'no-close', 'dup-same', 'dup-diff'],
    'heading': ['standard', 'suffix', 'h3', 'nospace', 'none'],
    'tasks': ['none', 'empty', 'template', 'done-x', 'indent', 'no-tnum'],
    'spec_value': ['approved', 'draft'],
    'plan_value': ['approved', 'draft'],
}
EXCLUDE = []
WHEN = {**{a: ('root', HAS_ROOT) for a in ('dir', 'fm', 'heading', 'tasks', 'spec_value')},
        'plan_value': ('tasks', FM_TASKS)}

COMPANION = '2026-01-01-base'
SUBJECT = {'date': ['2026-10-25-subject'], 'nondate': ['subject'], 'space': ['2026-10-24-sub ject'],
           'newline': ['2026-10-23-sub\nject'], 'dash': ['-subject'],
           'symlink': ['2026-10-22-link', '2026-10-21-real'], 'broken-link': [], 'hidden': [], 'no-spec': []}
VISIBLE = ('date', 'nondate', 'space', 'dash', 'symlink')
# The front matter's meaning as YAML when it says approved (S-INV1 table); None = unspecified.
INTENT = {'normal': True, 'nospace': True, 'tab': True, 'trail-ws': True, 'lead-ws': True, 'quoted': True,
          'comment': True, 'crlf': True, 'bom': True, 'dup-same': True, 'blank-first': False,
          'upper-key': False, 'body-cr': None, 'no-close': None, 'dup-diff': None}
BODY_SAFE = tuple(s for s in AXES['fm'] if s not in ('crlf', 'body-cr'))   # styles that leave body lines alone
LINE = re.compile(r'^(?P<name>.*?)  status=(?P<status>.*?)  plan=(?P<plan>.*?)  未決=(?P<q>\d+)  tasks=(?P<done>\d+)/(?P<total>\d+)$')
TASKS = {'template': '- [ ] T1: \n- [ ] T2: \n',
         'done-x': '- [X] T1: first\n- [x] T2: second\n- [ ] T3: third\n',
         'indent': '  - [x] T1: first\n\t- [ ] T2: second\n',
         'no-tnum': '- [x] first\n- [ ] second\n'}
HEADINGS = {'standard': '## 未決事項', 'suffix': '## 未決事項（2件）', 'h3': '### 未決事項', 'nospace': '##未決事項'}


def front_matter(style, value):
    other = 'draft' if value == 'approved' else 'approved'
    line = {'nospace': f'status:{value}', 'tab': f'status:\t{value}', 'trail-ws': f'status: {value}  ',
            'lead-ws': f'  status: {value}', 'quoted': f'status: "{value}"', 'comment': f'status: {value} # note',
            'upper-key': f'Status: {value}', 'dup-same': f'status: {value}\nstatus: {value}',
            'dup-diff': f'status: {value}\nstatus: {other}'}.get(style, f'status: {value}')
    head = '\n' if style == 'blank-first' else ('﻿' if style == 'bom' else '')
    return head + '---\n' + line + '\n' + ('' if style == 'no-close' else '---\n')


def encode(style, text):
    if style == 'crlf':
        return text.replace('\n', '\r\n')
    if style == 'body-cr':
        first, _, rest = text.partition('\n')
        return first + '\n' + rest.replace('\n', '\r\n')
    return text


def spec_text(row):
    heading = HEADINGS.get(row['heading'])
    section = f'{heading}\n\n- q1\n- q2\n' if heading else '## 目的\n\n- goal\n'
    return encode(row['fm'], front_matter(row['fm'], row['spec_value']) + f'\n# subject\n\n{section}\n## 次\n\n- not counted\n')


def tasks_text(row):
    if row['tasks'] == 'empty':
        return ''
    return encode(row['fm'], front_matter(row['fm'], row['plan_value']) + '\n## タスク\n\n' + TASKS[row['tasks']])


def builder(row):
    def build(tmp):
        work = tmp / 'work'
        work.mkdir()
        rootdir = {'default': work / 'docs/changes', 'relative': work / 'rel/changes',
                   'absolute': work / 'abs root/changes', 'absent': work / 'absent'}[row['root']]
        args = {'default': [], 'relative': ['rel/changes']}.get(row['root'], [str(rootdir)])
        if row['root'] == 'absent':
            return Invocation(args, work, {'root': rootdir, 'arg': str(rootdir)})
        rootdir.mkdir(parents=True)
        base = rootdir / COMPANION
        base.mkdir()
        (base / 'spec.md').write_text('---\nstatus: draft\n---\n')
        d = row['dir']
        if d == 'broken-link':
            (rootdir / '2026-10-22-broken').symlink_to('missing-target')
        else:
            real = rootdir / {'symlink': '2026-10-21-real', 'hidden': '.2026-10-20-hidden',
                              'no-spec': '2026-10-25-nospec'}.get(d, SUBJECT[d][0] if SUBJECT[d] else '')
            real.mkdir()
            if d != 'no-spec':
                (real / 'spec.md').write_bytes(spec_text(row).encode())
            if row['tasks'] != 'none':
                (real / 'tasks.md').write_bytes(tasks_text(row).encode())
            if d == 'symlink':
                (rootdir / '2026-10-22-link').symlink_to('2026-10-21-real')
        return Invocation(args, work, {'root': rootdir, 'arg': args[0] if args else 'docs/changes'})
    return build


def is_approved(value):
    """S-INV1 predicate: the value between `status=`/`plan=` and the next two spaces is exactly approved."""
    return value == 'approved'


def lines(run):
    return [m for m in map(LINE.match, run.stdout.split('\n')) if m]


def subject_lines(run, row):
    return [m for m in lines(run) if m['name'] in SUBJECT[row['dir']]]


def check_inv1(row):
    def intent(which):
        if which == 'plan' and row['tasks'] not in FM_TASKS:
            return False
        value = row['spec_value'] if which == 'status' else row['plan_value']
        return INTENT[row['fm']] if value == 'approved' else (None if row['fm'] == 'dup-diff' else False)

    def test(run):
        for m in lines(run):
            for which in ('status', 'plan'):
                allowed = False if m['name'] == COMPANION else intent(which)
                if is_approved(m[which]) and allowed is False:
                    return f'{m["name"]!r}: {which}=approved although the front matter ({row["fm"]}) does not declare approved'
        return None
    return test


def check_inv2(run):
    root = run.inv.ctx['root']
    want = sum(1 for p in root.iterdir() if not p.name.startswith('.') and p.is_dir() and (p / 'spec.md').is_file())
    got = sum(' status=' in line for line in run.stdout.split('\n'))
    return None if got == want else f'{got} status lines for {want} change dirs with spec.md'


def check_inv3(run):
    dates = [m['name'][:10] for m in lines(run) if re.match(r'\d{4}-\d{2}-\d{2}', m['name'])]
    bad = [(a, b) for a, b in zip(dates, dates[1:]) if a < b]
    return f'older before newer: {bad}' if bad else None


def expect_subject(row, field, want, contract, text):
    def test(run):
        got = subject_lines(run, row)
        if not got:
            return f'no line for {SUBJECT[row["dir"]]}'
        bad = [m[field] if isinstance(field, str) else (m['done'], m['total']) for m in got]
        return None if all(b == want for b in bad) else f'{field}: {bad} != {want}'
    return Expect(contract, text, test)


def route(m):
    """Row of skills/ains/SKILL.md:28-35 that a status.sh line selects; None = no row."""
    s, p, done, total = m['status'], m['plan'], int(m['done']), int(m['total'])
    if s == 'draft':
        return 'ains-spec'
    if s == 'approved' and p == '-' and total == 0:
        return 'ains-tasks'
    if p == 'draft':
        return 'ains-tasks'
    if done < total:
        return 'ains-build'
    if total and done == total:
        return 'ains-ship'
    return None


def expects(row):
    out = [Expect('S-INV4', 'exit 0', lambda r: None if r.exit == 0 else f'exit {r.exit}')]
    if row['root'] == 'absent':
        out.append(Expect('S-C7', 'stdout は「変更ディレクトリがない: <root>」の1行',
                          lambda r: None if r.stdout == f'変更ディレクトリがない: {r.inv.ctx["arg"]}\n' else f'stdout {r.stdout!r}'))
        out.append(Expect('S-INV2', 'status 行は 0 行', check_inv2))
        return tuple(out)
    if INTENT[row['fm']] is None:
        out.append(Expect(UNSPECIFIED, f'S-INV1: {row["fm"]} の front matter は判定が未定なので記録する'))
    out.append(Expect('S-INV1', 'approved と出るのは、YAML として approved を宣言した front matter だけ', check_inv1(row)))
    if row['dir'] == 'newline':
        out.append(Expect(UNSPECIFIED, 'S-INV2/S-INV3: 改行入りのディレクトリ名は記録する'))
    else:
        out.append(Expect('S-INV2', 'status 行の数 = root/*/ の glob で spec.md を持つディレクトリの数', check_inv2))
        out.append(Expect('S-INV3', '日付形式の名前は日付の新しい順', check_inv3))
    if row['root'] == 'default':
        out.append(Expect('S-C7', '引数なしは docs/changes を読む（companion の行がある）',
                          lambda r: None if any(m['name'] == COMPANION for m in lines(r)) else 'companion line missing'))
    if row['dir'] not in VISIBLE:
        return tuple(out)
    if row['fm'] == 'normal':
        out.append(expect_subject(row, 'status', row['spec_value'], 'S-C1', f'status={row["spec_value"]}'))
        plan = {'none': '-', 'empty': 'draft'}.get(row['tasks'], row.get('plan_value'))
        out.append(expect_subject(row, 'plan', plan, 'S-C3' if plan != '-' else 'S-C4', f'plan={plan}'))
    if row['fm'] in BODY_SAFE:
        q = {'standard': '2', 'none': '0'}.get(row['heading'])
        if q:
            out.append(expect_subject(row, 'q', q, 'S-C8', f'未決={q}'))
        else:
            out.append(Expect(UNSPECIFIED, f'未決: 見出し {row["heading"]} の数え方は記録する'))
        tasks = {'none': ('0', '0'), 'empty': ('0', '0'), 'template': ('0', '0'), 'done-x': ('2', '3')}.get(row['tasks'])
        if tasks:
            out.append(expect_subject(row, None, tasks, 'S-C6', f'tasks={tasks[0]}/{tasks[1]}'))
        else:
            out.append(Expect(UNSPECIFIED, f'tasks: {row["tasks"]} の数え方は記録する'))
    out.append(Expect(UNSPECIFIED, 'S-C9: SKILL.md の表での行き先を記録する（どの行にも当たらなければ仕様未定）'))
    return tuple(out)


def observe(row):
    def obs(run):
        return {'route': {m['name']: route(m) for m in subject_lines(run, row)}} if row.get('dir') in VISIBLE else {}
    return obs


def make(row):
    return Case(case_id('st', row), SCRIPT, row, expects(row), builder(row), observe(row))


def cases():
    return [make(row) for row in pairwise.generate(AXES, EXCLUDE, WHEN, covered=existing_rows(NAME))]
