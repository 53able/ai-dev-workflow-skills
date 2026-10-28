"""codex adapter: run a case prompt with `codex exec` and summarize the JSONL stream."""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile

from evallib import GIT_ENV, Case, Summary, clip, empty_summary, kill_group

SKILL_DIR = '.agents/skills/'
DEFAULT_MODEL = 'gpt-6.1-sol'   # same fixed model as tests/runtime/codex/runtime.py
MODEL_ENV = 'EVAL_CODEX_MODEL'  # overrides DEFAULT_MODEL
IGNORED_OPTIONS = ['max_turns', 'allowed_tools']  # codex exec has no equivalent flags

# `/ains...` as a slash command: at line start or after whitespace/an opening bracket or
# quote. A preceding path character (docs/ains/, ./ains) is not matched.
_SLASH_CMD = re.compile(r'(?m)(^|(?<=[\s(\[\'"`]))/(ains[A-Za-z0-9_-]*)')
# `<prefix>.agents/skills/<name>/SKILL.md` as one shell word; the prefix decides whether it
# is the working copy's copy (see invoked_skills).
_SKILL_MD = re.compile(r'(?:^|(?<=[\s\'"`=;(]))([^\s\'"`=;(]*?)\.agents/skills/(ains[A-Za-z0-9_-]*)/SKILL\.md')
# `cd <prefix>.agents/skills/<name> && cat SKILL.md` (or ;), with a bare SKILL.md argument.
_CD_SKILL = re.compile(r'\bcd\s+[\'"]?([^\s\'"`;&|]*?)\.agents/skills/(ains[A-Za-z0-9_-]*)/?[\'"]?\s*(?:&&|;)'
                       r'[^;&|]*?(?<![^\s\'"])SKILL\.md')


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


def invoked_skills(raw: str, workdir=None) -> list[str]:
    """Skills whose SKILL.md in the working copy the agent read, in first-read order.

    Basis: Codex loads a skill by reading `.agents/skills/<name>/SKILL.md` through a shell
    command. So an `item.completed` event of type `command_execution` whose `command`
    mentions that path (relative, `./`, or under workdir), or `cd`s into the skill
    directory and then names `SKILL.md`, counts as an invocation of <name>. A same-named
    SKILL.md elsewhere (e.g. ~/.codex/skills) does not count. Only command_execution
    items count; the same path inside agent_message text or in the prompt echo does not.
    """
    roots = {'', './'}
    if workdir:
        roots |= {f'{Path(workdir)}/', f'{Path(workdir).resolve()}/'}
    out = []
    for it in _items(raw):
        if it.get('type') != 'command_execution':
            continue
        command = str(it.get('command', ''))
        for m in [*_SKILL_MD.finditer(command), *_CD_SKILL.finditer(command)]:
            if m.group(1) in roots and m.group(2) not in out:
                out.append(m.group(2))
    return out


def summarize_jsonl(raw: str, workdir=None) -> dict:
    """Common summary fields from the `codex exec --json` stream (pure; no I/O)."""
    commands, edited, final, timeline = [], [], '', []
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
            timeline += [{'type': 'tool_use', 'name': 'shell', 'input': clip(commands[-1])},
                         {'type': 'tool_result', 'output': clip(it.get('aggregated_output', '')),
                          'is_error': it.get('exit_code') not in (0, None)}]
        elif typ == 'file_change':
            paths = []
            for ch in it.get('changes') or []:
                p = ch.get('path') if isinstance(ch, dict) else None
                if p:
                    paths.append(p)
                if p and p not in edited:
                    edited.append(p)
            timeline.append({'type': 'tool_use', 'name': 'file_change', 'input': clip(', '.join(paths))})
    return {'final_response': final, 'commands': commands, 'edited_files': edited,
            'invoked_skills': invoked_skills(raw, workdir), 'model': model, 'timeline': timeline}


def cli_version() -> str:
    try:
        r = subprocess.run(['codex', '--version'], text=True, capture_output=True, timeout=30)
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def isolated_env(home: Path) -> dict:
    """--ignore-user-config still loads ~/.codex/AGENTS.md and ~/.agents/skills/ (measured with
    codex-cli 0.165.0), so run under an empty HOME/CODEX_HOME that only links the existing login."""
    codex_home = home / '.codex'
    codex_home.mkdir(parents=True, exist_ok=True)
    real = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'auth.json'
    if real.exists():
        (codex_home / 'auth.json').symlink_to(real)
    return {**os.environ, **GIT_ENV, 'HOME': str(home), 'CODEX_HOME': str(codex_home)}


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
    home = Path(tempfile.mkdtemp(prefix='ains-codex-home-'))
    try:
        p = subprocess.Popen(args, cwd=workdir, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, start_new_session=True, env=isolated_env(home))
    except OSError as e:
        shutil.rmtree(home, ignore_errors=True)
        s['error'] = f'codex failed to start: {e}'
        return s
    timed_out = False
    try:
        out, err = p.communicate(timeout=case.timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_group(p, signal.SIGTERM)
        try:
            out, err = p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            kill_group(p)
            out, err = p.communicate()
    finally:
        kill_group(p)   # also on interrupt, and any leftover children
        shutil.rmtree(home, ignore_errors=True)
    raw, errtxt = out.decode(errors='replace'), err.decode(errors='replace')
    (out_dir / 'codex.jsonl').write_text(raw)
    (out_dir / 'codex.stderr').write_text(errtxt)
    s.update(summarize_jsonl(raw, workdir))
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
