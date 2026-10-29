"""Shared case model and executor for the L1 generators (gen_*.py).

Standard library only. A generator module provides:
  NAME      key in existing_map.json and prefix-free script label, e.g. 'status'
  SCRIPT    repository-relative path of the script under test
  AXES, EXCLUDE, WHEN   inputs for pairwise.py (see its docstring)
  cases()   -> list[Case], deterministic
run_l1.py discovers gen_*.py, so a new generator needs no change to this file or the runner.
No reference re-implementation: each Expect states one contract/invariant check or a
hand-decided expectation, and records (test=None) where no contract concludes.
"""
from dataclasses import dataclass, field
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
UNSPECIFIED = 'unspecified'
# status.sh sorts and new-change.sh matches [a-z]: both depend on the locale (plan step 2).
ENV_OVERRIDES = {'LC_ALL': 'C', 'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1'}
# Unset so a caller's git context (e.g. running from a git hook) never leaks into the temp repos.
GIT_UNSET = ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_CONFIG_COUNT', 'GIT_OBJECT_DIRECTORY')


def script_env():
    env = {k: v for k, v in os.environ.items() if k not in GIT_UNSET}
    return {**env, **ENV_OVERRIDES}
TIMEOUT = 60


@dataclass(frozen=True)
class Invocation:
    args: list
    cwd: Path
    ctx: dict = field(default_factory=dict)   # builder state the checks need (paths, snapshots)


@dataclass
class Run:
    tmp: Path
    inv: Invocation
    exit: int
    stdout: str
    stderr: str
    dates: tuple        # local dates (YYYY-MM-DD) just before and just after the run
    bash: str


@dataclass(frozen=True)
class Expect:
    contract: str                                   # e.g. 'S-INV1', 'N-C2', or 'unspecified'
    text: str                                       # the expectation in words
    test: Optional[Callable[[Run], Optional[str]]] = None   # failure message or None; None = record only


@dataclass(frozen=True)
class Case:
    id: str
    script: str
    axes: dict
    expects: tuple
    build: Callable[[Path], Invocation]
    observe: Optional[Callable[[Run], dict]] = None   # extra recorded facts (e.g. SKILL.md routing)

    @property
    def contracts(self):
        ids = sorted({e.contract for e in self.expects if e.test and e.contract != UNSPECIFIED})
        return ids or [UNSPECIFIED]


def case_id(prefix, axes):
    """Stable id from the axis values alone, so known_failures.json survives reordering."""
    digest = hashlib.sha1(json.dumps(axes, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return f'{prefix}-{digest[:10]}'


def existing_rows(name):
    """Axis rows already covered by tests/scripts or tests/route-review (existing_map.json)."""
    data = json.loads((HERE / 'existing_map.json').read_text())
    return [entry['axes'] for entry in data.get(name, [])]


def today():
    return datetime.date.today().isoformat()


def bash_version(bash):
    out = subprocess.run([bash, '-c', 'echo "$BASH_VERSION"'], text=True, capture_output=True)
    return out.stdout.strip()


def _cleanup(tmp):
    for p in [tmp, *tmp.rglob('*')]:
        if p.is_dir() and not p.is_symlink():
            p.chmod(0o700)
    shutil.rmtree(tmp)


def execute(case, bash):
    """Build inputs in a fresh temp dir, run `<bash> <script> args`, evaluate the expectations."""
    tmp = Path(tempfile.mkdtemp(prefix='ains-l1-')).resolve()
    try:
        inv = case.build(tmp)
        env = script_env()
        before = today()
        proc = subprocess.run([bash, str(REPO / case.script), *map(str, inv.args)], cwd=inv.cwd, env=env,
                              capture_output=True, timeout=TIMEOUT)
        run = Run(tmp, inv, proc.returncode, proc.stdout.decode(errors='replace'),
                  proc.stderr.decode(errors='replace'), (before, today()), bash)
        checks = []
        for e in case.expects:
            msg = e.test(run) if e.test else None
            checks.append({'contract': e.contract, 'text': e.text,
                           'result': 'recorded' if e.test is None else ('fail' if msg else 'pass'),
                           **({'detail': msg} if msg else {})})
        return run, checks, (case.observe(run) if case.observe else {})
    finally:
        _cleanup(tmp)


def snapshot(root):
    """Path -> (kind, content or link target) for everything under root."""
    out = {}
    for p in sorted(root.rglob('*')):
        rel = str(p.relative_to(root))
        if p.is_symlink():
            out[rel] = ('link', os.readlink(p))
        elif p.is_dir():
            out[rel] = ('dir', '')
        else:
            out[rel] = ('file', hashlib.sha1(p.read_bytes()).hexdigest())
    return out
