"""Grading (stub). Implementation lands in a separate issue."""
from pathlib import Path

from evallib import Case, Summary


def grade(case: Case, workdir: Path, summary: Summary, out_dir: Path) -> list[dict]:
    """Return one result dict per grader in case.graders."""
    raise NotImplementedError('grading is not implemented yet')


def write_summary(run_dir: Path, results: list[dict]) -> None:
    """Write the aggregate of all (product, case, trial) results under run_dir.

    Each result: {'product', 'case', 'trial', 'graders': list[dict], 'summary': Summary}.
    """
    raise NotImplementedError('write_summary is not implemented yet')
