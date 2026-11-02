"""Run the sh block of ains-retro/debt-hotspots.md on a fixture repo and check its range."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

DOC = Path(os.environ.get('DEBT_HOTSPOTS_DOC', Path(__file__).resolve().parents[2] / 'skills/ains-retro/debt-hotspots.md')).resolve()


def sh_block():
    blocks = re.findall(r'```sh\n(.*?)```', DOC.read_text(), re.S)
    if len(blocks) != 1:
        raise AssertionError(f'expected one sh block in {DOC}, found {len(blocks)}')
    return blocks[0]


class DebtHotspotsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ains-debt-hotspots-')
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 't')
        self.git('config', 'user.email', 't@example.com')
        self.git('config', 'commit.gpgsign', 'false')

    def git(self, *args):
        subprocess.run(['git', *args], cwd=self.repo, check=True, capture_output=True)

    def commit(self, message, *files):
        for name in files:
            path = self.repo / name
            with path.open('a') as f:
                f.write(message + '\n')
            self.git('add', name)
        self.git('commit', '-q', '-m', message)

    def run_block(self):
        result = subprocess.run(['sh', '-c', sh_block()], cwd=self.repo, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_every_count_stays_within_the_latest_100_commits(self):
        # 1 fix commit that falls outside the range, then 101 commits inside it.
        self.commit('fix: old bug', 'old.txt')
        for i in range(100):
            self.commit(f'chore: step {i}', 'a.txt')
        self.commit('fix: new bug', 'new.txt', 'a.txt')

        out = self.run_block()

        self.assertNotIn('old.txt', out, 'a fix older than the latest 100 commits leaked into a count')
        self.assertRegex(out, r'(?m)^\s*1 new\.txt$')
        self.assertRegex(out, r'(?m)^\s*1 a\.txt\tnew\.txt$')

    def test_short_history_uses_all_commits(self):
        self.commit('fix: only bug', 'b.txt', 'c.txt')
        self.commit('feat: add d', 'd.txt')

        out = self.run_block()

        self.assertRegex(out, r'(?m)^\s*1 d\.txt$')
        self.assertRegex(out, r'(?m)^\s*1 b\.txt\tc\.txt$')


if __name__ == '__main__':
    unittest.main()
