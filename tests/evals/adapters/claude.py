"""claude adapter: run a case with `claude -p` and summarize its stream-json output."""
import json
import os
from pathlib import Path
import signal
import subprocess

from evallib import Case, Summary, empty_summary

SKILL_DIR = '.claude/skills/'
# Pinned so pass rates stay comparable across runs; override with EVAL_CLAUDE_MODEL.
DEFAULT_MODEL = 'claude-sonnet-5-5'
EDIT_TOOLS = {'Write': 'file_path', 'Edit': 'file_path', 'NotebookEdit': 'notebook_path'}
# Keep user-level settings (~/.claude settings, hooks, plugins) and MCP servers out of the
# run; stream-json carries the first one only when it is the 'project' source.
ISOLATION_ARGS = ['--setting-sources', 'project', '--strict-mcp-config', '--permission-mode', 'dontAsk']
ISOLATION_ENV = {'CLAUDE_CODE_DISABLE_AUTO_MEMORY': '1'}


def _rel(path: str, workdir: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(workdir).resolve()))
    except ValueError:
        return path


def summarize(lines, workdir: Path = Path('.'), prompt: str = '') -> Summary:
    """Pure conversion of stream-json lines (iterable of str) into a Summary.

    Lines that are not valid JSON are skipped. cli_version and prompt_sent are
    not in the stream; the caller fills them in.

    A prompt starting with `/name` where name is a skill listed in the init event
    expands the skill without a Skill tool_use, so it is recorded as invoked.
    """
    s = empty_summary()
    skills = []
    result_error = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
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
                if name == 'Bash' and inp.get('command'):
                    s['commands'].append(inp['command'])
                elif name in EDIT_TOOLS and inp.get(EDIT_TOOLS[name]):
                    f = _rel(inp[EDIT_TOOLS[name]], workdir)
                    if f not in s['edited_files']:
                        s['edited_files'].append(f)
                elif name == 'Skill' and inp.get('skill'):
                    s['invoked_skills'].append(inp['skill'])
        elif kind == 'result':
            s['final_response'] = ev.get('result') or ''
            if ev.get('is_error') or str(ev.get('subtype', 'success')) != 'success':
                result_error = f'result {ev.get("subtype")}: {s["final_response"][:200]}'
    first = prompt.split(None, 1)[0] if prompt.strip() else ''
    if first.startswith('/') and first[1:] in skills:
        s['invoked_skills'].insert(0, first[1:])
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
           '--max-turns', str(case.max_turns), *ISOLATION_ARGS]
    if case.allowed_tools:
        cmd += ['--allowedTools', ','.join(case.allowed_tools)]
    env = {**os.environ, **ISOLATION_ENV}
    error = None
    try:
        proc = subprocess.Popen(cmd, cwd=workdir, env=env, text=True, start_new_session=True,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        s = empty_summary()
        s['prompt_sent'], s['error'] = case.prompt, f'cannot start claude: {e}'
        return s
    try:
        stdout, stderr = proc.communicate(case.prompt, timeout=case.timeout_seconds)
        if proc.returncode != 0:
            error = f'claude exited with code {proc.returncode}'
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate()
        error = f'timeout after {case.timeout_seconds}s'
    (out_dir / 'transcript.jsonl').write_text(stdout or '')
    (out_dir / 'stderr.txt').write_text(stderr or '')
    s = summarize((stdout or '').splitlines(), workdir, case.prompt)
    s['prompt_sent'] = case.prompt
    s['cli_version'] = _cli_version()
    s['model'] = s['model'] or model
    s['error'] = error or s['error']
    if error and stderr and stderr.strip():
        s['error'] += f': {stderr.strip()[:200]}'
    s['ignored_options'] = []
    return s
