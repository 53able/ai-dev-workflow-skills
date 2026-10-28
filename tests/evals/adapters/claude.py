"""claude adapter (stub). Implementation lands in a separate issue."""
from pathlib import Path

from evallib import Case, Summary

SKILL_DIR = '.claude/skills/'


def run(case: Case, workdir: Path, out_dir: Path) -> Summary:
    """Run case.prompt in workdir with the product CLI; save raw logs under out_dir.

    Must return a Summary (see evallib.SUMMARY_KEYS). Errors from the CLI go in
    Summary['error'] rather than being raised.
    """
    raise NotImplementedError('claude adapter is not implemented yet')
