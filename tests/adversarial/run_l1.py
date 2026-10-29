"""Run the L1 generated cases (every gen_*.py here) against the scripts. No model calls.

Results: ains-workspace/l1-<run-id>/results.jsonl, one JSON object per case. Exit 1 when a
case fails and is not listed in known_failures.json (case id -> issue number).
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime
import importlib
import json
import os
import sys
import time

import pairwise
from l1lib import HERE, REPO, UNSPECIFIED, bash_version, execute, existing_rows

KNOWN = HERE / 'known_failures.json'
WORKSPACE = REPO / 'ains-workspace'


def generators():
    sys.path.insert(0, str(HERE))
    return [importlib.import_module(p.stem) for p in sorted(HERE.glob('gen_*.py'))]


def all_cases(gens):
    return [(g, c) for g in gens for c in g.cases()]


def count(gens):
    for g in gens:
        cs = g.cases()
        unspec = sum(c.contracts == [UNSPECIFIED] for c in cs)
        print(f'{g.NAME}: {len(cs)} cases, unspecified {unspec} ({unspec / max(len(cs), 1):.0%})')
    return 0


def coverage(gens):
    bad = 0
    for g in gens:
        cov = pairwise.coverage(g.AXES, g.EXCLUDE, g.WHEN, [c.axes for c in g.cases()], existing_rows(g.NAME))
        print(f'{g.NAME}: values {cov["values"]}, unused {len(cov["unused_values"])}; pairs total {cov["pairs_total"]}, '
              f'excluded {cov["pairs_excluded"]}, required {cov["pairs_required"]}, by existing tests '
              f'{cov["pairs_by_existing"]}, by generated only {cov["pairs_by_generated_only"]}, '
              f'uncovered {len(cov["uncovered_pairs"])}')
        for item in cov['unused_values'] + cov['uncovered_pairs']:
            print(f'  missing: {item}')
        bad += len(cov['unused_values']) + len(cov['uncovered_pairs'])
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--count', action='store_true', help='print case counts per script and exit')
    ap.add_argument('--coverage', action='store_true', help='print value/pairwise coverage and exit (1 if incomplete)')
    ap.add_argument('--case', action='append', metavar='ID', help='run only these case ids (repeatable)')
    ap.add_argument('--bash', default=os.environ.get('BASH_BIN', 'bash'),
                    help='bash that runs the scripts (default $BASH_BIN or bash; /bin/bash checks 3.2)')
    ap.add_argument('--run-id', default=datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    ap.add_argument('--jobs', type=int, default=4)
    args = ap.parse_args(argv)
    gens = generators()
    if args.count:
        return count(gens)
    if args.coverage:
        return coverage(gens)

    selected = all_cases(gens)
    if args.case:
        known_ids = {c.id for _, c in selected}
        unknown = [i for i in args.case if i not in known_ids]
        if unknown:
            print(f'unknown case: {", ".join(unknown)}', file=sys.stderr)
            return 2
        selected = [(g, c) for g, c in selected if c.id in args.case]
    known = {k: v for k, v in json.loads(KNOWN.read_text()).items() if not k.startswith('_')}
    out_dir = WORKSPACE / f'l1-{args.run_id}'
    if out_dir.exists():
        print(f'{out_dir} already exists; pass a new --run-id', file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True)
    version = bash_version(args.bash)
    started = time.monotonic()

    def one(item):
        _, case = item
        run, checks, observed = execute(case, args.bash)
        return {'id': case.id, 'script': case.script, 'axes': case.axes, 'contracts': case.contracts,
                'expected': [{'contract': e.contract, 'text': e.text} for e in case.expects],
                'actual': {'exit': run.exit, 'checks': checks, **observed},
                'args': [str(a) for a in run.inv.args], 'stdout': run.stdout, 'stderr': run.stderr,
                'exit': run.exit, 'bash': version, 'passed': all(c['result'] != 'fail' for c in checks)}

    with ThreadPoolExecutor(max_workers=max(args.jobs, 1)) as pool:
        results = list(pool.map(one, selected))
    with (out_dir / 'results.jsonl').open('w') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    failed = [r for r in results if not r['passed']]
    new = [r for r in failed if r['id'] not in known]
    for r in failed:
        tag = f'known #{known[r["id"]]}' if r['id'] in known else 'NEW'
        details = '; '.join(f'{c["contract"]}: {c["detail"]}' for c in r['actual']['checks'] if c['result'] == 'fail')
        print(f'FAIL [{tag}] {r["id"]} {r["axes"]}: {details}')
    for cid in sorted(set(known) & {r['id'] for r in results if r['passed']}):
        print(f'note: known failure {cid} (#{known[cid]}) now passes')
    print(f'{len(results)} cases, {len(failed)} failed ({len(new)} not in known_failures.json), '
          f'bash {version}, {time.monotonic() - started:.1f}s -> {out_dir / "results.jsonl"}')
    return 1 if new else 0


if __name__ == '__main__':
    sys.exit(main())
