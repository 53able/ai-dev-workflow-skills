"""Adversarial cases (adv-*): every type: command grader is exercised by some test_graders_adv_*.py.

Each category module lists what it tests in COVERED as (case, grader_id); case may be a case
name, a (skill, name) tuple, or an alias resolved through the module's CASES map.
"""
import importlib
import unittest

import evallib

CATEGORIES = 'abcde'


def case_name(key, module):
    if isinstance(key, tuple):
        key = key[-1]
    key = getattr(module, 'CASES', {}).get(key, key)
    return key.rsplit('/', 1)[-1]


class AdversarialCoverageTests(unittest.TestCase):
    def test_every_command_grader_is_covered(self):
        covered = set()
        for c in CATEGORIES:
            m = importlib.import_module(f'test_graders_adv_{c}')
            covered |= {(case_name(k, m), g) for k, g in m.COVERED}
        graders = {(d.name, g.id) for d in evallib.discover_cases() if d.name.startswith('adv-')
                   for g in evallib.load_case(d).graders if g.type == 'command'}
        self.assertEqual(sorted(graders - covered), [], 'command graders without a good/bad test')
        self.assertEqual(sorted(covered - graders), [], 'COVERED entries without a command grader')

    def test_case_counts(self):
        names = [d.name for d in evallib.discover_cases()]
        self.assertEqual(sum(n.startswith('adv-') for n in names), 40)
        for c in CATEGORIES:
            self.assertTrue(any(n.startswith(f'adv-{c}-') for n in names), c)


if __name__ == '__main__':
    unittest.main()
