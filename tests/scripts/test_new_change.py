"""Exercise creation from an unrelated cwd, including a copied installed layout."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(os.environ.get('NEW_CHANGE_SCRIPT', Path(__file__).resolve().parents[2] / 'skills/ains-spec/scripts/new-change.sh')).resolve()

class NewChangeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ains-new-change-')
        self.addCleanup(self.tmp.cleanup)
        self.cwd = Path(self.tmp.name) / 'consumer cwd'
        self.cwd.mkdir()

    def run_script(self, *args, script=SCRIPT, want=0):
        result = subprocess.run(['bash', str(script), *map(str, args)], cwd=self.cwd, text=True, capture_output=True)
        self.assertEqual(result.returncode, want, result.stdout + result.stderr)
        return result

    def test_valid_slug_root_spaces_template_and_no_overwrite(self):
        root = self.cwd / 'changes with spaces'
        result = self.run_script('valid-123', '--root', root)
        d = Path(result.stdout.strip())
        self.assertEqual(d.parent, root)
        self.assertRegex(d.name, r'^\d{4}-\d{2}-\d{2}-valid-123$')
        expected = (SCRIPT.parent.parent / 'assets/spec.md').read_text().replace('{{CHANGE_ID}}', d.name)
        self.assertEqual((d / 'spec.md').read_text(), expected)
        (d / 'spec.md').write_text('preserve human content\n')
        self.run_script('valid-123', '--root', root)
        self.assertEqual((d / 'spec.md').read_text(), 'preserve human content\n')

    def test_default_root_is_consumer_relative(self):
        d = Path(self.run_script('default').stdout.strip())
        self.assertEqual(d.parent, Path('docs/changes'))
        self.assertTrue((self.cwd / d / 'spec.md').is_file())

    def test_existing_spec_symlink_does_not_create_missing_target(self):
        root = self.cwd / 'changes'
        d = Path(self.run_script('linked', '--root', root).stdout.strip())
        spec = d / 'spec.md'
        spec.unlink()
        target = Path(self.tmp.name) / 'outside-change-spec.md'
        spec.symlink_to(target)

        self.run_script('linked', '--root', root)

        self.assertTrue(spec.is_symlink())
        self.assertEqual(spec.readlink(), target)
        self.assertFalse(target.exists(), 'an existing spec path must not create its symlink target')

    def test_invalid_and_missing_slug_have_no_side_effects(self):
        for args in [['Bad'], ['../escape'], ['-bad'], ['has space'], [], ['a' * 245], ['first', 'second'], ['', 'second']]:
            with self.subTest(args=args):
                self.run_script(*args, '--root', self.cwd / 'changes', want=2)
        self.assertEqual(list(self.cwd.iterdir()), [])

    def test_longest_slug_fits_file_name_limit(self):
        d = Path(self.run_script('a' * 244, '--root', self.cwd / 'changes').stdout.strip())
        self.assertEqual(len(d.name.encode()), 255)
        self.assertTrue((d / 'spec.md').is_file())

    def test_missing_root_value_and_unknown_option(self):
        for args in [('valid', '--root'), ('valid', '--root', '--other'), ('valid', '--unknown')]:
            with self.subTest(args=args): self.run_script(*args, want=2)
        self.assertEqual(list(self.cwd.iterdir()), [])

    def test_copied_installed_asset_is_used_from_other_cwd(self):
        installed = Path(self.tmp.name) / 'installed skills/ains-spec'
        (installed / 'scripts').mkdir(parents=True)
        (installed / 'assets').mkdir()
        shutil.copy2(SCRIPT, installed / 'scripts/new-change.sh')
        (installed / 'assets/spec.md').write_text('installed marker {{CHANGE_ID}}\n')
        d = Path(self.run_script('installed', script=installed / 'scripts/new-change.sh').stdout.strip())
        self.assertEqual((self.cwd / d / 'spec.md').read_text(), f'installed marker {d.name}\n')

if __name__ == '__main__': unittest.main(verbosity=2)
