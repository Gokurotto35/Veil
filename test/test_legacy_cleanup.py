import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.integration import pengu_loader
from utils.system import legacy_cleanup


def _completed(returncode):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout='', stderr='')


class RemoveRoseLeftoversTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.local = self.tmp / 'Desktop' / 'Local'
        self.veil_app = self.local / 'VeilApp'
        self.rose = self.local / 'Rose'
        self.bundled = self.tmp / 'install' / '_internal' / 'Pengu Loader'
        (self.bundled / 'plugins').mkdir(parents=True)
        self.veil_app.mkdir(parents=True)

        self.task_query = 1  # schtasks /Query exit code: no Rose task
        self.task_command = r'C:\Program Files\Rose\Rose.exe'
        self.schtasks = []

        def run(args, **kwargs):
            self.schtasks.append(args)
            if '/Query' in args:
                xml = f'<Task><Actions><Exec><Command>"{self.task_command}"</Command></Exec></Actions></Task>'
                return subprocess.CompletedProcess(args=args, returncode=self.task_query, stdout=xml, stderr='')
            return _completed(0)

        for target in (
            patch.object(legacy_cleanup, 'get_user_data_dir', return_value=self.veil_app),
            patch.object(legacy_cleanup, '_rose_is_running', return_value=False),
            patch.object(legacy_cleanup.subprocess, 'run', side_effect=run),
            patch.object(pengu_loader, '_registered_pengu_core', return_value=None),
            patch.object(pengu_loader, '_get_bundled_pengu_dir', return_value=self.bundled),
        ):
            target.start()
            self.addCleanup(target.stop)

    def make_rose_install(self):
        core = self.rose / 'Pengu Loader' / 'core.dll'
        core.parent.mkdir(parents=True)
        core.write_bytes(b'core')
        (self.rose / 'config.ini').write_text('[General]', encoding='utf-8')
        self.task_query = 0
        return core

    def test_rose_dir_is_sibling_of_user_data_dir(self):
        self.make_rose_install()
        with patch.dict(os.environ, {'LOCALAPPDATA': str(self.tmp / 'Elsewhere')}):
            legacy_cleanup.remove_legacy_leftovers()
        self.assertFalse(self.rose.exists())
        self.assertTrue(self.veil_app.is_dir())

    def test_does_nothing_while_rose_runs(self):
        self.make_rose_install()
        with patch.object(legacy_cleanup, '_rose_is_running', return_value=True):
            self.assertEqual(legacy_cleanup.remove_legacy_leftovers(), [])
        self.assertTrue((self.rose / 'config.ini').is_file())
        self.assertEqual(self.schtasks, [])

    def test_removes_hook_task_and_folder(self):
        core = self.make_rose_install()
        with patch.object(pengu_loader, '_registered_pengu_core', return_value=core), \
                patch.object(pengu_loader, '_remove_hook', return_value=True) as remove_hook:
            removed = legacy_cleanup.remove_legacy_leftovers()
        remove_hook.assert_called_once_with(core)
        self.assertIn(['schtasks', '/Delete', '/TN', 'Rose', '/F'], self.schtasks)
        self.assertFalse(self.rose.exists())
        self.assertEqual(len(removed), 3)

    def test_removes_rose_plugins_from_bundled_loader(self):
        for name in ('ROSE-UI', 'VEIL-UI', 'my-plugin'):
            (self.bundled / 'plugins' / name).mkdir()
        legacy_cleanup.remove_legacy_leftovers()
        self.assertEqual(sorted(p.name for p in (self.bundled / 'plugins').iterdir()), ['VEIL-UI', 'my-plugin'])

    def test_locked_folder_is_retried_later(self):
        self.make_rose_install()
        with patch.object(legacy_cleanup.shutil, 'rmtree', side_effect=PermissionError('in use')), \
                self.assertLogs(legacy_cleanup.log.name, 'WARNING'):
            removed = legacy_cleanup.remove_legacy_leftovers()
        self.assertTrue(self.rose.is_dir())
        self.assertFalse(any(str(self.rose) in entry for entry in removed))

    def test_never_touches_the_veil_folder(self):
        # VoidVeil, another app, keeps its data there
        self.make_rose_install()
        voidveil = self.local / 'Veil'
        (voidveil / 'mods').mkdir(parents=True)
        (voidveil / 'config.toml').write_text('league_path = "C:/Riot Games"', encoding='utf-8')
        legacy_cleanup.remove_legacy_leftovers()
        self.assertFalse(self.rose.exists())
        self.assertEqual(sorted(p.name for p in voidveil.iterdir()), ['config.toml', 'mods'])
        self.assertEqual((voidveil / 'config.toml').read_text(encoding='utf-8'), 'league_path = "C:/Riot Games"')

    def test_another_apps_rose_folder_is_kept(self):
        # "Rose" is a generic name: only a folder Rose left is deleted
        self.rose.mkdir()
        (self.rose / 'notes.txt').write_text('not Rose', encoding='utf-8')
        self.assertEqual(legacy_cleanup.remove_legacy_leftovers(), [])
        self.assertEqual((self.rose / 'notes.txt').read_text(encoding='utf-8'), 'not Rose')

    def test_another_apps_rose_task_is_kept(self):
        self.task_query = 0
        self.task_command = r'C:\Tools\Rose\backup.exe'
        legacy_cleanup.remove_legacy_leftovers()
        self.assertFalse(any('/Delete' in args for args in self.schtasks))

    def test_clean_machine_is_a_no_op(self):
        with patch.object(legacy_cleanup.shutil, 'rmtree') as rmtree:
            self.assertEqual(legacy_cleanup.remove_legacy_leftovers(), [])
        rmtree.assert_not_called()
        self.assertFalse(any('/Delete' in args for args in self.schtasks))


class InstallerLegacyTests(unittest.TestCase):
    def setUp(self):
        self.script = (Path(__file__).resolve().parents[1] / 'installer.iss').read_text(encoding='utf-8-sig')

    def test_never_installs_into_the_rose_folder(self):
        # Inno would reuse the folder of the install it replaces, C:\Program Files\Rose
        self.assertRegex(self.script, r'(?im)^UsePreviousAppDir=no\s*$')

    def test_install_keeps_another_apps_rose_data(self):
        # legacy_cleanup.py removes it at startup, once it's recognised as Rose's
        self.assertNotRegex(self.script, r'(?im)^Type:\s*filesandordirs;\s*Name:\s*"\{localappdata\}\\Rose"')

    def test_old_apps_entry_is_matched_against_the_rose_folder(self):
        # Veil installs to its own folder, so the entry Rose left never points at {app}
        match = re.search(r'(?s)procedure _CleanupLegacyUninstallEntry\(\);(.*?)\nend;', self.script)
        self.assertIsNotNone(match)
        self.assertIn('_LegacyAppDir()', match.group(1))
        self.assertNotIn("ExpandConstant('{app}')", match.group(1))

    def test_removes_the_old_rose_program_folder(self):
        match = re.search(r'(?s)procedure _DeleteLegacyAppDir\(\);(.*?)\nend;', self.script)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn('_LegacyAppDir()', body)
        self.assertRegex(self.script, r"(?s)function _LegacyAppDir\(\): string;.*?ExpandConstant\('\{autopf\}\\Rose'\)")
        # Only a folder that holds Rose.exe, and never Veil's own
        self.assertIn("FileExists(AddBackslash(Dir) + '{#LegacyAppExeName}')", body)
        self.assertIn("ExpandConstant('{app}')", body)
        self.assertIn('DelTree(Dir, True, True, True)', body)
        self.assertEqual(self.script.count('_DeleteLegacyAppDir();'), 1 + 1)


if __name__ == '__main__':
    unittest.main()
