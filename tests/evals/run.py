"""Eval runner skeleton: parse cases, scaffold a workdir, hand it to a product adapter.

Standard library only. Results: ains-workspace/<run-id>/<product>/<case>/<trial>/.
"""
import argparse
import datetime
import importlib
from pathlib import Path
import subprocess
import sys
import tempfile

import evallib
from evallib import EvalError

PRODUCTS = ('claude', 'codex')
WORKSPACE = evallib.REPO / 'ains-workspace'


def load_adapter(product):
    return importlib.import_module(f'adapters.{product}')


def select_cases(evals_dir, names):
    by_name = {}
    for d in evallib.discover_cases(evals_dir):
        if d.name in by_name:
            raise EvalError(f'{d}: duplicate case name also at {by_name[d.name]}')
        by_name[d.name] = d
    unknown = [n for n in names or [] if n not in by_name]
    if unknown:
        raise EvalError(f'unknown case: {", ".join(unknown)} (available: {", ".join(sorted(by_name))})')
    return [evallib.load_case(by_name[n]) for n in (names or sorted(by_name))]


def dry_run_one(case, product, trial, adapter, out_dir):
    with tempfile.TemporaryDirectory(prefix='ains-eval-') as tmp:
        workdir = Path(tmp) / 'project'
        skills = evallib.scaffold(case, workdir, adapter.SKILL_DIR)
        status = subprocess.run(['git', 'status', '--porcelain'], cwd=workdir, text=True, capture_output=True)
        if status.returncode == 0 and status.stdout.strip():
            raise EvalError(f'{case.dir}: placed skills show up in git status: {status.stdout.strip()}')
    kinds = ','.join(sorted({g.type for g in case.graders}))
    print(f'[dry-run] {product}/{case.name}/{trial}: scaffold={case.scaffold_script} '
          f'skills={len(skills)}->{adapter.SKILL_DIR} graders={len(case.graders)}({kinds}) '
          f'max_turns={case.max_turns} timeout={case.timeout_seconds}s -> {out_dir}')


def run_one(case, product, trial, adapter, out_dir):
    import grading
    out_dir.mkdir(parents=True, exist_ok=True)
    workdir = out_dir / 'project'
    evallib.scaffold(case, workdir, adapter.SKILL_DIR)
    try:
        summary = adapter.run(case, workdir, out_dir)
    except Exception as exc:  # noqa: BLE001 - a crashing adapter is an error trial, not a crashed run
        summary = evallib.empty_summary()
        summary['error'] = f'adapter raised {type(exc).__name__}: {exc}'
    # A trial that did not run properly (e.g. skill not invoked) is not graded.
    graders = [] if summary['error'] else grading.grade(case, workdir, summary, out_dir)
    return {'product': product, 'case': case.name, 'trial': trial, 'graders': graders, 'summary': summary}


def main(argv=None, evals_dir=evallib.HERE, workspace=WORKSPACE):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run', action='store_true', help='parse, scaffold and place skills without calling any model')
    ap.add_argument('--case', action='append', metavar='NAME', help='case name (repeatable); default all')
    ap.add_argument('--trials', type=int, default=1)
    ap.add_argument('--product', choices=(*PRODUCTS, 'all'), default='all')
    ap.add_argument('--run-id', default=datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    args = ap.parse_args(argv)
    if args.trials < 1:
        ap.error('--trials must be >= 1')
    products = PRODUCTS if args.product == 'all' else (args.product,)
    try:
        cases = select_cases(evals_dir, args.case)
        run_dir = workspace / args.run_id
        results = []
        for product in products:
            adapter = load_adapter(product)
            for case in cases:
                for trial in range(1, args.trials + 1):
                    out_dir = run_dir / product / case.name / str(trial)
                    if args.dry_run:
                        dry_run_one(case, product, trial, adapter, out_dir)
                    else:
                        results.append(run_one(case, product, trial, adapter, out_dir))
        if not args.dry_run:
            import grading
            grading.write_summary(run_dir, results)
    except EvalError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
