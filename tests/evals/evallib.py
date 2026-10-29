"""Shared definitions for the eval runner: restricted parsers, case loading, scaffold.

Standard library only. The parsers accept exactly the formats the eval files use
(see SCHEMAS); anything else, unknown or duplicate keys included, is an explicit
EvalError naming the file instead of a guess. This is not a YAML parser.
"""
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
from typing import Optional, TypedDict

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SCHEMA_VERSION = '1.1'
# Keep the user's git config (commit.gpgsign, core.hooksPath, ...) out of scaffold and grading.
GIT_ENV = {'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1'}
# The agent under test must not reach real remotes or accounts: git transports only to
# local paths (the cases' .git/remote.git), no ssh, and gh/GitHub tokens are unusable.
SUBJECT_ENV = {**GIT_ENV, 'GIT_ALLOW_PROTOCOL': 'file', 'GIT_SSH_COMMAND': 'false', 'GIT_TERMINAL_PROMPT': '0',
               'GH_TOKEN': 'ains-eval-invalid', 'GITHUB_TOKEN': 'ains-eval-invalid',
               'GH_CONFIG_DIR': '/nonexistent-ains-eval-gh', 'GH_PROMPT_DISABLED': '1',
               # git's default ~/.config/git/{ignore,attributes} are unreadable in Claude's sandbox
               # and only add warnings to the agent's output.
               'GIT_CONFIG_COUNT': '2', 'GIT_CONFIG_KEY_0': 'core.excludesFile', 'GIT_CONFIG_VALUE_0': os.devnull,
               'GIT_CONFIG_KEY_1': 'core.attributesFile', 'GIT_CONFIG_VALUE_1': os.devnull}
SUBJECT_UNSET = ('SSH_AUTH_SOCK', 'GIT_CONFIG_PARAMETERS', 'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE',
                 'GIT_OBJECT_DIRECTORY', 'GIT_COMMON_DIR')
# Credentials in the caller's environment stay out of the subject process (Bash can print them
# into the outputs), except the ones the product CLIs log in with.
SECRET_ENV = re.compile(r'TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|_KEY$|_KEY_|SESSION|COOKIE|^AWS_|^AZURE_|^GOOGLE_', re.I)
LOGIN_ENV = {'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN', 'OPENAI_API_KEY', 'CODEX_API_KEY'}


def subject_env(base=None, login=LOGIN_ENV):
    """Environment for the agent under test; login: the credential variables its CLI may keep."""
    env = {k: v for k, v in (base if base is not None else os.environ).items()
           if k not in SUBJECT_UNSET and (k in login or not SECRET_ENV.search(k))}
    return {**env, **SUBJECT_ENV}
TIMELINE_CHARS = 400   # per timeline entry; enough to see a test failure, bounded for the grader


class EvalError(Exception):
    """Invalid eval input or scaffold failure; the message names the file."""


class Summary(TypedDict):
    """Product-independent result of one agent run, returned by adapter.run()."""
    final_response: str
    commands: list[str]
    edited_files: list[str]
    invoked_skills: list[str]
    # Of invoked_skills, those counted without a read in the transcript (codex `$name` injection).
    injected_skills: list[str]
    ignored_options: list[str]
    prompt_sent: str
    cli_version: str
    model: str
    error: Optional[str]
    # Ordered tool calls and results: {'type': 'tool_use', 'name', 'input'} or
    # {'type': 'tool_result', 'output', 'is_error'}; text clipped to TIMELINE_CHARS.
    timeline: list[dict]


SUMMARY_KEYS = tuple(Summary.__annotations__)


def empty_summary() -> Summary:
    return Summary(final_response='', commands=[], edited_files=[], invoked_skills=[], injected_skills=[],
                   ignored_options=[], prompt_sent='', cli_version='', model='', error=None,
                   timeline=[])


def clip(text, limit=TIMELINE_CHARS):
    text = str(text)
    return text if len(text) <= limit else text[:limit] + '...(truncated)'


def git_env():
    return {**os.environ, **GIT_ENV}


# Agent processes in flight. Ctrl+C reaches only the main thread, so with --jobs the
# runner kills these itself; the adapters' own finally runs in worker threads.
_tracked = set()
_tracked_lock = threading.Lock()
_stopping = threading.Event()


def track(proc):
    with _tracked_lock:
        _tracked.add(proc)
    if _stopping.is_set():   # started after kill_tracked()
        kill_group(proc)


def stopping():
    return _stopping.is_set()


def kill_tracked():
    _stopping.set()
    with _tracked_lock:
        procs = list(_tracked)
    for proc in procs:
        kill_group(proc)


def kill_group(proc, sig=signal.SIGKILL):
    """Kill the process group of proc (started with start_new_session); it may be gone already."""
    if sig == signal.SIGKILL:
        with _tracked_lock:
            _tracked.discard(proc)
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


# Value kinds: str (plain or double-quoted), int, num, list (flow list of plain
# words), block ('|' literal block), strblock (one-line scalar or '|' block),
# map:<schema name> (indented one-level mapping).
SCHEMAS = {
    'case': {
        'schema_version': ('str', True), 'name': ('str', True),
        'expected_outcome': ('block', True), 'context': ('map:context', True),
    },
    'context': {'scaffold_script': ('str', True)},
    'prompt': {
        'tags': ('list', False), 'max_turns': ('int', False),
        'timeout_seconds': ('int', False), 'allowed_tools': ('list', False),
    },
    'grader': {
        'type': ('str', True), 'focus': ('str', False),
        'weight': ('num', False), 'run': ('strblock', False),
    },
}


def _scalar(raw, kind, where):
    if kind == 'str':
        if raw.startswith('"'):
            if not re.fullmatch(r'"[^"\\]*"', raw):
                raise EvalError(f'{where}: unsupported quoted scalar {raw!r}')
            return raw[1:-1]
        if not raw or raw[0] in "'|>[{&*!%@`#" or ': ' in raw or ' #' in raw:
            raise EvalError(f'{where}: unsupported scalar {raw!r}; expected a plain or double-quoted string')
        return raw
    if kind == 'int':
        if not re.fullmatch(r'[0-9]+', raw):
            raise EvalError(f'{where}: expected integer, got {raw!r}')
        return int(raw)
    if kind == 'num':
        if not re.fullmatch(r'[0-9]+(\.[0-9]+)?', raw):
            raise EvalError(f'{where}: expected number, got {raw!r}')
        return float(raw)
    if kind == 'list':
        m = re.fullmatch(r'\[(.*)\]', raw)
        if not m:
            raise EvalError(f'{where}: expected flow list [a, b], got {raw!r}')
        items = [i.strip() for i in m.group(1).split(',')] if m.group(1).strip() else []
        if not all(re.fullmatch(r'[A-Za-z0-9_.:/-]+', i) for i in items):
            raise EvalError(f'{where}: unsupported list item in {raw!r}')
        return items
    raise AssertionError(kind)


def parse_mapping(lines, schema_name, filename, indent=0):
    """Parse `key: value` lines at `indent` against SCHEMAS[schema_name]."""
    schema = SCHEMAS[schema_name]
    result = {}
    i = 0
    pad = ' ' * indent
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if not line.startswith(pad) or line[indent:indent + 1] in (' ', '\t'):
            raise EvalError(f'{filename}: unexpected indentation: {line!r}')
        m = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*):(?: +(.*?))?\s*', line[indent:])
        if not m:
            raise EvalError(f'{filename}: unsupported line {line!r}')
        key, raw = m.group(1), m.group(2)
        where = f'{filename}: {key}'
        if key not in schema:
            raise EvalError(f'{where}: unknown key')
        if key in result:
            raise EvalError(f'{where}: duplicate key')
        kind = schema[key][0]
        child = []
        while i < len(lines) and (not lines[i].strip() or lines[i].startswith(pad + ' ')):
            child.append(lines[i])
            i += 1
        while child and not child[-1].strip():   # blank lines before the next key
            child.pop()
        if kind.startswith('map:'):
            if raw is not None or not child:
                raise EvalError(f'{where}: expected an indented mapping')
            result[key] = parse_mapping(child, kind[4:], filename, indent + 2)
        elif kind == 'block' or (kind == 'strblock' and raw == '|'):
            if raw != '|':
                raise EvalError(f'{where}: expected a "|" block')
            body = [c for c in child]
            while body and not body[-1].strip():
                body.pop()
            if not body:
                raise EvalError(f'{where}: empty block')
            bpad = indent + 2
            if any(b.strip() and not b.startswith(' ' * bpad) for b in body):
                raise EvalError(f'{where}: block must be indented by {bpad} spaces')
            result[key] = '\n'.join(b[bpad:] for b in body) + '\n'
        else:
            if child or raw is None:
                raise EvalError(f'{where}: expected a one-line value')
            result[key] = _scalar(raw, 'str' if kind == 'strblock' else kind, where)
    for key, (_, required) in schema.items():
        if required and key not in result:
            raise EvalError(f'{filename}: missing required key {key}')
    return result


def split_frontmatter(text, filename):
    lines = text.splitlines()
    if not lines or lines[0] != '---' or '---' not in lines[1:]:
        raise EvalError(f'{filename}: expected front matter delimited by --- on the first line')
    end = lines[1:].index('---') + 1
    return lines[1:end], '\n'.join(lines[end + 1:]).strip('\n') + '\n'


@dataclass
class Grader:
    id: str          # file stem, e.g. "01-assert"
    path: Path
    type: str        # "llm" | "command"
    focus: str
    weight: float
    run: Optional[str]   # shell command (type == "command")
    body: str            # grader instructions (Markdown body)


@dataclass
class Case:
    name: str
    dir: Path
    expected_outcome: str
    scaffold_script: str
    prompt: str          # prompt.md body
    tags: list = field(default_factory=list)
    max_turns: int = 40
    timeout_seconds: int = 900
    allowed_tools: Optional[list] = None
    graders: list = field(default_factory=list)


def load_grader(path):
    fm, body = split_frontmatter(path.read_text(), str(path))
    data = parse_mapping(fm, 'grader', str(path))
    if data['type'] not in ('llm', 'command'):
        raise EvalError(f'{path}: type must be llm or command, got {data["type"]!r}')
    if data['type'] == 'command' and not data.get('run'):
        raise EvalError(f'{path}: type command requires run')
    if data['type'] == 'llm' and 'run' in data:
        raise EvalError(f'{path}: run is only valid for type command')
    if not body.strip():
        raise EvalError(f'{path}: empty grader body')
    return Grader(id=path.stem, path=path, type=data['type'], focus=data.get('focus', 'trace'),
                  weight=data.get('weight', 1.0), run=data.get('run'), body=body)


def load_case(case_dir):
    case_dir = Path(case_dir)
    yaml_path = case_dir / 'case.yaml'
    if not yaml_path.is_file():
        raise EvalError(f'{yaml_path}: missing')
    data = parse_mapping(yaml_path.read_text().splitlines(), 'case', str(yaml_path))
    if data['schema_version'] != SCHEMA_VERSION:
        raise EvalError(f'{yaml_path}: schema_version must be "{SCHEMA_VERSION}", got {data["schema_version"]!r}')
    if data['name'] != case_dir.name:
        raise EvalError(f'{yaml_path}: name {data["name"]!r} does not match directory {case_dir.name!r}')
    script = case_dir / data['context']['scaffold_script']
    if not script.is_file():
        raise EvalError(f'{yaml_path}: scaffold_script {script.name} not found')
    prompt_path = case_dir / 'prompt.md'
    if not prompt_path.is_file():
        raise EvalError(f'{prompt_path}: missing')
    fm, body = split_frontmatter(prompt_path.read_text(), str(prompt_path))
    meta = parse_mapping(fm, 'prompt', str(prompt_path))
    if not body.strip():
        raise EvalError(f'{prompt_path}: empty prompt')
    graders = [load_grader(p) for p in sorted((case_dir / 'graders').glob('*.md'))]
    if not graders:
        raise EvalError(f'{case_dir / "graders"}: no graders')
    return Case(name=data['name'], dir=case_dir, expected_outcome=data['expected_outcome'],
                scaffold_script=data['context']['scaffold_script'], prompt=body, graders=graders,
                **{k: v for k, v in meta.items()})


def discover_cases(evals_dir=HERE):
    return sorted(p.parent for p in Path(evals_dir).glob('*/*/case.yaml'))


def place_skills(workdir, skill_dir, skills_src=REPO / 'skills'):
    """Copy skills/* into workdir/skill_dir; return the skill names placed.

    Done after the scaffold script, so the skills are not in its initial commit.
    The destination is also added to .git/info/exclude: grading reads the agent's
    changes from git, and the placed skills must never show up as a diff.
    """
    dest = Path(workdir) / skill_dir
    dest.mkdir(parents=True, exist_ok=True)
    names = []
    for src in sorted(p for p in Path(skills_src).iterdir() if p.is_dir()):
        shutil.copytree(src, dest / src.name)
        names.append(src.name)
    exclude = Path(workdir) / '.git' / 'info' / 'exclude'
    if exclude.parent.parent.is_dir():
        exclude.parent.mkdir(exist_ok=True)
        with exclude.open('a') as f:
            f.write(f'/{skill_dir.strip("/")}/\n')
    return names


def scaffold(case, workdir, skill_dir, skills_src=REPO / 'skills'):
    """Run the case's place-files.sh with cwd=workdir, then place the skills."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    script = case.dir / case.scaffold_script
    r = subprocess.run(['bash', str(script)], cwd=workdir, text=True, capture_output=True, env=git_env())
    if r.returncode != 0:
        raise EvalError(f'{script}: exit {r.returncode}: {r.stderr.strip()}')
    # Subject runs get GIT_ENV (no global/system git config), so the agent's own commit
    # needs a repo-local identity.
    if (workdir / '.git').exists():
        for k, v in (('user.name', 'eval'), ('user.email', 'eval@example.com')):
            subprocess.run(['git', 'config', '--local', k, v], cwd=workdir, check=True, env=git_env())
    return place_skills(workdir, skill_dir, skills_src)
