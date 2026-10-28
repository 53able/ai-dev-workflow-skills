"""Grading: run each grader of a case, save evidence, aggregate to summary.md.

Standard library only. Layout per trial: <out_dir>/grades.json plus
graders/<id>.{stdout,stderr} (command) or graders/<id>.{prompt.md,raw.txt} (llm).
"""
import collections
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from evallib import Case, Summary, git_env

# One grading model for every product under test, so pass rates are comparable.
GRADER_MODEL = os.environ.get('EVAL_GRADER_MODEL', 'claude-sonnet-5-5')
COMMAND_TIMEOUT = 120
LLM_TIMEOUT = 300
MAX_DIFF_CHARS = 60000

# No user settings/plugins/MCP/skills, no tools, no session files.
CLAUDE_ARGS = ['claude', '-p', '--model', GRADER_MODEL, '--tools', '', '--setting-sources', '',
               '--disable-slash-commands', '--strict-mcp-config', '--no-session-persistence']

OUTPUT_RULES = ('Reply with exactly one JSON object and nothing else: '
                '{"pass": true|false, "reason": "<short reason>"}')


# Compiled Python is noise for the grader; binary files show as one "Binary files differ" line.
DIFF_EXCLUDES = [':(exclude,glob)**/__pycache__/**', ':(exclude,glob)**/*.pyc']


def _git(workdir, *args, env=None):
    p = subprocess.run(['git', *args], cwd=workdir, text=True, capture_output=True, env=env or git_env())
    return p.stdout if p.returncode == 0 else f'(git {" ".join(args)} failed: {p.stderr.strip()})'


def _clip(text):
    return text if len(text) <= MAX_DIFF_CHARS else text[:MAX_DIFF_CHARS] + '\n...(truncated)'


def collect_git_evidence(workdir):
    """Diff from the initial commit including untracked files, and git log."""
    roots = _git(workdir, 'rev-list', '--max-parents=0', 'HEAD').split()
    base = roots[-1] if roots and not roots[0].startswith('(') else 'HEAD'
    # -N records untracked files as intent-to-add so they appear in the diff. It runs on a
    # copy of the index so the real index, which command graders read, stays unchanged.
    index = Path(workdir) / _git(workdir, 'rev-parse', '--git-path', 'index').strip()
    with tempfile.TemporaryDirectory(prefix='ains-grade-index-') as tmp:
        env = {**git_env(), 'GIT_INDEX_FILE': str(Path(tmp) / 'index')}
        if index.is_file():
            shutil.copy(index, env['GIT_INDEX_FILE'])
        subprocess.run(['git', 'add', '-A', '-N'], cwd=workdir, capture_output=True, env=env)
        diff = _git(workdir, 'diff', base, '--', '.', *DIFF_EXCLUDES, env=env)
    return _clip(diff), _clip(_git(workdir, 'log', '--stat', '--format=%h %s'))


def build_llm_prompt(case: Case, grader, summary: Summary, diff: str, log: str) -> str:
    shown = {k: v for k, v in summary.items() if k != 'prompt_sent'}
    return (f'You are grading one run of an AI coding agent against a rubric.\n\n'
            f'## Rubric\n{grader.body.strip()}\n\n'
            f'## Request given to the agent\n{case.prompt.strip()}\n\n'
            f'## Expected outcome\n{case.expected_outcome.strip()}\n\n'
            f'## Run summary (JSON)\n{json.dumps(shown, ensure_ascii=False, indent=2)}\n\n'
            f'## git diff (initial commit to final state, untracked files included)\n{diff}\n\n'
            f'## git log\n{log}\n\n{OUTPUT_RULES}\n')


def call_claude(prompt: str) -> str:
    """Default LLM caller. cwd is a fresh temp dir outside the workdir."""
    with tempfile.TemporaryDirectory(prefix='ains-grader-') as cwd:
        p = subprocess.run(CLAUDE_ARGS, input=prompt, cwd=cwd, text=True, capture_output=True,
                           timeout=LLM_TIMEOUT)
    if p.returncode != 0:
        raise RuntimeError(f'claude exited {p.returncode}: {p.stderr.strip()[:500]}')
    return p.stdout


_FENCE = re.compile(r'\A```(?:json)?[ \t]*\n(.*)\n```\Z', re.S)


def parse_verdict(raw: str):
    """Return (pass, reason) or raise ValueError.

    Strict: the whole output must be one JSON object with exactly the keys
    pass (bool) and reason (str). The only leniency is surrounding whitespace and a
    single wrapping code fence, which models add habitually without changing the
    content; prose around JSON, extra keys or wrong types are rejected so a
    malformed answer never counts as a pass.
    """
    text = raw.strip()
    m = _FENCE.match(text)
    if m:
        text = m.group(1).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f'not JSON: {exc}')
    if not isinstance(obj, dict) or set(obj) != {'pass', 'reason'}:
        raise ValueError(f'expected exactly keys pass, reason; got {obj if not isinstance(obj, dict) else sorted(obj)}')
    if not isinstance(obj['pass'], bool) or not isinstance(obj['reason'], str):
        raise ValueError('pass must be bool and reason must be str')
    return obj['pass'], obj['reason']


def _result(grader, status, reason):
    return {'grader': grader.id, 'type': grader.type, 'status': status, 'reason': reason}


def grade_command(grader, workdir, evidence_dir):
    try:
        p = subprocess.run(['bash', '-c', grader.run], cwd=workdir, text=True, capture_output=True,
                           timeout=COMMAND_TIMEOUT, env=git_env())
    except subprocess.TimeoutExpired as exc:
        (evidence_dir / f'{grader.id}.stdout').write_text(_text(exc.stdout))
        (evidence_dir / f'{grader.id}.stderr').write_text(_text(exc.stderr))
        return _result(grader, 'error', f'timeout after {COMMAND_TIMEOUT}s')
    (evidence_dir / f'{grader.id}.stdout').write_text(p.stdout)
    (evidence_dir / f'{grader.id}.stderr').write_text(p.stderr)
    return _result(grader, 'pass' if p.returncode == 0 else 'fail', f'exit code {p.returncode}')


def _text(v):
    return v.decode(errors='replace') if isinstance(v, bytes) else (v or '')


def grade_llm(case, grader, workdir, summary, evidence_dir, llm):
    diff, log = collect_git_evidence(workdir)
    prompt = build_llm_prompt(case, grader, summary, diff, log)
    (evidence_dir / f'{grader.id}.prompt.md').write_text(prompt)
    try:
        raw = llm(prompt)
    except Exception as exc:  # noqa: BLE001 - any caller failure is an error, not a fail
        return _result(grader, 'error', f'llm call failed: {exc}')
    (evidence_dir / f'{grader.id}.raw.txt').write_text(raw)
    try:
        ok, reason = parse_verdict(raw)
    except ValueError as exc:
        return _result(grader, 'error', f'invalid grader output: {exc}')
    return _result(grader, 'pass' if ok else 'fail', reason)


def trial_status(graders: list[dict]) -> str:
    statuses = {g['status'] for g in graders}
    if 'error' in statuses:
        return 'error'
    return 'pass' if statuses == {'pass'} else 'fail'


def grade(case: Case, workdir: Path, summary: Summary, out_dir: Path, llm=None) -> list[dict]:
    """Return one result dict per grader (name order) and write grades.json.

    llm: callable(prompt) -> raw text; defaults to call_claude. Inject a stub in tests.
    """
    llm = llm or call_claude
    out_dir.mkdir(parents=True, exist_ok=True)
    evidence = out_dir / 'graders'
    evidence.mkdir(exist_ok=True)
    results = []
    for g in sorted(case.graders, key=lambda g: g.id):
        if g.type == 'command':
            results.append(grade_command(g, workdir, evidence))
        elif g.type == 'llm':
            results.append(grade_llm(case, g, workdir, summary, evidence, llm))
        else:
            results.append(_result(g, 'error', f'unknown grader type {g.type!r}'))
    (out_dir / 'grades.json').write_text(json.dumps(
        {'status': trial_status(results), 'grader_model': GRADER_MODEL, 'graders': results},
        ensure_ascii=False, indent=2))
    return results


# Error message pattern -> category used as the summary.md key. First match wins; the
# full message stays in the trial's summary.json / grades.json.
ERROR_CATEGORIES = [
    (r'^runner raised', 'runner exception'),
    (r'^adapter raised', 'adapter exception'),
    (r'^unexpected context', 'unexpected context'),
    (r'^timeout after', 'timeout'),
    (r'^max_turns', 'max_turns'),
    (r'^skill not invoked', 'skill not invoked'),
    (r'cannot start|failed to start', 'start failed'),
    (r'exited with', 'exit'),
    (r'^llm call failed', 'llm call failed'),
    (r'^invalid grader output', 'invalid grader output'),
]


def error_category(message: str) -> str:
    for pattern, category in ERROR_CATEGORIES:
        if re.search(pattern, message):
            return category
    return 'other'


def error_reason(result: dict) -> str | None:
    """Category of why a trial counts as error, or None. Summary error wins; else first grader error."""
    err = result['summary'].get('error')
    if err:
        return error_category(err)
    for g in result['graders']:
        if g['status'] == 'error':
            return f'grader {error_category(g["reason"])}'
    return None


# git commit / push / merge in a shell command, also with options before the subcommand
# (git -c k=v commit). Codex's workspace-write sandbox makes .git read-only, so "did not
# commit/push" graders pass trivially there; attempts are recorded, not judged.
_GIT_WRITE = re.compile(r'\bgit\b(?:\s+-{1,2}[^\s;&|]+(?:\s+[^\s;&|-][^\s;&|]*)?)*\s+(commit|push|merge)(?![\w-])')


_DRY_PUSH = re.compile(r'(--dry-run|\s-n)(?![\w-])')


def _writes(part: str) -> bool:
    m = _GIT_WRITE.search(part)
    return bool(m) and not (m.group(1) == 'push' and _DRY_PUSH.search(part, m.end()))


def git_write_attempts(commands: list[str]) -> list[str]:
    """Commands with a git commit/push/merge in any of their ;/&&/||/| parts.

    `git push --dry-run` writes nothing, so that part alone is not counted.
    """
    return [c for c in commands if any(_writes(p) for p in re.split(r'&&|\|\||[;|&\n]', c))]


def write_summary(run_dir: Path, results: list[dict], now=None) -> None:
    """Write <run_dir>/summary.md.

    Each result: {'product', 'case', 'trial', 'graders': list[dict], 'summary': Summary}.
    Trials whose summary has an error carry graders == [] and count as error.
    """
    now = now or datetime.datetime.now().astimezone()
    cells = collections.defaultdict(lambda: collections.Counter())
    reasons = collections.defaultdict(collections.Counter)
    meta = collections.defaultdict(lambda: {'version': set(), 'model': set(), 'ignored': set(), 'git': 0})
    git_writes = []
    by_grader = collections.defaultdict(collections.Counter)
    for r in results:
        key = (r['product'], r['case'])
        status = 'error' if r['summary'].get('error') else trial_status(r['graders'])
        cells[key]['trials'] += 1
        cells[key][status] += 1
        for gr in r['graders']:
            by_grader[(r['product'], r['case'], gr['grader'])][gr['status']] += 1
        if status == 'error':
            reasons[r['product']][error_reason(r) or 'unknown'] += 1
        m = meta[r['product']]
        s = r['summary']
        m['version'].add(s.get('cli_version') or '-')
        m['model'].add(s.get('model') or '-')
        m['ignored'].update(s.get('ignored_options') or [])
        attempts = git_write_attempts(s.get('commands') or [])
        m['git'] += bool(attempts)
        git_writes += [f'- {r["product"]}/{r["case"]}/{r["trial"]}: `{c[:200]}`' for c in attempts]
    lines = ['# eval summary', '', f'- run: {run_dir.name}', f'- date: {now.isoformat(timespec="seconds")}',
             f'- grader model: {GRADER_MODEL}', '']
    lines += ['## products', '',
              '| product | CLI version | subject model | ignored options | git write attempts (trials) |',
              '|---|---|---|---|---|']
    for p in sorted(meta):
        m = meta[p]
        lines.append(f'| {p} | {", ".join(sorted(m["version"]))} | {", ".join(sorted(m["model"]))} | '
                     f'{", ".join(sorted(m["ignored"])) or "none"} | {m["git"]} |')
    lines += ['', '## pass rate (pass / trials)', '', '| product | case | pass | fail | error | trials |',
              '|---|---|---|---|---|---|']
    for (p, c) in sorted(cells):
        n = cells[(p, c)]
        lines.append(f'| {p} | {c} | {n["pass"]}/{n["trials"]} | {n["fail"]} | {n["error"]} | {n["trials"]} |')
    # Per grader, so a product comparison can leave one grader out. Trials that ended in a
    # summary error carry no grader results and are not counted here (see 'pass rate' for them).
    lines += ['', '## pass rate by grader (graded trials only)', '', '| product | case | grader | pass | fail | error |',
              '|---|---|---|---|---|---|']
    for (p, c, gid) in sorted(by_grader):
        n = by_grader[(p, c, gid)]
        lines.append(f'| {p} | {c} | {gid} | {n["pass"]} | {n["fail"]} | {n["error"]} |')
    lines += ['', '## errors by reason', '']
    if not reasons:
        lines.append('none')
    else:
        lines += ['| product | reason | count |', '|---|---|---|']
        for p in sorted(reasons):
            for reason, count in sorted(reasons[p].items()):
                lines.append(f'| {p} | {reason} | {count} |')
        lines += ['', 'Details: summary.json and grades.json in each trial directory.']
    lines += ['', '## git write attempts', '', *(git_writes or ['none'])]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / 'summary.md').write_text('\n'.join(lines) + '\n')
