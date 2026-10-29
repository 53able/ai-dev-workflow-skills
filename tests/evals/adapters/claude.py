"""claude adapter: run a case with `claude -p` and summarize its stream-json output."""
import json
import os
from pathlib import Path
import subprocess

from evallib import Case, Summary, clip, empty_summary, kill_group, subject_env, track

SKILL_DIR = '.claude/skills/'
# Pinned so pass rates stay comparable across runs; override with EVAL_CLAUDE_MODEL.
DEFAULT_MODEL = 'claude-sonnet-5-5'
EDIT_TOOLS = {'Write': 'file_path', 'Edit': 'file_path', 'NotebookEdit': 'notebook_path'}
# Keep user-level settings (~/.claude settings, hooks, plugins) and MCP servers out of the
# run; stream-json carries the first one only when it is the 'project' source.
ISOLATION_ARGS = ['--setting-sources', 'project', '--strict-mcp-config', '--permission-mode', 'dontAsk']
# subject_env(): the agent's git ignores the user's global git config, as in scaffold and
# grading, and cannot reach real remotes, ssh or GitHub.
ISOLATION_ENV = {'CLAUDE_CODE_DISABLE_AUTO_MEMORY': '1'}
# HOME is the user's (the CLI needs its login), so Bash runs in Claude Code's sandbox: no
# reads under ~, no network, and no start without the sandbox. Read/Edit deny rules cover the
# file tools, which the sandbox does not confine. Passed with --settings, so nothing is
# written into the working copy.
SANDBOX_SETTINGS = {
    'sandbox': {'enabled': True, 'failIfUnavailable': True, 'allowUnsandboxedCommands': False,
                'filesystem': {'denyRead': ['~/']},
                'network': {'allowedDomains': [], 'strictAllowlist': True}},
    # The file tools: ~ in both the ~/ and the absolute //<home>/ form, and no writes to the
    # project settings or git internals (a rewritten .claude/settings.json could loosen the
    # sandbox; .git/config could make the grader's git run a program).
    'permissions': {'deny': ['Read(~/**)', 'Edit(~/**)', f'Read(/{Path.home()}/**)', f'Edit(/{Path.home()}/**)',
                             'Edit(/.claude/**)', 'Edit(/.git/**)', 'WebFetch', 'WebSearch',
                             # The sandbox still lets `security` reach the login keychain (measured,
                             # Claude Code 2.1.312). Prefix rules only slow this down; see the plan.
                             'Bash(security *)', 'Bash(/usr/bin/security *)']},
}


def _rel(path: str, workdir: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(workdir).resolve()))
    except ValueError:
        return path


def _events(lines):
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict):
            yield ev


def init_event(lines) -> dict:
    """The system/init event of the stream, or {}."""
    return next((ev for ev in _events(lines) if ev.get('type') == 'system' and ev.get('subtype') == 'init'), {})


def check_init(init: dict, workdir: Path, allowed_tools) -> str | None:
    """Error message if the session saw more than the working copy and the allowed tools.

    The init event lists no memory/CLAUDE.md files, so only cwd, additional directories
    and the provided tools are checked.
    """
    if not init:
        return 'unexpected context: no init event'
    if Path(init.get('cwd') or '').resolve() != Path(workdir).resolve():
        return f'unexpected context: cwd {init.get("cwd")!r} is not the working copy'
    if init.get('additional_directories'):
        return f'unexpected context: additional directories {init["additional_directories"]}'
    extra = sorted(set(init.get('tools') or []) - set(allowed_tools or init.get('tools') or []))
    if extra:
        return f'unexpected context: tools outside allowed_tools: {", ".join(extra)}'
    return None


def _result_text(content) -> str:
    if isinstance(content, list):
        return '\n'.join(str(b.get('text', '')) for b in content if isinstance(b, dict))
    return str(content or '')


def summarize(lines, workdir: Path = Path('.'), prompt: str = '') -> Summary:
    """Pure conversion of stream-json lines (iterable of str) into a Summary.

    Lines that are not valid JSON are skipped. cli_version and prompt_sent are
    not in the stream; the caller fills them in.

    A prompt starting with `/name` where name is a skill listed in the init event
    expands the skill without a Skill tool_use, so it is recorded as invoked. A
    `/ains...` name that is not listed is a `skill not invoked` error, as in codex.
    """
    s = empty_summary()
    skills = []
    result_error = None
    for ev in _events(lines):
        kind = ev.get('type')
        if kind == 'system' and ev.get('subtype') == 'init':
            s['model'] = ev.get('model') or s['model']
            skills = ev.get('skills') or []
        elif kind == 'assistant':
            msg = ev.get('message') or {}
            s['model'] = s['model'] or msg.get('model', '')
            for block in msg.get('content') or []:
                if not isinstance(block, dict) or block.get('type') != 'tool_use':
                    continue
                name, inp = block.get('name'), block.get('input') or {}
                s['timeline'].append({'type': 'tool_use', 'name': name,
                                      'input': clip(json.dumps(inp, ensure_ascii=False))})
                if name == 'Bash' and inp.get('command'):
                    s['commands'].append(inp['command'])
                elif name in EDIT_TOOLS and inp.get(EDIT_TOOLS[name]):
                    f = _rel(inp[EDIT_TOOLS[name]], workdir)
                    if f not in s['edited_files']:
                        s['edited_files'].append(f)
                elif name == 'Skill' and inp.get('skill'):
                    s['invoked_skills'].append(inp['skill'])
        elif kind == 'user':
            for block in (ev.get('message') or {}).get('content') or []:
                if isinstance(block, dict) and block.get('type') == 'tool_result':
                    s['timeline'].append({'type': 'tool_result', 'output': clip(_result_text(block.get('content'))),
                                          'is_error': bool(block.get('is_error'))})
        elif kind == 'result':
            s['final_response'] = ev.get('result') or ''
            subtype = str(ev.get('subtype', 'success'))
            if subtype == 'error_max_turns':
                result_error = f'max_turns: result {subtype}: {s["final_response"][:200]}'
            elif ev.get('is_error') or subtype != 'success':
                result_error = f'result {subtype}: {s["final_response"][:200]}'
    first = prompt.split(None, 1)[0] if prompt.strip() else ''
    if first.startswith('/') and first[1:] in skills:
        s['invoked_skills'].insert(0, first[1:])
    elif first.startswith('/ains'):
        result_error = result_error or f'skill not invoked: {first[1:]}'
    if result_error:
        s['error'] = result_error
    return s


def _cli_version() -> str:
    try:
        r = subprocess.run(['claude', '--version'], capture_output=True, text=True, timeout=30)
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def run(case: Case, workdir: Path, out_dir: Path) -> Summary:
    """Run case.prompt in workdir with claude; raw stream-json and stderr go under out_dir.

    Failures (timeout, non-zero exit, missing CLI) are returned in Summary['error'].
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model = os.environ.get('EVAL_CLAUDE_MODEL') or DEFAULT_MODEL
    cmd = ['claude', '-p', '--output-format', 'stream-json', '--verbose', '--model', model,
           '--max-turns', str(case.max_turns), *ISOLATION_ARGS, '--settings', json.dumps(SANDBOX_SETTINGS)]
    if case.allowed_tools:
        # --tools limits the tools provided (no Agent unless listed); --allowedTools only
        # pre-approves, which dontAsk needs.
        tools = ','.join(case.allowed_tools)
        cmd += ['--tools', tools, '--allowedTools', tools]
    env = {**subject_env(login={'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN'}), **ISOLATION_ENV}
    error = None
    try:
        proc = subprocess.Popen(cmd, cwd=workdir, env=env, text=True, start_new_session=True,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        s = empty_summary()
        s['prompt_sent'], s['error'] = case.prompt, f'cannot start claude: {e}'
        return s
    try:
        track(proc)
        stdout, stderr = proc.communicate(case.prompt, timeout=case.timeout_seconds)
        if proc.returncode != 0:
            error = f'claude exited with code {proc.returncode}'
    except subprocess.TimeoutExpired:
        kill_group(proc)
        stdout, stderr = proc.communicate()
        error = f'timeout after {case.timeout_seconds}s'
    finally:
        kill_group(proc)   # also on interrupt, and any leftover children
    (out_dir / 'transcript.jsonl').write_text(stdout or '')
    (out_dir / 'stderr.txt').write_text(stderr or '')
    lines = (stdout or '').splitlines()
    init = init_event(lines)
    (out_dir / 'init.json').write_text(json.dumps(init, ensure_ascii=False, indent=2))
    s = summarize(lines, workdir, case.prompt)
    s['prompt_sent'] = case.prompt
    s['cli_version'] = _cli_version()
    s['model'] = s['model'] or model
    # error_max_turns also exits non-zero; keep the more specific max_turns reason.
    if error and not (s['error'] or '').startswith('max_turns'):
        s['error'] = error + (f': {stderr.strip()[:200]}' if stderr and stderr.strip() else '')
    s['error'] = s['error'] or check_init(init, workdir, case.allowed_tools)
    s['ignored_options'] = []
    return s
