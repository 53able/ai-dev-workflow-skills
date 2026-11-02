import unittest

from legacy.report import r


class ReportTest(unittest.TestCase):
    DATA = [('2026-09-01', 'pen', 100, 2), ('2026-09-15', 'note', 300, 1), ('2026-10-01', 'pen', 100, 1)]

    def test_tsv_for_month(self):
        self.assertEqual(r(self.DATA, '2026-09'), 'note\t300\t1\npen\t200\t2\nTOTAL\t500\n')

    def test_csv_all(self):
        self.assertEqual(r(self.DATA, f=1), 'note,300,1\npen,300,3\nTOTAL,600\n')


if __name__ == '__main__':
    unittest.main()
