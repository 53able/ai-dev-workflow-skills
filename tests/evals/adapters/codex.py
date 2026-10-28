"""codex adapter: run a case prompt with `codex exec` and summarize the JSONL stream."""
import json
import os
from pathlib import Path
import re
import signal
import subprocess

from evallib import Case, Summary, empty_summary

SKILL_DIR = '.agents/skills/'
DEFAULT_MODEL = 'gpt-6.1-sol'   # same fixed model as tests/runtime/codex/runtime.py
MODEL_ENV = 'EVAL_CODEX_MODEL'  # overrides DEFAULT_MODEL
IGNORED_OPTIONS = ['max_turns', 'allowed_tools']  # codex exec has no equivalent flags

# `/ains...` as a slash command: at line start or after whitespace/an opening bracket or
# quote. A preceding path character (docs/ains/, ./ains) is not matched.
_SLASH_CMD = re.compile(r'(?m)(^|(?<=[\s(\[\'"`]))/(ains[A-Za-z0-9_-]*)')
_SKILL_MD = re.compile(r'(?:^|[\s\'"`=/])skills/(ains[A-Za-z0-9_-]*)/SKILL\.md')


def to_codex_prompt(prompt: str) -> str:
    """Rewrite Claude Code `/ains-xxx` to Codex `$ains-xxx` (README notation rule)."""
    return _SLASH_CMD.sub(r'\1$\2', prompt)


def named_skills(prompt_sent: str) -> list[str]:
    """Skills the prompt invokes by name: `$ains...` tokens in the (converted) prompt."""
    seen = []
    for m in re.finditer(r'(?m)(?:^|(?<=[\s(\[\'"`]))\$(ains[A-Za-z0-9_-]*)', prompt_sent):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def _events(raw: str):
    for line in raw.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict):
            yield e


def _items(raw: str):
    """Completed items only; started events duplicate them."""
    for e in _events(raw):
        if e.get('type') == 'item.completed' and isinstance(e.get('item'), dict):
            yield e['item']


def invoked_skills(raw: str) -> list[str]:
    """Skills whose SKILL.md the agent read, in first-read order.

    Basis: Codex loads a skill by reading `<skills dir>/<name>/SKILL.md` through a shell
    command. So an `item.completed` event of type `command_execution` whose `command`
    mentions `skills/<name>/SKILL.md` counts as an invocation of <name>. Only
    command_execution items count; the same path inside agent_message text or in the
    prompt echo does not.
    """
    out = []
    for it in _items(raw):
        if it.get('type') != 'command_execution':
            continue
        for m in _SKILL_MD.finditer(str(it.get('command', ''))):
            if m.group(1) not in out:
                out.append(m.group(1))
    return out


def summarize_jsonl(raw: str) -> dict:
    """Common summary fields from the `codex exec --json` stream (pure; no I/O)."""
    commands, edited, final = [], [], ''
    model = ''
    for e in _events(raw):
        for key in ('model', 'model_slug'):
            if not model and isinstance(e.get(key), str):
                model = e[key]
    for it in _items(raw):
        typ = it.get('type')
        if typ == 'agent_message':
            final = str(it.get('text', ''))  # the last agent_message is the final response
        elif typ == 'command_execution':
            commands.append(str(it.get('command', '')))
        elif typ == 'file_change':
            for ch in it.get('changes') or []:
                p = ch.get('path') if isinstance(ch, dict) else None
                if p and p not in edited:
                    edited.append(p)
    return {'final_response': final, 'commands': commands, 'edited_files': edited,
            'invoked_skills': invoked_skills(raw), 'model': model}


def cli_version() -> str:
    try:
        r = subprocess.run(['codex', '--version'], text=True, capture_output=True, timeout=30)
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def run(case: Case, workdir: Path, out_dir: Path) -> Summary:
    s = empty_summary()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    s['ignored_options'] = list(IGNORED_OPTIONS)
    s['prompt_sent'] = to_codex_prompt(case.prompt)
    s['cli_version'] = cli_version()
    model = os.environ.get(MODEL_ENV) or DEFAULT_MODEL
    args = ['codex', '-a', 'never', 'exec', '--ignore-user-config', '--ephemeral',
            '-s', 'workspace-write', '-m', model, '--json', '-C', str(workdir), s['prompt_sent']]
    try:
        p = subprocess.Popen(args, cwd=workdir, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, start_new_session=True)
    except OSError as e:
        s['error'] = f'codex failed to start: {e}'
        return s
    timed_out = False
    try:
        out, err = p.communicate(timeout=case.timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(p.pid, signal.SIGTERM)
        try:
            out, err = p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            out, err = p.communicate()
    raw, errtxt = out.decode(errors='replace'), err.decode(errors='replace')
    (out_dir / 'codex.jsonl').write_text(raw)
    (out_dir / 'codex.stderr').write_text(errtxt)
    s.update(summarize_jsonl(raw))
    s['model'] = s['model'] or model
    if timed_out:
        s['error'] = f'timeout after {case.timeout_seconds}s'
    elif p.returncode != 0:
        s['error'] = f'codex exited with {p.returncode}: {errtxt.strip()[-500:]}'
    else:
        missing = [n for n in named_skills(s['prompt_sent']) if n not in s['invoked_skills']]
        if missing:
            s['error'] = f'skill not invoked: {", ".join(missing)}'
    return s
