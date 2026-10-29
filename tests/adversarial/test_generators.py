"""Generator checks: coverage (AC1), unspecified ratio (AC2), ids, determinism, duplicates."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

import l1lib
import pairwise
import run_l1

GENS = run_l1.generators()


class GeneratorTests(unittest.TestCase):
    def test_generators_found(self):
        self.assertGreaterEqual({g.NAME for g in GENS}, {'status', 'new-change', 'route-review'})

    def test_coverage_complete(self):
        for g in GENS:
            with self.subTest(g.NAME):
                cov = pairwise.coverage(g.AXES, g.EXCLUDE, g.WHEN, [c.axes for c in g.cases()],
                                        l1lib.existing_rows(g.NAME))
                self.assertEqual(cov['unused_values'], [])
                self.assertEqual(cov['uncovered_pairs'], [])

    def test_unspecified_ratio_and_contracts(self):
        for g in GENS:
            with self.subTest(g.NAME):
                cs = g.cases()
                self.assertTrue(cs)
                self.assertTrue(all(c.contracts for c in cs))
                unspec = sum(c.contracts == [l1lib.UNSPECIFIED] for c in cs)
                self.assertLessEqual(unspec / len(cs), 0.30)

    def test_ids_unique_and_no_duplicate_combo(self):
        ids, combos = set(), set()
        for g in GENS:
            for c in g.cases():
                self.assertNotIn(c.id, ids)
                ids.add(c.id)
                combo = (c.script, tuple(c.contracts), json.dumps(c.axes, sort_keys=True))
                self.assertNotIn(combo, combos)
                combos.add(combo)
                self.assertEqual(c.script, g.SCRIPT)
                self.assertTrue((l1lib.REPO / c.script).is_file())

    def test_deterministic_in_process_and_across_hash_seeds(self):
        def sig(g):
            return [(c.id, c.axes, c.contracts, [(e.contract, e.text) for e in c.expects]) for c in g.cases()]
        for g in GENS:
            self.assertEqual(sig(g), sig(g))
        code = 'import run_l1; print([(c.id, c.axes) for g in run_l1.generators() for c in g.cases()])'
        outs = {subprocess.run([sys.executable, '-c', code], cwd=l1lib.HERE, text=True, capture_output=True, check=True,
                               env={**os.environ, 'PYTHONHASHSEED': seed}).stdout for seed in ('1', '2')}
        self.assertEqual(len(outs), 1)

    def test_existing_map_matches_axes(self):
        data = json.loads((l1lib.HERE / 'existing_map.json').read_text())
        for g in GENS:
            with self.subTest(g.NAME):
                self.assertIn(g.NAME, data)
                for entry in data[g.NAME]:
                    self.assertTrue(entry['source'].startswith('tests/'))
                    for axis, value in entry['axes'].items():
                        self.assertIn(value, g.AXES[axis], entry['source'])

    def test_known_failures_refer_to_cases(self):
        known = json.loads(run_l1.KNOWN.read_text())
        ids = {c.id for g in GENS for c in g.cases()}
        for cid, issue in known.items():
            if not cid.startswith('_'):
                self.assertIn(cid, ids)
                self.assertIsInstance(issue, int)


class PairwiseTests(unittest.TestCase):
    AXES = {'mode': ['a', 'b'], 'x': ['1', '2', '3'], 'y': ['p', 'q'], 'only_b': ['u', 'v']}
    EXCLUDE = [(('x', '3'), ('y', 'q'))]
    WHEN = {'only_b': ('mode', ('b',))}

    def test_exclusions_and_conditions_hold(self):
        rows = pairwise.generate(self.AXES, self.EXCLUDE, self.WHEN)
        for row in rows:
            self.assertFalse(row.get('x') == '3' and row.get('y') == 'q')
            self.assertEqual('only_b' in row, row['mode'] == 'b')
        cov = pairwise.coverage(self.AXES, self.EXCLUDE, self.WHEN, rows)
        self.assertEqual(cov['uncovered_pairs'], [])
        self.assertEqual(cov['unused_values'], [])
        # mode=a with only_b (2 pairs) and x=3 with y=q (1 pair) are excluded.
        self.assertEqual(cov['pairs_excluded'], 3)

    def test_covered_rows_are_not_generated_again(self):
        full = pairwise.generate(self.AXES, self.EXCLUDE, self.WHEN)
        existing = [{'mode': 'b', 'x': '1', 'y': 'p', 'only_b': 'u'}]
        rest = pairwise.generate(self.AXES, self.EXCLUDE, self.WHEN, covered=existing)
        self.assertNotIn(existing[0], rest)
        cov = pairwise.coverage(self.AXES, self.EXCLUDE, self.WHEN, rest, existing)
        self.assertEqual((cov['uncovered_pairs'], cov['pairs_by_existing']), ([], 6))
        self.assertLessEqual(len(rest), len(full))

    def test_condition_axis_must_come_first(self):
        with self.assertRaises(ValueError):
            pairwise.generate({'c': ['1'], 'm': ['a']}, when={'c': ('m', ('a',))})


class RunnerTests(unittest.TestCase):
    """AC4: an unregistered failure exits 1; registering its id exits 0."""

    def test_known_failures_gate_exit_code(self):
        failing = l1lib.Case('fake-1', 'skills/ains/scripts/status.sh', {'a': '1'},
                             (l1lib.Expect('S-INV4', 'exit 1 on purpose', lambda r: 'forced failure'),),
                             lambda tmp: l1lib.Invocation([str(tmp / 'absent')], tmp))
        fake = types.SimpleNamespace(NAME='fake', cases=lambda: [failing])
        with tempfile.TemporaryDirectory() as d:
            known = Path(d) / 'known.json'
            with mock.patch.object(run_l1, 'generators', lambda: [fake]), \
                    mock.patch.object(run_l1, 'KNOWN', known), mock.patch.object(run_l1, 'WORKSPACE', Path(d)), \
                    contextlib.redirect_stdout(io.StringIO()):
                known.write_text('{}')
                self.assertEqual(run_l1.main(['--run-id', 'before']), 1)
                known.write_text('{"fake-1": 1}')
                self.assertEqual(run_l1.main(['--run-id', 'after']), 0)
            line = json.loads((Path(d) / 'l1-after/results.jsonl').read_text())
            self.assertEqual((line['id'], line['passed'], line['contracts']), ('fake-1', False, ['S-INV4']))


if __name__ == '__main__': unittest.main(verbosity=2)
