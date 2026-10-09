"""Installer regression tests; requires an official Dify 1.11.1 Git checkout."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
BASELINE = json.loads((HERE / 'baseline.json').read_text())
PANEL = 'web/app/components/workflow/nodes/tool/panel.tsx'
DEST = 'web/app/components/workflow/nodes/tool/components/dmn-decision-table'


class InstallerTest(unittest.TestCase):
    def setUp(self):
        source = os.environ.get('DIFY_111_SOURCE')
        if not source:
            self.skipTest('Set DIFY_111_SOURCE to an official Dify checkout')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'dify'
        self.root.mkdir()
        self.git('init', '--quiet')
        objects = subprocess.run(['git', '-C', source, 'rev-parse', '--git-path', 'objects'], text=True, capture_output=True, check=True).stdout.strip()
        objects_path = (Path(source) / objects).resolve()
        (self.root / '.git/objects/info/alternates').write_text(str(objects_path) + '\n')
        self.git('update-ref', 'HEAD', BASELINE['dify_commit'])
        self.git('checkout', BASELINE['dify_commit'], '--', *BASELINE['files'])

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], text=True, capture_output=True, check=True).stdout.strip()

    def apply(self, *args):
        return subprocess.run([sys.executable, str(HERE / 'apply.py'), str(self.root), *args], text=True, capture_output=True)

    def test_check_does_not_modify_and_apply_is_idempotent(self):
        original = (self.root / PANEL).read_bytes()
        self.assertEqual(self.apply('--check').returncode, 0)
        self.assertEqual((self.root / PANEL).read_bytes(), original)
        self.assertFalse((self.root / DEST).exists())
        self.assertEqual(self.apply().returncode, 0)
        after = {p: (self.root / p).read_bytes() for p in BASELINE['files']}
        self.assertEqual(self.apply().returncode, 0)
        self.assertEqual(after, {p: (self.root / p).read_bytes() for p in BASELINE['files']})
        self.assertEqual(self.apply('--check').returncode, 0)

    def test_modified_baseline_is_rejected_without_copying(self):
        panel = self.root / PANEL
        panel.write_text(panel.read_text() + '\n// customized\n')
        original = panel.read_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(panel.read_bytes(), original)
        self.assertFalse((self.root / DEST).exists())

    def test_differing_component_is_not_overwritten(self):
        dest = self.root / DEST
        dest.mkdir(parents=True)
        target = dest / 'model.ts'
        target.write_text('// custom component\n')
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(target.read_text(), '// custom component\n')

    def test_partial_patch_is_rejected(self):
        self.assertEqual(self.apply().returncode, 0)
        self.git('checkout', BASELINE['dify_commit'], '--', PANEL)
        self.assertNotEqual(self.apply().returncode, 0)

    def test_symlink_component_destination_is_rejected(self):
        external = Path(self.temp.name) / 'external'
        external.mkdir()
        (self.root / DEST).parent.mkdir(parents=True)
        (self.root / DEST).symlink_to(external, target_is_directory=True)
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(list(external.iterdir()), [])

    def test_wrong_commit_is_rejected(self):
        tree = self.git('rev-parse', 'HEAD^{tree}')
        commit = subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Installer Test', '-c', 'user.email=test@example.invalid', 'commit-tree', tree, '-p', 'HEAD', '-m', 'Synthetic installer rejection fixture'], text=True, capture_output=True, check=True).stdout.strip()
        self.git('update-ref', 'HEAD', commit)
        result = self.apply()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Wrong Dify commit', result.stderr)
        self.assertFalse((self.root / DEST).exists())


if __name__ == '__main__':
    unittest.main()
